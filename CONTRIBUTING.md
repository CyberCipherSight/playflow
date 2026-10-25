# Contributing

Contributions are welcome under the project's MIT license. Begin with a small issue or pull request describing a concrete problem and expected behavior. Discuss larger workflow or format changes before implementing them.

The agent skill offers an optional [community contribution workflow](skills/playflow-publish/references/contributing.md). It prepares verified, sanitized changes locally and requires approval for the exact outbound proposal before any fork, push, or PR. GitHub connection and opting into local proposals do not authorize a submission. Community changes arrive as draft PRs for maintainer review; they are not automatically merged.

## Development setup

Use Python 3.11+ and Node.js 22+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
make check
```

Optional integrations: `python -m pip install -e '.[browser,publish]'`. Download Chromium only when testing live browser behavior with `python -m playwright install chromium`.

Follow the boundaries in [the architecture guide](docs/architecture.md). Add application behavior to `workflow.py`; keep prompting and terminal output in `cli.py`. Tests should be deterministic, use temporary directories, and avoid network calls and credentials. Native Android fixtures should be minimal and sanitized. Do not add tests that publish or require a real browser session to the default suite.

Before submitting:

```bash
make format
make schema   # when the manifest model changes
make check
make dist     # when packaging changes
```

Describe what changed, why it changed, and how you verified it. Include behavioral regressions for meaningful fixes. Preserve manifest compatibility; breaking formats require versioning, migration instructions, and updated examples. Documentation changes do not require new tests.

Do not submit credentials, signing keys, browser profiles, unreviewed recordings, account identifiers, or private Android source. See [SECURITY.md](SECURITY.md) for private vulnerability reporting. Contributors retain copyright to their work and submit it under the existing MIT license; no additional contributor agreement is required.
