"""Unit tests for the MSG91 OTP sender.

These pin down the request shape deliberately: posting our flow template to
MSG91's *OTP* endpoint returns `type: success` and then silently drops the
message, so a wrong endpoint or placeholder name is invisible at runtime.
"""

import httpx
import pytest

from app.services.otp import get_otp_sender
from app.services.otp.base import OtpError
from app.services.otp.console_sender import ConsoleOtpSender
from app.services.otp.msg91_sender import MSG91_FLOW_URL, Msg91OtpSender, _to_msg91_mobile


class _FakeResponse:
    def __init__(self, payload: dict | None, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text or str(payload)

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _sender() -> Msg91OtpSender:
    return Msg91OtpSender("key", "tmpl-id", "THEiSC", "91", "var")


def test_posts_flow_endpoint_with_named_variable(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _FakeResponse({"message": "req-123", "type": "success"})

    monkeypatch.setattr(httpx, "post", fake_post)
    _sender().send("+91-7970871477", "445566", doctor_name="Dr Test")

    assert captured["url"] == MSG91_FLOW_URL
    body = captured["json"]
    assert body["template_id"] == "tmpl-id"
    assert body["sender"] == "THEiSC"
    # The code must arrive under the template's placeholder name, not "otp".
    assert body["recipients"] == [{"mobiles": "917970871477", "var": "445566"}]
    assert captured["headers"]["authkey"] == "key"


def test_custom_variable_name_is_honoured(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse({"type": "success"})

    monkeypatch.setattr(httpx, "post", fake_post)
    Msg91OtpSender("key", "tmpl", "S", "91", "otp_code").send("9876543210", "1234", doctor_name="D")

    assert captured["json"]["recipients"][0]["otp_code"] == "1234"


def test_logical_error_raises_even_on_http_200(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: _FakeResponse({"type": "error", "message": "bad template"})
    )
    with pytest.raises(OtpError, match="bad template"):
        _sender().send("9876543210", "1234", doctor_name="D")


def test_network_failure_retries_then_raises(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(OtpError):
        _sender().send("9876543210", "1234", doctor_name="D")
    assert calls["n"] == 2  # one retry


def test_missing_config_raises() -> None:
    with pytest.raises(OtpError, match="not configured"):
        Msg91OtpSender("", "", "").send("9876543210", "1234", doctor_name="D")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7970871477", "917970871477"),
        ("+91-7970871477", "917970871477"),
        ("917970871477", "917970871477"),
        ("+1 415 555 0100", "14155550100"),
    ],
)
def test_mobile_normalisation(raw: str, expected: str) -> None:
    assert _to_msg91_mobile(raw, "91") == expected


def test_factory_defaults_to_console() -> None:
    assert isinstance(get_otp_sender(), ConsoleOtpSender)


def test_factory_rejects_msg91_without_credentials(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "otp_provider", "msg91")
    monkeypatch.setattr(settings, "msg91_authkey", "")
    with pytest.raises(OtpError, match="MSG91_AUTHKEY"):
        get_otp_sender()
