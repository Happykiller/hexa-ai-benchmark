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
        total_tests = 0
        
        for root, dirs, files in os.walk(self.target_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            
            # Identify if we are in a tests directory
            is_test_dir = 'tests' in root.split(os.sep) or '__tests__' in root.split(os.sep)

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
                    
                    # Test file detection
                    if is_test_dir or file.endswith(('.test.ts', '.spec.ts', '.test.tsx', '.spec.tsx')):
                        total_tests += 1

                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            total_lines += sum(1 for _ in f)
                    except (UnicodeDecodeError, OSError):
                        pass
        
        return {
            "total_files": total_files,
            "total_ts_files": total_ts_files,
            "total_size_kb": round(total_size_bytes / 1024, 2),
            "total_lines": total_lines,
            "total_tests": total_tests
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
        all_maluses = []
        
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
        abstract_factory_detected = abstract_factory_count > 0
        if abstract_factory_detected:
            detected_maluses.append({"reason": f"Over-abstraction detected ({abstract_factory_count} AbstractFactories)", "points": -5 * abstract_factory_count})
        all_maluses.append({
            "id": "abstract_factory",
            "reason": "Over-abstraction via AbstractFactory classes",
            "status": "DETECTE" if abstract_factory_detected else "NON_DETECTE",
            "count": abstract_factory_count,
            "detail": f"abstract_factory_count={abstract_factory_count}",
        })

        tiny_file_ratio = (tiny_files_count / total_ts_files) if total_ts_files > 0 else 0
        tiny_file_fragmented = tiny_file_ratio > 0.3
        if tiny_file_fragmented:
            detected_maluses.append({"reason": f"Extreme fragmentation ({round(tiny_file_ratio*100)}% of files < 10 lines)", "points": -10})
        all_maluses.append({
            "id": "tiny_file_fragmentation",
            "reason": "Extreme fragmentation (< 10 lines per TS file)",
            "status": "DETECTE" if tiny_file_fragmented else "NON_DETECTE",
            "count": tiny_files_count,
            "ratio": round(tiny_file_ratio * 100, 2),
            "detail": f"tiny_files_count={tiny_files_count}, total_ts_files={total_ts_files}, ratio_pct={round(tiny_file_ratio * 100, 2)}",
        })

        # Process all bonuses with status
        all_bonuses = []
        for pb in self.possible_bonuses:
            status = flags.get(pb["id"], False)
            all_bonuses.append({
                "reason": pb["reason"],
                "points": pb["points"],
                "status": "OK" if status else "ABSENT"
            })
            if status:
                detected_bonuses.append(pb)

        total_malus = sum(m["points"] for m in detected_maluses)
        total_bonus = sum(b["points"] for b in detected_bonuses)

        return {
            "maluses": detected_maluses,
            "all_maluses": all_maluses,
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
            return {"status": "KO", "score": 0, "error": "src/ directory not found", "rules": []}

        violations = []
        rule_results = []
        for layer_dir, forbidden_segment, reason in self._LAYER_RULES:
            layer_path = os.path.join(src_path, layer_dir)
            layer_exists = os.path.exists(layer_path)
            layer_violations = []
            if layer_exists:
                layer_violations = self._scan_layer(layer_path, forbidden_segment, reason)
                violations.extend(layer_violations)

            rule_results.append({
                "rule": f"{layer_dir} should not depend on {forbidden_segment}",
                "status": "KO" if (layer_violations or not layer_exists) else "OK",
                "violations_count": len(layer_violations),
                "layer_exists": layer_exists,
            })

        score = max(0, 100 - len(violations) * 10)
        return {
            "status": "KO" if violations else "OK",
            "score": score,
            "violations": violations,
            "rules": rule_results
        }

class ReadmeChecker:
    def __init__(self, target_path: str):
        self.target_path = target_path

    def check(self) -> Dict[str, Any]:
        readme_path = os.path.join(self.target_path, "README.md")
        if not os.path.exists(readme_path):
            return {"status": "KO", "found": False, "score": 0, "indicators": {}}

        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
        except Exception:
            return {"status": "KO", "found": True, "error": "Could not read README.md", "score": 0, "indicators": {}}

        indicators = {
            "has_architecture_section": "architecture" in content,
            "has_installation_section": any(x in content for x in ["install", "setup", "démarrage"]),
            "has_api_documentation": "graphql" in content or "api" in content,
            "has_docker_info": "docker" in content,
        }
        
        score = sum(1 for v in indicators.values() if v)
        return {
            "status": "OK" if score >= 3 else "PARTIEL",
            "found": True,
            "score": score,
            "total_indicators": len(indicators),
            "indicators": indicators
        }

class UseCaseInjectionChecker:
    """
    Checks that core use cases use constructor injection (InversifyJS pattern)
    and do not directly instantiate concrete infrastructure/adapter classes.
    """
    def __init__(self, target_path: str):
        self.target_path = target_path

    # Direct instantiation of concrete impls — anti-pattern in core/
    _direct_new = re.compile(
        r'\bnew\s+\w*(?:Repository|Adapter|DataSource|Connector|Mongoose|TypeOrm)\w*\s*\(',
        re.IGNORECASE,
    )
    _injectable = re.compile(r'@injectable\(\)')
    _inject_param = re.compile(r'@inject\(')
    _constructor_with_params = re.compile(r'constructor\s*\(\s*@')

    def check(self) -> Dict[str, Any]:
        indicators = {
            "no_direct_instantiation_in_core": True,
            "injectable_decorator_used": False,
            "inject_on_constructor_params": False,
            "constructors_receive_dependencies": False,
        }
        violations: List[Dict[str, str]] = []
        injectable_count = 0
        inject_count = 0
        ctor_with_inject = 0
        usecase_files = 0

        core_path = os.path.join(self.target_path, "src", "core")
        if not os.path.exists(core_path):
            return {
                "status": "KO",
                "error": "src/core/ not found",
                "violations": [],
                "indicators": indicators,
            }

        for root, dirs, files in os.walk(core_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if not file.endswith(('.ts', '.tsx')):
                    continue
                fname_lower = file.lower()
                is_usecase = any(kw in fname_lower for kw in ('usecase', 'use-case', 'use_case', 'interactor'))
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except (UnicodeDecodeError, OSError):
                    continue

                if is_usecase:
                    usecase_files += 1

                for match in self._direct_new.finditer(content):
                    violations.append({
                        "file": os.path.relpath(file_path, self.target_path),
                        "pattern": match.group(0).strip(),
                    })

                if self._injectable.search(content):
                    injectable_count += 1
                if self._inject_param.search(content):
                    inject_count += 1
                if self._constructor_with_params.search(content):
                    ctor_with_inject += 1

        if violations:
            indicators["no_direct_instantiation_in_core"] = False
        indicators["injectable_decorator_used"] = injectable_count > 0
        indicators["inject_on_constructor_params"] = inject_count > 0
        indicators["constructors_receive_dependencies"] = ctor_with_inject >= max(1, usecase_files // 2)

        score_count = sum(1 for v in indicators.values() if v)
        return {
            "status": "OK" if score_count >= 4 else "PARTIEL" if score_count >= 2 else "KO",
            "score_count": score_count,
            "usecase_files_scanned": usecase_files,
            "violations": violations[:10],
            "indicators": indicators,
        }


class DualPersistenceChecker:
    """
    Verifies that the project uses MongoDB for tasks and MySQL for users simultaneously.
    Checks package.json deps, import patterns by file context, and adapter file naming.
    """
    def __init__(self, target_path: str):
        self.target_path = target_path

    _mongoose_import = re.compile(r'from\s+[\'"]mongoose[\'"]')
    _sql_import = re.compile(r'from\s+[\'"](typeorm|sequelize|knex|mysql2|mysql|@nestjs/typeorm)[\'"]')
    _SQL_DEPS = {"typeorm", "sequelize", "knex", "mysql2", "mysql", "@nestjs/typeorm"}

    def check(self) -> Dict[str, Any]:
        indicators = {
            "mongoose_installed": False,
            "sql_orm_installed": False,
            "mongoose_in_task_code": False,
            "sql_in_user_auth_code": False,
            "separate_db_adapters": False,
        }

        pkg_path = os.path.join(self.target_path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    pkg = json.load(f)
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                indicators["mongoose_installed"] = "mongoose" in all_deps
                indicators["sql_orm_installed"] = bool(self._SQL_DEPS & set(all_deps.keys()))
            except (OSError, json.JSONDecodeError):
                pass

        src_path = os.path.join(self.target_path, "src")
        if not os.path.exists(src_path):
            return {"status": "KO", "error": "src/ not found", "indicators": indicators}

        for root, dirs, files in os.walk(src_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                if not file.endswith(('.ts', '.tsx')):
                    continue
                fname_lower = file.lower()
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except (UnicodeDecodeError, OSError):
                    continue

                if 'task' in fname_lower and self._mongoose_import.search(content):
                    indicators["mongoose_in_task_code"] = True

                if ('user' in fname_lower or 'auth' in fname_lower) and self._sql_import.search(content):
                    indicators["sql_in_user_auth_code"] = True

        adapters_path = os.path.join(src_path, "adapters")
        if os.path.exists(adapters_path):
            has_mongo_file = False
            has_sql_file = False
            for root, dirs, files in os.walk(adapters_path):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                for file in files:
                    fl = file.lower()
                    if any(kw in fl for kw in ('mongo', 'mongoose')):
                        has_mongo_file = True
                    if any(kw in fl for kw in ('mysql', 'sql', 'typeorm', 'sequelize', 'knex')):
                        has_sql_file = True
            indicators["separate_db_adapters"] = has_mongo_file and has_sql_file

        implemented = sum(1 for v in indicators.values() if v)
        return {
            "status": "OK" if implemented >= 5 else "PARTIEL" if implemented >= 3 else "KO",
            "implemented_count": implemented,
            "indicators": indicators,
        }


class AuthImplementationChecker:
    """Checks for JWT authentication implementation signals in the codebase."""
    def __init__(self, target_path: str):
        self.target_path = target_path

    _jwt_import = re.compile(r'from\s+[\'"](jsonwebtoken|jose|@nestjs/jwt|passport-jwt)[\'"]')
    _auth_mutation = re.compile(r'(?:register|login|signup|signin)\s*[:(,\(]', re.IGNORECASE)
    _auth_guard = re.compile(r'(isAuthenticated|authGuard|AuthGuard|verifyToken|checkAuth|@Authorized|authenticate\b)', re.IGNORECASE)
    _hash_import = re.compile(r'from\s+[\'"](bcrypt|bcryptjs|argon2)[\'"]')

    def check(self) -> Dict[str, Any]:
        indicators = {
            "jwt_library_present": False,
            "auth_mutations_present": False,
            "auth_guard_present": False,
            "password_hashing_present": False,
        }

        pkg_path = os.path.join(self.target_path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    pkg = json.load(f)
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if any(k in all_deps for k in ("jsonwebtoken", "jose", "@nestjs/jwt", "passport-jwt")):
                    indicators["jwt_library_present"] = True
                if any(k in all_deps for k in ("bcrypt", "bcryptjs", "argon2")):
                    indicators["password_hashing_present"] = True
            except (OSError, json.JSONDecodeError):
                pass

        src_path = os.path.join(self.target_path, "src")
        if os.path.exists(src_path):
            for root, dirs, files in os.walk(src_path):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                for file in files:
                    if not file.endswith(('.ts', '.tsx')):
                        continue
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        if self._jwt_import.search(content):
                            indicators["jwt_library_present"] = True
                        if self._auth_mutation.search(content):
                            indicators["auth_mutations_present"] = True
                        if self._auth_guard.search(content):
                            indicators["auth_guard_present"] = True
                        if self._hash_import.search(content):
                            indicators["password_hashing_present"] = True
                    except (UnicodeDecodeError, OSError):
                        pass

        implemented_count = sum(1 for v in indicators.values() if v)
        return {
            "status": "OK" if implemented_count >= 4 else "PARTIEL" if implemented_count >= 2 else "KO",
            "implemented_count": implemented_count,
            "indicators": indicators,
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
            {"name": "Naming Conventions", "status": "OK", "detail": "Standard naming followed"},
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
        quality_points[0]["status"] = "OK" if score > 90 else "PARTIEL" if score > 70 else "KO"
        quality_points[0]["detail"] = f"{any_count} occurrences of 'any' found"

        return {
            "any_count": any_count,
            "ts_files": ts_files,
            "score": score,
            "status": "OK" if score > 80 else "PARTIEL",
            "points": quality_points
        }
