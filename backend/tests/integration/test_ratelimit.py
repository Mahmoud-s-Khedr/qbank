from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from qbank.config import get_settings
from qbank.security.ratelimit import check_limits, client_ip


@pytest.mark.integration
def test_fixed_window_limits_and_reset() -> None:
    ident = uuid4().hex
    limits = [(f"ip-{ident}", 3), (f"email-{ident}", 2)]
    check_limits("test", limits, 60, now=601)
    check_limits("test", limits, 60, now=602)
    with pytest.raises(HTTPException) as exc:
        check_limits("test", limits, 60, now=603)
    assert exc.value.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert exc.value.headers == {"Retry-After": "57"}
    with pytest.raises(HTTPException):
        check_limits("test", [(f"ip-{ident}", 3), (f"other-{ident}", 2)], 60, now=604)
    check_limits("test", limits, 60, now=660)


def test_trusted_proxy_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QBANK_TRUSTED_PROXIES", '["10.0.0.0/8"]')
    get_settings.cache_clear()
    try:

        def request(peer: str, forwarded: str) -> Request:
            return Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/",
                    "headers": [(b"x-forwarded-for", forwarded.encode())],
                    "client": (peer, 123),
                }
            )

        assert client_ip(request("192.0.2.1", "1.1.1.1")) == "192.0.2.1"
        assert client_ip(request("10.0.0.1", "1.1.1.1, 192.0.2.1, 10.0.0.2")) == "192.0.2.1"
        assert client_ip(request("10.0.0.1", "not-an-ip")) == "10.0.0.1"
    finally:
        get_settings.cache_clear()
