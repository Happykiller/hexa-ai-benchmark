import subprocess
import time
import requests
import json
from typing import Dict, Any, List, Optional

class MakefileRunner:
    def __init__(self, target_path: str):
        self.target_path = target_path

    def run_target(self, target: str) -> Dict[str, Any]:
        try:
            result = subprocess.run(["make", target], cwd=self.target_path, capture_output=True, text=True, timeout=300)
            return {
                "status": "OK" if result.returncode == 0 else "KO",
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "KO", "error": f"Target 'make {target}' timed out after 5 minutes"}
        except Exception as e:
            return {"status": "KO", "error": str(e)}

class DockerOrchestrator:
    def __init__(self, target_path: str, endpoint: str = "http://localhost:4000/graphql"):
        self.target_path = target_path
        self.endpoint = endpoint

    def start(self) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                ["make", "start"],
                cwd=self.target_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            # Polling for health
            max_retries = 30
            retry_interval = 2
            for i in range(max_retries):
                try:
                    # Simple introspection query to check if GraphQL is alive
                    r = requests.post(self.endpoint, json={"query": "{ __schema { types { name } } }"}, timeout=2)
                    if r.status_code == 200:
                        return {
                            "status": "OK",
                            "waited_seconds": i * retry_interval,
                            "output": result.stdout,
                            "error": result.stderr,
                        }
                except requests.exceptions.RequestException:
                    pass
                time.sleep(retry_interval)
            
            return {
                "status": "KO",
                "error": "GraphQL endpoint did not become healthy within 60s",
                "output": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"status": "KO", "error": "Target 'make start' timed out after 2 minutes"}
        except Exception as e:
            return {"status": "KO", "error": str(e)}

    def stop(self):
        try:
            subprocess.run(["docker", "compose", "down", "-v"], cwd=self.target_path, capture_output=True, timeout=60)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            subprocess.run(["docker-compose", "down", "-v"], cwd=self.target_path, capture_output=True, timeout=60)

    def inspect_exposed_containers(self) -> Dict[str, Any]:
        """Collect running containers and exposed ports for the current compose project."""
        commands = [
            ["docker", "compose", "ps", "--format", "json"],
            ["docker-compose", "ps", "--format", "json"],
        ]

        last_error = ""
        for cmd in commands:
            try:
                result = subprocess.run(cmd, cwd=self.target_path, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    last_error = result.stderr or result.stdout or f"Command failed: {' '.join(cmd)}"
                    continue

                raw = (result.stdout or "").strip()
                if not raw:
                    return {"status": "KO", "error": "No containers reported by docker compose ps", "containers": []}

                containers: List[Dict[str, Any]] = []
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
                return {"status": "KO", "error": "Unable to parse docker compose ps output", "raw_output": raw, "containers": []}
            except subprocess.TimeoutExpired:
                last_error = f"Timed out: {' '.join(cmd)}"
            except FileNotFoundError:
                last_error = f"Command not found: {' '.join(cmd)}"

        return {"status": "KO", "error": last_error or "Docker compose inspection failed", "containers": []}

class E2EFunctionalTester:
    def __init__(self, endpoint: str, token: Optional[str] = None):
        self.endpoint = endpoint
        self.token = token

    def run_scenario(self) -> List[Dict[str, Any]]:
        results = []
        
        # 0. Check Login / Auth (Optional check if endpoint requires it, here we check connectivity/existence)
        # We'll simulate a 'Get Current User' or similar if available, otherwise we just list.
        
        # 1. List Tasks (Initial)
        list_query = "{ tasks { id title status } }"
        resp_list = self._post(list_query)
        tasks_initial = self._extract_path(resp_list, ["data", "tasks"])
        results.append({
            "step": "List Tasks (Initial)",
            "success": tasks_initial is not None,
            "error": self._extract_graphql_error_message(resp_list),
        })

        # 2. Create Task A
        task_a_query = """
        mutation { createTask(input: {title: "Task A", description: "Parent"}) { id status } }
        """
        resp_a = self._post(task_a_query)
        task_a_id = self._extract_path(resp_a, ["data", "createTask", "id"])
        results.append({
            "step": "Create Task A",
            "success": task_a_id is not None,
            "error": self._extract_graphql_error_message(resp_a),
        })

        if not task_a_id: return results

        # 3. Get Task A
        get_a_query = f"{{ tasks {{ id title status }} }}" # Simplified Get via list filtering or similar if no single get
        resp_get = self._post(get_a_query)
        found_a = any(t.get("id") == task_a_id for t in (self._extract_path(resp_get, ["data", "tasks"]) or []))
        results.append({
            "step": "Get Task A",
            "success": found_a,
            "error": "Task A not found in list" if not found_a else None,
        })

        # 4. Create Task B dependent on A
        task_b_query = f"""
        mutation {{ createTask(input: {{title: "Task B", description: "Child", dependsOn: ["{task_a_id}"]}}) {{ id status }} }}
        """
        resp_b = self._post(task_b_query)
        task_b_id = self._extract_path(resp_b, ["data", "createTask", "id"])
        results.append({
            "step": "Create Task B (Dependent on A)",
            "success": task_b_id is not None,
            "error": self._extract_graphql_error_message(resp_b),
        })

        if not task_b_id: return results

        # 5. Attempt to close B (Should fail because A is not closed)
        close_b_query = f"""
        mutation {{ updateTaskStatus(id: "{task_b_id}", status: "COMPLETED") {{ id status }} }}
        """
        resp_close_b = self._post(close_b_query)
        error_message = self._extract_graphql_error_message(resp_close_b)
        dependency_blocked = (
            error_message is not None
            and any(token in error_message.lower() for token in ("depend", "blocked", "prerequisite", "precondition"))
        )
        results.append({"step": "Close B (Should Fail)", "success": dependency_blocked, "error": error_message})

        # 6. Close A
        close_a_query = f"""
        mutation {{ updateTaskStatus(id: "{task_a_id}", status: "COMPLETED") {{ id status }} }}
        """
        resp_close_a = self._post(close_a_query)
        status_a = self._extract_path(resp_close_a, ["data", "updateTaskStatus", "status"])
        success_a = status_a == "COMPLETED"
        results.append({"step": "Close A (Success)", "success": success_a, "error": self._extract_graphql_error_message(resp_close_a)})

        # 7. Close B (Should now succeed)
        resp_close_b_final = self._post(close_b_query)
        status_b = self._extract_path(resp_close_b_final, ["data", "updateTaskStatus", "status"])
        success_b = status_b == "COMPLETED"
        results.append({"step": "Close B (Now Success)", "success": success_b, "error": self._extract_graphql_error_message(resp_close_b_final)})

        # 8. Delete Tasks (Cleanup / Test Delete if implemented)
        # Note: Delete is not strictly in the prompt but good for E2E. 
        # If not implemented, it will just show as failed/not reached.
        return results

    def _post(self, query: str) -> Dict[str, Any]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = requests.post(self.endpoint, json={"query": query}, headers=headers, timeout=10)
            payload = r.json()
            if isinstance(payload, dict):
                return payload
            return {"_invalid_json_payload": True, "raw_payload_type": type(payload).__name__}
        except Exception:
            return {"_request_failed": True}

    def _extract_path(self, payload: Dict[str, Any], path: List[str]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _extract_graphql_error_message(self, response: Dict[str, Any]) -> Optional[str]:
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
    def __init__(self, endpoint: str, token: Optional[str] = None):
        self.endpoint = endpoint
        self.token = token

    def run_benchmark(self, query: str, variables: Dict[str, Any], iterations: int = 50) -> Dict[str, Any]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        latencies = []
        errors = 0
        for _ in range(iterations):
            start = time.time()
            try:
                r = requests.post(self.endpoint, json={'query': query, 'variables': variables}, headers=headers, timeout=5)
                if r.status_code == 200 and "errors" not in r.json():
                    latencies.append(time.time() - start)
                else:
                    errors += 1
            except Exception:
                errors += 1
        
        if not latencies: return {"avg_latency_ms": 0, "p95_ms": 0, "error_rate": 100}
        
        latencies.sort()
        return {
            "avg_latency_ms": (sum(latencies) / len(latencies)) * 1000,
            "p95_ms": latencies[int(len(latencies) * 0.95)] * 1000,
            "error_rate": (errors / iterations) * 100
        }


class AuthTester:
    """Tests JWT authentication: registration, login, access control, and token validation."""

    _TEST_EMAIL = "audit_agent@test.com"
    _TEST_PASSWORD = "AuditPass1!"

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.token: Optional[str] = None

    def obtain_token(self) -> Optional[str]:
        """Attempt register then login to obtain a bearer token for downstream tests."""
        register_q = f'mutation {{ register(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token }} }}'
        token = self._extract_path(self._post(register_q), ["data", "register", "token"])
        if not token:
            login_q = f'mutation {{ login(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token }} }}'
            token = self._extract_path(self._post(login_q), ["data", "login", "token"])
        self.token = token
        return token

    def run_scenario(self) -> List[Dict[str, Any]]:
        results = []

        # 1. Unauthenticated createTask must be rejected
        probe_q = 'mutation { createTask(input: {title: "Unauth"}) { id } }'
        resp_unauth = self._post(probe_q)
        error_msg = self._extract_graphql_error_message(resp_unauth)
        is_blocked = (
            error_msg is not None
            and any(kw in error_msg.lower() for kw in ("unauthenticated", "unauthorized", "auth", "token", "forbidden"))
        ) or self._has_auth_error_code(resp_unauth)
        results.append({"step": "Auth: Accès non-authentifié bloqué", "success": is_blocked, "error": error_msg})

        # 2. Register
        register_q = f'mutation {{ register(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token user {{ id email }} }} }}'
        resp_reg = self._post(register_q)
        reg_token = self._extract_path(resp_reg, ["data", "register", "token"])
        results.append({"step": "Auth: Inscription (register)", "success": reg_token is not None, "error": self._extract_graphql_error_message(resp_reg)})
        if reg_token:
            self.token = reg_token

        # 3. Login
        login_q = f'mutation {{ login(email: "{self._TEST_EMAIL}", password: "{self._TEST_PASSWORD}") {{ token user {{ id email }} }} }}'
        resp_login = self._post(login_q)
        login_token = self._extract_path(resp_login, ["data", "login", "token"])
        results.append({"step": "Auth: Connexion (login)", "success": login_token is not None, "error": self._extract_graphql_error_message(resp_login)})
        if login_token:
            self.token = login_token

        # 4. Authenticated operation must succeed
        if self.token:
            resp_auth = self._post('mutation { createTask(input: {title: "Auth Task"}) { id status } }', token=self.token)
            task_id = self._extract_path(resp_auth, ["data", "createTask", "id"])
            results.append({"step": "Auth: Opération authentifiée autorisée", "success": task_id is not None, "error": self._extract_graphql_error_message(resp_auth)})

        # 5. Tampered token must be rejected
        if self.token:
            tampered = self.token[:-6] + "XXXXXX"
            resp_tampered = self._post(probe_q, token=tampered)
            tampered_err = self._extract_graphql_error_message(resp_tampered)
            results.append({
                "step": "Auth: Token falsifié rejeté",
                "success": tampered_err is not None or self._has_auth_error_code(resp_tampered),
                "error": tampered_err,
            })

        return results

    def _post(self, query: str, token: Optional[str] = None) -> Dict[str, Any]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = requests.post(self.endpoint, json={"query": query}, headers=headers, timeout=10)
            payload = r.json()
            return payload if isinstance(payload, dict) else {"_invalid_json_payload": True}
        except Exception:
            return {"_request_failed": True}

    def _has_auth_error_code(self, response: Dict[str, Any]) -> bool:
        for err in response.get("errors") or []:
            if isinstance(err, dict):
                code = (err.get("extensions") or {}).get("code", "")
                if isinstance(code, str) and code.upper() in ("UNAUTHENTICATED", "UNAUTHORIZED", "FORBIDDEN"):
                    return True
        return False

    def _extract_path(self, payload: Dict[str, Any], path: List[str]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _extract_graphql_error_message(self, response: Dict[str, Any]) -> Optional[str]:
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
