from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .analyzer import Analysis
from .assets import validate_assets
from .gradle import find_aab
from .models import Manifest
from .policy import unresolved_questions
from .requirements import (
    COUNTRIES_SOURCE,
    LISTING_LIMITS,
    LISTING_SOURCE,
    RULESET_VERSION,
    TESTERS_SOURCE,
    VERIFIED_ON,
)


def testing_plan(manifest: Manifest) -> dict:
    testing = manifest.testing
    if testing is None:
        return {"status": "not_configured"}
    return {
        "mode": testing.mode,
        "track_id": manifest.play.default_track,
        "google_groups": testing.google_groups,
        "country_scope": testing.country_scope,
        "countries": testing.countries,
        "console_state": "not_checked",
        "steps": [
            {"action": "resolve_track", "adapter": "console_or_api"},
            {
                "action": "configure_country_availability",
                "adapter": "console",
                "source": COUNTRIES_SOURCE,
            },
            {
                "action": "merge_google_groups",
                "adapter": "android_publisher_api",
                "source": TESTERS_SOURCE,
            },
        ],
    }


def resolve_track(manifest: Manifest, override: str | None = None) -> str:
    track = override or manifest.play.default_track
    if not track or not track.strip():
        raise ValueError("Set play.default_track to the actual Console/API track identifier")
    track = track.strip()
    testing = manifest.testing
    if testing and testing.mode == "closed" and track in {"internal", "production"}:
        raise ValueError(
            "Closed testing requires a closed track identifier, not internal or production"
        )
    if testing and testing.mode == "internal" and track != "internal":
        raise ValueError("testing.mode is internal but the selected track is different")
    if testing and testing.mode == "open" and track in {"internal", "production"}:
        raise ValueError("Open testing requires an open test track identifier")
    return track


def readiness_report(manifest: Manifest, project: Path, analysis: Analysis) -> dict:
    """Read-only preparation checks, independent of builds or remote mutation."""
    checks: list[dict] = []

    def add(key: str, status: str, message: str, source: str | None = None):
        item = {"key": key, "status": status, "message": message}
        if source:
            item["source"] = source
        checks.append(item)

    package = manifest.play.package_name or analysis.package_name
    add(
        "play.package_name",
        "pass" if package else "missing",
        package or "Set the built variant's package name.",
    )
    if manifest.play.package_name and analysis.package_name and package != analysis.package_name:
        add(
            "play.package_name.source",
            "manual",
            "Configured package differs from source; verify the built variant.",
        )
    if not manifest.listing:
        add(
            "listing",
            "missing",
            "Provide at least the default-language store listing.",
            LISTING_SOURCE,
        )
    languages = [listing.language for listing in manifest.listing]
    if len(languages) != len(set(languages)):
        add("listing.languages", "error", "Each listing language must be unique.", LISTING_SOURCE)
    for index, listing in enumerate(manifest.listing):
        for field, limit in LISTING_LIMITS.items():
            value = getattr(listing, field)
            add(
                f"listing.{index}.{field}",
                "pass" if value else "missing",
                f"{len(value or '')}/{limit} characters; provide accurate listing text.",
                LISTING_SOURCE,
            )
    checks.extend(check.to_dict() for check in validate_assets(project, manifest.assets))
    add(
        "assets.ai_generated",
        "manual" if manifest.assets.ai_generated is None else "pass",
        "Review asset provenance and complete Console's per-asset AI declaration."
        if manifest.assets.ai_generated is None
        else "AI asset label intent recorded; verify the labels in Console.",
        "https://support.google.com/googleplay/android-developer/answer/17262077",
    )
    asset_ids = {
        key
        for key, value in {
            "icon": manifest.assets.icon,
            "feature_graphic": manifest.assets.feature_graphic,
            **{
                f"phone_screenshots.{i}": path
                for i, path in enumerate(manifest.assets.phone_screenshots)
            },
        }.items()
        if value
    }
    for asset_id in manifest.assets.ai_generated or []:
        if asset_id not in asset_ids:
            add(
                "assets.ai_generated.reference",
                "error",
                f"AI label references an unconfigured asset: {asset_id}",
            )
    for question in unresolved_questions(manifest, analysis):
        add(f"developer_facts.{question.key}", "missing", question.prompt)
    # These broader facts are not certified by the current minimal policy gate.
    if not manifest.developer_facts.privacy_policy_url and not any(
        check["key"] == "developer_facts.privacy_policy_url" for check in checks
    ):
        add(
            "developer_facts.privacy_policy_url",
            "missing",
            "Provide and review the app's public privacy-policy URL.",
        )
    if not manifest.developer_facts.target_audience:
        add("developer_facts.target_audience", "missing", "Confirm the intended target age groups.")
    add(
        "developer_facts.uses_advertising_id",
        "missing" if manifest.developer_facts.uses_advertising_id is None else "pass",
        "Confirm advertising-ID use, including third-party SDKs; Android 13+ targets require this Console declaration."
        if manifest.developer_facts.uses_advertising_id is None
        else "Advertising-ID intent recorded; verify the declaration in Console.",
        "https://support.google.com/googleplay/android-developer/answer/6048248",
    )
    add(
        "developer_facts.support_email",
        "pass" if manifest.developer_facts.support_email else "missing",
        "Public support email configured."
        if manifest.developer_facts.support_email
        else "Provide the public store-listing support email.",
    )
    try:
        aab = find_aab(project, manifest.build.aab_path, manifest.build.module)
    except FileNotFoundError as exc:
        add("build.aab", "missing", str(exc))
    except ValueError as exc:
        add("build.aab", "error", str(exc))
    else:
        add("build.aab", "pass", str(aab))
    add(
        "build.signature_and_identity",
        "manual",
        "Verify the release bundle's signing certificate, package and version before upload.",
    )
    if manifest.testing:
        try:
            track = resolve_track(manifest)
        except ValueError as exc:
            add("play.default_track", "missing", str(exc))
        else:
            add(
                "play.default_track",
                "pass",
                f"Configured track identifier: {track}; remote existence is unverified.",
            )
        if manifest.testing.mode == "closed":
            add(
                "testing.google_groups",
                "pass" if manifest.testing.google_groups else "missing",
                "Google Groups are configured locally."
                if manifest.testing.google_groups
                else "Provide Google Groups email addresses.",
                TESTERS_SOURCE,
            )
        add(
            "testing.country_scope",
            "pass" if manifest.testing.country_scope else "missing",
            f"Requested scope: {manifest.testing.country_scope or 'unset'}.",
            COUNTRIES_SOURCE,
        )
        add(
            "testing.console_configuration",
            "manual",
            "Apply and verify tester/country settings in Console; local settings do not prove remote completion.",
        )
    if manifest.browser.engine == "firefox":
        add(
            "browser.firefox",
            "manual",
            "Use the temporary Firefox bridge for live controls; verify applicable Console workflows separately. Offline preflight does not inspect the session.",
        )
    add(
        "console.questionnaires",
        "manual",
        "Complete and verify applicable access, rating, Data safety, health, financial, government and other Console declarations.",
    )
    summary = {
        status: sum(check["status"] == status for check in checks)
        for status in ("pass", "missing", "error", "manual")
    }
    return {
        "status": "blocked"
        if any(summary[key] for key in ("missing", "error", "manual"))
        else "local_ready",
        "scope": "Mobile listing preparation; not a Console completion or policy-compliance certificate.",
        "ruleset": {"version": RULESET_VERSION, "verified_on": VERIFIED_ON},
        "project_dir": str(project),
        "package_name": package,
        "repository_url": manifest.repository_url,
        "summary": summary,
        "checks": checks,
        "testing_plan": testing_plan(manifest),
        "policy_questions": [
            asdict(question) for question in unresolved_questions(manifest, analysis)
        ],
    }
