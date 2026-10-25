# Security policy

PlayFlow is an early-alpha local automation tool. Security fixes target the current development version; no older release branches currently receive separate maintenance.

## Report a vulnerability

If the hosted repository enables private vulnerability reporting, use its Security → Report a vulnerability action. Otherwise use the hosting platform's private abuse/security reporting channel or a maintainer's listed private contact. Do not publish exploit details, credentials, or private recordings in public issues. Maintainers must enable a private reporting route before announcing a public release; see [the release guide](docs/releasing.md).

## Trust boundaries

- Android repositories, Gradle wrappers, and build scripts are executable code. Run PlayFlow only against projects you trust.
- Service-account keys are referenced by an environment variable and should live outside the repository. Restrict account permissions to the intended application/workflow.
- Human sign-in takes place in the chosen browser: a dedicated Chromium profile for that adapter or the existing Firefox profile for the scoped live bridge. PlayFlow does not export cookies or ask an agent to handle passwords, passkeys, or OTPs.
- Browser profiles, `.playflow/`, local manifests, recordings, and signing keys are private. The ignore rules reduce accidental commits; they do not inspect arbitrary renamed secret files.
- The Firefox recorder reads semantic controls while enabled. It does not read cookies or browser storage, omits whole-document text, strips URL queries/fragments, and redacts known password/file/secret-like fields and autocomplete hints. Redaction is heuristic: ordinary form values and URL path account IDs can remain. Review exports before sharing.
- Offline replay previews do not open a browser. Live replay requires both the manifest flag and `--allow-write`, restricts navigation to Play Console, skips known sensitive values, and stops on the first failed/ambiguous action. It is not a sandbox for hostile recordings.
- API validation creates an edit and uploads to Google even without `--commit`. The edit is deleted after validation; a failed commit response can leave an uncertain remote outcome.
- Final commit requires the configured approval through the shared workflow. Disabling that setting is an explicit opt-in to unattended commits.
- State saves are atomic and private on POSIX; raw subprocess logs and error messages are not persisted. State contains project/artifact paths, inferred facts, and API result metadata, and should still be treated as private.

Policy checks cover only the implemented declaration questions; they do not certify Google Play policy compliance. SDK behavior, Data safety, audience, privacy, and account-access/deletion declarations still require human review.
