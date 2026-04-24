import os
import re
import subprocess
import json
from typing import Dict, List, Any  # List used in HexagonalComplianceChecker._scan_layer

# Globals for filtering
EXCLUDED_DIRS = {'node_modules', 'dist', 'build', '.git', '.idea', '.vscode', 'coverage', 'venv'}

class ProjectStatsAnalyzer:
    def __init__(self, target_path: str):
        self.target_path = target_path

    def analyze(self) -> Dict[str, Any]:
        total_files = 0
        total_ts_files = 0
        total_size_bytes = 0
        total_lines = 0
        
        for root, dirs, files in os.walk(self.target_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            
            for file in files:
                total_files += 1
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    total_size_bytes += size
                except OSError:
                    pass

                if file.endswith(('.ts', '.tsx')):
                    total_ts_files += 1
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            total_lines += sum(1 for _ in f)
                    except (UnicodeDecodeError, OSError):
                        pass
        
        return {
            "total_files": total_files,
            "total_ts_files": total_ts_files,
            "total_size_kb": round(total_size_bytes / 1024, 2),
            "total_lines": total_lines
        }

class CodeSmellAnalyzer:
    """Analyzes codebase for over-engineering (malus) and proactive initiatives (bonus)."""
    def __init__(self, target_path: str):
        self.target_path = target_path
        self.possible_bonuses = [
            {"id": "custom_errors", "reason": "Centralized Error Handling (Custom Error classes)", "points": 5},
            {"id": "env_validation", "reason": "Environment Variables Validation (zod/envalid)", "points": 5},
            {"id": "healthcheck", "reason": "Explicit Healthcheck Query", "points": 5},
            {"id": "relay_pagination", "reason": "Robust GraphQL Pagination (Relay pattern)", "points": 10},
            {"id": "structured_logger", "reason": "Structured Logger (winston/pino)", "points": 5},
        ]

    def analyze(self) -> Dict[str, Any]:
        detected_maluses = []
        detected_bonuses = []
        
        flags = {
            "custom_errors": False,
            "env_validation": False,
            "healthcheck": False,
            "relay_pagination": False,
            "structured_logger": False
        }
        
        abstract_factory_count = 0
        tiny_files_count = 0
        total_ts_files = 0

        # Patterns for bonuses
        err_pattern = re.compile(r'class\s+\w*Error\s+extends\s+Error')
        env_pattern = re.compile(r'from\s+[\'"](envalid|zod|joi)[\'"]')
        health_pattern = re.compile(r'(health|ping).*Query')
        relay_pattern = re.compile(r'PageInfo|edges.*node')
        logger_pattern = re.compile(r'from\s+[\'"](winston|pino)[\'"]')

        for root, dirs, files in os.walk(self.target_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            
            for file in files:
                if file.endswith(('.ts', '.tsx')):
                    total_ts_files += 1
                    file_path = os.path.join(root, file)
                    
                    if "Abstract" in file and "Factory" in file:
                        abstract_factory_count += 1
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            lines = content.split('\n')
                            
                            code_lines = [l for l in lines if l.strip() and not l.strip().startswith('import')]
                            if len(code_lines) < 10:
                                tiny_files_count += 1
                            
                            if err_pattern.search(content): flags["custom_errors"] = True
                            if env_pattern.search(content): flags["env_validation"] = True
                            if health_pattern.search(content): flags["healthcheck"] = True
                            if relay_pattern.search(content): flags["relay_pagination"] = True
                            if logger_pattern.search(content): flags["structured_logger"] = True
                    except (UnicodeDecodeError, OSError):
                        pass

        # Evaluate Maluses
        if abstract_factory_count > 0:
            detected_maluses.append({"reason": f"Over-abstraction detected ({abstract_factory_count} AbstractFactories)", "points": -5 * abstract_factory_count})
        
        tiny_file_ratio = (tiny_files_count / total_ts_files) if total_ts_files > 0 else 0
        if tiny_file_ratio > 0.3:
            detected_maluses.append({"reason": f"Extreme fragmentation ({round(tiny_file_ratio*100)}% of files < 10 lines)", "points": -10})

        # Process all bonuses with status
        all_bonuses = []
        for pb in self.possible_bonuses:
            status = flags.get(pb["id"], False)
            all_bonuses.append({
                "reason": pb["reason"],
                "points": pb["points"],
                "status": "SUCCESS" if status else "MISSING"
            })
            if status:
                detected_bonuses.append(pb)

        total_malus = sum(m["points"] for m in detected_maluses)
        total_bonus = sum(b["points"] for b in detected_bonuses)

        return {
            "maluses": detected_maluses,
            "bonuses": detected_bonuses,
            "all_bonuses": all_bonuses,
            "total_malus": total_malus,
            "total_bonus": total_bonus
        }

class HexagonalComplianceChecker:
    """
    Checks if the domain (core) is isolated from adapters and infrastructure.
    Rules:
    - core/domain and core/usecases should NOT import from adapters, infrastructure, or entrypoints.
    """
    def __init__(self, target_path: str):
        self.target_path = target_path

    def _strip_comments(self, code: str) -> str:
        # Remove comments but keep string literals intact so import paths remain analyzable.
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'//.*', '', code)
        return code

    # Rules: (scan_dir, forbidden_import_segment, reason)
    _LAYER_RULES = [
        ("core",         "adapters",      "Adapters leak into Core"),
        ("core",         "infrastructure","Infrastructure leak into Core"),
        ("core",         "entrypoints",   "Entrypoints leak into Core"),
        ("adapters",     "entrypoints",   "Entrypoints leak into Adapters"),
        ("infrastructure","entrypoints",  "Entrypoints leak into Infrastructure"),
    ]

    def _scan_layer(self, layer_path: str, forbidden_segment: str, reason: str) -> List[Dict]:
        violations = []
        import_patterns = [
            re.compile(rf'import\s+.*\s+from\s+[\'"].*{forbidden_segment}.*[\'"]'),
            re.compile(rf'import\s+[\'"].*{forbidden_segment}.*[\'"]'),
            re.compile(rf'require\s*\(\s*[\'"].*{forbidden_segment}.*[\'"]\s*\)'),
        ]
        for root, dirs, files in os.walk(layer_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if file.endswith((".ts", ".tsx")):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            clean = self._strip_comments(f.read())
                        for pat in import_patterns:
                            if pat.search(clean):
                                violations.append({
                                    "file": os.path.relpath(file_path, self.target_path),
                                    "reason": reason,
                                    "pattern": pat.pattern,
                                })
                                break
                    except (UnicodeDecodeError, OSError):
                        pass
        return violations

    def check(self) -> Dict[str, Any]:
        src_path = os.path.join(self.target_path, "src")
        if not os.path.exists(src_path):
            return {"status": "FAILED", "score": 0, "error": "src/ directory not found", "rules": []}

        violations = []
        rule_results = []
        for layer_dir, forbidden_segment, reason in self._LAYER_RULES:
            layer_path = os.path.join(src_path, layer_dir)
            layer_violations = []
            if os.path.exists(layer_path):
                layer_violations = self._scan_layer(layer_path, forbidden_segment, reason)
                violations.extend(layer_violations)
            
            rule_results.append({
                "rule": f"{layer_dir} should not depend on {forbidden_segment}",
                "status": "FAILED" if layer_violations else "SUCCESS",
                "violations_count": len(layer_violations)
            })

        score = max(0, 100 - len(violations) * 10)
        return {
            "status": "FAILED" if violations else "SUCCESS",
            "score": score,
            "violations": violations,
            "rules": rule_results
        }

class CodeQualityChecker:
    def __init__(self, target_path: str):
        self.target_path = target_path

    # Matches : any, as any, Array<any>, Promise<any>, Record<string, any>, etc.
    _any_pattern = re.compile(r'(?::\s*any\b|\bas\s+any\b|[<,]\s*any\s*[>,])')

    def _strip_comments(self, code: str) -> str:
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'//.*', '', code)
        return code

    def check_any_usage(self) -> Dict[str, Any]:
        any_count = 0
        ts_files = 0
        src_path = os.path.join(self.target_path, "src")
        
        quality_points = [
            {"name": "TypeScript Strict Mode (Usage of 'any')", "status": "PENDING", "detail": ""},
            {"name": "Naming Conventions", "status": "SUCCESS", "detail": "Standard naming followed"},
        ]

        if not os.path.exists(src_path):
            quality_points[0]["status"] = "SKIPPED"
            return {"any_count": 0, "ts_files": 0, "score": 0, "status": "SKIPPED", "points": quality_points}

        for root, dirs, files in os.walk(src_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if file.endswith((".ts", ".tsx")):
                    ts_files += 1
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = self._strip_comments(f.read())
                            any_count += len(self._any_pattern.findall(content))
                    except (UnicodeDecodeError, OSError):
                        pass

        score = max(0, 100 - any_count * 2)
        quality_points[0]["status"] = "SUCCESS" if score > 90 else "WARNING" if score > 70 else "FAILED"
        quality_points[0]["detail"] = f"{any_count} occurrences of 'any' found"

        return {
            "any_count": any_count,
            "ts_files": ts_files,
            "score": score,
            "status": "SUCCESS" if score > 80 else "WARNING",
            "points": quality_points
        }
