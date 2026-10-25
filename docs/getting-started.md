# Install PlayFlow and prepare a Google Play release

PlayFlow is an early prototype for supervised Android release automation. The standard skill format is portable; browser and operating-system execution still require compatible tools. Linux with Firefox has live evidence. Windows is a development target, and Chrome/Brave/Edge publishing adapters are not available yet.

## Download

Download a release source ZIP from [CyberCipherSight/playflow](https://github.com/CyberCipherSight/playflow), or clone the repository:

```text
git clone https://github.com/CyberCipherSight/playflow.git
cd playflow
```

Review the source and license. Do not put your Android project, private keys, or browser profile inside the downloaded source folder.

## Install the CLI

Use Python 3.11 or later. In the downloaded folder, Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/playflow --help
```

Windows PowerShell or CMD:

```text
py -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\playflow.exe --help
```

These examples avoid activation and execution-policy changes. Elsewhere in the guides, `playflow` means this environment's executable. Install `.[publish]` only when using the official Play API; `.[browser]` and Playwright's Chromium download are for the separate Chromium recorder/replay path, not required for the Firefox bridge.

Builds need your project's compatible JDK, Android SDK, and Gradle wrapper. Flutter projects also need Flutter. Preserve an existing app's registered upload key and signing setup.

## Install the optional agent skill

Follow [the Agent Skill guide](agent-skill.md). Give the agent access to the installed CLI. From the source folder, run the prerequisite inventory with the same environment:

```text
python skills/playflow-publish/scripts/doctor.py --project /path/to/android-source
```

Substitute `.venv/bin/python` or `.venv\Scripts\python.exe` as appropriate. Missing dependencies should be resolved before publishing; the doctor does not install anything or inspect credentials.

## Configure one app

Keep an editable manifest outside this source checkout, beside your Android source or in a private configuration folder. Start from [the Firefox example](../examples/firefox-agent.yaml). Replace the example package, app URL, project path, selected artifact, and profile name with your actual values. Leave unknown declaration facts unanswered until reviewed. Do not copy sample answers as real policy statements.

Use the exact app-specific URL from your signed-in Play Console, not the account app-list URL. For Flutter, `project_dir` can point to its `android/` subdirectory and the selected bundle path to `../build/app/outputs/bundle/release/app-release.aab`. Build Flutter from the Flutter source root.

Check CLI help and run:

```text
playflow inspect --manifest /path/to/private/play-manifest.yaml
playflow preflight --manifest /path/to/private/play-manifest.yaml
playflow firefox-profiles
playflow open-console --manifest /path/to/private/play-manifest.yaml
```

Preflight may correctly report missing listing, policy, or artifact inputs. It does not certify Console declarations. Opening Firefox is not an upload.

## Connect your signed-in Firefox

In one terminal:

```text
playflow bridge-serve --manifest /path/to/private/play-manifest.yaml
```

Keep it running. In the selected Firefox profile, open `about:debugging`, select **This Firefox → Load Temporary Add-on**, then choose the generated `manifest.json` printed by the server. Do not load `firefox-recorder/manifest.json` for this connection; that is a different tool.

In a second terminal:

```text
playflow bridge-status --manifest /path/to/private/play-manifest.yaml
playflow console-inspect --manifest /path/to/private/play-manifest.yaml
```

Check the app and account. Keep only one tab matching that app's target. The initial example disables browser writes. Enable `approvals.allow_browser_write_actions` in your private manifest only when ready for the intended operations. Final submission remains a separate bounded action.

Temporary add-ons unload when Firefox restarts. A server restart generates a new session/add-on; reload that generated add-on and verify the connection again. Stop the bridge and remove its temporary add-on when finished. Never copy browser cookies or provide passwords to the agent.

## Verify the actual AAB

Artifact inspection requires the official [bundletool 1.18.3 release](https://github.com/google/bundletool/releases/tag/1.18.3). Download `bundletool-all-1.18.3.jar` and verify SHA-256:

```text
a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29
```

Place it at `~/.cache/playflow/tools/bundletool-all-1.18.3.jar` (under your home folder), or pass its location with `--bundletool`. Linux `sha256sum` and PowerShell `Get-FileHash -Algorithm SHA256` can check it. A checksum mismatch must stop inspection.

```text
playflow inspect-bundle --manifest /path/to/private/play-manifest.yaml --after-version-code <previous-code> --certificate-sha256 <registered-upload-certificate>
```

The public certificate option supports existing Gradle signing without copying its passwords. It does not generate a replacement key. Use [the signing guide](signing.md) for unsigned native bundles and [the release execution reference](../skills/playflow-publish/references/releases.md) for draft operations, supported locales, native uploads, and production intent.

## What happens next

The agent prepares the requested release, resolves relevant declarations from reviewed facts, and checks saved remote state. Some Console questionnaires, native widgets, privacy-site editing, and required reviewer videos need supervised work. The Firefox transport accepts up to 16 MiB per file and 64 MiB per session; larger AABs require the exact verified file through the native picker or an authorized API path. These are PlayFlow limits, not Google limits.

The final report must distinguish **draft saved**, **submitted**, **in review**, **approved**, and **published**. Managed publishing can leave an approved update waiting for a separate Publish action. Do not retry an uncertain upload or submission without first inspecting Google.

Troubleshooting and security details are in [the Firefox guide](firefox-bridge.md), [integration evidence](integration-notes.md), and [SECURITY.md](../SECURITY.md). Keep logs private and share only sanitized minimal reproductions.
