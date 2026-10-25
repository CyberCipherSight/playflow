# Roadmap

The current foundation is a small installable Python package with separate CLI, workflow use cases, local/remote adapters, and a standalone recorder. Keep that layout as the project grows.

## Current scope

- Versioned, validated YAML manifest and generated editor schema.
- Conservative module-scoped source analysis and explicit policy questions.
- Gradle build, unambiguous artifact selection, optional ADB install.
- Shared publish gates, API validation/commit/discard, staged-release fraction.
- Private atomic stage journal, manual browser sign-in, sanitized recording and restricted replay.
- Offline listing/mobile asset readiness checks and a versioned requirements subset.
- Closed-testing intent and Google Groups merge/validation/commit through the official API. Reusable country setup remains pending.
- Authenticated, app-scoped Firefox session bridge with semantic controls and explicit privacy-policy/ads/no-advertising-ID save-and-verify workflows. Full questionnaire automation remains pending.
- Explicit manifest-selected image/AAB attachments through the bridge, with immutable captured bytes, content hashes, narrow file-input handling and documented size limits.
- Offline regression suite, CI, source/wheel verification, contributor and security guidance.

## Next milestones

1. Validate against a developer-owned internal test app: actual Gradle/AGP variants, ADB, service-account authorization, Firefox capture, browser controls, and API failures. Add sanitized integration fixtures and record supported versions.
2. Verify built artifact identity: extract package/version and merged permissions from the actual AAB/APK before upload. Source scanning remains advisory. Add custom module-directory mappings only with a clear manifest contract.
3. Build reusable listing/asset workflows above the generic Firefox controls and attachment transport, and add official API listing uploads with shared approval boundaries.
4. Compile multiple sanitized recordings into explicit Console screen/action workflows with reviewed developer facts. Avoid distributing account-specific recordings or fragile page-wide selectors.
5. Introduce versioned per-run state, input/artifact fingerprints, concurrency control, and remote reconciliation before adding automatic resume. Never skip publishing based solely on a prior `done` entry.
6. Expand publishing to retained version codes, existing-release promotion/halting, and multiple releases. Keep track mutations explicit and reviewable.

Release/version automation, public package publication, and broader OS support should follow verified integration behavior and a real repository identity. There is no automatic deployment or release on pushes to the default branch.
