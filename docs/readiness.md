# Preparation and closed-testing configuration

`playflow preflight` checks the current mobile preparation inputs without launching a browser, building an app, contacting Google, or writing workflow state. It returns JSON and exits 2 while missing inputs or manual verification steps remain. `playflow testing-plan` shows the requested test setup offline. Neither command proves that Console settings were saved.

The checked-in requirements subset lives in `src/playflow/requirements.py`, with a version, verification date, and authoritative sources. It covers the checks implemented today, not a complete questionnaire catalogue. Changes to Google requirements need review, source verification, schema updates where applicable, and boundary regressions.

## Implemented input checks

| Input | Validation |
| --- | --- |
| Localized title | At most 30 characters |
| Short description | At most 80 characters |
| Full description | At most 4,000 characters |
| Release notes | At most 500 Unicode characters per language |
| Store icon | 512 × 512, 32-bit RGBA PNG, at most 1,024 KB |
| Feature graphic | 1024 × 500, RGB JPEG or 24-bit PNG, no alpha/transparency |
| Phone screenshots | 2–8 distinct files; RGB JPEG or 24-bit PNG without alpha; dimensions 320–3840; longest side at most twice shortest |
| Bundle | Configured/scoped AAB file exists; signature and actual identity still require verification |
| Closed test groups | Normalized, deduplicated email addresses |
| Country selection | Explicit `all`, or `selected` with nonempty two-letter codes |
| Track | Explicit actual track identifier; closed mode rejects internal/production |
| Support contact | Explicit public support email address |
| AI asset labels | Explicit per-asset intent; remote labels still require verification |

Listing limits come from Google's [app setup documentation](https://support.google.com/googleplay/android-developer/answer/9859152). Image rules come from [preview asset requirements](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en-GE), checked October 17, 2026. The screenshot validator currently supports phone assets only. It uses two phone screenshots to satisfy the general minimum; requirements for tablets, TV, Wear, Automotive and XR need dedicated validation. Promotional recommendations and visual/content compliance are not checked. Launcher vector XML does not substitute for a store-ready PNG icon.

The [release preparation guide](https://support.google.com/googleplay/android-developer/answer/9859348) specifies the 500-character limit for each language's release notes; language tags are a Console editing wrapper, not part of each manifest text value.

Pydantic enforces listing length limits when loading the manifest. The asset checker verifies file encoding and decodes images without modifying them. Asset paths resolve relative to `project_dir`. Missing declarations are reported, with broader questionnaires explicitly marked for manual/Console verification rather than silently certified complete.

`assets.ai_generated` records the asset IDs that need AI labels, for example `[feature_graphic]`. Use `[]` only after reviewing provenance and determining that none need labels; null means unreviewed. IDs are `icon`, `feature_graphic`, or `phone_screenshots.<index>`. Google asks for an [individual asset declaration](https://support.google.com/googleplay/android-developer/answer/17262077) during listing review. Recording this intention does not apply the remote labels.

## Example plan

See [examples/closed-testing.yaml](../examples/closed-testing.yaml):

```yaml
play:
  # Resolve the actual Console/API closed-track identifier before remote operations.
  default_track: null
  release_status: draft
testing:
  mode: closed
  google_groups:
    - first-testers@googlegroups.com
    - second-testers@googlegroups.com
  country_scope: all
  countries: []
```

Do not guess that a custom closed track uses a particular identifier. `play.default_track` can remain null during preparation; remote commands require it. Existing manifests without `testing` retain their previous behavior and default internal track.

`country_scope: all` records an intention to select all countries/regions available in Console. It is not translated into a fabricated country list or staged-release `countryTargeting`. The [country availability API](https://developers.google.com/android-publisher/api-ref/rest/v3/edits.countryavailability) exposes a read operation, so applying track-wide availability remains a Console step. No country changes are performed by `configure-testers` or `publish`.

## Google Groups adapter

After authorizing the service account and resolving the actual closed track:

```bash
playflow configure-testers           # update inside an edit, validate, then discard
playflow configure-testers --commit  # request configured approval, validate, then commit
```

The adapter reads the existing track groups, merges the configured groups without removing existing ones, verifies the returned group list, and validates the edit before commit. Failures trigger best-effort cleanup. The [official testers API](https://developers.google.com/android-publisher/api-ref/rest/v3/edits.testers) supports Google Groups email addresses; Console-managed individual-email lists are outside this adapter's scope. Group membership, ownership, and enrollment by testers are not managed.

`publish` also merges configured Google Groups into the same edit as the bundle/track update. Country configuration and Console declarations remain separate. A successful tester update does not make a release available by itself; the track/release must be configured and active. Publishing outcomes still require integration testing against a developer-owned app.

## External projects and browser preferences

Use `state_dir` to keep state beside a local manifest when the Android source tree is outside the current writable workspace:

```yaml
project_dir: ../my-android-project
state_dir: .playflow/my-app
repository_url: https://github.com/example/my-app
browser:
  engine: firefox
  firefox_profile_name: normal
```

The state directory resolves relative to the manifest. Without it, state still lives under the Android project's `.playflow/`. This changes the journal location only; Gradle still needs a writable build checkout.

`playflow firefox-profiles` reads names and paths from both `profiles.ini` and newer `Profile Groups/*.sqlite` databases in read-only mode. `playflow open-console` requests a tab in the configured existing profile at `browser.console_url` (defaults to the Console home). Set `browser.firefox_profile_path` to the exact directory if needed; it takes precedence over the configured name. Names must resolve uniquely, with case-insensitive matching only when no exact match exists. Unknown names do not fall back to another account or create profiles.

`open-console` provides browser launching. Use the separate [live Firefox bridge](firefox-bridge.md) for existing-session form control and supported save-and-verify workflows. `auth`, `browser-doctor`, and write replay still use the Chromium adapter. The standalone recorder supports manual Firefox recording, and offline recording preview works for either browser preference. A successful `open-console` result records a launch request, not verified Google sign-in, app selection or form completion.

`repository_url` is informational project context; saving it does not publish a repository or change the app's package identity.
