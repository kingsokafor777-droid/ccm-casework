"""Strict deterministic public contracts for ccm-casework v1.

The contracts retain supplied technical workflow evidence. They do not authenticate
actors, authorize risk, perform remediation, or assert certification, audit opinion,
or framework conformance.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .canonical import require_digest, sha256_digest, stable_identifier

SCHEMA_VERSION: Final = "ccm.casework/v1"
UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
UTCDateTime = Annotated[str, StringConstraints(pattern=UTC_TIMESTAMP_PATTERN.pattern)]
StableId = Annotated[str, StringConstraints(pattern=ID_PATTERN.pattern)]
NonEmpty = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class StrictModel(BaseModel):
    """Fail closed on unknown or coercible public contract fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AssessmentStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"
    ERROR = "error"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class RemediationStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"


class CaseStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    READY_FOR_CLOSURE = "ready_for_closure"
    CLOSED = "closed"


class ExceptionStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ClosureStatus(str, Enum):
    NOT_SUBMITTED = "not_submitted"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ExceptionDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ClosureDecision(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"


class SlaState(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    WITHIN_SLA = "within_sla"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"


class CaseActionKind(str, Enum):
    ASSIGN_REMEDIATION = "assign_remediation"
    SET_REMEDIATION_STATUS = "set_remediation_status"
    REQUEST_EXCEPTION = "request_exception"
    DECIDE_EXCEPTION = "decide_exception"
    ADD_COMPENSATING_CONTROL = "add_compensating_control"
    REVOKE_EXCEPTION = "revoke_exception"
    SUBMIT_CLOSURE = "submit_closure"
    VERIFY_CLOSURE = "verify_closure"
    REOPEN_CASE = "reopen_case"


class EvidenceReferences(StrictModel):
    """Payload-blind references that bind identifiers to their SHA-256 digests."""

    evidence_ids: tuple[StableId, ...]
    evidence_hashes: tuple[str, ...]

    @field_validator("evidence_hashes")
    @classmethod
    def _validate_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for digest in value:
            require_digest(digest)
        return value

    @model_validator(mode="after")
    def _validate_cardinality(self) -> EvidenceReferences:
        if not self.evidence_ids:
            raise ValueError("evidence references require at least one evidence ID")
        if len(self.evidence_ids) != len(self.evidence_hashes):
            raise ValueError("evidence IDs and hashes must have matching lengths")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence IDs must be unique within one reference set")
        return self


class CompensatingControl(StrictModel):
    """A supplied compensating-control claim with evidence references, not a finding."""

    control_reference: NonEmpty
    rationale: NonEmpty
    evidence: EvidenceReferences


class CaseOpenRequest(StrictModel):
    """Source-linked case opening information for one assessed technical control."""

    case_id: StableId
    tenant_id: StableId
    assessment_manifest_hash: str
    control_id: StableId
    control_version: NonEmpty
    assessment_status: AssessmentStatus
    risk: RiskLevel
    assessed_at: UTCDateTime
    opened_at: UTCDateTime
    owner_team: StableId
    owner_id: StableId | None = None
    due_at: UTCDateTime | None = None
    source_evidence: EvidenceReferences

    @field_validator("assessment_manifest_hash")
    @classmethod
    def _validate_manifest_hash(cls, value: str) -> str:
        return require_digest(value)

    @model_validator(mode="after")
    def _validate_opening(self) -> CaseOpenRequest:
        if self.assessment_status == AssessmentStatus.PASS:
            raise ValueError("casework openings must not be created from pass assessments")
        if self.assessed_at > self.opened_at:
            raise ValueError("assessed_at must not be after opened_at")
        if self.due_at is not None and self.due_at <= self.opened_at:
            raise ValueError("due_at must be after opened_at")
        return self


class CaseAction(StrictModel):
    """One supplied immutable workflow action with kind-specific closed fields."""

    action_id: StableId
    sequence: int = Field(ge=1, le=1_000_000)
    kind: CaseActionKind
    actor_id: StableId
    occurred_at: UTCDateTime
    reason: NonEmpty
    owner_id: StableId | None = None
    remediation_status: RemediationStatus | None = None
    exception_expires_at: UTCDateTime | None = None
    exception_decision: ExceptionDecision | None = None
    compensating_control: CompensatingControl | None = None
    closure_evidence: EvidenceReferences | None = None
    closure_decision: ClosureDecision | None = None

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> CaseAction:
        required_fields: dict[CaseActionKind, tuple[str, ...]] = {
            CaseActionKind.ASSIGN_REMEDIATION: ("owner_id",),
            CaseActionKind.SET_REMEDIATION_STATUS: ("remediation_status",),
            CaseActionKind.REQUEST_EXCEPTION: ("exception_expires_at",),
            CaseActionKind.DECIDE_EXCEPTION: ("exception_decision",),
            CaseActionKind.ADD_COMPENSATING_CONTROL: ("compensating_control",),
            CaseActionKind.REVOKE_EXCEPTION: (),
            CaseActionKind.SUBMIT_CLOSURE: ("closure_evidence",),
            CaseActionKind.VERIFY_CLOSURE: ("closure_decision",),
            CaseActionKind.REOPEN_CASE: (),
        }
        supplied = {
            name
            for name in (
                "owner_id",
                "remediation_status",
                "exception_expires_at",
                "exception_decision",
                "compensating_control",
                "closure_evidence",
                "closure_decision",
            )
            if getattr(self, name) is not None
        }
        required = set(required_fields[self.kind])
        if supplied != required:
            expected = ", ".join(sorted(required)) or "no extra fields"
            raise ValueError(f"{self.kind.value} requires exactly: {expected}")
        if self.exception_expires_at is not None and self.exception_expires_at <= self.occurred_at:
            raise ValueError("exception_expires_at must be after action occurrence time")
        return self


class CaseEvent(StrictModel):
    """Hash-linked, derived event projection over one validated case action."""

    event_id: StableId
    action: CaseAction
    previous_event_hash: str | None = None
    event_hash: str

    @field_validator("previous_event_hash", "event_hash")
    @classmethod
    def _validate_event_hashes(cls, value: str | None) -> str | None:
        return None if value is None else require_digest(value)

    def hash_projection(self, case_id: str) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "sequence": self.action.sequence,
            "action": self.action.model_dump(mode="json", exclude_none=True),
            "previous_event_hash": self.previous_event_hash,
        }

    def computed_hash(self, case_id: str) -> str:
        return sha256_digest(self.hash_projection(case_id))

    def verify_integrity(self, case_id: str, expected_previous_hash: str | None) -> bool:
        return (
            self.previous_event_hash == expected_previous_hash
            and self.event_hash == self.computed_hash(case_id)
            and self.event_id
            == stable_identifier(
                "case_event",
                {
                    "case_id": case_id,
                    "sequence": self.action.sequence,
                    "event_hash": self.event_hash,
                },
            )
        )


class CaseSnapshot(StrictModel):
    """Current deterministic workflow state after applying a valid action sequence."""

    case_id: StableId
    tenant_id: StableId
    case_status: CaseStatus
    remediation_status: RemediationStatus
    exception_status: ExceptionStatus
    closure_status: ClosureStatus
    owner_team: StableId
    owner_id: StableId | None = None
    exception_expires_at: UTCDateTime | None = None
    compensating_controls: tuple[CompensatingControl, ...] = ()
    closure_evidence: EvidenceReferences | None = None
    last_action_sequence: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_snapshot(self) -> CaseSnapshot:
        if self.case_status == CaseStatus.CLOSED and self.closure_status != ClosureStatus.VERIFIED:
            raise ValueError("closed cases require verified closure status")
        if (
            self.closure_status == ClosureStatus.PENDING_VERIFICATION
            and self.closure_evidence is None
        ):
            raise ValueError("pending closure requires verification evidence")
        if self.exception_status == ExceptionStatus.APPROVED and self.exception_expires_at is None:
            raise ValueError("approved exceptions require an expiry")
        return self


class SlaEvaluation(StrictModel):
    """Transparent deadline result derived only from supplied request timestamps."""

    policy_id: Literal["ccm.casework.sla/v1"] = "ccm.casework.sla/v1"
    evaluated_at: UTCDateTime
    due_at: UTCDateTime | None = None
    due_soon_hours: int = Field(ge=1, le=8_760)
    state: SlaState
    hours_until_due: int | None = None
    reason: NonEmpty

    @model_validator(mode="after")
    def _validate_sla(self) -> SlaEvaluation:
        if self.state == SlaState.NOT_APPLICABLE and self.hours_until_due is not None:
            raise ValueError("not_applicable SLA state must not have remaining hours")
        if self.state != SlaState.NOT_APPLICABLE and self.due_at is None:
            raise ValueError("active SLA state requires due_at")
        return self


class CaseManifest(StrictModel):
    """Sealed result containing source case, immutable action chain, snapshot, and SLA state."""

    schema_version: Literal["ccm.casework/v1"] = SCHEMA_VERSION
    manifest_id: StableId | None = None
    case: CaseOpenRequest
    events: tuple[CaseEvent, ...]
    snapshot: CaseSnapshot
    sla: SlaEvaluation
    input_hashes: tuple[str, ...]
    manifest_hash: str | None = None

    @field_validator("input_hashes", "manifest_hash")
    @classmethod
    def _validate_hashes(
        cls,
        value: tuple[str, ...] | str | None,
    ) -> tuple[str, ...] | str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return require_digest(value)
        for digest in value:
            require_digest(digest)
        return value

    @model_validator(mode="after")
    def _validate_alignment(self) -> CaseManifest:
        if (
            self.snapshot.case_id != self.case.case_id
            or self.snapshot.tenant_id != self.case.tenant_id
        ):
            raise ValueError("snapshot case and tenant must align with opening")
        sequences = tuple(event.action.sequence for event in self.events)
        if sequences != tuple(range(1, len(self.events) + 1)):
            raise ValueError("manifest events must have contiguous sequence numbers from one")
        if self.snapshot.last_action_sequence != len(self.events):
            raise ValueError("snapshot last_action_sequence must align with event count")
        return self

    def hash_projection(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json",
            exclude={"manifest_hash", "manifest_id"},
            exclude_none=True,
        )

    def computed_hash(self) -> str:
        return sha256_digest(self.hash_projection())

    def seal(self) -> CaseManifest:
        content_hash = self.computed_hash()
        return self.model_copy(
            update={
                "manifest_hash": content_hash,
                "manifest_id": stable_identifier("case_manifest", {"manifest_hash": content_hash}),
            }
        )

    def verify_integrity(self) -> bool:
        previous_hash: str | None = None
        for event in self.events:
            if not event.verify_integrity(self.case.case_id, previous_hash):
                return False
            previous_hash = event.event_hash
        return (
            self.manifest_hash is not None
            and self.manifest_id is not None
            and self.manifest_hash == self.computed_hash()
            and self.manifest_id
            == stable_identifier("case_manifest", {"manifest_hash": self.manifest_hash})
        )


class CaseworkRequest(StrictModel):
    """Input to the pure casework reducer with an explicit, supplied evaluation time."""

    schema_version: Literal["ccm.casework/v1"] = SCHEMA_VERSION
    case: CaseOpenRequest
    actions: tuple[CaseAction, ...] = ()
    evaluated_at: UTCDateTime
    due_soon_hours: int = Field(default=168, ge=1, le=8_760)

    @model_validator(mode="after")
    def _validate_request(self) -> CaseworkRequest:
        sequences = tuple(action.sequence for action in self.actions)
        if len(set(sequences)) != len(sequences):
            raise ValueError("action sequence values must be unique")
        if sequences != tuple(range(1, len(self.actions) + 1)):
            raise ValueError("actions must be ordered with contiguous sequence values from one")
        action_ids = tuple(action.action_id for action in self.actions)
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("action IDs must be unique")
        if any(action.occurred_at < self.case.opened_at for action in self.actions):
            raise ValueError("actions must not occur before case opening")
        if any(action.occurred_at > self.evaluated_at for action in self.actions):
            raise ValueError("actions must not occur after evaluated_at")
        action_times = tuple(action.occurred_at for action in self.actions)
        if action_times != tuple(sorted(action_times)):
            raise ValueError("action occurrence times must not move backward in sequence order")
        return self
