"""Normalise the many YouTube URL shapes into an embeddable video id.

Doctors paste whatever the share button gave them — youtu.be short links,
watch?v=, /embed/, /shorts/, sometimes with playlist or timestamp params. The
player needs the bare id, so we extract it once on the server rather than
re-deriving it in every frontend.
"""

import re
from urllib.parse import parse_qs, urlparse

# A YouTube id is 11 chars of URL-safe base64.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_PATH_PREFIXES = ("/embed/", "/shorts/", "/v/", "/live/")


def youtube_video_id(url: str) -> str | None:
    """Return the 11-character video id, or None if this isn't a YouTube URL."""
    if not url:
        return None

    raw = url.strip()
    # A bare id pasted directly.
    if _ID_RE.match(raw):
        return raw

    if "://" not in raw:
        raw = f"https://{raw}"

    try:
        parsed = urlparse(raw)
    except ValueError:
        return None

    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path or ""

    if host in {"youtu.be"}:
        candidate = path.lstrip("/").split("/")[0]
        return candidate if _ID_RE.match(candidate) else None

    if host not in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
        return None

    if path == "/watch":
        values = parse_qs(parsed.query).get("v", [])
        candidate = values[0] if values else ""
        return candidate if _ID_RE.match(candidate) else None

    for prefix in _PATH_PREFIXES:
        if path.startswith(prefix):
            candidate = path[len(prefix) :].split("/")[0]
            return candidate if _ID_RE.match(candidate) else None

    return None
