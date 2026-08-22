# ccm-casework design record

## Purpose and boundary

`ccm-casework` is the CCM program’s deterministic workflow layer for **supplied** technical-control casework. It turns a strictly typed case-opening record plus an ordered action sequence into an append-only hash-linked event history, current workflow snapshot, supplied-time SLA evaluation, and sealed manifest. It is deliberately a library and file-only CLI, not a hosted GRC product.

NIST’s RMF distinguishes assessment, authorization, and monitoring: assessment determines whether controls are implemented and operating as intended; authorization is a senior official’s risk-based decision; monitoring continually observes control implementation and risk.[1] The reducer therefore preserves assessment-linked workflow evidence while refusing to infer authorization, risk acceptance, certification, or framework conformance.

| In scope | Explicitly out of scope |
|---|---|
| Exception request/decision/revocation evidence | Identity authentication or approver-authority verification |
| Compensating-control references with evidence hashes | Determining whether a compensating control is effective |
| Owner and remediation-state tracking | Executing remediation, opening tickets, or sending notifications |
| Deadline evaluation from supplied time | Background clocks, schedulers, service-level enforcement, or escalation |
| Closure submission and independently supplied decision | Declaring a control compliant, granting risk acceptance, or closing an audit |
| Canonical hash chaining and sealed exports | Storing raw evidence payloads, credentials, secrets, or customer data |

## Reference rationale

SP 800-53A describes customizable control-assessment procedures and guidance for analyzing assessment results in support of organizational risk-management processes.[2] SP 800-37 identifies plans of action and milestones among the RMF concepts and describes responsibility/accountability for implemented controls.[1] SP 800-137 frames continuous monitoring as visibility into assets, threats, vulnerabilities, and control effectiveness that provides information to respond to risk in a timely manner.[3]

These sources justify an engineering model that carries assessment provenance, assigned work, remediation evidence, and review events. They do **not** make this package an implementation of RMF authorization or a decision authority. The caller is responsible for policy, identities, delegation, signatures, retention, and human decision validity.

## Input model

A `CaseOpenRequest` binds a stable case identifier to exactly one tenant, source assessment-manifest digest, source control/version, assessed status/risk, owner team, optional owner, opening time, optional due time, and source evidence references. A `CaseAction` is an ordered, typed record with an actor, occurrence time, and only the fields permitted for its kind. Raw evidence is never accepted; only stable evidence identifiers and lower-case `sha256:<hex>` digests are permitted.

The `CaseworkRequest` supplies `evaluated_at`. It is part of the request and is the only time used by SLA logic. No operation reads wall-clock state.

## Deterministic reducer rules

| Action | Preconditions | Reducer effect |
|---|---|---|
| `assign_remediation` | Case is not terminal | Changes accountable owner. |
| `set_remediation_status` | Case is not terminal | Sets `open`, `in_progress`, `blocked`, or `resolved`. |
| `request_exception` | Case is not closed/rejected | Opens a pending exception with bounded expiry and justification. |
| `decide_exception` | A pending exception exists | Moves it to approved or rejected using supplied decision evidence. |
| `add_compensating_control` | An exception is pending or active | Appends a typed reference and evidence hashes. |
| `revoke_exception` | An approved exception exists | Revokes the active exception; it does not close remediation. |
| `submit_closure` | Remediation is resolved and no active exception exists | Stores verification-evidence references and waits for review. |
| `verify_closure` | Closure is pending | A supplied `verified` decision closes the case; a `rejected` decision reopens remediation. |
| `reopen_case` | Case is closed or rejected | Returns the workflow to active remediation. |

Invalid action order, duplicate sequence numbers, missing action-specific fields, mismatched evidence identifier/hash cardinality, unbounded exceptions, and attempts to close without verification evidence fail validation. The reducer never treats missing evidence, unavailable evidence, or an expired exception as a pass.

## SLA evaluation

SLA evaluation is a transparent derived signal. If no due time exists, the result is `not_applicable`. If the case is closed, the result is `not_applicable`. Otherwise the reducer compares caller-supplied `evaluated_at` to caller-supplied `due_at`; it reports `within_sla`, `due_soon`, or `overdue` using an explicit policy window. The default `due_soon_hours` is 168 (seven days), but it is present in the request and sealed into the manifest.

An approved exception does not erase the original assessment or alter SLA logic by itself. An expired exception is reported explicitly and does not produce a closure or pass condition. A deployer may use these outputs to create notifications or escalations, but that execution is outside this package.

## Integrity and compatibility

All artifacts use `ccm-jcs/v1`: UTF-8 canonical JSON, deterministic UTF-16 object-key ordering, I-JSON-safe integers, and lower-case SHA-256 digests. Action event hashes include the case identifier, sequence, action projection, and the prior event hash. A sealed `CaseManifest` includes the final snapshot, action chain, all input hashes, and a deterministic `case_manifest_<digest>` identifier.

The package operates without a runtime dependency on other CCM packages. Its source links are compatible by convention with ccm-core and ccm-assessor identifiers and hashes. Cross-package verification remains an integration responsibility until a separately versioned adapter is introduced.

## Non-negotiable rules

1. No cloud calls, credentials, network access, database state, scheduler, wall-clock state, or AI is permitted in runtime behavior or tests.
2. No raw evidence payload, token, secret, personal data, or customer data belongs in fixtures or manifests.
3. Approval events are evidence records, not identity verification or authority determination.
4. Closure requires both submitted verification evidence and an explicit verification decision; neither an exception nor a resolved remediation alone may close a case.
5. Framework references document design context only; this package does not certify, attest, authorize, or declare compliance.

## References

[1] [NIST SP 800-37 Rev. 2 — Risk Management Framework](https://csrc.nist.gov/pubs/sp/800/37/r2/final)

[2] [NIST SP 800-53A Rev. 5 — Assessing Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/a/r5/final)

[3] [NIST SP 800-137 — Information Security Continuous Monitoring](https://csrc.nist.gov/pubs/sp/800/137/final)
