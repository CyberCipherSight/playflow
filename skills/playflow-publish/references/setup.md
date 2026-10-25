# First-time setup

This skill requires the separate PlayFlow CLI from the matching trusted source release. Do not assume installing these instructions installs the CLI, Android tooling, or browser extension. The repository's `docs/getting-started.md` contains the full user-facing installation guide.

1. Check local file/terminal access and whether execution is Linux or Windows. Windows is a product target with incomplete live verification; macOS is deferred.
2. Locate or download the trusted PlayFlow release chosen by the developer. Install in its own virtual environment: Linux uses `python3 -m venv .venv`, then `.venv/bin/python -m pip install .`; Windows uses `py -m venv .venv`, then `.venv\Scripts\python.exe -m pip install .`. Do not require shell activation or change PowerShell execution policy.
3. Run the skill's `scripts/doctor.py` with the same Python environment and the chosen Android source folder. Its result is a prerequisite inventory, not proof of SDK, signing, browser, or policy readiness.
4. Use a private per-app manifest. Identify the exact package, artifact, intended track, existing signing identity, and unresolved developer facts. Never copy one developer's profile path, account, groups, or declarations into another user's configuration.
5. Run `playflow firefox-profiles` and choose the developer's intended existing profile. Open the exact Console app and let the developer sign in normally if necessary. Never export cookies or automate passwords.
6. Run `playflow bridge-serve --manifest <manifest>` in a separate terminal. Through Firefox `about:debugging`, select This Firefox, Load Temporary Add-on, and the generated extension manifest printed by that server. This is distinct from the optional standalone recorder.
7. Run `playflow bridge-status --manifest <manifest>` and `playflow console-inspect --manifest <manifest>`. Verify the actual app and account context. Exactly one tab should match the selected app scope.

An inactive bridge is a connection problem, not permission to widen browser scope. Diagnose whether the server stopped, the temporary add-on unloaded, the session changed, or no matching app tab exists. Reconnect using the current server's generated add-on. After reconnection, inspect remote state before considering another write. Extension installation may need the developer or the agent's native desktop tools; this prototype has no universal OS desktop controller.

Official bundletool 1.18.3 is also required for artifact inspection. Use the upstream `google/bundletool` release and verify the checksum documented in the repository's getting-started guide. Keep this external prerequisite out of the skill bundle. Continue with [releases.md](releases.md) after setup.
