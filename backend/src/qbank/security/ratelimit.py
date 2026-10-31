"""Redis-backed fixed-window limits. All keys in a decision are updated atomically."""

import hashlib
import ipaddress
import time
from math import ceil

from fastapi import HTTPException, Request
from redis import Redis

from qbank.config import get_settings

_SCRIPT = """
local exceeded = 0
for i, key in ipairs(KEYS) do
    local n = redis.call('INCR', key)
    if n == 1 then redis.call('EXPIRE', key, ARGV[1]) end
    if n > tonumber(ARGV[i + 1]) then exceeded = 1 end
end
return exceeded
"""


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(peer)
        trusted = any(
            address in ipaddress.ip_network(net, strict=False)
            for net in get_settings().trusted_proxies
        )
    except ValueError:
        return peer
    if not trusted:
        return peer
    forwarded = request.headers.get("x-forwarded-for", "").split(",")
    # Walk from the trusted proxy toward the client; never trust entries before an untrusted hop.
    for hop in reversed(forwarded):
        try:
            candidate = ipaddress.ip_address(hop.strip())
        except ValueError:
            return peer
        if not any(
            candidate in ipaddress.ip_network(net, strict=False)
            for net in get_settings().trusted_proxies
        ):
            return str(candidate)
        address = candidate
    return str(address)


def check_limits(
    kind: str, subjects: list[tuple[str, int]], window: int, *, now: float | None = None
) -> None:
    timestamp = time.time() if now is None else now
    bucket = int(timestamp // window)
    retry = max(1, ceil((bucket + 1) * window - timestamp))
    keys = [
        f"qbank:limit:{kind}:{bucket}:{hashlib.sha256(subject.encode()).hexdigest()}"
        for subject, _ in subjects
    ]
    redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
    exceeded = redis.eval(_SCRIPT, len(keys), *keys, retry, *(limit for _, limit in subjects))
    if exceeded:
        raise HTTPException(
            429,
            detail={"code": "rate_limited", "message": "Rate limit exceeded"},
            headers={"Retry-After": str(retry)},
        )


def login_limit(request: Request, email: str) -> None:
    settings = get_settings()
    ip = client_ip(request)
    check_limits(
        "login",
        [
            (f"ip:{ip}", settings.rate_login_ip),
            (f"email:{ip}:{email.strip().lower()}", settings.rate_login_email),
        ],
        settings.rate_login_window,
    )


def user_limit(kind: str, user_id: object) -> None:
    settings = get_settings()
    limit = settings.rate_upload if kind == "upload" else settings.rate_ai
    check_limits(kind, [(str(user_id), limit)], settings.rate_user_window)
