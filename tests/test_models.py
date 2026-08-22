from __future__ import annotations

import pytest
from pydantic import ValidationError

from ccm_casework.evaluator import evaluate_casework
from ccm_casework.models import (
    AssessmentStatus,
    CaseActionKind,
    CaseManifest,
    CaseSnapshot,
    CaseStatus,
    CaseworkRequest,
    ClosureStatus,
    EvidenceReferences,
    ExceptionStatus,
    RemediationStatus,
    SlaEvaluation,
    SlaState,
)

from .helpers import HASH_A, action, case, request


def test_opening_and_evidence_reject_unsafe_or_inconsistent_inputs() -> None:
    opening_payload = case().model_dump()
    opening_payload["assessment_status"] = AssessmentStatus.PASS
    with pytest.raises(ValidationError):
        type(case()).model_validate(opening_payload)
    with pytest.raises(ValidationError):
        EvidenceReferences(evidence_ids=(), evidence_hashes=())
    with pytest.raises(ValidationError):
        EvidenceReferences(evidence_ids=("evidence_a",), evidence_hashes=())
    with pytest.raises(ValidationError):
        EvidenceReferences(
            evidence_ids=("evidence_a", "evidence_a"),
            evidence_hashes=(HASH_A, HASH_A),
        )
    with pytest.raises(ValidationError):
        EvidenceReferences(evidence_ids=("evidence_a",), evidence_hashes=("sha256:wrong",))
    overdue_opening = case().model_dump()
    overdue_opening["due_at"] = "2026-08-22T00:00:00Z"
    with pytest.raises(ValidationError):
        type(case()).model_validate(overdue_opening)
    future_assessment = case().model_dump()
    future_assessment["assessed_at"] = "2026-08-23T00:00:00Z"
    with pytest.raises(ValidationError):
        type(case()).model_validate(future_assessment)


def test_actions_reject_wrong_kind_fields_and_invalid_time_sequence() -> None:
    with pytest.raises(ValidationError):
        action(1, CaseActionKind.ASSIGN_REMEDIATION)
    with pytest.raises(ValidationError):
        action(
            1,
            CaseActionKind.REQUEST_EXCEPTION,
            exception_expires_at="2026-08-22T00:00:00Z",
        )
    first = action(1, CaseActionKind.ASSIGN_REMEDIATION, owner_id="team_member_b")
    second = action(
        2,
        CaseActionKind.SET_REMEDIATION_STATUS,
        remediation_status=RemediationStatus.IN_PROGRESS,
        occurred_at="2026-08-22T12:00:00Z",
    )
    with pytest.raises(ValidationError):
        request(second, first)


def test_manifest_is_sealed_and_rejects_alignment_or_hash_tampering() -> None:
    result = evaluate_casework(request())
    assert result.verify_integrity() and result.manifest_id is not None
    assert not result.model_copy(update={"input_hashes": (HASH_A,)}).verify_integrity()
    with pytest.raises(ValidationError):
        CaseManifest(
            case=result.case,
            events=result.events,
            snapshot=result.snapshot.model_copy(update={"case_id": "case_other_control"}),
            sla=result.sla,
            input_hashes=result.input_hashes,
        )


def test_opening_rejects_a_pass_assessment_in_direct_validation() -> None:
    payload = case().model_dump()
    payload["assessment_status"] = AssessmentStatus.PASS
    with pytest.raises(ValidationError):
        type(case()).model_validate(payload)


def test_snapshot_and_sla_contracts_reject_inconsistent_derived_states() -> None:
    with pytest.raises(ValidationError):
        CaseSnapshot(
            case_id="case_identity_mfa_coverage",
            tenant_id="demo_tenant",
            case_status=CaseStatus.CLOSED,
            remediation_status=RemediationStatus.RESOLVED,
            exception_status=ExceptionStatus.NONE,
            closure_status=ClosureStatus.NOT_SUBMITTED,
            owner_team="cloud_security",
            last_action_sequence=0,
        )
    with pytest.raises(ValidationError):
        CaseSnapshot(
            case_id="case_identity_mfa_coverage",
            tenant_id="demo_tenant",
            case_status=CaseStatus.OPEN,
            remediation_status=RemediationStatus.OPEN,
            exception_status=ExceptionStatus.NONE,
            closure_status=ClosureStatus.PENDING_VERIFICATION,
            owner_team="cloud_security",
            last_action_sequence=0,
        )
    with pytest.raises(ValidationError):
        SlaEvaluation(
            evaluated_at="2026-08-23T00:00:00Z",
            due_soon_hours=24,
            state=SlaState.WITHIN_SLA,
            reason="invalid without due time",
        )
    with pytest.raises(ValidationError):
        SlaEvaluation(
            evaluated_at="2026-08-23T00:00:00Z",
            due_soon_hours=24,
            state=SlaState.NOT_APPLICABLE,
            hours_until_due=0,
            reason="invalid remaining hours",
        )


def test_request_rejects_duplicate_ids_and_temporal_batch_ambiguity() -> None:
    first = action(1, CaseActionKind.ASSIGN_REMEDIATION, owner_id="team_member_b")
    duplicate_id = action(
        2,
        CaseActionKind.SET_REMEDIATION_STATUS,
        remediation_status=RemediationStatus.IN_PROGRESS,
    ).model_copy(update={"action_id": first.action_id})
    with pytest.raises(ValidationError):
        CaseworkRequest(
            case=case(),
            actions=(first, duplicate_id),
            evaluated_at="2026-08-30T00:00:00Z",
        )
    before_opening = action(
        1,
        CaseActionKind.ASSIGN_REMEDIATION,
        owner_id="team_member_b",
        occurred_at="2026-08-21T00:00:00Z",
    )
    with pytest.raises(ValidationError):
        CaseworkRequest(case=case(), actions=(before_opening,), evaluated_at="2026-08-30T00:00:00Z")
    future_action = action(
        1,
        CaseActionKind.ASSIGN_REMEDIATION,
        owner_id="team_member_b",
        occurred_at="2026-09-01T00:00:00Z",
    )
    with pytest.raises(ValidationError):
        CaseworkRequest(case=case(), actions=(future_action,), evaluated_at="2026-08-30T00:00:00Z")
    backward = action(
        2,
        CaseActionKind.SET_REMEDIATION_STATUS,
        remediation_status=RemediationStatus.IN_PROGRESS,
        occurred_at="2026-08-22T00:00:00Z",
    )
    with pytest.raises(ValidationError):
        CaseworkRequest(case=case(), actions=(first, backward), evaluated_at="2026-08-30T00:00:00Z")
