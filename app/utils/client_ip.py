"""Work out who is actually calling, given we may sit behind a proxy.

``X-Forwarded-For`` is just a request header: anyone can send one. It may only be
believed when the machine that opened the connection is a reverse proxy we put
there ourselves, listed in ``TRUSTED_PROXY_RANGES``. Without that check an
attacker rotates the header and every per-IP limit becomes decorative.
"""

import ipaddress
from typing import Optional

from fastapi import Request

from ..core import settings


def peer_is_trusted_proxy(peer_ip: str) -> bool:
    """True when the direct peer is one of our configured reverse proxies."""
    if not peer_ip:
        return False
    try:
        peer = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False

    for raw in str(settings.trusted_proxy_ranges or "").split(","):
        entry = raw.strip()
        if not entry:
            continue
        try:
            network = ipaddress.ip_network(
                entry if "/" in entry else f"{entry}/{peer.max_prefixlen}",
                strict=False,
            )
        except ValueError:
            continue
        if peer in network:
            return True
    return False


def client_ip(request: Request) -> str:
    """The caller's IP, trusting forwarded headers only from our own proxies."""
    peer_ip = (
        str(request.client.host).strip()
        if request.client and request.client.host
        else ""
    )
    if not peer_ip:
        return ""

    if peer_is_trusted_proxy(peer_ip):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Read RIGHT to left, not left to right.
            #
            # nginx here uses `$proxy_add_x_forwarded_for`, which APPENDS to
            # whatever the client sent. A request carrying
            # `X-Forwarded-For: 1.2.3.4` arrives as "1.2.3.4, <real client>", so
            # the leftmost entry is chosen by the attacker. Only the entries our
            # own proxies appended can be believed, and those are on the right.
            # Skipping trailing trusted-proxy hops makes this correct for a
            # chain of proxies too, not just the single nginx in front today.
            for candidate in reversed([p.strip() for p in forwarded.split(",")]):
                if not candidate:
                    continue
                try:
                    ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if peer_is_trusted_proxy(candidate):
                    continue  # another hop of ours, keep walking left
                return candidate[:64]
    return peer_ip[:64]


def rate_limit_key(request: Request) -> Optional[str]:
    """Bucket key for the global rate limiter.

    Falls back to the raw forwarded header when no trusted proxy range is
    configured, which is what this deployment did before the range existed —
    tightening that without the operator setting TRUSTED_PROXY_RANGES would put
    every request behind the load balancer into one shared bucket.
    """
    peer_ip = (
        str(request.client.host).strip()
        if request.client and request.client.host
        else ""
    )
    if not peer_ip:
        return None

    configured = bool(str(settings.trusted_proxy_ranges or "").strip())
    if not configured:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
        return peer_ip[:64]

    return client_ip(request) or peer_ip[:64]


def throttle_ip(request: Request) -> Optional[str]:
    """Client IP for per-IP login throttling, or None when it is not meaningful.

    Behind a reverse proxy that has not been declared in TRUSTED_PROXY_RANGES,
    every request arrives from the proxy's own address. Bucketing on that would
    add up the whole school's failed logins and lock everybody out at once — so
    return None instead and let the per-account counter do the work. That
    counter is the stronger signal anyway: it cannot be dodged by changing IP.
    """
    peer_ip = (
        str(request.client.host).strip()
        if request.client and request.client.host
        else ""
    )
    if not peer_ip:
        return None

    if str(settings.trusted_proxy_ranges or "").strip():
        return client_ip(request) or None

    # No proxy configured. A forwarded header means something in front of us is
    # rewriting the peer address, so neither value identifies one caller.
    if request.headers.get("X-Forwarded-For"):
        return None
    return peer_ip[:64]
