# Supervised store-listing updates

Use this guide when a developer asks to change an existing Google Play listing. The CLI does not yet provide a deterministic end-to-end listing editor: the agent observes and operates the Console through the app-scoped Firefox bridge. An existing listing can be updated without building or uploading an AAB. Keep each app's manifest, scope, observations and outcome separate.

## Prepare accurate changes

1. Match the exact application ID in the selected Console app. Inspect the current default or requested localized listing and note its text, assets and pending changes before editing. Do not overwrite another draft without resolving conflicts.
2. Check the production or relevant track version and compare proposed claims with the shipped app and reliable developer statements. Source code, old notes, developer statements and observed behavior are different kinds of evidence. Avoid promises of universal compatibility, continuous real-time updates, privacy, encryption, no advertising, open-source availability or performance without support. Describe availability and limitations accurately.
3. Use the user's existing research when provided. Check current [Google Play listing field limits](https://support.google.com/googleplay/android-developer/answer/9859152), [metadata guidance](https://support.google.com/googleplay/android-developer/answer/13393723), and [visual asset requirements](https://support.google.com/googleplay/android-developer/answer/9866151) when relevant. Keep names recognizable, describe the main job naturally and avoid keyword stuffing or implied affiliation. Preserve an existing name unless changing it is within the request.
4. Prepare the exact title, short and full descriptions in the selected locale, and count characters. Make only requested changes; preserve existing screenshots and visual assets unless replacing them is in scope. Do not claim an app feature before it is available in the relevant build.

## Apply and verify

- Connect the selected signed-in Firefox profile with a bridge scoped to the exact app. Use fresh semantic controls, re-inspect after navigation and stop when controls are ambiguous. If the UI changes, investigate rather than guessing or reusing coordinates across sessions.
- Select only explicitly prepared assets. Review asset provenance and apply Google Play's individual AI-asset declaration if required. A file upload or thumbnail alone does not prove the listing has saved the asset.
- Review the resulting fields and retained assets. Save to Publishing overview when the user requests a listing update, or save a draft when requested. Wait for an acknowledgement; a disabled Save button may mean an in-flight operation rather than success.
- Reopen the listing in a fresh document and compare each intended field and asset with the prepared result. If the action times out or the browser disconnects, inspect remote state before any retry. Do not repeat a mutation blindly.

## Review and publication

Inspect Publishing overview and the full pending change set for this app before submission. Confirm the changes are exactly those authorized; an unrelated pending release or another developer's draft must not be swept into a counted submission. Observe managed-publishing status and preserve existing settings.

Respect existing explicit authorization and the app's approval policy. The counted review-submit bridge permission only authorizes the matching pending set; it does not authorize a separate Publish action. User authorization to publish the reviewed listing may cover that separate action, but never assume it covers unrelated ready changes. Reinspect the ready-to-publish set before a consequential action, and stop if it is mixed or ambiguous.

Distinguish saved draft, saved pending changes, queued for quick checks, in review, approved and ready to publish, and actually published. Console headings can show “in review” while quick checks are still running; report both observations when present. Managed publishing may require a separate publish action after approval. Verify in a fresh document after any submission or publication and, when possible, independently verify the public listing. A skill does not monitor review in the background or schedule the publish step.

Keep account identifiers, private paths, credentials, screenshots, actual listing text and app-specific facts out of public contribution examples unless the developer explicitly authorizes sharing them. Report the exact status separately for each app.
