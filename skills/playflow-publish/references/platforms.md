# Linux and Windows execution

Current product targets are Linux and Windows. Linux has real Firefox/Play submission evidence. Windows paths and Gradle wrappers have code support, but the complete Windows release/security flow remains unverified. macOS is deferred.

Use Python 3.11+, compatible JDK/Android SDK tools, Firefox, and Flutter when the project uses Flutter. Prefer a project virtual environment; inspect the chosen distribution before installing. Do not assume the package-index name `playflow` belongs to this source project.

Linux source installation uses `python3 -m venv .venv` and `.venv/bin/python -m pip install -e .`. On Windows, use the user's Python launcher and `.venv\Scripts\python.exe -m pip install -e .`; PowerShell and CMD activate environments differently, so calling that Python directly avoids unnecessary activation changes. Do not change execution policy just to activate a venv.

Native Gradle wrappers are `gradlew` on Linux and `gradlew.bat` on Windows. Use argument arrays and correct working directories; quote paths with spaces. Firefox on Windows may not be on PATH, even when installed. An unsupported launch should lead to finding its actual executable or asking the user to open the intended profile, rather than creating another profile.

Profile discovery reads legacy registrations and newer profile-group databases. Choose a unique existing name or exact path. Do not guess another account when a profile is missing. Browser startup success is not sign-in verification.

Load the temporary addon through Firefox `about:debugging`, This Firefox, Load Temporary Add-on, using the generated manifest. Avoid Linux desktop dependencies in portable instructions: the original development helper used Hyprland/grim/wl-copy and is not a Windows adapter. Native picker/bootstrap assistance may still be needed from the agent's available desktop tools or the user.

Signing credentials and session tokens must be stored outside the public checkout. Linux permissions and Windows ACLs need platform-appropriate checks; a successful chmod call alone does not prove credential privacy. Keep existing app-specific signing controls intact. Do not claim verified Windows support until it has been exercised on Windows.
