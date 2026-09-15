"""Resolve the rate-limit identity of a client from what the deployment edge provides.

Pure logic. Which header (if any) is trusted is a deployment decision made in
configuration, not something guessed from request contents.
"""

import re
from typing import Mapping, Optional

# Key used when nothing identifies the client (local development, no proxy header).
LOCAL_CLIENT_KEY = "local"

MAX_CLIENT_KEY_LENGTH = 128

# Header values may only contain printable ASCII; anything else is treated as tampering.
_PRINTABLE_ASCII = re.compile(r"^[\x21-\x7e]+$")


class ClientIdentityError(ValueError):
    """The deployment expects a trusted identity header and the request lacks a valid one."""


def _last_forwarded_entry(header_value: str) -> str:
    # A single trusted proxy appends the real client as the last entry; earlier
    # entries are client-supplied and must not be trusted.
    return header_value.rsplit(",", 1)[-1].strip()


def _lookup_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def resolve_client_key(
    connection_ip: Optional[str],
    headers: Mapping[str, str],
    trusted_header: Optional[str],
) -> str:
    """Return the key the limiter should charge this request to.

    With ``trusted_header`` unset the connection address is used, falling back
    to a shared local key when there is none. With it set, the header is
    required and the request is rejected (fail closed) when it is missing or
    malformed.
    """
    if not trusted_header:
        return connection_ip if connection_ip else LOCAL_CLIENT_KEY

    raw_value = _lookup_header(headers, trusted_header)
    if raw_value is None:
        raise ClientIdentityError(f"Required client identity header {trusted_header!r} is missing.")

    client_key = _last_forwarded_entry(raw_value)
    if not client_key or len(client_key) > MAX_CLIENT_KEY_LENGTH or not _PRINTABLE_ASCII.match(client_key):
        raise ClientIdentityError(f"Client identity header {trusted_header!r} has an invalid value.")
    return client_key
