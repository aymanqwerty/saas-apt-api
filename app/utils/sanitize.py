"""Server-side sanitisation of doctor-authored rich text.

The blog body is HTML produced by a rich-text editor in the admin panel and is
rendered into patient-facing pages. Trusting the client here would mean a
compromised (or merely curious) doctor account could inject script into every
patient's browser, so the allowlist is applied on the server where it cannot be
bypassed. Client-side sanitisation is a UX nicety; this is the control.
"""

import nh3

# Formatting a doctor plausibly needs, and nothing that executes.
ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "blockquote",
    "ul",
    "ol",
    "li",
    "h2",
    "h3",
    "h4",
    "a",
    "code",
    "pre",
    "hr",
    "span",
}

ALLOWED_ATTRIBUTES = {
    # "rel" is deliberately absent: nh3 sets it itself via link_rel below, and
    # allowing both is rejected as ambiguous.
    "a": {"href", "title", "target"},
    "span": {"class"},
}

# http/https/mailto only — this is what blocks javascript: and data: URLs.
ALLOWED_SCHEMES = {"http", "https", "mailto"}


def sanitize_html(html: str | None) -> str | None:
    """Strip everything outside the allowlist. Returns None for empty input."""
    if html is None:
        return None
    cleaned = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_SCHEMES,
        link_rel="noopener noreferrer",
    )
    return cleaned or None


def strip_html(html: str | None) -> str | None:
    """Plain-text form of rich text, for alt attributes and previews.

    Removing every tag also removes any chance of markup leaking into an
    attribute, which is why alt text is derived rather than passed through.
    """
    if html is None:
        return None
    text = nh3.clean(html, tags=set(), attributes={}).strip()
    # nh3 escapes entities; unescape so alt text reads naturally.
    import html as html_module

    return html_module.unescape(text) or None
