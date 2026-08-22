"""Export ccm-casework public JSON Schemas deterministically."""

from __future__ import annotations

import json
from pathlib import Path

from ccm_casework.models import (
    CaseAction,
    CaseManifest,
    CaseOpenRequest,
    CaseSnapshot,
    CaseworkRequest,
    SlaEvaluation,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "v1"
MODELS = {
    "case-action.schema.json": CaseAction,
    "case-manifest.schema.json": CaseManifest,
    "case-open-request.schema.json": CaseOpenRequest,
    "case-snapshot.schema.json": CaseSnapshot,
    "casework-request.schema.json": CaseworkRequest,
    "sla-evaluation.schema.json": SlaEvaluation,
}


def main() -> None:
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    for filename, model in MODELS.items():
        rendered = json.dumps(
            model.model_json_schema(),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        (SCHEMAS / filename).write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
