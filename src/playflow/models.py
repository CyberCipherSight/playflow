from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .requirements import LISTING_LIMITS, RELEASE_NOTES_LIMIT
from .urls import PLAY_CONSOLE, is_console_url


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class ReleaseNotes(ConfigModel):
    language: str = "en-US"
    text: str = Field(max_length=RELEASE_NOTES_LIMIT)


class Listing(ConfigModel):
    language: str = "en-US"
    title: str | None = Field(default=None, max_length=LISTING_LIMITS["title"])
    short_description: str | None = Field(
        default=None, max_length=LISTING_LIMITS["short_description"]
    )
    full_description: str | None = Field(
        default=None, max_length=LISTING_LIMITS["full_description"]
    )


class AssetConfig(ConfigModel):
    icon: str | None = None
    feature_graphic: str | None = None
    phone_screenshots: list[str] = Field(default_factory=list)
    ai_generated: list[str] | None = None

    @field_validator("ai_generated")
    @classmethod
    def valid_ai_assets(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if any(not re.fullmatch(r"icon|feature_graphic|phone_screenshots\.\d+", x) for x in values):
            raise ValueError(
                "AI asset IDs must be icon, feature_graphic or phone_screenshots.<index>"
            )
        return list(dict.fromkeys(values))


class DeveloperFacts(ConfigModel):
    contains_ads: bool | None = None
    uses_advertising_id: bool | None = None
    login_required: bool | None = None
    target_audience: str | None = None
    privacy_policy_url: str | None = None
    account_deletion_url: str | None = None
    data_safety_reviewed: bool = False
    support_email: str | None = None

    @field_validator("support_email")
    @classmethod
    def valid_support_email(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("support_email must be an email address")
        return value


class BuildConfig(ConfigModel):
    gradle_task: str = Field(default="bundleRelease", pattern=r"^:?[\w.-]+(?::[\w.-]+)*$")
    module: str = "app"
    aab_path: str | None = None
    apk_path: str | None = None

    @field_validator("module")
    @classmethod
    def valid_module(cls, value: str) -> str:
        if not re.fullmatch(r"[\w-]+(?::[\w-]+)*", value):
            raise ValueError("module must be a Gradle module path, e.g. app or mobile:app")
        return value

    @property
    def task(self) -> str:
        if self.gradle_task.startswith(":"):
            return self.gradle_task
        return f":{self.module}:{self.gradle_task}"


class PlayConfig(ConfigModel):
    package_name: str | None = None
    default_track: str | None = Field(default="internal", min_length=1)
    release_status: Literal["draft", "completed", "inProgress", "halted"] = "draft"
    service_account_env: str = "PLAYFLOW_GOOGLE_CREDENTIALS"
    browser_profile: str = "~/.local/share/playflow/chromium-profile"
    user_fraction: float | None = Field(default=None, gt=0, lt=1)

    @model_validator(mode="after")
    def validate_rollout(self) -> PlayConfig:
        staged = self.release_status in {"inProgress", "halted"}
        if staged != (self.user_fraction is not None):
            raise ValueError("user_fraction is required only for inProgress or halted releases")
        return self


class ApprovalConfig(ConfigModel):
    require_final_submit_approval: bool = True
    allow_browser_write_actions: bool = False


class BrowserConfig(ConfigModel):
    engine: Literal["chromium", "firefox"] = "chromium"
    firefox_profile_name: str | None = Field(default=None, min_length=1)
    firefox_profile_path: str | None = Field(default=None, min_length=1)
    console_url: str = PLAY_CONSOLE

    @field_validator("console_url")
    @classmethod
    def valid_console_url(cls, value: str) -> str:
        if not is_console_url(value):
            raise ValueError("Use an HTTPS Play Console URL without query parameters or fragment")
        return value


class TestingConfig(ConfigModel):
    mode: Literal["internal", "closed", "open"]
    google_groups: list[str] = Field(default_factory=list)
    country_scope: Literal["all", "selected"] | None = None
    countries: list[str] = Field(default_factory=list)

    @field_validator("google_groups")
    @classmethod
    def valid_groups(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values]
        if any(
            not re.fullmatch(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", x) for x in normalized
        ):
            raise ValueError("Google Groups must be supplied as email addresses")
        return list(dict.fromkeys(normalized))

    @field_validator("countries")
    @classmethod
    def valid_countries(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in values]
        if any(not re.fullmatch(r"[A-Z]{2}", value) for value in normalized):
            raise ValueError("countries must use two-letter country codes")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_country_scope(self) -> TestingConfig:
        if self.country_scope == "selected" and not self.countries:
            raise ValueError("selected country scope requires a nonempty countries list")
        if self.country_scope != "selected" and self.countries:
            raise ValueError("countries can only be supplied with country_scope: selected")
        return self


class Manifest(ConfigModel):
    schema_version: Literal[1] = 1
    app_name: str = Field(min_length=1)
    project_dir: str = "."
    state_dir: str | None = Field(default=None, min_length=1)
    repository_url: str | None = Field(default=None, pattern=r"^https://[^\s]+$")
    build: BuildConfig = Field(default_factory=BuildConfig)
    play: PlayConfig = Field(default_factory=PlayConfig)
    developer_facts: DeveloperFacts = Field(default_factory=DeveloperFacts)
    listing: list[Listing] = Field(default_factory=list)
    assets: AssetConfig = Field(default_factory=AssetConfig)
    release_notes: list[ReleaseNotes] = Field(default_factory=list)
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    testing: TestingConfig | None = None

    def resolved_state_dir(self, manifest_path: Path) -> Path | None:
        if self.state_dir is None:
            return None
        path = Path(self.state_dir).expanduser()
        return (path if path.is_absolute() else manifest_path.parent / path).resolve()

    def resolved_project_dir(self, manifest_path: Path) -> Path:
        p = Path(self.project_dir).expanduser()
        if not p.is_absolute():
            p = manifest_path.parent / p
        p = p.resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"Android project directory not found: {p}")
        return p
