# Contributing to ccm-casework

Contributions must preserve ccm-casework as a deterministic, offline technical workflow reducer. New behavior must have strict public contracts, deterministic fixtures, unit tests, generated-schema updates, documentation, and Python 3.10 compatibility.

Do not add cloud SDKs, network clients, credentials, raw evidence, databases, background workers, wall-clock reads, schedules, AI dependencies, or assertions of compliance/certification/authorization. The package records supplied approval and verification evidence but does not validate a human identity, role, delegation, signature, or risk-acceptance authority.

Run `make release-gate` before opening a pull request. Generated fixture and schema changes must be committed deliberately. Do not weaken coverage, type, lint, formatting, or immutable-action pin requirements.
