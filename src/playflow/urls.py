"""Shared navigation restrictions for Play Console integrations."""

from urllib.parse import urlsplit

PLAY_CONSOLE = "https://play.google.com/console/"


def is_console_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "play.google.com"
        and (parsed.path == "/console" or parsed.path.startswith("/console/"))
        and not parsed.query
        and not parsed.fragment
    )
