"""Extract the embeddable shortcode from an Instagram URL.

Instagram serves an iframe at `/{kind}/{shortcode}/embed` which needs no API
key — the oEmbed API does, and requires Facebook App Review, so we use the
iframe. Only individual posts/reels/IGTV can be embedded; a profile or story
link has no shortcode and must fall back to a plain link.

Returns the kind too, because reels are portrait (9:16) and posts are roughly
square — the frontend needs to size the frame differently.
"""

import re
from urllib.parse import urlparse

# Instagram shortcodes are URL-safe base64, typically 11 chars but not fixed.
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,30}$")

# Path segments that carry an embeddable shortcode.
_EMBEDDABLE = {"p": "p", "reel": "reel", "reels": "reel", "tv": "tv"}


def instagram_embed(url: str) -> tuple[str, str] | None:
    """Return (kind, shortcode), or None when the URL isn't embeddable."""
    if not url:
        return None

    raw = url.strip()
    if "://" not in raw:
        raw = f"https://{raw}"

    try:
        parsed = urlparse(raw)
    except ValueError:
        return None

    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in {"instagram.com", "instagr.am"}:
        return None

    segments = [segment for segment in (parsed.path or "").split("/") if segment]
    # Profile-scoped reel links look like /<username>/reel/<code>/.
    for index, segment in enumerate(segments):
        kind = _EMBEDDABLE.get(segment.lower())
        if kind and index + 1 < len(segments):
            code = segments[index + 1]
            return (kind, code) if _CODE_RE.match(code) else None

    return None
