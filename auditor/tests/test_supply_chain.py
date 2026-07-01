import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from modules.supply_chain import (
    ComposePortsChecker,
    DevExChecker,
    MakefileTeardownChecker,
    NpmAuditChecker,
    SecretsScanner,
)

_PORT_CONTRACT = {"MongoDB": (47017, 27017), "MySQL": (43306, 3306)}


def test_devex_detects_strict_with_comments_and_extends(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "tsconfig.json").write_text(
        '{\n  // extends a base config\n  "extends": "./tsconfig.base.json",\n'
        '  "compilerOptions": { "target": "ES2020", }\n}',
        encoding="utf-8",
    )
    (project / "tsconfig.base.json").write_text(
        '{ "compilerOptions": { "strict": true } }', encoding="utf-8"
    )

    result = DevExChecker(str(project)).check()

    assert result["indicators"]["tsconfig_strict"] is True


def test_devex_detects_non_strict(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "tsconfig.json").write_text(
        '{ "compilerOptions": { "strict": false } }', encoding="utf-8"
    )

    result = DevExChecker(str(project)).check()

    assert result["indicators"]["tsconfig_strict"] is False


def test_devex_gitignore_and_ci(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (project / ".gitignore").write_text("node_modules\n.env\ndist\n", encoding="utf-8")

    result = DevExChecker(str(project)).check()

    assert result["indicators"]["ci_pipeline"] is True
    assert result["indicators"]["gitignore_ok"] is True


def test_secrets_scanner_flags_real_and_skips_placeholders(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    # Whitelisted example file with placeholder values → must NOT flag.
    (project / ".env.example").write_text(
        "JWT_SECRET=changeme\nAPI_KEY=your-key-here\n", encoding="utf-8"
    )
    # Real hardcoded secret in source → must flag.
    (project / "config.ts").write_text(
        'export const cfg = { apiKey: "sk-live-9f8a7b6c5d4e3f2a1b0c4d5e" };', encoding="utf-8"
    )

    result = SecretsScanner(str(project)).scan()

    assert result["status"] == "DETECTE"
    assert any("config.ts" in f["file"] for f in result["findings"])
    assert not any(".env.example" in f["file"] for f in result["findings"])


def test_secrets_scanner_flags_committed_dotenv(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / ".env").write_text("DB_PASSWORD=anything\n", encoding="utf-8")

    result = SecretsScanner(str(project)).scan()

    assert result["status"] == "DETECTE"
    assert any(f["kind"] == "committed_dotenv" for f in result["findings"])


def test_secrets_scanner_clean_project(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / ".env.example").write_text("JWT_SECRET=changeme\n", encoding="utf-8")
    (project / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")

    result = SecretsScanner(str(project)).scan()

    assert result["status"] == "NON_DETECTE"
    assert result["count"] == 0


def test_secrets_scanner_skips_test_files(tmp_path: Path) -> None:
    # Co-located *.test.ts files legitimately contain fixture passwords and tokens —
    # they must never trigger a committed_secrets malus.
    project = tmp_path / "deliverable" / "src" / "core" / "use-cases"
    project.mkdir(parents=True)
    (project / "LoginUseCase.test.ts").write_text(
        'it("logs in", () => { const pwd = "SuperSecret99!"; });', encoding="utf-8"
    )
    (project / "TokenService.test.ts").write_text(
        'const token = "header.payload.signaturevalue0123456789012345";', encoding="utf-8"
    )
    # A real production file with the same content SHOULD still be flagged.
    (project / "LoginUseCase.ts").write_text(
        'export const HARDCODED: secret = "SuperSecret99!";', encoding="utf-8"
    )

    result = SecretsScanner(str(tmp_path / "deliverable")).scan()

    flagged = [f["file"] for f in result["findings"]]
    assert not any("LoginUseCase.test.ts" in f for f in flagged), "test file must not be flagged"
    assert not any("TokenService.test.ts" in f for f in flagged), "test file must not be flagged"
    assert any("LoginUseCase.ts" in f for f in flagged), (
        "production file with hardcoded secret must be flagged"
    )


def test_compose_ports_checker_accepts_mandated_ports(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "docker-compose.yml").write_text(
        "services:\n"
        '  api:\n    ports:\n      - "4000:4000"\n'
        '  mongodb:\n    image: mongo\n    ports:\n      - "47017:27017"\n'
        '  mysql:\n    image: mysql\n    ports:\n      - "43306:3306"\n',
        encoding="utf-8",
    )

    result = ComposePortsChecker(str(project), _PORT_CONTRACT).check()

    assert result["status"] == "OK"
    assert result["services"]["MongoDB"]["compliant"] is True
    assert result["services"]["MySQL"]["compliant"] is True


def test_compose_ports_checker_flags_standard_ports(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "docker-compose.yml").write_text(
        "services:\n"
        '  mongodb:\n    ports:\n      - "27017:27017"\n'
        '  mysql:\n    ports:\n      - "3306:3306"\n',
        encoding="utf-8",
    )

    result = ComposePortsChecker(str(project), _PORT_CONTRACT).check()

    assert result["status"] == "KO"
    assert result["services"]["MongoDB"]["compliant"] is False
    assert "27017:27017" in result["services"]["MongoDB"]["detail"]  # diagnoses the collision
    assert "attendu 47017:27017" in result["services"]["MongoDB"]["detail"]


def test_compose_ports_checker_missing_file(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()

    result = ComposePortsChecker(str(project), _PORT_CONTRACT).check()

    assert result["status"] == "KO"
    assert result["compose_file"] is None


def test_makefile_teardown_detected(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "Makefile").write_text(
        "start:\n\tdocker compose up -d\n\ndown:\n\tdocker compose down\n", encoding="utf-8"
    )

    result = MakefileTeardownChecker(str(project)).check()

    assert result["status"] == "OK"
    assert result["has_teardown"] is True
    assert result["target"] == "down"


def test_makefile_teardown_accepts_hyphenated_compose(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "Makefile").write_text("clean:\n\tdocker-compose down -v\n", encoding="utf-8")

    result = MakefileTeardownChecker(str(project)).check()

    assert result["has_teardown"] is True
    assert result["target"] == "clean"


def test_makefile_teardown_missing(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "Makefile").write_text("start:\n\tdocker compose up -d\n", encoding="utf-8")

    result = MakefileTeardownChecker(str(project)).check()

    assert result["status"] == "KO"
    assert result["has_teardown"] is False


def test_npm_audit_skips_without_lockfile(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()

    result = NpmAuditChecker(str(project)).audit()

    assert result["status"] == "SKIPPED"


def test_npm_audit_parses_high_and_critical(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "package-lock.json").write_text("{}", encoding="utf-8")
    fake_stdout = json.dumps(
        {
            "metadata": {
                "vulnerabilities": {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 1}
            }
        }
    )
    completed = subprocess.CompletedProcess(
        args=["npm", "audit", "--json"], returncode=1, stdout=fake_stdout, stderr=""
    )

    with patch("modules.supply_chain.subprocess.run", return_value=completed):
        result = NpmAuditChecker(str(project)).audit()

    assert result["status"] == "DETECTE"
    assert result["critical"] == 1
    assert result["high"] == 3


def test_npm_audit_skips_when_offline(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "package-lock.json").write_text("{}", encoding="utf-8")
    completed = subprocess.CompletedProcess(
        args=["npm", "audit", "--json"],
        returncode=1,
        stdout=json.dumps({"error": {"code": "ENOTFOUND"}}),
        stderr="",
    )

    with patch("modules.supply_chain.subprocess.run", return_value=completed):
        result = NpmAuditChecker(str(project)).audit()

    assert result["status"] == "SKIPPED"
