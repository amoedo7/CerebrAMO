# CerebrAMO Recovery

## Scope

This procedure restores CerebrAMO repository/runtime state without changing provider credentials, authentication authority, quotas, permissions, routing policy, or external services.

## Safe recovery sequence

1. Identify the last known-good commit on `main` whose canonical AutoCheck passed.
2. Preserve the failing revision and its evidence before rollback; do not rewrite or delete history.
3. Restore only versioned CerebrAMO code/configuration from the known-good revision.
4. Do not copy provider credentials into Git. Provider authentication remains delegated to OpenCode or the currently authorized external credential store.
5. Do not infer missing quota/resource values during recovery. Any resource without a verifiable source remains `unknown`.
6. Run `bash scripts/autocheck.sh` and require its tests, syntax checks, and credential-pattern checks to pass.
7. If external providers or host telemetry cannot be reached, record those observations as `UNKNOWN`; do not convert them to PASS.
8. Integrate a recovery change only through a reviewable commit/PR with passing gates when the change affects the canonical branch.

## Rollback

If a recovery change regresses CerebrAMO, revert the recovery commit or PR using normal Git history. Do not rotate secrets, broaden scopes, disable safety checks, or modify external provider accounts as part of repository rollback.

## Boundaries

Recovery does not authorize CerebrAMO to:

- reveal, store, rotate, or manufacture provider credentials;
- purchase credits or consume paid services beyond existing authorization;
- change StoreAMO, RaizAMO, signing, distribution, or other cross-domain systems;
- claim provider, quota, telemetry, or host health that was not directly verified;
- treat a local CI PASS as proof that an external provider is operational.
