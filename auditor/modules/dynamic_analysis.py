import base64
import hashlib
import hmac
import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime
from typing import Any

import requests
import yaml

# Diagnostics are emitted at DEBUG so the default audit console stays quiet; enable them
# with HEXA_AUDIT_LOG_LEVEL=DEBUG (wired in main.cli) when a run needs investigating.
logger = logging.getLogger(__name__)

_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


def _iter_bind_sources(compose: dict[str, Any]) -> list[str]:
    """Host bind-mount source paths declared in a compose dict (short & long syntax)."""
    sources: list[str] = []
    services = compose.get("services")
    if not isinstance(services, dict):
        return sources
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        for vol in svc.get("volumes") or []:
            if isinstance(vol, str):
                # short syntax "source:target[:mode]"; source is a bind mount only when
                # it's a path (starts with . or /), not a named volume.
                source = vol.split(":", 1)[0].strip()
                if source.startswith((".", "/")):
                    sources.append(source)
            elif isinstance(vol, dict) and vol.get("type") == "bind" and vol.get("source"):
                sources.append(str(vol["source"]))
    return sources


def precreate_bind_mount_dirs(target_path: str) -> list[str]:
    """Pre-create host bind-mount directories (owned by the audit user) BEFORE any compose
    command runs, so the Docker daemon (root) doesn't auto-create them as root:root and
    break the build context (``error from sender: ... permission denied`` → false
    ``make build failed``). Only paths resolving inside the deliverable are created; named
    volumes and out-of-tree paths are skipped. Returns the dirs created."""
    target = os.path.abspath(target_path)
    compose: Any = None
    for name in _COMPOSE_FILES:
        path = os.path.join(target, name)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as handle:
                    compose = yaml.safe_load(handle)
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
                logger.debug("compose parse failed (%s): %s", name, exc)
            break
    if not isinstance(compose, dict):
        return []

    created: list[str] = []
    for source in _iter_bind_sources(compose):
        host_path = source if os.path.isabs(source) else os.path.join(target, source)
        host_path = os.path.abspath(host_path)
        # Safety: never create dirs outside the deliverable tree.
        if os.path.commonpath([target, host_path]) != target:
            continue
        if os.path.exists(host_path):
            continue
        try:
            os.makedirs(host_path, exist_ok=True)
            created.append(host_path)
        except OSError as exc:
            logger.debug("could not pre-create bind mount %s: %s", host_path, exc)
    return created


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _b64url(data: bytes) -> str:
    """Base64url without padding (JWT segment encoding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _mint_jwt(
    payload: dict[str, Any], alg: str = "HS256", secret: str = "auditor-foreign-secret"
) -> str:
    """Forge a JWT for negative security tests (stdlib only, no PyJWT).

    alg="none" produces an unsigned token (empty signature) to probe the classic
    alg-confusion bypass. alg="HS256" signs with a secret the audited server does
    NOT know, so a correct implementation must reject it on signature mismatch.
    """
    header = {"alg": alg, "typ": "JWT"}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    if alg == "none":
        return signing_input + "."
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(signature)


class MakefileRunner:
    def __init__(self, target_path: str):
        self.target_path = target_path

    def run_target(self, target: str) -> dict[str, Any]:
        started_at = _now_iso()
        monotonic_started_at = time.monotonic()
        try:
            result = subprocess.run(
                ["make", target], cwd=self.target_path, capture_output=True, text=True, timeout=300
            )
            return {
                "status": "OK" if result.returncode == 0 else "KO",
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.returncode,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "KO",
                "error": f"Target 'make {target}' timed out after 5 minutes",
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }
        except Exception as e:
            return {
                "status": "KO",
                "error": str(e),
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }


class DockerOrchestrator:
    def __init__(self, target_path: str, endpoint: str = "http://localhost:4000/graphql"):
        self.target_path = target_path
        self.endpoint = endpoint

    def start(self, fresh: bool = False) -> dict[str, Any]:
        started_at = _now_iso()
        monotonic_started_at = time.monotonic()
        fresh_result: dict[str, Any] | None = None
        try:
            if fresh:
                fresh_result = self.stop()

            result = subprocess.run(
                ["make", "start"],
                cwd=self.target_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return {
                    "status": "KO",
                    "error": f"make start exited with code {result.returncode}",
                    "output": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                    "fresh_docker": fresh,
                    "fresh_result": fresh_result,
                    "started_at": started_at,
                    "finished_at": _now_iso(),
                    "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
                }

            # Polling for health.
            #
            # IMPORTANT : la sonde de santé NE DOIT PAS être une requête d'introspection
            # (`{ __schema ... }`). Les serveurs Apollo désactivent l'introspection en
            # production (NODE_ENV=production), ce qui est une bonne pratique de sécurité.
            # Une sonde d'introspection y reçoit alors un HTTP 400 INTROSPECTION_DISABLED
            # alors que l'API est parfaitement up — produisant un faux « API ne démarre
            # pas » qui cappe tout le dynamique à 0. On sonde donc le méta-champ `__typename`,
            # toujours disponible, introspection activée ou non.
            #
            # Budget large (120s) : `make start` rend la main avant que les conteneurs soient
            # healthy, et l'init cold-volume de MySQL 8.4 peut consommer plusieurs dizaines de
            # secondes sous charge I/O.
            max_retries = 60
            retry_interval = 2
            health_query = {"query": "{ __typename }"}
            for i in range(max_retries):
                try:
                    r = requests.post(self.endpoint, json=health_query, timeout=2)
                    if r.status_code == 200:
                        return {
                            "status": "OK",
                            "waited_seconds": i * retry_interval,
                            "output": result.stdout,
                            "stderr": result.stderr,
                            "fresh_docker": fresh,
                            "fresh_result": fresh_result,
                            "started_at": started_at,
                            "finished_at": _now_iso(),
                            "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
                        }
                except requests.exceptions.RequestException:
                    pass
                time.sleep(retry_interval)

            # Diagnostic ciblé : les logs du service `api` (cause réelle d'un endpoint
            # injoignable) sont sinon noyés par le bruit d'init de MySQL dans un tail global.
            def _compose_logs(args: list[str]) -> str:
                try:
                    res = subprocess.run(
                        ["docker", "compose", "logs"] + args,
                        cwd=self.target_path,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    return res.stdout or res.stderr or ""
                except Exception as exc:
                    logger.debug("docker compose logs capture failed: %s", exc)
                    return ""

            api_logs = _compose_logs(["api", "--tail=200"])
            container_logs = _compose_logs(["--tail=80"])
            try:
                ps_result = subprocess.run(
                    ["docker", "compose", "ps"],
                    cwd=self.target_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                containers_status = ps_result.stdout or ps_result.stderr or ""
            except Exception as exc:
                logger.debug("docker compose ps capture failed: %s", exc)
                containers_status = ""

            return {
                "status": "KO",
                "error": f"GraphQL endpoint did not become healthy within {max_retries * retry_interval}s",
                "output": result.stdout,
                "stderr": result.stderr,
                "api_logs": api_logs,
                "containers_status": containers_status,
                "container_logs": container_logs,
                "fresh_docker": fresh,
                "fresh_result": fresh_result,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "KO",
                "error": "Target 'make start' timed out after 2 minutes",
                "fresh_docker": fresh,
                "fresh_result": fresh_result,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }
        except Exception as e:
            return {
                "status": "KO",
                "error": str(e),
                "fresh_docker": fresh,
                "fresh_result": fresh_result,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }

    def stop(self) -> dict[str, Any]:
        started_at = _now_iso()
        monotonic_started_at = time.monotonic()
        try:
            result = subprocess.run(
                ["docker", "compose", "down", "-v"],
                cwd=self.target_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "status": "OK" if result.returncode == 0 else "KO",
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.returncode,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }
        except FileNotFoundError:
            try:
                result = subprocess.run(
                    ["docker-compose", "down", "-v"],
                    cwd=self.target_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                return {
                    "status": "OK" if result.returncode == 0 else "KO",
                    "output": result.stdout,
                    "error": result.stderr,
                    "exit_code": result.returncode,
                    "started_at": started_at,
                    "finished_at": _now_iso(),
                    "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
                }
            except subprocess.TimeoutExpired:
                return {
                    "status": "KO",
                    "error": "docker-compose down -v timed out after 60s",
                    "started_at": started_at,
                    "finished_at": _now_iso(),
                    "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "KO",
                "error": "docker compose down -v timed out after 60s",
                "started_at": started_at,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - monotonic_started_at, 3),
            }

    def inspect_exposed_containers(self) -> dict[str, Any]:
        """Collect running containers and exposed ports for the current compose project."""
        commands = [
            ["docker", "compose", "ps", "--format", "json"],
            ["docker-compose", "ps", "--format", "json"],
        ]

        last_error = ""
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd, cwd=self.target_path, capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    last_error = (
                        result.stderr or result.stdout or f"Command failed: {' '.join(cmd)}"
                    )
                    continue

                raw = (result.stdout or "").strip()
                if not raw:
                    return {
                        "status": "KO",
                        "error": "No containers reported by docker compose ps",
                        "containers": [],
                    }

                containers: list[dict[str, Any]] = []
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        rows = parsed
                    elif isinstance(parsed, dict):
                        rows = [parsed]
                    else:
                        rows = []
                except json.JSONDecodeError:
                    rows = []
                    for line in raw.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            if isinstance(item, dict):
                                rows.append(item)
                        except json.JSONDecodeError:
                            pass

                for row in rows:
                    containers.append(
                        {
                            "name": row.get("Name") or row.get("Service") or "unknown",
                            "state": row.get("State") or "unknown",
                            "status": row.get("Status") or "unknown",
                            "publishers": row.get("Publishers") or [],
                            "ports": row.get("Ports") or "",
                        }
                    )

                if containers:
                    return {"status": "OK", "containers": containers}
                return {
                    "status": "KO",
                    "error": "Unable to parse docker compose ps output",
                    "raw_output": raw,
                    "containers": [],
                }
            except subprocess.TimeoutExpired:
                last_error = f"Timed out: {' '.join(cmd)}"
            except FileNotFoundError:
                last_error = f"Command not found: {' '.join(cmd)}"

        return {
            "status": "KO",
            "error": last_error or "Docker compose inspection failed",
            "containers": [],
        }


class E2EFunctionalTester:
    def __init__(self, endpoint: str, token: str | None = None):
        self.endpoint = endpoint
        self.token = token

    def run_scenario(self) -> list[dict[str, Any]]:
        results = []

        # The spec mandates authentication for tasks / createTask / updateTaskStatus.
        # When the orchestrator could not inject a token (the auth probe failed to
        # locate it in this server's response shape), self-register a throwaway user so a
        # working Task domain is still exercised — instead of collapsing the whole
        # functional scenario, and the score (40% cap), on an auth-token detail.
        if not self.token:
            self.token = self._self_authenticate()

        # 1. List Tasks (Initial)
        list_query = "{ tasks { id title status } }"
        resp_list = self._post(list_query)
        tasks_initial = self._extract_path(resp_list, ["data", "tasks"])
        results.append(
            {
                "step": "List Tasks (Initial)",
                "success": tasks_initial is not None,
                "error": self._extract_graphql_error_message(resp_list),
            }
        )

        # 2. Create Task A
        task_a_query = """
        mutation { createTask(input: {title: "Task A", description: "Parent"}) { id status } }
        """
        resp_a = self._post(task_a_query)
        task_a_id = self._extract_path(resp_a, ["data", "createTask", "id"])
        results.append(
            {
                "step": "Create Task A",
                "success": task_a_id is not None,
                "error": self._extract_graphql_error_message(resp_a),
            }
        )

        if not task_a_id:
            return results

        # 3. Get Task A
        get_a_query = "{ tasks { id title status } }"  # Simplified Get via list filtering or similar if no single get
        resp_get = self._post(get_a_query)
        found_a = any(
            t.get("id") == task_a_id
            for t in (self._extract_path(resp_get, ["data", "tasks"]) or [])
        )
        results.append(
            {
                "step": "Get Task A",
                "success": found_a,
                "error": "Task A not found in list" if not found_a else None,
            }
        )

        # 4. Create Task B dependent on A
        task_b_query = f"""
        mutation {{ createTask(input: {{title: "Task B", description: "Child", dependsOn: ["{task_a_id}"]}}) {{ id status }} }}
        """
        resp_b = self._post(task_b_query)
        task_b_id = self._extract_path(resp_b, ["data", "createTask", "id"])
        results.append(
            {
                "step": "Create Task B (Dependent on A)",
                "success": task_b_id is not None,
                "error": self._extract_graphql_error_message(resp_b),
            }
        )

        if not task_b_id:
            return results

        # 5. Attempt to close B (Should fail because A is not closed)
        close_b_query = f"""
        mutation {{ updateTaskStatus(id: "{task_b_id}", status: "COMPLETED") {{ id status }} }}
        """
        resp_close_b = self._post(close_b_query)
        error_message = self._extract_graphql_error_message(resp_close_b)
        dependency_blocked = error_message is not None and any(
            token in error_message.lower()
            for token in ("depend", "blocked", "prerequisite", "precondition")
        )
        results.append(
            {"step": "Close B (Should Fail)", "success": dependency_blocked, "error": error_message}
        )

        # 6. Close A
        close_a_query = f"""
        mutation {{ updateTaskStatus(id: "{task_a_id}", status: "COMPLETED") {{ id status }} }}
        """
        resp_close_a = self._post(close_a_query)
        status_a = self._extract_path(resp_close_a, ["data", "updateTaskStatus", "status"])
        success_a = status_a == "COMPLETED"
        results.append(
            {
                "step": "Close A (Success)",
                "success": success_a,
                "error": self._extract_graphql_error_message(resp_close_a),
            }
        )

        # 7. Close B (Should now succeed)
        resp_close_b_final = self._post(close_b_query)
        status_b = self._extract_path(resp_close_b_final, ["data", "updateTaskStatus", "status"])
        success_b = status_b == "COMPLETED"
        results.append(
            {
                "step": "Close B (Now Success)",
                "success": success_b,
                "error": self._extract_graphql_error_message(resp_close_b_final),
            }
        )

        # 8. Independent task (no dependencies) must close successfully.
        # Guards against "always-block" gaming where updateTaskStatus throws a
        # dependency error unconditionally just to pass "Close B (Should Fail)".
        indep_resp = self._post(
            'mutation { createTask(input: {title: "Independent", description: "no deps"}) { id status } }'
        )
        indep_id = self._extract_path(indep_resp, ["data", "createTask", "id"])
        indep_ok = False
        indep_err = self._extract_graphql_error_message(indep_resp)
        if indep_id:
            close_indep = self._post(
                f'mutation {{ updateTaskStatus(id: "{indep_id}", status: "COMPLETED") {{ id status }} }}'
            )
            indep_status = self._extract_path(close_indep, ["data", "updateTaskStatus", "status"])
            indep_ok = indep_status == "COMPLETED"
            indep_err = None if indep_ok else self._extract_graphql_error_message(close_indep)
        results.append(
            {"step": "Close Independent Task (No Deps)", "success": indep_ok, "error": indep_err}
        )

        return results

    # --------------------------------------------------------------------- #
    # Adversarial scenario — harder, deterministic edge cases that separate a
    # robust dependency engine from a naive one. Kept OUT of run_scenario so an
    # edge-case failure never triggers the 40% functional cap.
    # --------------------------------------------------------------------- #
    def run_adversarial_scenario(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if not self.token:
            self.token = self._self_authenticate()

        # A. Multiple dependencies: a task with two prerequisites must stay blocked
        #    until BOTH are COMPLETED (catches impls that check only the first dep).
        a = self._create_task("Adv A")
        b = self._create_task("Adv B")
        multi_ok, multi_err = False, "setup incomplet (création des tâches)"
        if a and b:
            d = self._create_task("Adv D depends on A and B", depends_on=[a, b])
            if d:
                self._set_status(a, "COMPLETED")  # close A only — B still open
                closed_early, _ = self._try_close(d)  # must be refused (B open)
                self._set_status(b, "COMPLETED")  # now both closed
                closed = self._set_status(d, "COMPLETED") == "COMPLETED"
                multi_ok = (closed_early is False) and closed
                multi_err = (
                    None
                    if multi_ok
                    else "Tâche fermée alors qu'une de ses dépendances était encore ouverte"
                )
        results.append(
            {
                "step": "Adversarial: Dépendances multiples (toutes requises)",
                "success": multi_ok,
                "error": multi_err,
            }
        )

        # B. Deep chain A→B→C: closing C while B is open must fail; full cascade succeeds.
        ca = self._create_task("Chain A")
        chain_ok, chain_err = False, "setup incomplet (chaîne)"
        if ca:
            cb = self._create_task("Chain B", depends_on=[ca])
            cc = self._create_task("Chain C", depends_on=[cb]) if cb else None
            if cb and cc:
                early, _ = self._try_close(cc)  # B open → must be blocked
                self._set_status(ca, "COMPLETED")
                self._set_status(cb, "COMPLETED")
                final = self._set_status(cc, "COMPLETED") == "COMPLETED"
                chain_ok = (early is False) and final
                chain_err = None if chain_ok else "Chaîne de dépendances à 2 niveaux mal gérée"
        results.append(
            {
                "step": "Adversarial: Chaîne de dépendances profonde",
                "success": chain_ok,
                "error": chain_err,
            }
        )

        # C. A dependsOn referencing a non-existent task must be rejected at creation.
        ghost = self._post(
            'mutation { createTask(input: {title: "Adv ghost", dependsOn: ["00000000-ghost-id-0000"]}) { id } }'
        )
        ghost_id = self._extract_path(ghost, ["data", "createTask", "id"])
        ghost_ok = ghost_id is None
        results.append(
            {
                "step": "Adversarial: Dépendance inexistante rejetée",
                "success": ghost_ok,
                "error": None if ghost_ok else "Tâche créée avec une dépendance inexistante",
            }
        )

        # D. An invalid status value must be rejected, not silently accepted.
        ts = self._create_task("Adv status")
        status_ok, status_err = False, "setup incomplet (statut)"
        if ts:
            resp = self._post(
                f'mutation {{ updateTaskStatus(id: "{ts}", status: "BANANA") {{ id status }} }}'
            )
            new_status = self._extract_path(resp, ["data", "updateTaskStatus", "status"])
            status_ok = new_status is None  # rejected rather than accepting an arbitrary status
            status_err = None if status_ok else f"Statut arbitraire accepté ({new_status})"
        results.append(
            {
                "step": "Adversarial: Statut invalide rejeté",
                "success": status_ok,
                "error": status_err,
            }
        )

        return results

    def _create_task(self, title: str, depends_on: list[str] | None = None) -> str | None:
        deps = ""
        if depends_on:
            ids = ", ".join(f'"{i}"' for i in depends_on)
            deps = f", dependsOn: [{ids}]"
        resp = self._post(f'mutation {{ createTask(input: {{title: "{title}"{deps}}}) {{ id }} }}')
        return self._extract_path(resp, ["data", "createTask", "id"])

    def _set_status(self, task_id: str, status: str) -> str | None:
        resp = self._post(
            f'mutation {{ updateTaskStatus(id: "{task_id}", status: "{status}") {{ status }} }}'
        )
        return self._extract_path(resp, ["data", "updateTaskStatus", "status"])

    def _try_close(self, task_id: str) -> "tuple[bool, str | None]":
        """Attempt to close a task. Returns (closed, error_message): closed=True only
        if the server actually set it to COMPLETED."""
        resp = self._post(
            f'mutation {{ updateTaskStatus(id: "{task_id}", status: "COMPLETED") {{ status }} }}'
        )
        status = self._extract_path(resp, ["data", "updateTaskStatus", "status"])
        return status == "COMPLETED", self._extract_graphql_error_message(resp)

    def _post(self, query: str) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = requests.post(self.endpoint, json={"query": query}, headers=headers, timeout=10)
            payload = r.json()
            if isinstance(payload, dict):
                return payload
            return {"_invalid_json_payload": True, "raw_payload_type": type(payload).__name__}
        except Exception as exc:
            logger.debug("E2E GraphQL request failed: %s", exc)
            return {"_request_failed": True}

    def _extract_path(self, payload: dict[str, Any], path: list[str]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _self_authenticate(self) -> str | None:
        """Best-effort register-then-login to obtain a bearer token when none was
        injected. Tolerant to the exact response shape (see _deep_find_token), so a
        working Task domain stays drivable even when the auth probe could not extract
        the token itself."""
        email = f"audit_e2e_{uuid.uuid4().hex[:8]}@test.com"
        password = "AuditPass1!"
        token = self._deep_find_token(
            self._post(
                f'mutation {{ register(email: "{email}", password: "{password}") {{ token }} }}'
            )
        )
        if not token:
            token = self._deep_find_token(
                self._post(
                    f'mutation {{ login(email: "{email}", password: "{password}") {{ token }} }}'
                )
            )
        return token

    @staticmethod
    def _looks_like_jwt(value: Any) -> bool:
        return (
            isinstance(value, str)
            and value.count(".") == 2
            and all(value.split("."))
            and len(value) > 20
        )

    def _deep_find_token(self, payload: Any) -> str | None:
        """Locate a bearer token in a register/login response. Tries the spec path
        first, then any token-ish key, then any JWT-shaped string — so a server that
        names the field accessToken / jwt stays drivable by the functional scenario."""
        for op in ("register", "login", "signup", "signIn", "authenticate"):
            tok = self._extract_path(payload, ["data", op, "token"])
            if isinstance(tok, str) and tok:
                return tok
        stack: list[Any] = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, val in node.items():
                    if (
                        isinstance(val, str)
                        and val
                        and ("token" in key.lower() or "jwt" in key.lower())
                    ):
                        return val
                    if self._looks_like_jwt(val):
                        return val
                    if isinstance(val, (dict, list)):
                        stack.append(val)
            elif isinstance(node, list):
                stack.extend(node)
        return None

    def _extract_graphql_error_message(self, response: dict[str, Any]) -> str | None:
        if response.get("_request_failed"):
            return None

        errors = response.get("errors")
        if not isinstance(errors, list) or not errors:
            return None

        first_error = errors[0]
        if not isinstance(first_error, dict):
            return None

        message = first_error.get("message")
        return message if isinstance(message, str) else None


class PerformanceBenchmarker:
    def __init__(self, endpoint: str, token: str | None = None):
        self.endpoint = endpoint
        self.token = token

    def run_benchmark(
        self, query: str, variables: dict[str, Any], iterations: int = 50
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        latencies = []
        errors = 0
        for _ in range(iterations):
            start = time.time()
            try:
                r = requests.post(
                    self.endpoint,
                    json={"query": query, "variables": variables},
                    headers=headers,
                    timeout=5,
                )
                if r.status_code == 200 and "errors" not in r.json():
                    latencies.append(time.time() - start)
                else:
                    errors += 1
            except Exception as exc:
                logger.debug("perf iteration request failed: %s", exc)
                errors += 1

        if not latencies:
            return {"avg_latency_ms": 0, "p95_ms": 0, "error_rate": 100}

        latencies.sort()
        return {
            "avg_latency_ms": (sum(latencies) / len(latencies)) * 1000,
            "p95_ms": latencies[int(len(latencies) * 0.95)] * 1000,
            "error_rate": (errors / iterations) * 100,
        }


class AuthTester:
    """Tests JWT authentication: registration, login, access control, and token validation."""

    _TEST_PASSWORD = "AuditPass1!"

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.token: str | None = None
        self._u1_task_id: str | None = None
        self._TEST_EMAIL = f"audit_agent_{uuid.uuid4().hex[:8]}@test.com"

    def obtain_token(self) -> str | None:
        """Attempt register then login to obtain a bearer token for downstream tests."""
        register_q = f'mutation {{ register(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token }} }}'
        token = self._extract_path(self._post(register_q), ["data", "register", "token"])
        if not token:
            login_q = f'mutation {{ login(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token }} }}'
            token = self._extract_path(self._post(login_q), ["data", "login", "token"])
        self.token = token
        return token

    def run_scenario(self) -> list[dict[str, Any]]:
        results = []

        # 1. Unauthenticated createTask must be rejected
        probe_q = 'mutation { createTask(input: {title: "Unauth"}) { id } }'
        resp_unauth = self._post(probe_q)
        error_msg = self._extract_graphql_error_message(resp_unauth)
        is_blocked = (
            error_msg is not None
            and any(
                kw in error_msg.lower()
                for kw in ("unauthenticated", "unauthorized", "auth", "token", "forbidden")
            )
        ) or self._has_auth_error_code(resp_unauth)
        results.append(
            {
                "step": "Auth: Accès non-authentifié bloqué",
                "success": is_blocked,
                "error": error_msg,
            }
        )

        # 2. Register
        register_q = f'mutation {{ register(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token user {{ id email }} }} }}'
        resp_reg = self._post(register_q)
        reg_token = self._extract_path(resp_reg, ["data", "register", "token"])
        results.append(
            {
                "step": "Auth: Inscription (register)",
                "success": reg_token is not None,
                "error": self._extract_graphql_error_message(resp_reg),
            }
        )
        if reg_token:
            self.token = reg_token

        # 3. Login
        login_q = f'mutation {{ login(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token user {{ id email }} }} }}'
        resp_login = self._post(login_q)
        login_token = self._extract_path(resp_login, ["data", "login", "token"])
        results.append(
            {
                "step": "Auth: Connexion (login)",
                "success": login_token is not None,
                "error": self._extract_graphql_error_message(resp_login),
            }
        )
        if login_token:
            self.token = login_token

        # 4. Authenticated operation must succeed
        if self.token:
            resp_auth = self._post(
                'mutation { createTask(input: {title: "Auth Task"}) { id status } }',
                token=self.token,
            )
            task_id = self._extract_path(resp_auth, ["data", "createTask", "id"])
            self._u1_task_id = task_id
            results.append(
                {
                    "step": "Auth: Opération authentifiée autorisée",
                    "success": task_id is not None,
                    "error": self._extract_graphql_error_message(resp_auth),
                }
            )

        # 5. Tampered token must be rejected
        if self.token:
            tampered = self.token[:-6] + "XXXXXX"
            resp_tampered = self._post(probe_q, token=tampered)
            tampered_err = self._extract_graphql_error_message(resp_tampered)
            results.append(
                {
                    "step": "Auth: Token falsifié rejeté",
                    "success": tampered_err is not None or self._has_auth_error_code(resp_tampered),
                    "error": tampered_err,
                }
            )

        # --- Real security depth (black-box, no knowledge of the server secret) ---
        fake_uid = "00000000-0000-0000-0000-000000000000"
        forged_payload = {
            "sub": fake_uid,
            "userId": fake_uid,
            "id": fake_uid,
            "email": self._TEST_EMAIL,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        auth_probe = "{ tasks { id } }"  # requires authentication per the spec

        # 6. alg:none token must be rejected (alg-confusion bypass)
        none_token = _mint_jwt(forged_payload, alg="none")
        resp_none = self._post(auth_probe, token=none_token)
        none_rejected = self._extract_path(resp_none, ["data", "tasks"]) is None
        results.append(
            {
                "step": "Auth: Token alg=none rejeté",
                "success": none_rejected,
                "error": None if none_rejected else "Token alg=none accepté (faille critique)",
            }
        )

        # 7. Token signed with a foreign secret must be rejected (signature check)
        foreign_token = _mint_jwt(
            forged_payload, alg="HS256", secret="auditor-not-the-real-secret-" + uuid.uuid4().hex
        )
        resp_foreign = self._post(auth_probe, token=foreign_token)
        foreign_rejected = self._extract_path(resp_foreign, ["data", "tasks"]) is None
        results.append(
            {
                "step": "Auth: Signature étrangère rejetée",
                "success": foreign_rejected,
                "error": None
                if foreign_rejected
                else "Token signé avec un secret étranger accepté",
            }
        )

        # 8. Unauthenticated error must carry extensions.code == "UNAUTHENTICATED"
        resp_code = self._post(probe_q)
        code_ok = self._has_exact_code(resp_code, "UNAUTHENTICATED")
        results.append(
            {
                "step": "Auth: Code UNAUTHENTICATED exact",
                "success": code_ok,
                "error": None
                if code_ok
                else "extensions.code != UNAUTHENTICATED sur accès non authentifié",
            }
        )

        # 9. Weak password must be rejected at registration
        weak_email = f"audit_weak_{uuid.uuid4().hex[:8]}@test.com"
        resp_weak = self._post(
            f'mutation {{ register(email: "{weak_email}", password: "123") {{ token }} }}'
        )
        weak_token = self._extract_path(resp_weak, ["data", "register", "token"])
        results.append(
            {
                "step": "Auth: Mot de passe faible refusé",
                "success": weak_token is None,
                "error": "Mot de passe faible accepté"
                if weak_token is not None
                else self._extract_graphql_error_message(resp_weak),
            }
        )

        # 10. Per-user isolation: a second user must not see the first user's task
        intruder_email = f"audit_intruder_{uuid.uuid4().hex[:8]}@test.com"
        reg2 = self._post(
            f'mutation {{ register(email: "{intruder_email}", password: "{self._TEST_PASSWORD}") {{ token }} }}'
        )
        u2_token = self._extract_path(reg2, ["data", "register", "token"])
        if not u2_token:
            login2 = self._post(
                f'mutation {{ login(email: "{intruder_email}", password: "{self._TEST_PASSWORD}") {{ token }} }}'
            )
            u2_token = self._extract_path(login2, ["data", "login", "token"])
        u2_tasks = (
            self._extract_path(self._post(auth_probe, token=u2_token), ["data", "tasks"])
            if u2_token
            else None
        )
        u2_ids = (
            {t.get("id") for t in u2_tasks if isinstance(t, dict)}
            if isinstance(u2_tasks, list)
            else set()
        )
        isolation_ok = (
            bool(self._u1_task_id) and u2_token is not None and self._u1_task_id not in u2_ids
        )
        results.append(
            {
                "step": "Auth: Isolation inter-utilisateurs",
                "success": isolation_ok,
                "error": None
                if isolation_ok
                else "Tâche d'un autre utilisateur visible ou setup incomplet",
            }
        )

        return results

    def _post(self, query: str, token: str | None = None) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = requests.post(self.endpoint, json={"query": query}, headers=headers, timeout=10)
            payload = r.json()
            return payload if isinstance(payload, dict) else {"_invalid_json_payload": True}
        except Exception as exc:
            logger.debug("Auth GraphQL request failed: %s", exc)
            return {"_request_failed": True}

    def _has_auth_error_code(self, response: dict[str, Any]) -> bool:
        for err in response.get("errors") or []:
            if isinstance(err, dict):
                code = (err.get("extensions") or {}).get("code", "")
                if isinstance(code, str) and code.upper() in (
                    "UNAUTHENTICATED",
                    "UNAUTHORIZED",
                    "FORBIDDEN",
                ):
                    return True
        return False

    def _has_exact_code(self, response: dict[str, Any], expected: str) -> bool:
        for err in response.get("errors") or []:
            if isinstance(err, dict):
                code = (err.get("extensions") or {}).get("code", "")
                if isinstance(code, str) and code.upper() == expected.upper():
                    return True
        return False

    def _extract_path(self, payload: dict[str, Any], path: list[str]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _extract_graphql_error_message(self, response: dict[str, Any]) -> str | None:
        if response.get("_request_failed"):
            return None
        errors = response.get("errors")
        if not isinstance(errors, list) or not errors:
            return None
        first = errors[0]
        if not isinstance(first, dict):
            return None
        msg = first.get("message")
        return msg if isinstance(msg, str) else None
