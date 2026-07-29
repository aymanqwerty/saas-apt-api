"""Unit tests for the MSG91 WhatsApp (template) notifier.

Variable ORDER is the fragile part: values fill {{1}}..{{n}} of a template whose
wording lives in Meta, so a reordering here silently sends a wrong-but-valid
message. These tests pin the mapping.
"""

import httpx
import pytest

from app.services.notifications import (
    TEMPLATE_APPOINTMENT_CONFIRMED,
    TEMPLATE_PAYMENT_LINK,
    TEMPLATE_REVIEW_LINK,
    ConsoleNotifier,
    Message,
    NotificationError,
    get_notifier,
)
from app.services.notifications.msg91_whatsapp_notifier import (
    MSG91_WA_URL,
    Msg91WhatsAppNotifier,
    _to_wa_digits,
)

TEMPLATES = {
    TEMPLATE_APPOINTMENT_CONFIRMED: "appointment_confirmed",
    TEMPLATE_PAYMENT_LINK: "payment_link",
}


class _FakeResponse:
    def __init__(self, payload: dict | None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _notifier() -> Msg91WhatsAppNotifier:
    return Msg91WhatsAppNotifier("wa-key", "919039515379", TEMPLATES, "en", "", "91")


def _message() -> Message:
    return Message(
        template=TEMPLATE_APPOINTMENT_CONFIRMED,
        variables=("Dr. Surbhi Patne", "BSP Sector 9", "2026-08-05", "10:30 AM", "3", "APT-Q7"),
        text="free-form fallback",
    )


def test_sends_template_with_positional_body_variables(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _FakeResponse({"type": "success", "request_id": "abc"})

    monkeypatch.setattr(httpx, "post", fake_post)
    _notifier().send("+91-7970871477", _message())

    assert captured["url"] == MSG91_WA_URL
    body = captured["json"]
    assert body["integrated_number"] == "919039515379"
    assert body["content_type"] == "template"

    template = body["payload"]["template"]
    assert template["name"] == "appointment_confirmed"
    assert template["language"] == {"code": "en", "policy": "deterministic"}
    # namespace omitted entirely when not configured
    assert "namespace" not in template

    entry = template["to_and_components"][0]
    assert entry["to"] == ["917970871477"]
    # Order is the contract: body_1..body_6 in the order the caller supplied.
    assert entry["components"] == {
        "body_1": {"type": "text", "value": "Dr. Surbhi Patne"},
        "body_2": {"type": "text", "value": "BSP Sector 9"},
        "body_3": {"type": "text", "value": "2026-08-05"},
        "body_4": {"type": "text", "value": "10:30 AM"},
        "body_5": {"type": "text", "value": "3"},
        "body_6": {"type": "text", "value": "APT-Q7"},
    }
    assert captured["headers"]["authkey"] == "wa-key"


def test_namespace_included_when_configured(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse({"type": "success"})

    monkeypatch.setattr(httpx, "post", fake_post)
    notifier = Msg91WhatsAppNotifier("k", "919039515379", TEMPLATES, "en", "ns-123", "91")
    notifier.send("9876543210", _message())
    assert captured["json"]["payload"]["template"]["namespace"] == "ns-123"


def test_unmapped_template_raises(monkeypatch) -> None:
    msg = Message(template="something_else", variables=("a",), text="t")
    with pytest.raises(NotificationError, match="No MSG91 WhatsApp template"):
        _notifier().send("9876543210", msg)


def test_logical_error_raises_even_on_http_200(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kw: _FakeResponse({"type": "error", "message": "template not approved"}),
    )
    with pytest.raises(NotificationError, match="template not approved"):
        _notifier().send("9876543210", _message())


def test_http_error_raises(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _FakeResponse({"x": 1}, status_code=401))
    with pytest.raises(NotificationError, match="401"):
        _notifier().send("9876543210", _message())


def test_missing_credentials_raise() -> None:
    with pytest.raises(NotificationError, match="not configured"):
        Msg91WhatsAppNotifier("", "", TEMPLATES).send("9876543210", _message())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7970871477", "917970871477"),
        ("+91-7970871477", "917970871477"),
        ("917970871477", "917970871477"),
    ],
)
def test_number_normalisation(raw: str, expected: str) -> None:
    assert _to_wa_digits(raw, "91") == expected


def test_factory_returns_console_when_selected(monkeypatch) -> None:
    from app.core.config import settings

    # Set explicitly rather than relying on the ambient .env, which varies.
    monkeypatch.setattr(settings, "notification_provider", "console")
    assert isinstance(get_notifier(), ConsoleNotifier)


def test_factory_builds_msg91_whatsapp_from_settings(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "notification_provider", "msg91_whatsapp")
    monkeypatch.setattr(settings, "msg91_wa_authkey", "k")
    monkeypatch.setattr(settings, "msg91_wa_integrated_number", "919039515379")
    monkeypatch.setattr(settings, "msg91_wa_template_review_link", "review_link")

    notifier = get_notifier()
    assert isinstance(notifier, Msg91WhatsAppNotifier)
    # All three logical keys must be mapped, or that message silently fails.
    assert set(notifier._templates) == {
        TEMPLATE_APPOINTMENT_CONFIRMED,
        TEMPLATE_PAYMENT_LINK,
        TEMPLATE_REVIEW_LINK,
    }


def test_factory_rejects_msg91_whatsapp_without_credentials(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "notification_provider", "msg91_whatsapp")
    monkeypatch.setattr(settings, "msg91_wa_authkey", "")
    with pytest.raises(NotificationError, match="MSG91_WA_AUTHKEY"):
        get_notifier()
