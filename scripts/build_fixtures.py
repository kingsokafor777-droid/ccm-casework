"""Build deterministic synthetic ccm-casework fixtures without external inputs."""

from __future__ import annotations

import json
from pathlib import Path

from ccm_casework.evaluator import evaluate_casework
from ccm_casework.models import (
    AssessmentStatus,
    CaseAction,
    CaseActionKind,
    CaseOpenRequest,
    CaseworkRequest,
    ClosureDecision,
    CompensatingControl,
    EvidenceReferences,
    ExceptionDecision,
    RemediationStatus,
    RiskLevel,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)
HASH_C = "sha256:" + ("c" * 64)


def _case() -> CaseOpenRequest:
    return CaseOpenRequest(
        case_id="case_identity_mfa_coverage",
        tenant_id="demo_tenant",
        assessment_manifest_hash=HASH_A,
        control_id="identity_mfa_coverage",
        control_version="1.0.0",
        assessment_status=AssessmentStatus.PARTIAL,
        risk=RiskLevel.HIGH,
        assessed_at="2026-08-21T00:00:00Z",
        opened_at="2026-08-22T00:00:00Z",
        owner_team="cloud_security",
        owner_id="team_member_a",
        due_at="2026-08-30T00:00:00Z",
        source_evidence=EvidenceReferences(
            evidence_ids=("evidence_identity_mfa",),
            evidence_hashes=(HASH_B,),
        ),
    )


def _safe_actions() -> tuple[CaseAction, ...]:
    return (
        CaseAction(
            action_id="assign_owner",
            sequence=1,
            kind=CaseActionKind.ASSIGN_REMEDIATION,
            actor_id="case_manager_a",
            occurred_at="2026-08-22T01:00:00Z",
            reason="assign accountable remediation owner",
            owner_id="team_member_b",
        ),
        CaseAction(
            action_id="begin_remediation",
            sequence=2,
            kind=CaseActionKind.SET_REMEDIATION_STATUS,
            actor_id="team_member_b",
            occurred_at="2026-08-22T02:00:00Z",
            reason="begin documented remediation work",
            remediation_status=RemediationStatus.IN_PROGRESS,
        ),
        CaseAction(
            action_id="request_temporary_exception",
            sequence=3,
            kind=CaseActionKind.REQUEST_EXCEPTION,
            actor_id="team_member_b",
            occurred_at="2026-08-22T03:00:00Z",
            reason="request time-bounded exception during change window",
            exception_expires_at="2026-08-25T00:00:00Z",
        ),
        CaseAction(
            action_id="record_compensating_control",
            sequence=4,
            kind=CaseActionKind.ADD_COMPENSATING_CONTROL,
            actor_id="team_member_b",
            occurred_at="2026-08-22T04:00:00Z",
            reason="record supplied compensating-control reference",
            compensating_control=CompensatingControl(
                control_reference="monitoring_alert_review",
                rationale="documented supplemental monitoring during remediation",
                evidence=EvidenceReferences(
                    evidence_ids=("evidence_monitoring_alert",),
                    evidence_hashes=(HASH_C,),
                ),
            ),
        ),
        CaseAction(
            action_id="reject_exception",
            sequence=5,
            kind=CaseActionKind.DECIDE_EXCEPTION,
            actor_id="risk_reviewer_a",
            occurred_at="2026-08-22T05:00:00Z",
            reason="record supplied exception decision",
            exception_decision=ExceptionDecision.REJECTED,
        ),
        CaseAction(
            action_id="resolve_remediation",
            sequence=6,
            kind=CaseActionKind.SET_REMEDIATION_STATUS,
            actor_id="team_member_b",
            occurred_at="2026-08-23T01:00:00Z",
            reason="submit remediation completion state",
            remediation_status=RemediationStatus.RESOLVED,
        ),
        CaseAction(
            action_id="submit_closure",
            sequence=7,
            kind=CaseActionKind.SUBMIT_CLOSURE,
            actor_id="team_member_b",
            occurred_at="2026-08-23T02:00:00Z",
            reason="submit payload-blind verification references",
            closure_evidence=EvidenceReferences(
                evidence_ids=("evidence_closure_verification",),
                evidence_hashes=(HASH_A,),
            ),
        ),
        CaseAction(
            action_id="verify_closure",
            sequence=8,
            kind=CaseActionKind.VERIFY_CLOSURE,
            actor_id="control_reviewer_a",
            occurred_at="2026-08-23T03:00:00Z",
            reason="record supplied closure verification decision",
            closure_decision=ClosureDecision.VERIFIED,
        ),
    )


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    request = CaseworkRequest(
        case=_case(),
        actions=_safe_actions(),
        evaluated_at="2026-08-24T00:00:00Z",
    )
    manifest = evaluate_casework(request)
    active_request = CaseworkRequest(
        case=_case(),
        actions=_safe_actions()[:2],
        evaluated_at="2026-08-29T12:00:00Z",
    )
    payloads = {
        "safe-request.json": request.model_dump(mode="json", exclude_none=True),
        "safe-manifest.json": manifest.model_dump(mode="json", exclude_none=True),
        "active-request.json": active_request.model_dump(mode="json", exclude_none=True),
    }
    for name, payload in payloads.items():
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        (FIXTURES / name).write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
