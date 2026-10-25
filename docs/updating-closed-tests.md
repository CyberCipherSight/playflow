# Update an existing closed test

An update uses the existing Play app, closed track, countries, and tester groups. Build a new version with the same application ID and registered upload key. App setup and declarations need attention again if the product's features, data practices, permissions, or Google requirements have changed.

The October 23, 2026 integration updated the existing Alpha release from code 3 to code 5, version 0.2.1. Code 4 was uploaded to an unfinished draft before full lint exposed an API-specific theme resource error. That draft was discarded, the resource corrected, and code 5 used for the corrected bundle. Uploaded version codes should be treated as consumed even if a draft is later discarded.

## Preparation

1. Inspect the actual track in Console and record the latest uploaded version codes, existing draft/review state, and intended target. A numeric Console track ID is not necessarily the API identifier.
2. Set a new, unused `versionCode` in the Android build and the intended `versionName`. PlayFlow does not silently increment arbitrary Gradle expressions.
3. Review changes to the app's behavior and declarations. Update `release_notes` in the private manifest.
4. Run full appropriate checks **before upload**. For the demonstrated native Android project:

```bash
./gradlew :app:lintDebug :app:assembleDebug :app:bundleRelease
```

From the PlayFlow manifest's working directory, reuse the registered key and select the newly signed bundle:

```bash
playflow finish-release
playflow inspect-bundle --after-version-code 42
```

Here 42 is an example of the observed previous code; supply the actual highest relevant uploaded code. This option does not query Google or reserve the next code. A debug APK is not the release AAB used by this workflow.

## Built-artifact verification

`inspect-bundle` validates the selected AAB with the official bundletool jar, dumps each base/feature manifest, checks the configured package and optional version-code floor, collects permissions and components, and strictly checks its signature against the saved upload keystore. It reports version name/code, SDK values, artifact SHA-256, certificate fingerprint, and module observations. It hashes the bundle again to reject a file changed during inspection.

Install the official [bundletool 1.18.3 release](https://github.com/google/bundletool/releases/tag/1.18.3) at `~/.cache/playflow/tools/bundletool-all-1.18.3.jar`, or provide its path using `--bundletool`. The CLI accepts only the pinned jar checksum:

```text
a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29
```

The tool does not download or execute a replacement version automatically. Java, jarsigner, the original local signing descriptor, and access to its private password file are required. This separate check is not part of lightweight `preflight`; the `console-release` workflow requires it before any browser mutation. A passed artifact check does not certify runtime behavior, data practices, or Google acceptance.

## Reusable upload and save

Open the existing track and create a new draft, or inspect the intended existing draft. Copy its actual `/tracks/<id>/releases/<id>/prepare` URL. The current helper deliberately does not invent release IDs, create tracks, discard existing drafts, or replace another bundle.

Restart `bridge-serve` after `finish-release` selects the new artifact, then load that session's newly printed temporary addon manifest. The bridge captures immutable upload bytes at startup; a previously running session still contains the old bundle.

```bash
playflow bridge-serve
```

In a second terminal, preview the explicit draft workflow:

```bash
playflow bridge-status
playflow console-release '<actual-draft-prepare-url>' --after-version-code 42
```

The preview performs local bundle/signing verification but does not connect to Firefox or change Google. Enable `approvals.allow_browser_write_actions` in the private manifest before applying:

```bash
playflow console-release '<actual-draft-prepare-url>' \
  --after-version-code 42 --apply
```

The workflow:

1. Verifies the actual artifact and checks the app URL and explicit closed-testing intent.
2. Refuses a bridge session whose captured bundle hash differs from the verified artifact.
3. Reads the intended English-language closed-release draft.
4. Refuses to modify a draft containing a different bundle.
5. Observes an already uploading bundle instead of blindly attaching it again.
6. Attaches the configured bundle once if absent, then waits for the expected version row.
7. Fills the reviewed localized release notes only when different.
8. Saves when needed, waits for the recognized acknowledgement/document transition, and handles the saved/overview dialog if shown.
9. Reopens the draft in a new document and verifies the bundle version and release notes.
10. Records `draft_verified` in the private stage journal.

The browser's displayed package/version row does not expose an independent remote SHA-256; the local verified hash is bound to captured upload bytes. An existing matching row is verified by package-scoped version identity. The helper does not claim to have read a remote hash Google does not expose through this snapshot.

This workflow requires expected English labels and a complete snapshot. Unknown, ambiguous, disabled, or truncated screens stop it. It does not automatically retry writes after timeouts. Reinspect Google before another attempt. It is not a general run/resume engine.

## Review and submit

`console-release` prepares a draft only. Use Console's Next screen to review processing results, warnings, and supported-device changes, then save to Publishing overview. Resolve actual blockers before submitting. Keep final review authorization separate.

After the user approves the prepared update, restart the bridge with the **actual** pending-change count:

```bash
playflow bridge-serve --approved-review-changes 1
```

Load the newly printed addon manifest. The permission supports singular `Submit 1 change for review` and plural counted controls, plus one uncounted confirmation, only in the selected app's Publishing overview. It does not itself click Submit, authorize production promotion, or waive the configured approval requirement. Both Python and the extension enforce the counted permission.

Observe Google's acknowledgement, then reopen Publishing overview in a new document. `Changes in review` means submitted, with possible quick checks still running. It does not mean approved or already available to testers. The existing release remains the tester release until Google accepts and publishes the update. Production access and tester opt-in requirements are separate.

The October 23 update was acknowledged as `1 change sent for review`, and a fresh page showed `Changes in review`. No production promotion, tester-group changes, or country changes were performed. New app layout, icon, and hardware behavior still need appropriate device testing; the automated verification does not substitute for it.
