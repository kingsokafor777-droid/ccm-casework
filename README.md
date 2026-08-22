# ccm-casework

`ccm-casework` is a **deterministic, local-first casework reducer** for technical-control exceptions, compensating-control references, remediation ownership, supplied-time SLA evaluation, approval evidence, and closure verification. It is CCM repository **#07**.

It accepts strict JSON inputs, performs no cloud collection or network activity, and returns a sealed case manifest. The same request produces the same event chain, snapshot, SLA result, and SHA-256 manifest identity.

> **Scope boundary:** ccm-casework records and validates supplied technical workflow evidence. It does not authenticate people, grant authorization, accept enterprise risk, schedule notifications, execute remediation, retain evidence payloads, or issue audit, certification, legal, or compliance-conformance conclusions.

## What it owns

| Capability | Deterministic behavior |
|---|---|
| Case opening | Binds one tenant, assessed control/version, source assessment-manifest reference, accountable owner, and optional due time. |
| Exceptions | Records requested, approved, rejected, revoked, or expired exception states only from validated supplied actions. |
| Compensating controls | Binds a typed control reference, rationale, and evidence identifiers/hashes without copying raw evidence. |
| Remediation | Tracks assigned owner, open/in-progress/blocked/resolved work state, and source-linked activity. |
| SLA evaluation | Evaluates due state against an explicit `evaluated_at` input; it has no clock, timer, scheduler, or notification side effect. |
| Approval evidence | Preserves supplied actor, decision, reason, time, and event-chain position. It does not verify identity or authority. |
| Closure | Requires submitted verification evidence and an explicit supplied verification decision before a case can close. |

## Install and run

```bash
python -m pip install ccm-casework
ccm-casework evaluate fixtures/safe-request.json --output case-manifest.json
ccm-casework validate case-manifest.json
```

For repository development:

```bash
python -m pip install -e . -r requirements-dev.txt
make release-gate
```

## Operating constraints

The package is intentionally stateless. Its deadline result is a function of the caller-supplied `evaluated_at`, not local wall-clock time. It does not use cloud credentials, database state, background workers, webhooks, or AI. Callers remain responsible for identity verification, authorization policy, notification delivery, evidence retention, risk acceptance, and operational remediation.

## Evidence and standards boundary

The design uses NIST publications as engineering context for assessment, remediation planning, monitoring, responsibility, and accountability. It does not implement an authorization-to-operate workflow or infer a formal risk decision. See [the design record](docs/design.md).

## Release integrity

The repository includes deterministic fixtures and schemas, strict Pydantic contracts, canonical JSON SHA-256 sealing, a Python 3.10–3.13 matrix, immutable-pinned CI and CodeQL workflows, and a wheel inventory check. Generated fixture/schema drift fails CI.

## Security

Use [SECURITY.md](SECURITY.md) for private vulnerability reporting. Do not include credentials, cloud payloads, personally identifying information, secrets, or live customer evidence in issues, fixtures, or pull requests.

## License

Apache-2.0. See [LICENSE](LICENSE).
