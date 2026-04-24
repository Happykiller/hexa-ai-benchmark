import subprocess
import time
import requests
import json
from typing import Dict, Any, List

class MakefileRunner:
    def __init__(self, target_path: str):
        self.target_path = target_path

    def run_target(self, target: str) -> Dict[str, Any]:
        try:
            result = subprocess.run(["make", target], cwd=self.target_path, capture_output=True, text=True, timeout=300)
            return {
                "status": "SUCCESS" if result.returncode == 0 else "FAILED",
                "output": result.stdout,
                "error": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "FAILED", "error": f"Target 'make {target}' timed out after 5 minutes"}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

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
                            "status": "SUCCESS",
                            "waited_seconds": i * retry_interval,
                            "output": result.stdout,
                            "error": result.stderr,
                        }
                except requests.exceptions.RequestException:
                    pass
                time.sleep(retry_interval)
            
            return {
                "status": "FAILED",
                "error": "GraphQL endpoint did not become healthy within 60s",
                "output": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"status": "FAILED", "error": "Target 'make start' timed out after 2 minutes"}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

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
                    return {"status": "FAILED", "error": "No containers reported by docker compose ps", "containers": []}

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
                    return {"status": "SUCCESS", "containers": containers}
                return {"status": "FAILED", "error": "Unable to parse docker compose ps output", "raw_output": raw, "containers": []}
            except subprocess.TimeoutExpired:
                last_error = f"Timed out: {' '.join(cmd)}"
            except FileNotFoundError:
                last_error = f"Command not found: {' '.join(cmd)}"

        return {"status": "FAILED", "error": last_error or "Docker compose inspection failed", "containers": []}

class E2EFunctionalTester:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def run_scenario(self) -> List[Dict[str, Any]]:
        results = []
        
        # 1. Create Task A
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

        # 2. Create Task B dependent on A
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

        # 3. Attempt to close B (Should fail because A is not closed)
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

        # 4. Close A
        close_a_query = f"""
        mutation {{ updateTaskStatus(id: "{task_a_id}", status: "COMPLETED") {{ id status }} }}
        """
        resp_close_a = self._post(close_a_query)
        status_a = self._extract_path(resp_close_a, ["data", "updateTaskStatus", "status"])
        success_a = status_a == "COMPLETED"
        results.append({"step": "Close A (Success)", "success": success_a, "error": self._extract_graphql_error_message(resp_close_a)})

        # 5. Close B (Should now succeed)
        resp_close_b_final = self._post(close_b_query)
        status_b = self._extract_path(resp_close_b_final, ["data", "updateTaskStatus", "status"])
        success_b = status_b == "COMPLETED"
        results.append({"step": "Close B (Now Success)", "success": success_b, "error": self._extract_graphql_error_message(resp_close_b_final)})

        return results

    def _post(self, query: str) -> Dict[str, Any]:
        try:
            r = requests.post(self.endpoint, json={"query": query}, timeout=10)
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

    def _extract_graphql_error_message(self, response: Dict[str, Any]) -> str | None:
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
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def run_benchmark(self, query: str, variables: Dict[str, Any], iterations: int = 50) -> Dict[str, Any]:
        latencies = []
        errors = 0
        for _ in range(iterations):
            start = time.time()
            try:
                r = requests.post(self.endpoint, json={'query': query, 'variables': variables}, timeout=5)
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
