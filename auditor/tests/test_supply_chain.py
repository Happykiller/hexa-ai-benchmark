import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

AUDITOR_DIR = Path(__file__).resolve().parents[1]
if str(AUDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(AUDITOR_DIR))

from modules.supply_chain import DevExChecker, NpmAuditChecker, SecretsScanner


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
    (project / ".env.example").write_text("JWT_SECRET=changeme\nAPI_KEY=your-key-here\n", encoding="utf-8")
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
        {"metadata": {"vulnerabilities": {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 1}}}
    )
    completed = subprocess.CompletedProcess(args=["npm", "audit", "--json"], returncode=1, stdout=fake_stdout, stderr="")

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
        args=["npm", "audit", "--json"], returncode=1, stdout=json.dumps({"error": {"code": "ENOTFOUND"}}), stderr=""
    )

    with patch("modules.supply_chain.subprocess.run", return_value=completed):
        result = NpmAuditChecker(str(project)).audit()

    assert result["status"] == "SKIPPED"
