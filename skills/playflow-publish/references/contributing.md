# Contribute a verified Play Console improvement

Use this workflow only when the developer opted into local proposals or explicitly requested a contribution. Keep app publishing independent: declining or lacking GitHub access must not prevent normal PlayFlow use. Upstream is `CyberCipherSight/playflow`; its maintainer reviews PRs and decides what merges.

## Remember the local preference

Resolve these paths relative to the installed skill directory and use its Python environment:

```text
python scripts/community.py status
python scripts/community.py set review
python scripts/community.py set off
```

Run `set review` only after Yes to the first-use offer, and `set off` after No. `set ask` resets the choice at the user's request. On Linux, state is `$XDG_CONFIG_HOME/playflow/community.json` or `~/.config/playflow/community.json`. Windows uses `%LOCALAPPDATA%/playflow/community.json`, falling back to the user's `AppData/Local` folder. `--config <file>` before the subcommand selects another private location. Preferences contain only a schema version and mode; never add tokens, app facts, or recordings. The helper does not ask questions itself, contact GitHub, discover credentials, or authorize a submission.

`review` enables preparing local proposals. Even in this mode, each exact proposed contribution requires permission before creating a fork, pushing a branch, opening an issue/PR, or otherwise sending content externally. Use existing exact authorization if already given. Missing, malformed, or unavailable preferences never count as consent. A changed proposal needs renewed review if its approved scope changes.

## Turn an observation into a useful proposal

1. Finish or stabilize the user's requested task first. A timeout, clicked Save, or disabled button alone does not prove a new step succeeded; independently observe persisted remote state.
2. Describe the generalized trigger, observed semantic controls, expected outcome, verified result, browser/OS, and what remains uncertain. Separate live evidence from mocked tests. Do not advertise a one-user workaround as universal compatibility.
3. Check current upstream code, docs, and related PRs for an existing fix. Use an isolated trusted checkout. Do not commit from the developer's Android project, runtime directory, or browser profile. Keep a private candidate if a reusable change cannot be prepared yet; do not send an empty PR merely to announce a successful action.
4. Make the smallest relevant instruction/code change. Preserve app scoping, existing signing identity, semantic references, approval gates, and observe-before-retry behavior. Add a synthetic regression fixture when it meaningfully verifies the fix; documentation-only clarifications need appropriate link/format checks instead.
5. Run the checks relevant to the change. For core changes use `make check`; skill changes should keep the standard entrypoint, references, and installer/export resource lists consistent. Confirm installable skill archives include new resources.

## Review the exact outbound material

Create a fresh minimal fixture with synthetic values rather than uploading a raw snapshot. Exclude app/package identifiers, developer account IDs, personal emails, tester groups, machine paths, app source, screenshots, videos, recordings, journals, cookies, credentials, signing material, and session configuration. Never attach `.playflow/` or an entire project. Required private evidence stays local; if sanitization removes necessary context, explain the limitation rather than sending it.

Inspect every new/changed file, full staged diff, commit author metadata, PR title/body, and any proposed attachments. Run an available secret scanner and inspect its findings locally; passing a scanner is not a substitute for review. Do not print suspected secrets. Use the user's public GitHub noreply address when committing on their behalf, unless they explicitly selected another public author address.

Show the user the exact diff or local patch, target `CyberCipherSight/playflow`, intended fork/branch, sanitized verification summary, and proposed PR title/body. Ask whether to send this contribution. General browser access or permission to publish their Android app is not this permission.

## Send only the approved proposal

Prefer available GitHub tools; use the authenticated GitHub CLI when needed. Confirm the intended GitHub identity and repository access without printing tokens or requesting broader permissions automatically. If disconnected, leave the reviewed patch local and offer manual submission. Never log in, create a fork, or upload anything simply to test the contribution flow.

After permission, create a fork in that user's account if necessary, or an isolated branch if they have appropriate upstream access. Push only the reviewed commit(s) to that branch. Never push a community contribution directly to upstream's default branch or enable auto-merge. Open a **draft pull request**, with a title describing the changed behavior and a body describing the trigger, fix, validation, and limits. The maintainer decides whether to merge.

For an already-authorized prepared branch, an example using the official GitHub CLI is:

```text
gh pr create --repo CyberCipherSight/playflow --base main --head <contributor>:<branch> --draft --title <reviewed-title> --body-file <reviewed-body-file>
```

Run this only with the actual reviewed values and authorization; it is not a setup command. A PR operation can publish branch contents. Do not use a dry-run flag as a safety guarantee. If a push or PR creation times out, inspect the remote branch and existing PRs before retrying to prevent duplicate submissions. Verify the returned PR URL, upstream/base/head, and changed file list, then give the user that link. Do not separately message maintainers or subscribe the user to notifications.

## Limits

This feature is an agent-guided contribution workflow plus a local preference helper. It is not a background watcher, automatic learning service, guaranteed secret sanitizer, or autonomous PR uploader. No cross-user data collection takes place. When no contribution is approved, nothing is sent.
