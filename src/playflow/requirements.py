"""Verified subset of Google Play requirements; not a complete policy catalogue."""

RULESET_VERSION = "2026-10-18.1"
VERIFIED_ON = "2026-10-18"
RELEASE_SOURCE = "https://support.google.com/googleplay/android-developer/answer/9859348"
RELEASE_NOTES_LIMIT = 500
LISTING_SOURCE = "https://support.google.com/googleplay/android-developer/answer/9859152"
ASSET_SOURCE = "https://support.google.com/googleplay/android-developer/answer/9866151"
TESTERS_SOURCE = "https://developers.google.com/android-publisher/api-ref/rest/v3/edits.testers"
COUNTRIES_SOURCE = (
    "https://developers.google.com/android-publisher/api-ref/rest/v3/edits.countryavailability"
)
LISTING_LIMITS = {"title": 30, "short_description": 80, "full_description": 4000}
ICON_SIZE = (512, 512)
ICON_MAX_BYTES = 1024 * 1024
FEATURE_SIZE = (1024, 500)
PHONE_SCREENSHOT_COUNT = (2, 8)
SCREENSHOT_DIMENSIONS = (320, 3840)
SCREENSHOT_MAX_RATIO = 2
