---
name: playflow-publish
description: Prepare, upload, and verify Android Google Play releases using PlayFlow and the developer's authenticated browser. Use for first submissions or updates to a specified testing or production track; installation alone does not authorize publication.
license: MIT
---

# PlayFlow publishing

Use the installed PlayFlow CLI for deterministic preparation and verification, and the agent for missing facts, changed Console screens, and exceptions. Target Linux and Windows; Linux has live integration evidence, while Windows still needs complete release testing. macOS is outside the current product scope.

## Establish the intended release

Identify the source folder, exact application ID, intended track, and whether the user wants a draft, review submission, or publication. For multiple apps, keep separate manifests, journals, artifact hashes, and outcomes. Preserve existing authorization; ask only where scope or essential facts remain unresolved.

Run `scripts/doctor.py --project <source-folder>` with Python, then `playflow --help`. The helper only reports prerequisites; it does not install software or read signing credentials. If PlayFlow is missing, install from the user's chosen trusted checkout/release, not an assumed package-index name. This skill contains instructions, not the publishing engine.

Resolve helper and reference paths relative to this skill's installed directory, not the Android project's working directory. Read [references/setup.md](references/setup.md) for first-time setup or a missing engine/bridge. No agent-specific tool names or shell substitutions are required by the shared workflow.

Use a private per-app manifest. Read its existing facts before asking questions. Inspect the actual Console application and latest relevant uploaded versions. Do not guess application identity from a folder name, namespace, display name, or another app's open tab. Match package names exactly, including case.

For execution details, read [references/releases.md](references/releases.md). Read [references/platforms.md](references/platforms.md) only for installation, paths, shell differences, or browser bootstrap problems.

## Prepare and verify

- Treat source analysis as hints and the selected built artifact as build evidence. Developer statements, inferred facts, and remote observations have different authority. Never silently turn an inference into a privacy, audience, ads, or access declaration.
- Check the current source project's local instructions. Preserve registered upload keys and existing Gradle signing configuration. Never generate or recover a key merely because an already-published app's credentials are inconvenient.
- Run appropriate project tests and analysis before upload. Choose a new unused version code from observed Play versions; do not assume the local version is newer. Retain build logs privately and stop on actual failures.
- Native Android unsigned bundles can use `finish-release`. Flutter uses `flutter build appbundle --release`, retaining its existing signing setup. Do not run a standalone signer over an already-signed Flutter bundle.
- Verify the selected AAB with `inspect-bundle`, including actual package/version, modules, permissions, hash, and certificate. For existing Gradle signing, use the pinned public certificate option rather than importing passwords. Compare with a known upload certificate where available; distinguish a local certificate observation from Google-confirmed acceptance.
- Revisit declarations when features, dependencies, data handling, or permissions change. Existing production status does not prove a new build needs no additional declarations.

## Execute within the selected browser scope

Use `firefox-profiles` and `open-console` for the selected existing profile. Load the temporary bridge addon printed by `bridge-serve`. Keep exactly one tab matching each configured app target. Do not export cookies, automate passwords, enable generic JavaScript execution, or widen scope to the entire browser.

Inspect semantic controls, act with fresh IDs, and independently verify saved remote state. Reinspect after navigation or ambiguity. A click, disabled button, received file, or timeout is not proof of persistence. Reusable declaration workflows are privacy, ads, and the reviewed no-advertising-ID branch; other questionnaire branches still require supervised execution.

For an explicit draft, use `console-release` with the intended track kind. Production requires explicit production intent in the manifest and `--track-kind production`. The helper never creates a track, discards another draft, promotes a release, or submits for review.

The bridge's attachment limit is 16 MiB per file and 64 MiB per session. Larger bundles use an authorized official API path or the browser's native picker for the exact verified AAB. After a native upload, `console-release --native-uploaded` verifies the expected version row and saves notes; it never attaches a missing file in this mode. Do not raise transport limits as a shortcut. The Console snapshot does not expose a remote hash: report version-row verification separately from local hash verification.

## Finish and report

Review errors, warnings, target countries, retained versions, rollout settings, and managed publishing. Preserve unrelated production settings. Honor any final approval already given for the actual prepared app/track/action. If approval is still required, show the concrete version, artifact hash, target, pending changes, and release consequence once before asking.

Only after authorization, start a bounded `--approved-review-changes <actual-count>` session. Use the fresh counted Submit/Send control and its confirmation. This permission does not authorize a separate production promotion or unrelated app changes.

After a timeout or crash, inspect Google before deciding on another mutation; do not retry writes blindly. The local stage journal does not implement general automatic resume.

Verify consequential changes in a fresh browser document and save private evidence. Distinguish draft saved, submitted, in review, approved, and available to users. Report each app separately, including blockers and what was verified. Skill installation does not start a background watcher, grant browser access, or schedule releases.
