"""Canonicalize public job URLs without weakening SSRF boundaries."""

from __future__ import annotations

import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from career_agent.errors import CareerError, ErrorCode

_TRACKING_PARAMETERS = {"fbclid", "gclid", "msclkid"}
_REDIRECT_PARAMETERS = {"continue", "next", "redirect", "target", "url"}


def _invalid(message: str, url: str) -> CareerError:
    return CareerError(ErrorCode.INVALID_INPUT, message, {"url": url})


def _validate_public_host(hostname: str, original: str) -> str:
    normalized = hostname.rstrip(".").casefold()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(
        (".local", ".localhost", ".internal")
    ):
        raise _invalid("Job URL must use a public host", original)
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            return normalized.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise _invalid("Job URL host is invalid", original) from error
    if not address.is_global:
        raise _invalid("Job URL must not target a local or private address", original)
    return address.compressed


def canonicalize_public_http_url(url: str) -> str:
    """Return a stable public HTTP(S) URL with known tracking removed."""

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise _invalid("Job URL is malformed", url) from error
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise _invalid("Job URL must use HTTP or HTTPS", url)
    if parsed.username is not None or parsed.password is not None:
        raise _invalid("Job URL must not contain credentials", url)
    host = _validate_public_host(parsed.hostname, url)
    if port is not None and port != (443 if scheme == "https" else 80):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    retained: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered.startswith("utm_") or lowered in _TRACKING_PARAMETERS:
            continue
        if lowered in _REDIRECT_PARAMETERS and value.casefold().startswith(("http://", "https://")):
            canonicalize_public_http_url(value)
        retained.append((key, value))
    retained.sort()
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, urlencode(retained, doseq=True), ""))
