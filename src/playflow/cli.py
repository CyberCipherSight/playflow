from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from .adb import devices as adb_devices
from .adb import install as adb_install
from .config import DEFAULT_MANIFEST, load_manifest, write_example_manifest
from .gradle import find_aab, find_apk
from .workflow import Workflow, run_pipeline


class CommandGroup(TyperGroup):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (typer.Exit, typer.Abort):
            raise
        except subprocess.CalledProcessError as exc:
            typer.echo(
                f"Error: external command failed (exit {exc.returncode}). Run it directly for full logs.",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        except (OSError, ValueError, RuntimeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc


app = typer.Typer(
    cls=CommandGroup,
    no_args_is_help=True,
    help="PlayFlow: agent-ready Google Play publishing automation",
)
console = Console()


def _approve() -> bool:
    return typer.confirm("Final submission approval is enabled. Commit this Play edit?")


def _chromium_required(cfg) -> None:
    if cfg.browser.engine != "chromium":
        raise ValueError(
            "This command requires Chromium. Use bridge-serve and console-inspect for an "
            "existing Firefox session, or configure browser.engine: chromium for this adapter."
        )


def _result(result: dict) -> None:
    console.print_json(data=result)
    if result.get("status") == "blocked":
        raise typer.Exit(code=2)


@app.command()
def init(app_name: str = typer.Option(..., "--app-name"), output: Path = Path(DEFAULT_MANIFEST)):
    """Create a versioned PlayFlow manifest."""
    if output.exists():
        raise typer.BadParameter(f"Already exists: {output}")
    write_example_manifest(output, app_name)
    console.print(f"Created {output}", markup=False)


@app.command()
def inspect(
    manifest: Path = Path(DEFAULT_MANIFEST), json_output: bool = typer.Option(False, "--json")
):
    """Inspect the configured Android module and show inferred facts."""
    result = Workflow.from_file(manifest).inspect()
    if json_output:
        # Rich's normal console rendering can wrap or interpret JSON strings.
        typer.echo(result.to_json())
        return
    table = Table(title="Android project analysis")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Project", result.project_dir)
    table.add_row("Package", result.package_name or "unknown")
    table.add_row("Permissions", "\n".join(result.permissions) or "none")
    table.add_row("Warnings", "\n".join(result.warnings))
    console.print(table)


@app.command("policy-check")
def policy_check(manifest: Path = Path(DEFAULT_MANIFEST)):
    """List declaration facts that still require human input."""
    workflow = Workflow.from_file(manifest)
    questions = workflow.policy_check(workflow.inspect())
    _result({"status": "blocked" if questions else "ready", "questions": questions})


@app.command()
def build(manifest: Path = Path(DEFAULT_MANIFEST)):
    """Build the configured module and resolve its AAB."""
    aab = Workflow.from_file(manifest).build()
    console.print(f"AAB: {aab}", markup=False)


@app.command()
def preflight(manifest: Path = Path(DEFAULT_MANIFEST)):
    """Check listing, mobile assets, bundle availability and unresolved setup without mutations."""
    _result(Workflow.from_file(manifest).preflight())


@app.command("testing-plan")
def testing_plan_cmd(manifest: Path = Path(DEFAULT_MANIFEST)):
    """Show the intended test track, countries and Google Groups offline."""
    console.print_json(data=Workflow.from_file(manifest).testing_plan())


@app.command("configure-testers")
def configure_testers(
    manifest: Path = Path(DEFAULT_MANIFEST),
    commit: bool = typer.Option(
        False, help="Commit tester changes; otherwise validate and discard."
    ),
):
    """Merge the configured Google Groups into a closed test track through the official API."""
    _result(Workflow.from_file(manifest).configure_testers(commit=commit, approve=_approve))


@app.command("signing-init")
def signing_init(
    manifest: Path = Path(DEFAULT_MANIFEST),
    password_file: Path | None = None,
):
    """Create a local upload key; save a generated password without displaying it."""
    import uuid

    from .release import signing_backup_root
    from .signing import create_upload_key

    workflow = Workflow.from_file(manifest)
    if password_file is None:
        password_file = (
            signing_backup_root(workflow.manifest.play.package_name or workflow.manifest.app_name)
            / "generations"
            / uuid.uuid4().hex
            / "upload-password.txt"
        )
    result = create_upload_key(workflow.state.path.parent / "signing", password_file)
    workflow.state.mark("signing_key", "done", metadata=result)
    console.print_json(data=result)


@app.command("finish-release")
def finish_release_cmd(
    manifest: Path = Path(DEFAULT_MANIFEST),
    recover_unused_key: bool = typer.Option(
        False,
        "--recover-unused-key",
        help="Replace an unrecoverable key ONLY if it was never uploaded or registered with Play.",
    ),
    open_console_after: bool = typer.Option(
        False,
        "--open-console",
        help="Open the configured Firefox Console URL after successful signing.",
    ),
):
    """Back up credentials, build and sign a release bundle locally; never upload."""
    from .release import finish_release

    console.print_json(data=finish_release(manifest, recover_unused_key=recover_unused_key))
    console.print("Manifest now selects the signed bundle. No upload was performed.")
    if open_console_after:
        open_console_cmd(manifest=manifest)


@app.command("signing-record-upload")
def signing_record_upload_cmd(
    certificate_sha256: str,
    manifest: Path = Path(DEFAULT_MANIFEST),
):
    """Record a confirmed Play upload so unused-key recovery cannot replace this key."""
    from .release import record_key_registration, signing_backup_root

    workflow = Workflow.from_file(manifest)
    package = workflow.manifest.play.package_name
    if not package:
        raise ValueError("Set play.package_name before recording an upload-key registration")
    record = record_key_registration(
        workflow.state.path.parent / "signing",
        signing_backup_root(package),
        package,
        certificate_sha256,
    )
    console.print_json(data=record)


@app.command("firefox-profiles")
def firefox_profiles_cmd():
    """List Firefox profile names and paths from registries and profile-group databases."""
    from .firefox import profiles

    console.print_json(data={"profiles": profiles()})


@app.command("open-console")
def open_console_cmd(
    manifest: Path = Path(DEFAULT_MANIFEST),
    url: str | None = None,
    firefox_profile: str | None = None,
    firefox_profile_path: Path | None = None,
):
    """Request a Play Console tab in an existing Firefox profile, without filling forms."""
    from .firefox import open_console

    cfg, _ = load_manifest(manifest)
    if cfg.browser.engine != "firefox":
        raise ValueError("open-console currently supports Firefox; use auth for dedicated Chromium")
    configured_path = (
        str(firefox_profile_path)
        if firefox_profile_path is not None
        else (None if firefox_profile is not None else cfg.browser.firefox_profile_path)
    )
    result = open_console(
        url or cfg.browser.console_url,
        firefox_profile or cfg.browser.firefox_profile_name,
        configured_path,
    )
    console.print_json(data=result)
    console.print(
        "Firefox navigation requested. Sign-in and Console form completion are not verified."
    )


@app.command("bridge-serve")
def bridge_serve_cmd(
    manifest: Path = Path(DEFAULT_MANIFEST),
    site_url: list[str] | None = typer.Option(None, "--site-url"),
    allow_site_publish: bool = False,
    approved_review_changes: int | None = typer.Option(None, min=1),
):
    """Serve the local Firefox connection and generate a private temporary add-on."""
    from .bridge import serve

    serve(
        manifest,
        site_url,
        allow_site_publish=allow_site_publish,
        approved_review_changes=approved_review_changes,
    )


@app.command("bridge-status")
def bridge_status_cmd(manifest: Path = Path(DEFAULT_MANIFEST)):
    """Check whether the temporary Firefox extension is polling PlayFlow."""
    from .bridge import Client

    console.print_json(data=Client(manifest).request("/status"))


@app.command("console-inspect")
def console_inspect_cmd(manifest: Path = Path(DEFAULT_MANIFEST), target: str | None = None):
    """Inspect visible controls in the selected app/site without changing fields."""
    from .bridge import Client

    cfg, _ = load_manifest(manifest)
    console.print_json(
        data=Client(manifest).request(
            "/command",
            {
                "operation": "inspect",
                "target": target or cfg.browser.console_url,
            },
        )
    )


@app.command("console-action")
def console_action_cmd(
    operation: str,
    manifest: Path = Path(DEFAULT_MANIFEST),
    control_id: str | None = None,
    value: str | None = None,
    target: str | None = None,
):
    """Act on a fresh control; final actions need separate permission and sensitive fields stay blocked."""
    from .bridge import Client

    cfg, _ = load_manifest(manifest)
    parsed_value = value
    if operation == "check":
        if value not in {"true", "false"}:
            raise typer.BadParameter("check requires --value true or --value false")
        parsed_value = value == "true"
    console.print_json(
        data=Client(manifest).request(
            "/command",
            {
                "operation": operation,
                "target": target or cfg.browser.console_url,
                "control_id": control_id,
                "value": parsed_value,
            },
        )
    )


@app.command("console-setup")
def console_setup_cmd(
    step: str,
    manifest: Path = Path(DEFAULT_MANIFEST),
    apply: bool = False,
):
    """Preview or save a supported declaration and verify it after reopening its page."""
    from .console import apply_setup

    console.print_json(data=apply_setup(manifest, step, apply))


@app.command("console-attach")
def console_attach_cmd(
    asset: str,
    control_id: str,
    manifest: Path = Path(DEFAULT_MANIFEST),
):
    """Attach a manifest-selected release file to a freshly inspected Console file input."""
    from .bridge import Client

    cfg, _ = load_manifest(manifest)
    console.print_json(
        data=Client(manifest).request(
            "/command",
            {
                "operation": "attach",
                "target": cfg.browser.console_url,
                "control_id": control_id,
                "asset": asset,
            },
        )
    )


@app.command("inspect-bundle")
def inspect_bundle_cmd(
    manifest: Path = Path(DEFAULT_MANIFEST),
    bundletool: Path | None = None,
    after_version_code: int | None = typer.Option(None, min=0),
    certificate_sha256: str | None = None,
):
    """Verify the selected AAB's built identity, modules, permissions and saved upload-key signature."""
    from .artifacts import DEFAULT_BUNDLETOOL, inspect_bundle

    console.print_json(
        data=inspect_bundle(
            manifest,
            bundletool or DEFAULT_BUNDLETOOL,
            after_version_code=after_version_code,
            certificate_sha256=certificate_sha256,
        )
    )


@app.command("console-release")
def console_release_cmd(
    release_url: str,
    manifest: Path = Path(DEFAULT_MANIFEST),
    bundletool: Path | None = None,
    after_version_code: int | None = typer.Option(None, min=0),
    certificate_sha256: str | None = None,
    track_kind: str = "closed",
    native_uploaded: bool = False,
    apply: bool = False,
):
    """Prepare an explicit closed/production draft; verify native uploads when requested; never submit."""
    from .artifacts import DEFAULT_BUNDLETOOL
    from .release_draft import prepare_draft

    console.print_json(
        data=prepare_draft(
            manifest,
            release_url,
            apply=apply,
            bundletool=bundletool or DEFAULT_BUNDLETOOL,
            after_version_code=after_version_code,
            certificate_sha256=certificate_sha256,
            track_kind=track_kind,
            native_uploaded=native_uploaded,
        )
    )


@app.command("sign-bundle")
def sign_bundle_cmd(
    aab: Path | None = None,
    manifest: Path = Path(DEFAULT_MANIFEST),
    output: Path | None = None,
):
    """Sign an unsigned release AAB copy and strictly verify its upload-key signature."""
    from .signing import sign_bundle

    workflow = Workflow.from_file(manifest)
    source = aab or find_aab(
        workflow.project, workflow.manifest.build.aab_path, workflow.manifest.build.module
    )
    directory = workflow.state.path.parent
    destination = output or directory / "artifacts" / "app-release-signed.aab"
    result = sign_bundle(source, directory / "signing", destination)
    workflow.state.mark("sign_bundle", "done", result=result)
    console.print_json(data=result)


@app.command("adb-install")
def adb_install_cmd(manifest: Path = Path(DEFAULT_MANIFEST), serial: str | None = None):
    """Install the configured APK on a connected device."""
    cfg, mpath = load_manifest(manifest)
    project = cfg.resolved_project_dir(mpath)
    apk = find_apk(project, cfg.build.apk_path, cfg.build.module)
    found = adb_devices()
    if not found:
        raise RuntimeError("No authorized ADB device connected")
    if serial is not None and serial not in found:
        raise ValueError(f"Device {serial} is not connected and authorized")
    if serial is None and len(found) > 1:
        raise ValueError(f"Multiple devices connected; choose --serial from {found}")
    console.print(adb_install(apk, serial or found[0]), markup=False)


@app.command()
def auth(manifest: Path = Path(DEFAULT_MANIFEST)):
    """Open a dedicated Chromium profile for human sign-in."""
    cfg, _ = load_manifest(manifest)
    _chromium_required(cfg)
    from .browser import authenticate

    authenticate(cfg.play.browser_profile)


@app.command("browser-doctor")
def browser_doctor(manifest: Path = Path(DEFAULT_MANIFEST)):
    """Check whether the dedicated profile reaches Play Console."""
    cfg, _ = load_manifest(manifest)
    _chromium_required(cfg)
    from .browser import doctor

    console.print_json(data=doctor(cfg.play.browser_profile))


@app.command()
def publish(
    manifest: Path = Path(DEFAULT_MANIFEST),
    track: str | None = None,
    commit: bool = typer.Option(False, help="Commit after validation; otherwise discard the edit."),
):
    """Upload an AAB and validate or commit a Google Play edit."""
    workflow = Workflow.from_file(manifest)
    _result(workflow.publish(workflow.inspect(), track=track, commit=commit, approve=_approve))


@app.command()
def run(
    manifest: Path = Path(DEFAULT_MANIFEST),
    publish: bool = typer.Option(False, help="Continue into Google Play API after build."),
    commit: bool = typer.Option(False, help="Commit the edit after validation."),
):
    """Run inspect -> policy gate -> build -> optional publish."""
    _result(run_pipeline(manifest, publish=publish, commit=commit, approve=_approve))


@app.command("replay-recording")
def replay_recording_cmd(
    recording: Path,
    manifest: Path = Path(DEFAULT_MANIFEST),
    allow_write: bool = typer.Option(False, "--allow-write", help="Permit browser interactions."),
    max_events: int | None = typer.Option(None, min=1),
):
    """Preview a recorder session offline, or explicitly replay its actions."""
    cfg, _ = load_manifest(manifest)
    if allow_write and not cfg.approvals.allow_browser_write_actions:
        raise typer.BadParameter("Manifest approvals.allow_browser_write_actions is false")
    if allow_write:
        _chromium_required(cfg)
    from .browser import replay_recording

    results = replay_recording(
        cfg.play.browser_profile,
        recording,
        allow_write=allow_write,
        max_events=max_events,
    )
    console.print_json(data=results)
    if any(result.get("error") for result in results):
        raise typer.Exit(code=1)


@app.command()
def state(manifest: Path = Path(DEFAULT_MANIFEST)):
    """Show the local stage journal."""
    console.print_json(data=Workflow.from_file(manifest).state.load())


if __name__ == "__main__":
    app()
