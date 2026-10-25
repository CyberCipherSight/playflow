# Changelog

## 0.1.0a2 — 2026-10-26

- Add a first-use community contribution offer with local ask/off/review preferences. The helper is offline and never authorizes GitHub writes.
- Guide opted-in agents through independently verified, sanitized proposals, exact-diff approval, isolated forks/branches, and draft PRs for maintainer review. Authentication, app publishing permission, and opt-in alone do not authorize a submission.
- Include the contribution helper and reference in manual installs, source distributions, and standalone skill ZIPs. MIT licensing is unchanged.

## 0.1.0a1 — 2026-10-25

- Publish the first open-source prototype with standard Agent Skill files, Linux/Windows setup instructions, a portable skill-copy helper, and a clean source export with separate skill ZIP.
- Keep personal publishing state, signing material, browser sessions, and prior workspace history out of public exports. Add packaging boundary tests and a Windows CLI/skill-install smoke job; Windows live publishing remains unverified.

- Package an optional `playflow-publish` agent skill with task-specific release/platform guidance and a read-only prerequisite inventory for Linux and Windows.
- Verify existing Gradle-signed bundles using a pinned public upload certificate without importing original signing credentials. Require explicit production intent for production drafts and support verification of native uploads without lifting the bridge transport limits.
- Reject unsupported release-note locale wrappers before saving; Google can omit notes for a locale that is not enabled for the app.

- Add `inspect-bundle` with pinned local bundletool validation, base/feature manifest inspection, package/version checks, bundle hashes, and strict saved-key signature verification.
- Add `console-release` to reconcile an explicit closed-release draft, attach the selected bundle once, save reviewed notes, and verify persistence after reopening. Refuse stale bridge assets and unrelated draft bundles; observe in-flight uploads before another action.
- Support Google's singular “Submit 1 change for review” wording while retaining app/page/count scoping and one-use confirmation permissions.

- Add a private loopback Firefox bridge with app/site scoping, semantic controls, stale/expired-action rejection, and final-submit protection. Add reusable privacy-policy/ads workflows that verify persistence after reopening the page.
- Add manifest-selected release attachments with content verification and bounded transport; record public support email and per-asset AI-label intent.
- Record confirmed upload-key registrations and prevent unused-key recovery from rotating a registered identity, including after restoration of an older descriptor.

- Discover Firefox profiles from legacy registries and selectable-profile databases; open the configured Console URL in an existing profile with `open-console` or `finish-release --open-console`, without claiming form automation or verified sign-in.

- Store generated signing passwords persistently by default; add `finish-release` with verified backups, explicit recovery for never-registered keys, preservation of old keys, and local build/sign/manifest integration.

- Add local upload-key generation and standalone AAB signing with strict signature verification, certificate matching, password-file references, overwrite protection, and private password storage checks.

- Add offline listing/mobile asset readiness checks, versioned requirement sources, explicit closed-testing/country intent, and Google Groups configuration through the official API.
- Support a manifest-relative state directory for external source projects; retain Firefox profile preferences and reject unsupported live browser operations explicitly.

- Share inspection, build, policy, and publishing use cases across entry points; require final approval in pipeline commits as well as direct publishing.
- Validate manifest fields/schema and staged-rollout fractions; safely serialize generated YAML and export its JSON Schema.
- Scope package/artifact detection to the selected module and fail on ambiguous artifacts.
- Save private state atomically, record failed stages, and avoid persisting subprocess logs or raw exception messages.
- Discard validation-only Play edits and preserve cleanup behavior on failures.
- Preview recordings offline; restrict live replay navigation, enforce unique controls, handle checkbox/select changes, and stop after errors.
- Limit Firefox capture to one tab, remove whole-page text capture, strip URL queries/fragments, improve sensitive-field handling, and bound session size.
- Separate optional integrations and add CI, package/archive checks, offline regressions, architecture/contribution/security/release documentation, and dependency updates.

## 0.1.0 — Initial alpha

- Initial manifest, Android analyzer, policy gate, Gradle/ADB adapters, local stage state, Google Play edit publishing, and Firefox/Playwright recording support.
