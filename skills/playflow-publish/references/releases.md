# Release execution reference

Use the installed command's `--help` when options differ. This reference describes the accompanying PlayFlow source, not every historical release.

## Per-app configuration

Use `playflow init` only for a new manifest. Existing manifests and signing identities take precedence. A Flutter manifest can set `project_dir` to its `android/` directory for Gradle inspection, while `build.aab_path` explicitly points to the signed bundle under the Flutter source root's `build/app/outputs/bundle/release/` directory. Build Flutter from its source root, not from the Android subdirectory.

Existing production updates use `play.default_track: production`, omit `testing`, and preserve current country settings. Closed updates use `testing.mode: closed` plus the intended groups/countries. A Console numeric track ID is not proof of the official API track identifier.

## Build and artifact verification

For Flutter, run its tests and analyzer, then build the release with the chosen version:

```text
flutter test
flutter analyze
flutter build appbundle --release --build-name <version-name> --build-number <new-code>
```

Respect local instructions protecting signing or runtime code. Missing production signing material is a blocker; a debug-key fallback is not an acceptable upload identity for a published app.

Select the exact signed output in the private manifest. PlayFlow expects a locally installed official bundletool 1.18.3 jar, pinned by checksum, plus Java/JDK tools. Use:

```text
playflow inspect-bundle --manifest <manifest> --after-version-code <previous-uploaded-code>
```

If the app already has Gradle signing and no PlayFlow upload-key descriptor, add `--certificate-sha256 <full-expected-upload-fingerprint>`. This verifies with the public certificate and an ephemeral public truststore without reading or copying the original signing password. A locally observed certificate must still match the registered Play upload certificate; Google acceptance is separate evidence.

## Browser draft

Start `bridge-serve --manifest <manifest>` with the actual app URL. Temporary addons are removed by browser restarts; server restarts require loading the newly printed manifest. For oversized native uploads, launch a separate browser-only manifest with the same app and state directory but no AAB selected, before selecting the real artifact in the client manifest. This intentionally keeps the server's attachment list empty; the native picker is the upload path.

Create or select the intended draft after observing existing releases. Do not discard another draft merely to obtain an enabled Create button. Copy the actual prepare URL rather than inventing a release ID.

```text
playflow console-release <actual-prepare-url> --manifest <manifest> --after-version-code <previous-code>
```

For production, add `--track-kind production`. For existing Gradle signing, add `--certificate-sha256`. Preview performs local inspection without browser changes. Add `--apply` to upload/save/verify the draft.

Read the existing release-note locale wrappers before choosing manifest languages. Do not assume `en-US`: an existing app can use `en-GB` or other locales. Unsupported wrappers can be discarded by Console. The helper stops on mismatches; reuse enabled locales or obtain explicit direction to change the listing's languages separately.

For native uploads, first select the exact verified file through a trusted browser gesture and native picker. Confirm processing succeeded and the expected version appears, then add `--native-uploaded --apply`. This mode checks the app-scoped version row, refuses a different/missing bundle, saves reviewed notes, and verifies after reopening. It does not compare a Google-provided remote hash, because that hash is not exposed in the snapshot.

If the UI labels differ, stop the deterministic workflow and inspect. Use scoped primitives or a native interaction only where needed, then preserve a sanitized compatibility observation. Never turn a single screen coordinate into a global selector.

## Review and final submission

Click Next, inspect actual release errors/warnings and supported-device changes, and review the configured rollout. Save to Publishing overview when appropriate. A Publish or Start rollout control can have an immediate effect and needs authorization for that action; the default bridge blocks it.

For the reviewed pending-change set, `bridge-serve --approved-review-changes <count>` permits one matching counted Submit/Send action and one uncounted confirmation in that app's Publishing overview. Reload the newly generated addon, submit once, and observe acknowledgement plus a fresh-document status. Singular `1 change` and plural `changes` are supported. A changed count or release state needs reconciliation, not a larger permission.

The official API adapter is optional and requires a pre-existing app, correct track ID, authorized service account, and supported operation. API validation uploads to Google even without commit. Never label it an offline dry run. Live service-account publishing still needs separate integration validation; browser submission evidence does not prove API permissions.
