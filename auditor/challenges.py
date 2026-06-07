"""Challenge profiles & declarative static-checker registry.

This module decouples the auditor orchestrator (``main.py``) from the specifics
of a single challenge (the "Todo List Hexagonale" cahier des charges). All the
Todo-specific literals that used to live inline in ``analyze()`` — GraphQL
endpoint, expected E2E step names, auth step weights, layer names — now live in a
:class:`ChallengeProfile`. Adding a second challenge becomes a new profile
instance instead of an edit to the orchestrator.

The :data:`ChallengeProfile.static_checkers` list is a *declarative registry*:
each :class:`StaticCheckerSpec` knows how to (a) run a static checker against a
deliverable path and (b) emit the resulting scored indicators. ``main.py``
iterates the registry instead of hand-writing one ``_append_indicator`` block per
checker, so a new static control = one new registry entry (see Phase D:
supply-chain / DevEx).

IMPORTANT: the ``emit`` callables receive an ``append`` function injected by the
caller (``functools.partial(_append_indicator, audit_db)``). This keeps this
module free of any dependency on ``main.py`` (no import cycle).
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from modules.static_analysis import (
    AuthImplementationChecker,
    CodeQualityChecker,
    DualPersistenceChecker,
    HexagonalComplianceChecker,
    ReadmeChecker,
    UseCaseInjectionChecker,
)
from modules.dynamic_analysis import AuthTester, E2EFunctionalTester
from modules.supply_chain import DevExChecker


# Local copy of main._first_non_empty to avoid a challenges <-> main import cycle.
def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


# ``append`` has the signature of ``functools.partial(_append_indicator, audit_db)``:
#   append(phase_number, phase_label, step_number, step_label, name, achieved,
#          remarks, *, polarity=..., status=..., details=..., kind=..., weight=..., ...)
Append = Callable[..., Dict[str, Any]]
Emit = Callable[[Dict[str, Any], Append], None]


@dataclass(frozen=True)
class StaticCheckerSpec:
    """One static checker plugged into the audit pipeline.

    ``analyze`` runs the checker on a deliverable path and returns its raw result
    dict (also stored under ``audit_db["artifacts"][artifact_key]`` when set).
    ``emit`` maps that result to one or more scored indicators via ``append``.
    """

    id: str
    analyze: Callable[[str], Dict[str, Any]]
    emit: Emit
    artifact_key: str = ""  # key under audit_db["artifacts"]; "" = not stored


# --------------------------------------------------------------------------- #
# emit functions — these MUST reproduce the exact indicators (labels, weights,
# order) previously inlined in main.py:1091-1200 so historical scores are stable.
# --------------------------------------------------------------------------- #

def emit_hexagonal(result: Dict[str, Any], append: Append) -> None:
    if result.get("rules"):
        for rule in result.get("rules", []):
            append(
                2, "Architecture & Qualité", 1, "Conformité hexagonale",
                rule.get("rule", "Unknown rule"),
                rule.get("status") == "OK",
                f"violations_count={rule.get('violations_count', 0)}",
                details=rule, weight=15,
            )
    else:
        append(
            2, "Architecture & Qualité", 1, "Conformité hexagonale",
            "Analyse hexagonale",
            result.get("status") == "OK",
            _first_non_empty(result.get("error"), result.get("status")),
            details=result, weight=15,
        )


def emit_quality(result: Dict[str, Any], append: Append) -> None:
    append(
        2, "Architecture & Qualité", 2, "Qualité de typage",
        "Occurrences de any",
        result.get("status") == "OK",
        f"any_count={result.get('any_count', 0)}, ts_files={result.get('ts_files', 0)}",
        status=result.get("status"),
        details=result, weight=8,
    )


def emit_readme(result: Dict[str, Any], append: Append) -> None:
    append(
        2, "Architecture & Qualité", 3, "Documentation du projet",
        "Présence du README.md",
        result.get("found", False),
        "Fichier README.md trouvé à la racine" if result.get("found") else "Fichier README.md manquant",
        details=result, weight=2,
    )
    if result.get("found"):
        for key, val in result.get("indicators", {}).items():
            append(
                2, "Architecture & Qualité", 3, "Documentation du projet",
                f"Contenu : {key}", val,
                "Présent" if val else "Manquant",
                details=result, weight=1,
            )


def emit_auth_static(result: Dict[str, Any], append: Append) -> None:
    for key, label, w in [
        ("jwt_library_present",      "Bibliothèque JWT (jsonwebtoken / jose)", 3),
        ("auth_mutations_present",   "Mutations register / login présentes",   5),
        ("auth_guard_present",       "Middleware / Guard d'authentification",   5),
        ("password_hashing_present", "Hachage de mot de passe (bcrypt/argon2)", 3),
    ]:
        append(
            2, "Architecture & Qualité", 4, "Sécurité & Authentification",
            label,
            bool(result.get("indicators", {}).get(key, False)),
            f"detected={'yes' if result.get('indicators', {}).get(key) else 'no'}",
            details=result, weight=w,
        )


def emit_injection(result: Dict[str, Any], append: Append) -> None:
    for key, label, w in [
        ("no_direct_instantiation_in_core",  "Pas d'instanciation directe dans Core",       10),
        ("injectable_decorator_used",         "@injectable() sur les use cases",              5),
        ("inject_on_constructor_params",      "@inject() sur les paramètres constructeur",    5),
        ("constructors_receive_dependencies", "Constructeurs avec dépendances injectées",     8),
    ]:
        val = bool(result.get("indicators", {}).get(key, False))
        violations = result.get("violations", [])
        detail = (
            f"violations={len(violations)}"
            if key == "no_direct_instantiation_in_core" and violations
            else f"detected={'yes' if val else 'no'}"
        )
        append(
            2, "Architecture & Qualité", 5, "Injection de Dépendances (Use Cases)",
            label, val, detail, details=result, weight=w,
        )


def emit_dual_persistence(result: Dict[str, Any], append: Append) -> None:
    for key, label, w in [
        ("mongoose_installed",      "Mongoose installé (MongoDB / tasks)",               5),
        ("sql_orm_installed",       "ORM SQL installé (TypeORM/Sequelize/mysql2)",        5),
        ("mongoose_in_task_code",   "Mongoose utilisé dans les fichiers Task",            8),
        ("sql_in_user_auth_code",   "ORM SQL utilisé dans les fichiers User/Auth",        8),
        ("separate_db_adapters",    "Adaptateurs séparés dans src/adapters/ (mongo+sql)", 5),
    ]:
        append(
            2, "Architecture & Qualité", 6, "Double Persistance (MySQL+MongoDB)",
            label,
            bool(result.get("indicators", {}).get(key, False)),
            f"detected={'yes' if result.get('indicators', {}).get(key) else 'no'}",
            details=result, weight=w,
        )


def emit_devex(result: Dict[str, Any], append: Append) -> None:
    for key, label, w in [
        ("tsconfig_strict", "tsconfig strict: true réellement activé", 5),
        ("eslint_config",   "Configuration ESLint présente",           3),
        ("ci_pipeline",     "Pipeline CI (.github/workflows)",          5),
        ("gitignore_ok",    ".gitignore couvre node_modules / .env",    3),
    ]:
        append(
            2, "Architecture & Qualité", 7, "DevEx & Outillage",
            label,
            bool(result.get("indicators", {}).get(key, False)),
            f"detected={'yes' if result.get('indicators', {}).get(key) else 'no'}",
            details=result, weight=w,
        )


# Default static registry for the Todo challenge. Order matters: it defines the
# append order (and therefore indicator codes 2-1-x .. 2-6-x, then 2-7-x for DevEx).
TODO_STATIC_CHECKERS: List[StaticCheckerSpec] = [
    StaticCheckerSpec("hexagonal", lambda p: HexagonalComplianceChecker(p).check(), emit_hexagonal, "hexagonal"),
    StaticCheckerSpec("quality", lambda p: CodeQualityChecker(p).check_any_usage(), emit_quality, "quality"),
    StaticCheckerSpec("readme", lambda p: ReadmeChecker(p).check(), emit_readme),
    StaticCheckerSpec("auth_static", lambda p: AuthImplementationChecker(p).check(), emit_auth_static, "auth_static"),
    StaticCheckerSpec("injection", lambda p: UseCaseInjectionChecker(p).check(), emit_injection, "injection"),
    StaticCheckerSpec("dual_persistence", lambda p: DualPersistenceChecker(p).check(), emit_dual_persistence, "dual_persistence"),
    StaticCheckerSpec("devex", lambda p: DevExChecker(p).check(), emit_devex, "devex"),
]


@dataclass(frozen=True)
class ChallengeProfile:
    """Everything that varies from one cahier des charges to another."""

    id: str
    label: str
    prompt_version: str
    graphql_endpoint: str
    expected_layers: Tuple[str, ...]
    e2e_step_names: Tuple[str, ...]
    auth_step_weights: Dict[str, int]
    static_checkers: List[StaticCheckerSpec] = field(default_factory=list)
    e2e_scenario: Callable[..., Any] = E2EFunctionalTester
    auth_scenario: Callable[..., Any] = AuthTester


TODO_HEXAGONAL = ChallengeProfile(
    id="todo_hexagonal",
    label="Todo List Hexagonale Multi-Base",
    prompt_version="2605291055",
    graphql_endpoint="http://localhost:4000/graphql",
    expected_layers=("core", "adapters", "infrastructure", "entrypoints"),
    e2e_step_names=(
        "List Tasks (Initial)",
        "Create Task A",
        "Get Task A",
        "Create Task B (Dependent on A)",
        "Close B (Should Fail)",
        "Close A (Success)",
        "Close B (Now Success)",
        "Close Independent Task (No Deps)",
    ),
    auth_step_weights={
        "Auth: Accès non-authentifié bloqué": 10,
        "Auth: Inscription (register)": 5,
        "Auth: Connexion (login)": 5,
        "Auth: Opération authentifiée autorisée": 5,
        "Auth: Token falsifié rejeté": 10,
        # Phase C — real security depth
        "Auth: Token alg=none rejeté": 8,
        "Auth: Signature étrangère rejetée": 8,
        "Auth: Isolation inter-utilisateurs": 10,
        "Auth: Code UNAUTHENTICATED exact": 5,
        "Auth: Mot de passe faible refusé": 3,
    },
    static_checkers=TODO_STATIC_CHECKERS,
    e2e_scenario=E2EFunctionalTester,
    auth_scenario=AuthTester,
)


# The auditor currently runs a single challenge; selection by deliverable becomes
# a lookup here when a second profile is added.
DEFAULT_PROFILE = TODO_HEXAGONAL
PROFILES: Dict[str, ChallengeProfile] = {TODO_HEXAGONAL.id: TODO_HEXAGONAL}
