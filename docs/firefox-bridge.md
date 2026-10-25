# Existing-session Firefox automation

The live bridge is separate from the recorder and Chromium replay adapter. It uses a temporary Firefox extension to read visible semantic controls and perform explicit actions in an already signed-in browser. No WebDriver or debug-port restart is needed.

## Setup

1. Select an existing Firefox profile with `playflow firefox-profiles`. Set `browser.engine: firefox` and its profile name/path in a private manifest.
2. Open the intended app in Play Console and put its actual URL in `browser.console_url`. The URL must contain `/developers/<id>/app/<id>/`; the account's app-list URL is too broad.
3. Run `playflow bridge-serve`. It prints the path of a generated extension manifest under `~/.config/playflow/`.
4. In that Firefox profile, open `about:debugging`, choose **This Firefox**, **Load Temporary Add-on**, and select the printed `manifest.json`. Firefox removes temporary add-ons on restart.
5. In another terminal, run `playflow bridge-status` and `playflow console-inspect`. Exactly one tab must match the selected app. The bridge activates that tab to avoid background-tab timer throttling.

The generated extension and connection files contain a session token. They stay on a filesystem enforcing private file permissions; the project state stores only a locator. Do not share these files. The distributable extension's `config.js` contains no credentials. Stop the server with Ctrl+C when finished, and remove the temporary add-on in Firefox if desired.

For a Google Sites editor, explicitly add its URL with `bridge-serve --site-url <editor-url>`. Only that site's `/d/<id>/` editor is added to the session scope. Rich-text editing and file upload are not implemented through this bridge. After the user has approved publishing that site, start the session with `--allow-site-publish` to authorize up to two exact **Publish** clicks for the editor/review flow. This bounded site permission does not permit Google Play review submission, rollout, or app deletion. Without it, site publication remains blocked.

## Commands and verification

`console-inspect` returns headings, notices and visible controls with short-lived IDs. Known sensitive values are redacted. Other field values and account identifiers can still be present; inspect output before sharing it.

```bash
playflow console-action fill --control-id '<fresh-id>' --value 'https://example.com/privacy'
playflow console-action check --control-id '<fresh-id>' --value true
```

The generic operations are `inspect`, `navigate`, `click`, `fill`, `check`, and native `select`. Custom widgets may expose clickable semantic options. A fresh inspection invalidates old IDs. A successful action only establishes that the event was dispatched; verify saved values independently.

`console-setup privacy`, `console-setup ads`, and `console-setup advertising-id` preview explicit manifest facts offline. The advertising-ID workflow supports an explicit `uses_advertising_id: false`; Yes requires separate reviewed purposes and is refused before any mutation. With `--apply`, each opens the known English Console form, fills the configured value, saves if necessary, waits for the fields to become usable again, reopens it, waits for a new document, and checks persistence. Missing facts, changed labels, duplicate controls, or disabled controls stop the workflow. Existing matching values are verified without saving again. These commands do not submit the app for review.

The bridge does not ask an agent to invent missing questionnaire answers. It does not operate passwords, payment credentials, or native file selectors. Default sessions block final publishing and review controls. `approvals.allow_browser_write_actions` must be enabled for mutations; changing `require_final_submit_approval` alone does not authorize a final action.

After the user explicitly approves the prepared Play release and its pending changes, restart the bridge with `--approved-review-changes <count>`, using the actual count shown in Publishing overview. This enables one matching counted Submit/Send-for-review click on that app's `/publishing` page, followed by one uncounted confirmation if Google shows one. Other counts/pages, repeated counted submission, rollout and deletion stay blocked. The permission expires when consumed or the session stops; never enable it before obtaining the user's approval or after the prepared changes have changed. Inspect the resulting status before any further action. Default sessions do not permit review submission.

## Release attachments

At startup, the bridge captures only the explicit `build.aab_path`, icon, feature graphic, and phone screenshots from the manifest. Relative file paths resolve against the Android project. It validates image encoding/AAB structure and keeps immutable copies with SHA-256 hashes in memory. `bridge-status` lists their asset IDs, filenames, sizes, and hashes, without file contents or local paths. Restart the bridge after changing an asset or selecting a new bundle.

```bash
playflow console-inspect  # Locate the intended file input, including hidden uploader inputs.
playflow console-attach icon '<fresh-file-control-id>'
playflow console-attach feature_graphic '<fresh-file-control-id>'
playflow console-attach phone_screenshots.0 '<fresh-file-control-id>'
playflow console-attach bundle '<fresh-file-control-id>'
```

This is a separate operation from generic field filling. The extension checks the content hash, creates a browser File, and emits the upload input events. Arbitrary local paths, signing keys, and account credentials cannot be selected through this command; only captured asset IDs are accepted. Attachments are restricted to the selected Play Console app, never the Sites editor. The initial bridge transport supports files up to 16 MiB and a total of 64 MiB per session; these are implementation limits, not Google Play limits. Larger bundles need a future streaming adapter or the official API.

An attachment response means the browser received the file. Wait for Console's upload/processing result, check that the correct asset or version appears, save the form, and verify persistence separately. No release is submitted by attaching a bundle.

## Failure recovery

Never blindly repeat a timed-out mutation. Its result may be unknown: inspect the current page, reload the saved declaration if appropriate, and reconcile the value before acting again. The server expires queued commands and requires inspection after an unknown outcome. It does not retry writes.

After a browser restart, reload the temporary add-on. After a server restart, load the newly printed manifest; an old extension has an obsolete token. If the server was killed without cleanup, verify that it has stopped before removing its `browser-bridge.json` locator and starting a new session. Keep only one bridge writer per manifest.

The server binds to loopback, authenticates every request, checks Host/Origin, and scopes targets to the chosen app and explicitly selected site. Firefox's extension host permissions are broader than the configured app path, so both the Python server and extension enforce that narrower path. Routing metadata such as `?source=dashboard` is allowed on returned pages without widening the scope.
