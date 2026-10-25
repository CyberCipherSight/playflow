# Integration evidence

Verified on October 18, 2026 against a developer-owned Android utility and its own Play Console draft. No account identifiers, credentials, private manifests, or browser recordings belong in this document.

| Component | Observed result |
| --- | --- |
| Android build | JDK 17, Gradle 8.13, AGP 8.11.1, Kotlin 2.2.21; compile/target API 36; debug APK, release bundle and debug lint passed |
| Emulator | API 36.1; real UI captures and offline privacy dialog checked; no physical infrared transmitter available |
| Bundle | Signed with the existing local upload key; strict signature verification and bundletool 1.18.3 validation passed; package/version/permissions inspected from the actual bundle |
| Firefox | Firefox 157, an existing signed-in profile, temporary add-on, authenticated loopback bridge |
| Console forms | Saved privacy, access, ads, content rating, target age, Data safety, government, financial, health, category/contact, listing and advertising-ID declarations |
| Store assets | PNG icon, feature graphic and two genuine phone captures attached; listing reopened to verify persistence; individual AI-label declaration completed |
| Closed testing | All available country rows including Rest of world selected; two Google Groups saved and checked after reload |
| Release | Bundle accepted and notes saved; after explicit developer approval, 15 changes submitted and “Changes in review” verified in a new browser document |
| Google Sites | Privacy page published, then contact email updated; unauthenticated public HTTP response checked |

These observations establish one working supervised path. Only privacy-policy, ads and the no-advertising-ID branch currently have reusable `console-setup` workflows. Other forms still require a controller to inspect and act through the bridge, with occasional desktop interaction for widgets that need native keyboard input. The recorder is separate. Rich-text editing in Sites is not implemented through the live bridge.

Live use exposed several conditions covered by regressions or documented boundaries:

- Console adds routing metadata such as `?source=dashboard`; it must not widen the selected app scope.
- Background-tab timers can delay action responses; the bridge activates its selected tab.
- Navigation must replace the document before persistence verification.
- A disabled Save button can represent an in-flight save. Wait for a positive acknowledgement and handle the saved/overview dialog before reopening.
- Google can require an advertising-ID declaration only after the first bundle is uploaded. No ads does not by itself establish no advertising-ID use; inspect SDKs and the merged bundle permissions.
- Optional Play automatic protection requires minimum SDK 24. The tested app retained minimum SDK 23 by turning off its installer check; Play App Signing remained on. This is an app-specific choice, not an automatic default for other projects. See Google's [protection documentation](https://support.google.com/googleplay/android-developer/answer/10183279).
- The unobfuscated test build produced a non-blocking deobfuscation-file warning. It did not have an R8 mapping file to upload.

The official Publisher API adapters have offline coverage but were not exercised with live service-account credentials in this integration. Actual track identifiers must still be resolved before API use. General OS/browser compatibility, other questionnaire branches, physical IR behavior, final review outcomes and production rollout remain outside this evidence.

## Existing-track update: October 23, 2026

The modified Android app was rebuilt and signed with the same registered upload key. Full lint exposed an API-27 theme attribute in unqualified resources; it was moved to versioned resources while preserving minimum SDK 23. The corrected release used a fresh version code after the initial uploaded draft was discarded. Debug lint, debug assembly, release bundle, pinned bundletool validation, actual manifest inspection and strict signature verification passed.

The new `console-release` workflow filled notes, saved, and reopened the existing closed draft to verify the selected version. Publishing overview contained one closed-track change. Google's singular Submit wording prompted a bounded compatibility fix with Python and JavaScript regressions. Submission was acknowledged and its in-review state checked after reopening. Google approval, new-version availability, physical-device behavior and service-account API publishing were not established by these checks. See [the update guide](updating-closed-tests.md).

## Existing production updates: October 24, 2026

Two Flutter applications were tested through supervised production-update preparation on Linux with the existing authenticated Firefox profile. Flutter tests and analyzer passed for each app. Their release AABs were built using the apps' existing Gradle upload keys, then inspected using pinned bundletool and strict public-certificate verification. No original signing passwords were copied into PlayFlow.

Both bundles exceeded the bridge's 16 MiB attachment limit, so the verified local files were selected through the native file picker. The production draft helper verified the expected app-scoped version row, saved release notes in the app's enabled locale, and reopened the draft. Google did not expose a remote artifact hash through the semantic snapshot; local hash evidence and remote version-row evidence remain distinct.

One update was submitted after explicit review approval. A fresh document confirmed in-review state. Google subsequently approved it; following separate developer authorization, the single approved production change was published. A separate production-track page confirmed Active and the expected latest release, with the existing country coverage retained. This establishes one supervised production rollout, not general browser or API compatibility.

The second update required an installation-permission declaration and an accessible reviewer demo. A real received-APK installation flow was recorded in an isolated emulator and, with authorization, uploaded as an unlisted video. Saved declaration text and URL were verified after reload, and YouTube's persisted Unlisted visibility was checked separately. Demo creation and upload were supervised native interactions, not a reusable built-in video-publishing workflow.

That app's final review submission remained blocked by Google's “Incomplete advertising ID declaration” issue despite a saved No answer and no AD_ID permission in the new inspected bundle. The run was paused at the developer's request. It must not be reported as submitted or published. This is a useful example of why saved form values and release validation are separate evidence.
