"""Supply-chain, secrets and DevEx checkers (Phase D).

Three independent static controls that broaden the audit horizontally:

- ``DevExChecker``     — positive signal: tsconfig strict actually enabled, ESLint
                         config, CI pipeline, sane .gitignore. Plugged into the
                         declarative registry (challenges.py) as phase 2 / step 7.
- ``SecretsScanner``   — malus: secrets / private keys / committed .env files.
- ``NpmAuditChecker``  — malus: high/critical npm advisories (graceful SKIP offline).

All three reuse the shared helpers from ``static_analysis`` (no duplication).
"""

import json
import os
import re
import subprocess
from typing import Any, Dict, List

from .static_analysis import EXCLUDED_DIRS, read_text_file, strip_ts_comments


# --------------------------------------------------------------------------- #
# DevEx & tooling (positive)
# --------------------------------------------------------------------------- #
class DevExChecker:
    """Developer-experience signals the prompt expects but the auditor never verified."""

    _ESLINT_FILES = (
        ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
        ".eslintrc.yml", ".eslintrc.yaml",
        "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
    )

    def __init__(self, target_path: str):
        self.target_path = target_path

    def check(self) -> Dict[str, Any]:
        indicators = {
            "tsconfig_strict": self._tsconfig_strict(),
            "eslint_config": any(os.path.exists(os.path.join(self.target_path, f)) for f in self._ESLINT_FILES),
            "ci_pipeline": self._has_ci(),
            "gitignore_ok": self._gitignore_ok(),
        }
        count = sum(1 for v in indicators.values() if v)
        return {
            "status": "OK" if count >= 3 else "PARTIEL" if count >= 1 else "KO",
            "implemented_count": count,
            "indicators": indicators,
        }

    def _has_ci(self) -> bool:
        workflows = os.path.join(self.target_path, ".github", "workflows")
        if not os.path.isdir(workflows):
            return False
        return any(f.endswith((".yml", ".yaml")) for f in os.listdir(workflows))

    def _gitignore_ok(self) -> bool:
        path = os.path.join(self.target_path, ".gitignore")
        if not os.path.exists(path):
            return False
        try:
            content = read_text_file(path)
        except (OSError, UnicodeDecodeError):
            return False
        return "node_modules" in content and re.search(r'(^|\n)\s*\.?env\b', content) is not None

    def _tsconfig_strict(self) -> bool:
        """True if compilerOptions.strict is enabled (resolving one level of extends).
        Tolerant to JSONC (comments / trailing commas); regex fallback on parse errors."""
        result = self._read_strict(os.path.join(self.target_path, "tsconfig.json"))
        return bool(result)

    def _read_strict(self, tsconfig_path: str, _depth: int = 0) -> bool:
        if not os.path.exists(tsconfig_path) or _depth > 3:
            return False
        try:
            raw = read_text_file(tsconfig_path)
        except (OSError, UnicodeDecodeError):
            return False

        data = self._parse_jsonc(raw)
        if isinstance(data, dict):
            strict = (data.get("compilerOptions") or {}).get("strict")
            if isinstance(strict, bool):
                return strict
            extends = data.get("extends")
            if isinstance(extends, str):
                parent = extends if extends.endswith(".json") else extends + ".json"
                parent_path = os.path.normpath(os.path.join(os.path.dirname(tsconfig_path), parent))
                return self._read_strict(parent_path, _depth + 1)
            return False
        # Fallback: parsing failed — look for an explicit strict:true in the raw text.
        return re.search(r'"strict"\s*:\s*true', raw) is not None

    @staticmethod
    def _parse_jsonc(raw: str) -> Any:
        no_comments = strip_ts_comments(raw)
        no_trailing = re.sub(r',(\s*[}\]])', r'\1', no_comments)
        try:
            return json.loads(no_trailing)
        except (json.JSONDecodeError, ValueError):
            return None


# --------------------------------------------------------------------------- #
# Secrets scanner (malus)
# --------------------------------------------------------------------------- #
class SecretsScanner:
    """High-precision scan for committed secrets. Conservative by design: it favours
    false negatives over false positives so it never penalises a clean deliverable."""

    _SKIP_DIRS = EXCLUDED_DIRS | {"__tests__", "tests", "fixtures", "__mocks__", "test"}
    _SKIP_FILE_SUFFIXES = (
        ".example", ".sample", ".template", ".dist",
        ".lock", "-lock.json", ".map", ".min.js", ".snap",
    )
    _SCAN_SUFFIXES = (
        ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml",
        ".env", ".sh", ".cfg", ".conf", ".ini", ".txt", ".py",
    )
    _PLACEHOLDER = re.compile(
        r'(change[_-]?me|example|placeholder|your[_-]|xxx+|<[^>]+>|\$\{|process\.env|'
        r'dummy|sample|todo|fixme|secret_?key_?here|s3cr3t)',
        re.IGNORECASE,
    )
    _PATTERNS = [
        ("aws_access_key", re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
        ("private_key_block", re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----')),
        ("github_token", re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b')),
        ("slack_token", re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b')),
    ]
    _ASSIGNMENT = re.compile(
        r'(?i)\b(secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|password|passwd)\b'
        r'\s*[:=]\s*["\']([^"\']{8,})["\']'
    )

    def __init__(self, target_path: str):
        self.target_path = target_path

    def scan(self) -> Dict[str, Any]:
        findings: List[Dict[str, str]] = []

        # A committed real .env (not an example) is itself a finding.
        env_path = os.path.join(self.target_path, ".env")
        if os.path.isfile(env_path):
            findings.append({"file": ".env", "kind": "committed_dotenv"})

        for root, dirs, files in os.walk(self.target_path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            for file in files:
                lower = file.lower()
                if lower == ".env":
                    continue  # already handled, and .env content is reported once
                if any(lower.endswith(suf) for suf in self._SKIP_FILE_SUFFIXES):
                    continue
                if not any(lower.endswith(suf) for suf in self._SCAN_SUFFIXES):
                    continue
                file_path = os.path.join(root, file)
                try:
                    content = read_text_file(file_path)
                except (OSError, UnicodeDecodeError):
                    continue
                rel = os.path.relpath(file_path, self.target_path)
                for kind, pattern in self._PATTERNS:
                    if pattern.search(content):
                        findings.append({"file": rel, "kind": kind})
                for match in self._ASSIGNMENT.finditer(content):
                    value = match.group(2)
                    if not self._PLACEHOLDER.search(value):
                        findings.append({"file": rel, "kind": f"hardcoded_{match.group(1).lower()}"})
                        break  # one per file is enough to flag it

        # de-duplicate (file, kind)
        unique = [dict(t) for t in {tuple(sorted(f.items())) for f in findings}]
        detail = "; ".join(f"{f['file']} ({f['kind']})" for f in unique[:8])
        if len(unique) > 8:
            detail += f" … +{len(unique) - 8}"
        return {
            "status": "DETECTE" if unique else "NON_DETECTE",
            "count": len(unique),
            "findings": unique,
            "detail": detail or "aucun secret détecté",
        }


# --------------------------------------------------------------------------- #
# npm audit (malus, graceful SKIP)
# --------------------------------------------------------------------------- #
class NpmAuditChecker:
    """Counts high/critical advisories via ``npm audit --json``. Network-dependent,
    so it SKIPs (no penalty) when offline / no lockfile / npm unavailable."""

    def __init__(self, target_path: str):
        self.target_path = target_path

    def audit(self) -> Dict[str, Any]:
        lockfiles = ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml")
        if not any(os.path.exists(os.path.join(self.target_path, f)) for f in lockfiles):
            return {"status": "SKIPPED", "detail": "no lockfile present"}
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=self.target_path,
                capture_output=True,
                text=True,
                timeout=90,
            )
        except FileNotFoundError:
            return {"status": "SKIPPED", "detail": "npm not available"}
        except subprocess.TimeoutExpired:
            return {"status": "SKIPPED", "detail": "npm audit timed out"}
        except Exception as exc:  # noqa: BLE001 - defensive: never break the audit
            return {"status": "SKIPPED", "detail": f"npm audit error: {exc}"}

        try:
            data = json.loads(result.stdout or "{}")
        except (json.JSONDecodeError, ValueError):
            return {"status": "SKIPPED", "detail": "npm audit output not parseable (offline?)"}

        meta = (data.get("metadata") or {}).get("vulnerabilities")
        if not isinstance(meta, dict):
            if "error" in data:
                return {"status": "SKIPPED", "detail": "npm audit could not reach registry"}
            return {"status": "SKIPPED", "detail": "npm audit returned no vulnerability metadata"}

        critical = int(meta.get("critical", 0) or 0)
        high = int(meta.get("high", 0) or 0)
        moderate = int(meta.get("moderate", 0) or 0)
        return {
            "status": "DETECTE" if (critical > 0 or high > 0) else "NON_DETECTE",
            "critical": critical,
            "high": high,
            "moderate": moderate,
            "detail": f"critical={critical}, high={high}, moderate={moderate}",
        }
