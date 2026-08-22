"""Deterministic synthetic ccm-casework contract builders."""

from __future__ import annotations

from ccm_casework.models import (
    AssessmentStatus,
    CaseAction,
    CaseActionKind,
    CaseOpenRequest,
    CaseworkRequest,
    CompensatingControl,
    EvidenceReferences,
    RiskLevel,
)

HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)
HASH_C = "sha256:" + ("c" * 64)


def evidence(name: str = "identity_mfa") -> EvidenceReferences:
    return EvidenceReferences(evidence_ids=(f"evidence_{name}",), evidence_hashes=(HASH_B,))


def case(*, due_at: str | None = "2026-09-15T00:00:00Z") -> CaseOpenRequest:
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
        due_at=due_at,
        source_evidence=evidence(),
    )


def action(
    sequence: int,
    kind: CaseActionKind,
    *,
    occurred_at: str | None = None,
    **changes: object,
) -> CaseAction:
    fields: dict[str, object] = {
        "action_id": f"action_{sequence}",
        "sequence": sequence,
        "kind": kind,
        "actor_id": "case_actor_a",
        "occurred_at": occurred_at or f"2026-08-{22 + sequence:02d}T00:00:00Z",
        "reason": f"synthetic {kind.value} action",
    }
    fields.update(changes)
    return CaseAction(**fields)


def compensating_control() -> CompensatingControl:
    return CompensatingControl(
        control_reference="monitoring_alert_review",
        rationale="synthetic supplemental monitoring reference",
        evidence=EvidenceReferences(
            evidence_ids=("evidence_monitoring",),
            evidence_hashes=(HASH_C,),
        ),
    )


def request(
    *actions: CaseAction,
    due_at: str | None = "2026-09-15T00:00:00Z",
    evaluated_at: str = "2026-09-01T00:00:00Z",
) -> CaseworkRequest:
    return CaseworkRequest(case=case(due_at=due_at), actions=actions, evaluated_at=evaluated_at)
