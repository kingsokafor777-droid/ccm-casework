"""Pure deterministic reducer for ccm-casework workflow manifests."""

from __future__ import annotations

import math
from datetime import datetime

from .canonical import sha256_digest, stable_identifier
from .models import (
    CaseAction,
    CaseActionKind,
    CaseEvent,
    CaseManifest,
    CaseSnapshot,
    CaseStatus,
    CaseworkRequest,
    ClosureDecision,
    ClosureStatus,
    ExceptionStatus,
    RemediationStatus,
    SlaEvaluation,
    SlaState,
)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _initial_snapshot(request: CaseworkRequest) -> CaseSnapshot:
    return CaseSnapshot(
        case_id=request.case.case_id,
        tenant_id=request.case.tenant_id,
        case_status=CaseStatus.OPEN,
        remediation_status=RemediationStatus.OPEN,
        exception_status=ExceptionStatus.NONE,
        closure_status=ClosureStatus.NOT_SUBMITTED,
        owner_team=request.case.owner_team,
        owner_id=request.case.owner_id,
        last_action_sequence=0,
    )


def _expire_exception(snapshot: CaseSnapshot, at_time: str) -> CaseSnapshot:
    if (
        snapshot.exception_status == ExceptionStatus.APPROVED
        and snapshot.exception_expires_at is not None
        and _parse_time(at_time) >= _parse_time(snapshot.exception_expires_at)
    ):
        return snapshot.model_copy(update={"exception_status": ExceptionStatus.EXPIRED})
    return snapshot


def _assert_not_closed(snapshot: CaseSnapshot, action: CaseAction) -> None:
    if snapshot.case_status == CaseStatus.CLOSED and action.kind != CaseActionKind.REOPEN_CASE:
        raise ValueError("closed cases accept only reopen_case actions")


def _case_status_for_remediation(status: RemediationStatus) -> CaseStatus:
    if status == RemediationStatus.BLOCKED:
        return CaseStatus.BLOCKED
    if status == RemediationStatus.RESOLVED:
        return CaseStatus.READY_FOR_CLOSURE
    if status == RemediationStatus.OPEN:
        return CaseStatus.OPEN
    return CaseStatus.IN_PROGRESS


def _apply_action(snapshot: CaseSnapshot, action: CaseAction) -> CaseSnapshot:
    """Apply a validated action or fail closed when its predecessor state is invalid."""

    snapshot = _expire_exception(snapshot, action.occurred_at)
    _assert_not_closed(snapshot, action)
    updates: dict[str, object] = {"last_action_sequence": action.sequence}

    if action.kind == CaseActionKind.ASSIGN_REMEDIATION:
        updates["owner_id"] = action.owner_id
    elif action.kind == CaseActionKind.SET_REMEDIATION_STATUS:
        if snapshot.closure_status == ClosureStatus.PENDING_VERIFICATION:
            raise ValueError(
                "remediation status cannot change while closure verification is pending"
            )
        assert action.remediation_status is not None
        updates["remediation_status"] = action.remediation_status
        updates["case_status"] = _case_status_for_remediation(action.remediation_status)
    elif action.kind == CaseActionKind.REQUEST_EXCEPTION:
        if snapshot.exception_status in {ExceptionStatus.PENDING, ExceptionStatus.APPROVED}:
            raise ValueError("a pending or approved exception must be decided or revoked first")
        assert action.exception_expires_at is not None
        updates["exception_status"] = ExceptionStatus.PENDING
        updates["exception_expires_at"] = action.exception_expires_at
        updates["compensating_controls"] = ()
    elif action.kind == CaseActionKind.DECIDE_EXCEPTION:
        if snapshot.exception_status != ExceptionStatus.PENDING:
            raise ValueError("exception decisions require a pending exception")
        assert action.exception_decision is not None
        updates["exception_status"] = ExceptionStatus(action.exception_decision.value)
        if action.exception_decision.value == ExceptionStatus.REJECTED.value:
            updates["exception_expires_at"] = None
    elif action.kind == CaseActionKind.ADD_COMPENSATING_CONTROL:
        if snapshot.exception_status not in {ExceptionStatus.PENDING, ExceptionStatus.APPROVED}:
            raise ValueError("compensating controls require a pending or approved exception")
        assert action.compensating_control is not None
        updates["compensating_controls"] = (
            *snapshot.compensating_controls,
            action.compensating_control,
        )
    elif action.kind == CaseActionKind.REVOKE_EXCEPTION:
        if snapshot.exception_status != ExceptionStatus.APPROVED:
            raise ValueError("only an approved exception can be revoked")
        updates["exception_status"] = ExceptionStatus.REVOKED
        updates["exception_expires_at"] = None
    elif action.kind == CaseActionKind.SUBMIT_CLOSURE:
        if snapshot.remediation_status != RemediationStatus.RESOLVED:
            raise ValueError("closure submission requires resolved remediation")
        if snapshot.exception_status in {ExceptionStatus.PENDING, ExceptionStatus.APPROVED}:
            raise ValueError("closure submission requires no pending or approved exception")
        assert action.closure_evidence is not None
        updates["closure_status"] = ClosureStatus.PENDING_VERIFICATION
        updates["closure_evidence"] = action.closure_evidence
        updates["case_status"] = CaseStatus.READY_FOR_CLOSURE
    elif action.kind == CaseActionKind.VERIFY_CLOSURE:
        if snapshot.closure_status != ClosureStatus.PENDING_VERIFICATION:
            raise ValueError("closure verification requires a submitted closure")
        assert action.closure_decision is not None
        if action.closure_decision == ClosureDecision.VERIFIED:
            updates["closure_status"] = ClosureStatus.VERIFIED
            updates["case_status"] = CaseStatus.CLOSED
        else:
            updates["closure_status"] = ClosureStatus.REJECTED
            updates["remediation_status"] = RemediationStatus.IN_PROGRESS
            updates["case_status"] = CaseStatus.IN_PROGRESS
    elif action.kind == CaseActionKind.REOPEN_CASE:
        if snapshot.case_status != CaseStatus.CLOSED:
            raise ValueError("reopen_case requires a closed case")
        updates["case_status"] = CaseStatus.OPEN
        updates["remediation_status"] = RemediationStatus.OPEN
        updates["closure_status"] = ClosureStatus.NOT_SUBMITTED
        updates["closure_evidence"] = None
    else:
        raise ValueError(f"unsupported action kind: {action.kind.value}")
    return snapshot.model_copy(update=updates)


def _event(case_id: str, action: CaseAction, previous_hash: str | None) -> CaseEvent:
    projection = {
        "case_id": case_id,
        "sequence": action.sequence,
        "action": action.model_dump(mode="json", exclude_none=True),
        "previous_event_hash": previous_hash,
    }
    event_hash = sha256_digest(projection)
    return CaseEvent(
        event_id=stable_identifier(
            "case_event",
            {"case_id": case_id, "sequence": action.sequence, "event_hash": event_hash},
        ),
        action=action,
        previous_event_hash=previous_hash,
        event_hash=event_hash,
    )


def evaluate_sla(
    snapshot: CaseSnapshot,
    *,
    due_at: str | None,
    evaluated_at: str,
    due_soon_hours: int,
) -> SlaEvaluation:
    """Evaluate deadline state using only explicit request timestamps and policy inputs."""

    if due_at is None:
        return SlaEvaluation(
            evaluated_at=evaluated_at,
            due_soon_hours=due_soon_hours,
            state=SlaState.NOT_APPLICABLE,
            reason="case has no supplied remediation due time",
        )
    if snapshot.case_status == CaseStatus.CLOSED:
        return SlaEvaluation(
            evaluated_at=evaluated_at,
            due_at=due_at,
            due_soon_hours=due_soon_hours,
            state=SlaState.NOT_APPLICABLE,
            reason="case is closed; deadline evaluation no longer applies",
        )
    seconds_until_due = (_parse_time(due_at) - _parse_time(evaluated_at)).total_seconds()
    hours_until_due = math.floor(seconds_until_due / 3_600)
    if seconds_until_due < 0:
        state = SlaState.OVERDUE
        reason = "supplied evaluation time is after the supplied remediation due time"
    elif seconds_until_due <= due_soon_hours * 3_600:
        state = SlaState.DUE_SOON
        reason = "supplied evaluation time is inside the configured due-soon window"
    else:
        state = SlaState.WITHIN_SLA
        reason = "supplied remediation due time is outside the configured due-soon window"
    return SlaEvaluation(
        evaluated_at=evaluated_at,
        due_at=due_at,
        due_soon_hours=due_soon_hours,
        state=state,
        hours_until_due=hours_until_due,
        reason=reason,
    )


def evaluate_casework(request: CaseworkRequest) -> CaseManifest:
    """Build and seal a deterministic manifest from supplied opening and action records."""

    snapshot = _initial_snapshot(request)
    previous_hash: str | None = None
    events: list[CaseEvent] = []
    for action in request.actions:
        snapshot = _apply_action(snapshot, action)
        event = _event(request.case.case_id, action, previous_hash)
        events.append(event)
        previous_hash = event.event_hash
    snapshot = _expire_exception(snapshot, request.evaluated_at)
    input_hashes = (
        sha256_digest(request.case.model_dump(mode="json", exclude_none=True)),
        *(
            sha256_digest(action.model_dump(mode="json", exclude_none=True))
            for action in request.actions
        ),
    )
    return CaseManifest(
        case=request.case,
        events=tuple(events),
        snapshot=snapshot,
        sla=evaluate_sla(
            snapshot,
            due_at=request.case.due_at,
            evaluated_at=request.evaluated_at,
            due_soon_hours=request.due_soon_hours,
        ),
        input_hashes=input_hashes,
    ).seal()
