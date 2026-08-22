from __future__ import annotations

import json
from pathlib import Path

from ccm_casework.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_cli_evaluates_fixture_and_validates_sealed_output(tmp_path, capsys) -> None:
    output = tmp_path / "case-manifest.json"
    request_path = ROOT / "fixtures" / "safe-request.json"
    assert main(["evaluate", str(request_path), "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    assert main(["validate", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_cli_rejects_malformed_or_tampered_json(tmp_path, capsys) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    assert main(["evaluate", str(malformed)]) == 2
    assert json.loads(capsys.readouterr().out)["valid"] is False
    tampered = tmp_path / "tampered.json"
    payload = json.loads((ROOT / "fixtures" / "safe-manifest.json").read_text(encoding="utf-8"))
    payload["snapshot"]["owner_id"] = "team_member_tampered"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["validate", str(tampered)]) == 2
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_exported_schema_inventory_is_complete() -> None:
    names = {path.name for path in (ROOT / "schemas" / "v1").glob("*.json")}
    assert names == {
        "case-action.schema.json",
        "case-manifest.schema.json",
        "case-open-request.schema.json",
        "case-snapshot.schema.json",
        "casework-request.schema.json",
        "sla-evaluation.schema.json",
    }
