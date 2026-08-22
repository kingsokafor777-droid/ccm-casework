from __future__ import annotations

import pytest

from ccm_casework.evaluator import evaluate_casework, evaluate_sla
from ccm_casework.models import (
    CaseActionKind,
    CaseStatus,
    ClosureDecision,
    ClosureStatus,
    ExceptionDecision,
    ExceptionStatus,
    RemediationStatus,
    SlaState,
)

from .helpers import action, compensating_control, request


def test_happy_path_requires_submitted_evidence_and_explicit_verified_closure() -> None:
    actions = (
        action(1, CaseActionKind.ASSIGN_REMEDIATION, owner_id="team_member_b"),
        action(
            2,
            CaseActionKind.SET_REMEDIATION_STATUS,
            remediation_status=RemediationStatus.IN_PROGRESS,
        ),
        action(
            3,
            CaseActionKind.SET_REMEDIATION_STATUS,
            remediation_status=RemediationStatus.RESOLVED,
        ),
        action(
            4,
            CaseActionKind.SUBMIT_CLOSURE,
            closure_evidence=compensating_control().evidence,
        ),
        action(
            5,
            CaseActionKind.VERIFY_CLOSURE,
            closure_decision=ClosureDecision.VERIFIED,
        ),
    )
    first = evaluate_casework(request(*actions))
    second = evaluate_casework(request(*actions))
    assert first == second
    assert first.snapshot.case_status == CaseStatus.CLOSED
    assert first.snapshot.closure_status == ClosureStatus.VERIFIED
    assert first.sla.state == SlaState.NOT_APPLICABLE
    assert first.verify_integrity()
    assert tuple(event.action.sequence for event in first.events) == (1, 2, 3, 4, 5)


def test_exception_workflow_preserves_expiry_and_compensating_references() -> None:
    actions = (
        action(
            1,
            CaseActionKind.REQUEST_EXCEPTION,
            exception_expires_at="2026-08-25T00:00:00Z",
        ),
        action(
            2,
            CaseActionKind.ADD_COMPENSATING_CONTROL,
            compensating_control=compensating_control(),
        ),
        action(
            3,
            CaseActionKind.DECIDE_EXCEPTION,
            exception_decision=ExceptionDecision.APPROVED,
        ),
    )
    result = evaluate_casework(request(*actions, evaluated_at="2026-08-26T00:00:00Z"))
    assert result.snapshot.exception_status == ExceptionStatus.EXPIRED
    assert len(result.snapshot.compensating_controls) == 1
    assert result.snapshot.case_status == CaseStatus.OPEN


def test_invalid_state_transitions_fail_closed() -> None:
    with pytest.raises(ValueError, match="pending exception"):
        evaluate_casework(
            request(
                action(
                    1,
                    CaseActionKind.DECIDE_EXCEPTION,
                    exception_decision=ExceptionDecision.APPROVED,
                )
            )
        )
    with pytest.raises(ValueError, match="resolved remediation"):
        evaluate_casework(
            request(
                action(
                    1,
                    CaseActionKind.SUBMIT_CLOSURE,
                    closure_evidence=compensating_control().evidence,
                )
            )
        )
    with pytest.raises(ValueError, match="only an approved exception"):
        evaluate_casework(request(action(1, CaseActionKind.REVOKE_EXCEPTION)))
    with pytest.raises(ValueError, match="compensating controls require"):
        evaluate_casework(
            request(
                action(
                    1,
                    CaseActionKind.ADD_COMPENSATING_CONTROL,
                    compensating_control=compensating_control(),
                )
            )
        )
    with pytest.raises(ValueError, match="submitted closure"):
        evaluate_casework(
            request(
                action(
                    1,
                    CaseActionKind.VERIFY_CLOSURE,
                    closure_decision=ClosureDecision.VERIFIED,
                )
            )
        )


def test_remediation_state_mapping_and_exception_order_fail_closed() -> None:
    blocked = evaluate_casework(
        request(
            action(
                1,
                CaseActionKind.SET_REMEDIATION_STATUS,
                remediation_status=RemediationStatus.BLOCKED,
            )
        )
    )
    assert blocked.snapshot.case_status == CaseStatus.BLOCKED
    reopened_work = evaluate_casework(
        request(
            action(
                1,
                CaseActionKind.SET_REMEDIATION_STATUS,
                remediation_status=RemediationStatus.IN_PROGRESS,
            ),
            action(
                2,
                CaseActionKind.SET_REMEDIATION_STATUS,
                remediation_status=RemediationStatus.OPEN,
            ),
        )
    )
    assert reopened_work.snapshot.case_status == CaseStatus.OPEN
    with pytest.raises(ValueError, match="pending or approved exception"):
        evaluate_casework(
            request(
                action(
                    1,
                    CaseActionKind.REQUEST_EXCEPTION,
                    exception_expires_at="2026-09-01T00:00:00Z",
                ),
                action(
                    2,
                    CaseActionKind.REQUEST_EXCEPTION,
                    exception_expires_at="2026-09-02T00:00:00Z",
                ),
            )
        )


def test_active_exception_blocks_closure_and_closed_case_requires_reopen() -> None:
    with pytest.raises(ValueError, match="no pending or approved exception"):
        evaluate_casework(
            request(
                action(
                    1,
                    CaseActionKind.REQUEST_EXCEPTION,
                    exception_expires_at="2026-09-20T00:00:00Z",
                ),
                action(
                    2,
                    CaseActionKind.DECIDE_EXCEPTION,
                    exception_decision=ExceptionDecision.APPROVED,
                ),
                action(
                    3,
                    CaseActionKind.SET_REMEDIATION_STATUS,
                    remediation_status=RemediationStatus.RESOLVED,
                ),
                action(
                    4,
                    CaseActionKind.SUBMIT_CLOSURE,
                    closure_evidence=compensating_control().evidence,
                ),
            )
        )
    closed_actions = (
        action(
            1,
            CaseActionKind.SET_REMEDIATION_STATUS,
            remediation_status=RemediationStatus.RESOLVED,
        ),
        action(
            2,
            CaseActionKind.SUBMIT_CLOSURE,
            closure_evidence=compensating_control().evidence,
        ),
        action(
            3,
            CaseActionKind.VERIFY_CLOSURE,
            closure_decision=ClosureDecision.VERIFIED,
        ),
    )
    with pytest.raises(ValueError, match="closed cases accept only"):
        evaluate_casework(
            request(
                *closed_actions,
                action(
                    4,
                    CaseActionKind.SET_REMEDIATION_STATUS,
                    remediation_status=RemediationStatus.IN_PROGRESS,
                ),
            )
        )
    reopened = evaluate_casework(request(*closed_actions, action(4, CaseActionKind.REOPEN_CASE)))
    assert reopened.snapshot.case_status == CaseStatus.OPEN
    assert reopened.snapshot.closure_status == ClosureStatus.NOT_SUBMITTED


def test_rejected_closure_reopens_remediation_and_closed_case_can_be_reopened() -> None:
    actions = (
        action(
            1,
            CaseActionKind.SET_REMEDIATION_STATUS,
            remediation_status=RemediationStatus.RESOLVED,
        ),
        action(
            2,
            CaseActionKind.SUBMIT_CLOSURE,
            closure_evidence=compensating_control().evidence,
        ),
        action(
            3,
            CaseActionKind.VERIFY_CLOSURE,
            closure_decision=ClosureDecision.REJECTED,
        ),
    )
    rejected = evaluate_casework(request(*actions))
    assert rejected.snapshot.closure_status == ClosureStatus.REJECTED
    assert rejected.snapshot.remediation_status == RemediationStatus.IN_PROGRESS
    with pytest.raises(ValueError, match="reopen_case requires a closed case"):
        evaluate_casework(request(*actions, action(4, CaseActionKind.REOPEN_CASE)))


def test_sla_is_supplied_time_only_and_covers_all_states() -> None:
    active = evaluate_casework(request(evaluated_at="2026-08-25T00:00:00Z"))
    assert active.sla.state == SlaState.WITHIN_SLA
    due_soon = evaluate_sla(
        active.snapshot,
        due_at="2026-08-26T00:00:00Z",
        evaluated_at="2026-08-25T00:00:00Z",
        due_soon_hours=48,
    )
    assert due_soon.state == SlaState.DUE_SOON
    overdue = evaluate_sla(
        active.snapshot,
        due_at="2026-08-24T00:00:00Z",
        evaluated_at="2026-08-25T00:00:00Z",
        due_soon_hours=48,
    )
    assert overdue.state == SlaState.OVERDUE and overdue.hours_until_due == -24
    not_applicable = evaluate_casework(request(due_at=None))
    assert not_applicable.sla.state == SlaState.NOT_APPLICABLE


def test_event_chain_tampering_is_detected() -> None:
    result = evaluate_casework(
        request(action(1, CaseActionKind.ASSIGN_REMEDIATION, owner_id="team_member_b"))
    )
    tampered_event = result.events[0].model_copy(update={"event_hash": "sha256:" + ("d" * 64)})
    tampered = result.model_copy(update={"events": (tampered_event,)})
    assert not tampered.verify_integrity()
