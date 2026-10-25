# PlayFlow — Google Play Console automation for AI agents

PlayFlow is an open-source **Google Play publishing automation CLI and Agent Skill** for Android developers. It helps an AI coding agent prepare signed Android App Bundles (AABs), update Google Play Console releases, configure testing, and verify saved changes using a scoped connection to your signed-in Firefox browser.

**Prototype / early alpha:** supervised Linux submissions and a production rollout have been verified. Windows is a development target, not yet verified end to end. Chrome, Brave, Edge, automatic recovery, and universal agent compatibility are not currently supported claims. This project is independent of Google.

Start with the [installation and first-release guide](docs/getting-started.md). For agent installation, workflow boundaries, and compatibility, read [using PlayFlow as an Agent Skill](docs/agent-skill.md).

```text
Developer → AI agent + skill → PlayFlow CLI → Firefox bridge / Play API
                                      ← verified results and local evidence
```

PlayFlow is a Python CLI for inspecting Android projects, checking explicit developer declarations, building release bundles, and publishing through the Google Play Developer API. A scoped Firefox bridge controls the existing signed-in session. A separate recorder and optional Playwright adapter support learning Console workflows.

**Status: early alpha.** The build/API pipeline and scoped Firefox bridge are implemented; complete reusable Console onboarding remains in progress. Source inspection provides hints rather than proof of policy compliance. Listing text and assets can be validated locally, then filled/attached through supervised browser actions. Google Groups can be merged into an existing closed test track through the API.

Current platform targets are **Linux and Windows**. Linux has live submission evidence; full Windows release and credential-security validation remains pending. macOS is outside the current scope.

The optional [PlayFlow agent skill](skills/playflow-publish/SKILL.md) teaches an agent to use this CLI, select the actual app/track, reuse reviewed facts, handle native uploads and exceptions, and verify saved results. Install it using the [skill guide](docs/agent-skill.md), then install the PlayFlow engine separately from this trusted source. Skill installation does not grant account access, start a background process, or authorize publication. Its read-only `scripts/doctor.py --project <path>` inventories prerequisites. The skill is included in source distributions; installing the wheel does not install a skill into an agent.

To install the instructions through the third-party [skills CLI](https://github.com/vercel-labs/skills):

```text
npx skills add CyberCipherSight/playflow --skill playflow-publish
```

Then [install the engine and connect Firefox](docs/getting-started.md). Start with a supervised draft on your own app. A typical request is: “Use PlayFlow to prepare an update for this Android project in its existing closed testing track.”

## Common questions

**Is this a skill or a command-line tool?** Both. The standard skill guides the AI agent; the Python CLI and scoped browser bridge execute and verify operations. The engine remains usable without the skill.

**Does it automate Google Play Console updates?** It supports release preparation and selected deterministic Console workflows, plus supervised handling of other forms. Real first-submission, closed-testing update, and production-rollout evidence are documented in [integration notes](docs/integration-notes.md). A single command that completes every possible questionnaire unattended is not available.

**Can any AI agent use it?** The instructions use the open Agent Skills format. Execution requires local files, terminal access, compatible Android tools, and the selected browser connection. Individual agent/OS combinations still need testing; model names alone do not establish compatibility.

**Does it need my Google password or upload key in GitHub?** No. You sign in through your own browser. Existing signing identity remains local. Public source excludes personal manifests, credentials, runtime journals, and browser profiles.

**Can I update an app already in production?** Yes, through an explicitly selected production draft and reviewed final action. Preserve its registered upload key and use a new unused version code. Google review and managed publishing are distinct stages.

## Get started

Requires Python 3.11+. Builds require your Android project's Gradle wrapper, a compatible JDK, and Android SDK. ADB is needed only for device installation. Linux is the primary development platform; other platforms have not been verified end to end.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
playflow --help
```

The base installation supports configuration, inspection, policy checks, builds, state, and offline recording previews. Install integrations only when needed:

```bash
python -m pip install -e '.[browser,publish]'
python -m playwright install chromium
```

On Arch Linux, `scripts/install-arch.sh` installs all integrations and development tools into a local virtual environment. Install a JDK suitable for the Android project's Gradle/AGP version, the Android SDK, and optionally `android-tools` separately.

From your Android project's root:

```bash
playflow init --app-name "My App"
# Edit play-manifest.yaml; see examples/play-manifest.yaml.
playflow inspect
playflow policy-check
playflow build
playflow state
playflow preflight
```

Use `--manifest /path/to/play-manifest.yaml` on commands when working from another directory. `project_dir` resolves relative to that manifest, artifact paths resolve relative to the Android project, and the browser profile path resolves on the local machine.

## Manifest and build selection

```yaml
schema_version: 1
app_name: My App
project_dir: .
build:
  module: app
  gradle_task: bundleRelease
  # Set this when multiple variants exist:
  aab_path: app/build/outputs/bundle/release/app-release.aab
play:
  package_name: com.example.app
  default_track: internal
  release_status: draft
```

`module: app` with `gradle_task: bundleRelease` executes `:app:bundleRelease`. Nested Gradle modules use `mobile:app` and the matching `mobile/app` directory. An absolute Gradle task such as `:app:bundleProdRelease` is used as supplied. Custom Gradle project-directory mappings are not currently supported by automatic inspection.

The manifest rejects unknown fields and unsupported schema versions. Its generated [JSON Schema](schemas/play-manifest.schema.json) supports editor validation. Preserve `schema_version: 1`; incompatible future formats must have an explicit migration.

Artifact discovery searches only the selected module. If multiple AABs/APKs exist, set the artifact path explicitly. PlayFlow does not choose the most recently modified file across unrelated modules. For flavored, suffixed, or dynamic application IDs, set `play.package_name` for the actual built variant.

## Preparation and closed testing

`playflow preflight` checks listing lengths, icon/feature graphic/phone screenshot formats and dimensions, AAB availability, unresolved declarations, and test setup. It runs offline and exits 2 while missing inputs or manual verification steps remain. It does not certify completed Console questionnaires or validate bundle signatures.

Use [the closed-testing example](examples/closed-testing.yaml) for Google Groups and country intent:

```bash
playflow testing-plan
playflow configure-testers           # API validation edit, then discard
playflow configure-testers --commit  # configured approval, then commit
```

Tester updates merge existing Google Groups. Country availability still requires a Console workflow. Set the actual closed track identifier in `play.default_track`; leave it null during preparation when unknown. `repository_url` stores project context, and optional `state_dir` relocates the journal relative to the manifest. Full details and authoritative rule sources are in [the readiness guide](docs/readiness.md).

## Release signing

For repeat uploads to an existing closed track, see [updating a closed test](docs/updating-closed-tests.md). `inspect-bundle` verifies the actual selected signed bundle; `console-release` can attach it, fill notes, save, and verify an explicitly selected draft. Final review submission remains a separate approved action.

If you already built an unsigned release AAB, PlayFlow can sign it without Gradle:

```bash
playflow signing-init
playflow sign-bundle --aab /path/to/app-release.aab
```

Key initialization runs once and refuses existing signing files. The signer preserves the input, signs a copy, and strictly verifies it. Keep the upload key and generated password backed up outside Git; choose a private persistent password path with `--password-file` when needed. Select the signed result in `build.aab_path` before publishing. See [the signing guide](docs/signing.md).

## Pipeline and publishing

```bash
playflow run                       # inspect -> policy -> build
playflow run --publish             # also upload, validate, then discard the edit
playflow run --publish --commit    # validate, request approval, then commit
```

Unresolved declarations stop the pipeline with exit code 2. `--commit` requires `--publish` on `run`. The default final-submit confirmation applies to both `run` and `publish`; embedding applications must supply an approval callback when the manifest requires one.

Publishing requires an existing Play application and an authorized service account. Keep its key outside the source checkout:

```bash
export PLAYFLOW_GOOGLE_CREDENTIALS="$HOME/.config/playflow/play-service-account.json"
playflow publish
playflow publish --commit
```

`publish` without `--commit` still uploads to Google's API for validation; it is not an offline dry run. The temporary edit is deleted after validation. A later `--commit` invocation creates a new edit and uploads again. Google documents the transaction model in its [edits guide](https://developers.google.com/android-publisher/edits).

For staged releases, set `play.release_status: inProgress` (or `halted`) and `play.user_fraction` between 0 and 1, exclusive. Draft/completed releases must omit the fraction; see the [Google track reference](https://developers.google.com/android-publisher/api-ref/rest/v3/edits.tracks).

Each track update submits the selected bundle as a single-release payload. Managing retained version codes, multiple active releases, and promoting or halting an existing release are not implemented. Review the target track before publishing.

## Browser authentication and recording

```bash
playflow auth
playflow browser-doctor
```

These two commands use `browser.engine: chromium` (the default). For an existing Firefox session, use the bridge below.

To open Console in your existing Firefox profile:

```bash
playflow firefox-profiles
playflow open-console
# Or build/sign first, then open Console:
playflow finish-release --open-console
```

Set `browser.engine: firefox`, `browser.firefox_profile_name`, and `browser.console_url` in your private manifest. Profile discovery reads both `profiles.ini` and the newer `Profile Groups/*.sqlite` databases. For duplicate names or a custom installation, set `browser.firefox_profile_path` to the exact existing directory. No new profile is created. Firefox receives the [profile path and new-tab URL](https://firefox-source-docs.mozilla.org/browser/CommandLineParameters.html). A successful launch request does not prove page load, Google sign-in, app selection, or form completion. `open-console` does not rebuild, upload, or submit forms.

Sign in manually in the dedicated Chromium profile, including 2FA/passkeys. The doctor reports whether the Console URL is reachable; it does not prove account permissions. Keep the profile private.

For live Firefox form control, set `browser.console_url` to the **actual app's** Console URL and run:

```bash
playflow bridge-serve
# Load the printed manifest.json through about:debugging → This Firefox → Load Temporary Add-on.
# Leave the server running; use another terminal:
playflow bridge-status
playflow console-inspect
playflow console-setup privacy          # Offline plan from the manifest
playflow console-setup privacy --apply  # Save and verify after reopening
playflow console-setup ads --apply
playflow console-setup advertising-id --apply  # Supported when explicitly declared No
```

Enable `approvals.allow_browser_write_actions` before applying changes. The bridge reads semantic controls on demand, uses fresh control IDs, and refuses ambiguous tabs, stale controls, sensitive inputs, and final publishing. It does not depend on screenshot coordinates. `console-attach` handles only manifest-selected release files in the chosen app. Privacy-policy, ads, and the no-advertising-ID branch have reusable save-and-verify workflows; other forms need supervised operations. The complete questionnaire catalog and end-to-end onboarding remain in progress. See [the Firefox bridge guide](docs/firefox-bridge.md) for setup, upload limits, security, and recovery.

To record manual Console work in Firefox:

1. Open `about:debugging` → **This Firefox** → **Load Temporary Add-on**.
2. Select `firefox-recorder/manifest.json` from this source checkout.
3. Open your Play Console tab and choose **Start recording** in the extension popup.
4. Perform the workflow, then choose **Stop** and **Export JSON**.

Recording is bound to the tab selected at start. It collects semantic controls and bounded DOM additions only while active, strips URL queries/fragments, and redacts known sensitive fields. Sessions are kept in memory, stop at 10,000 events, and are lost when the extension/browser restarts. Export before restarting. Other app text, account IDs in URL paths, and developer-provided values may remain: review recordings before sharing.

Offline preview never launches a browser or follows links:

```bash
playflow replay-recording recording.json
```

For actual replay, set `approvals.allow_browser_write_actions: true`, authenticate first, and use:

```bash
playflow replay-recording recording.json --allow-write --max-events 20
```

Replay accepts Play Console navigation without query strings/fragments, skips sensitive controls, and stops at the first failed or ambiguous action. Checkboxes, text inputs, and native selects are supported. It does not replay file uploads, login flows, arbitrary scripts, or submit events. Custom Console widgets may need dedicated workflows. Locator handling follows [Playwright's input actions](https://playwright.dev/python/docs/input).

## State and failures

`.playflow/state.json` is a private, atomically written **stage journal**. It records the latest running/done/blocked/failed stage, inferred facts, artifact paths, and publishing metadata. Raw subprocess output and exception messages are not saved.

Commands re-evaluate inputs and rerun stages; automatic resume, build caching, and continuation of an existing Play edit are not implemented. Do not run multiple PlayFlow writers against the same project. After an interrupted upload or uncertain commit response, inspect Play Console before retrying; PlayFlow does not retry publishing automatically. A stage left `running` indicates an interrupted process.

## Development and project layout

```bash
python -m pip install -e '.[dev]'
make check             # Python + recorder tests, Ruff, schema drift
make dist              # source/wheel builds, metadata and archive checks
```

Node.js 22+ runs recorder tests without npm dependencies. The Python regression suite also runs with `python -m unittest discover -s tests -v`. Tests use temporary projects and mock Google/browser adapters; they do not require credentials, Android builds, browser downloads, or publishing access.

```text
src/playflow/       Python domain models, workflow use cases, CLI and adapters
tests/             Offline Python, bridge and recorder regression tests
src/playflow/browser_extension/  Firefox live bridge assets, included in wheels
firefox-recorder/  Standalone Firefox extension, included in source distributions
docs/              Architecture, roadmap and release process
schemas/           Generated public manifest JSON Schema
examples/          Sanitized, portable configuration examples
tools/             Schema export and release-archive verification
.github/           CI, dependency updates and contribution templates
```

For a detailed explanation without reading the code, start with the [project guide and submission field notes](docs/project-field-guide.md). Read the [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), [contribution guide](CONTRIBUTING.md), [security policy](SECURITY.md), and [release process](docs/releasing.md). PlayFlow is licensed under [MIT](LICENSE).
