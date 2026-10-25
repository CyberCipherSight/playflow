# Use PlayFlow as an Agent Skill

PlayFlow packages a Google Play Console automation workflow in the open [Agent Skills format](https://agentskills.io/specification). A skill supplies instructions and small helpers; the separate Python CLI performs deterministic publishing operations. The agent resolves missing facts and handles unexpected screens.

## Install from GitHub

With the third-party [skills installer](https://github.com/vercel-labs/skills) and its required Node.js version installed, run:

```text
npx skills add CyberCipherSight/playflow --skill playflow-publish
```

Choose your coding agent and project installation. Add `-g` for installation across projects. The installer supports multiple agent applications, but its supported-agent list is not evidence that PlayFlow has been tested with every one of them. Read the files before enabling a third-party skill. The command installs instructions, not the Python engine or Firefox extension.

For manual installation, copy the **whole** `skills/playflow-publish` directory into the skill location documented by your agent. For example, Claude Code documents `~/.claude/skills/` for personal skills. Use the existing agent's configured location rather than guessing a universal directory. The folder must retain its references, scripts, and license.

From a downloaded PlayFlow source folder, this portable helper copies the curated skill and refuses to overwrite an existing installation:

```text
python tools/install_skill.py --destination /path/to/agent/skills/playflow-publish
```

Use the Python executable available on your system (`python3` on many Linux installations, or `py` on Windows). Restart or refresh the agent's skills if its documentation requires it.

## Install and connect the engine

Follow [getting started](getting-started.md). Install from this repository or its reviewed release artifact; the package-index name `playflow` is not a verified distribution source for this project. Keep the CLI version and skill from the same release, and check `playflow --help` before relying on an option.

The agent needs local terminal/file access and access to the computer running Firefox. A hosted chat that only reads Markdown cannot build your Android application or connect to your local browser. This is an execution requirement, not a particular language-model requirement. No MCP server is required by this prototype.

## First request

Give the agent a project and outcome:

> Use the playflow-publish skill to prepare an update for this Android project in its existing closed testing track. Ask for missing app facts, preserve its upload key, and show me the release before submitting.

The agent should identify the exact package and selected app, inspect the current remote versions, prepare an unused version code, verify the signed bundle, reconcile relevant declarations, and prepare the requested release. Final review submission or publication follows the developer's actual authorization and configured approval requirements. It must verify remote state after consequential changes.

## Optional community contributions

On first use the agent offers to prepare useful, verified improvements for PlayFlow. You can decline and keep using all publishing functionality. Yes enables **local proposals**; the agent must still show you the sanitized exact change and ask before creating a fork, pushing, or opening a PR. GitHub sign-in alone is not permission to contribute.

The offline `scripts/community.py` helper remembers `ask`, `off`, or `review` outside the installed skill. From the skill directory, use `python scripts/community.py status`, `set off` to decline, `set review` to opt into proposals, or `set ask` to reset your choice. Use the same Python environment as the other helpers. The file stores no app facts or credentials and is not uploaded.

When approved, the agent sends only reviewed reusable code/instructions and synthetic fixtures to a draft PR against `CyberCipherSight/playflow`. Private app source, recordings, browser/session data, account IDs, and signing credentials stay local. The maintainer reviews the PR and decides whether it merges. Without GitHub access or permission, the proposal remains local. See [the contribution workflow](../skills/playflow-publish/references/contributing.md) for the exact process and limits. No background PR uploader or automatic learning service is installed.

## Compatibility and current limits

| Area | Prototype status |
| --- | --- |
| Shared `SKILL.md` format | Included, with relative references and helpers |
| Agent applications | Local Codex-assisted Linux use has evidence; other agent applications need independent testing |
| Linux + existing Firefox profile | Supervised live submissions and production rollout observed |
| Windows | Targeted; no complete live release verification yet |
| Chrome, Brave, Edge | No supported live publishing adapter yet |
| Other models | Depends on their agent host's tools and permissions; unverified |
| Recovery | Inspect remote state before retries; no general automatic resume engine |
| Adaptation | Stored per-app facts and evidence; no automatic self-modifying or shared learning system |
| Fully unattended publishing | Not claimed; Console changes and special widgets may need supervised interaction |

Keep app manifests, tokens, browser profiles, signing credentials, screenshots, and recordings private. Never upload local runtime data with an issue. See [security](../SECURITY.md) and [Firefox connection details](firefox-bridge.md).
