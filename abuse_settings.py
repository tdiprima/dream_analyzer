"""Abuse-control configuration loaded from environment variables.

Every value has a sane default and is validated at import time so a bad
deployment fails at startup, not on the first request.
"""

import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional

DEFAULT_PER_CLIENT_LIMIT = 5
DEFAULT_GLOBAL_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_OUTPUT_TOKENS = 1500

# Hard ceiling regardless of configuration; four prose sections never need more.
MAX_ALLOWED_OUTPUT_TOKENS = 8000

# RFC 7230 header-name token characters.
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,100}$")


@dataclass(frozen=True)
class AbuseSettings:
    """Rate-limit and model-cost ceilings for analysis requests."""

    per_client_limit: int
    global_limit: int
    window_seconds: int
    max_output_tokens: int
    # Header set by a trusted reverse proxy that identifies the real client.
    # None means "use the connection address" (single-process, no proxy).
    client_id_header: Optional[str]


class AbuseSettingsError(ValueError):
    """Raised when an abuse-control environment variable is invalid."""


def _read_positive_int(env: Mapping[str, str], name: str, default: int, maximum: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise AbuseSettingsError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1 or value > maximum:
        raise AbuseSettingsError(f"{name} must be between 1 and {maximum}, got {value}")
    return value


def _read_header_name(env: Mapping[str, str], name: str) -> Optional[str]:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return None
    value = raw.strip()
    if not _HEADER_NAME.match(value):
        raise AbuseSettingsError(f"{name} must be a valid HTTP header name, got {raw!r}")
    return value


def load_abuse_settings(env: Mapping[str, str] = os.environ) -> AbuseSettings:
    """Parse and validate abuse-control settings from ``env``."""
    settings = AbuseSettings(
        per_client_limit=_read_positive_int(env, "RATE_LIMIT_PER_CLIENT", DEFAULT_PER_CLIENT_LIMIT, 10_000),
        global_limit=_read_positive_int(env, "RATE_LIMIT_GLOBAL", DEFAULT_GLOBAL_LIMIT, 1_000_000),
        window_seconds=_read_positive_int(env, "RATE_LIMIT_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS, 86_400),
        max_output_tokens=_read_positive_int(
            env, "ANALYSIS_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, MAX_ALLOWED_OUTPUT_TOKENS
        ),
        client_id_header=_read_header_name(env, "CLIENT_ID_HEADER"),
    )
    if settings.per_client_limit > settings.global_limit:
        raise AbuseSettingsError(
            "RATE_LIMIT_PER_CLIENT must not exceed RATE_LIMIT_GLOBAL "
            f"({settings.per_client_limit} > {settings.global_limit})"
        )
    return settings
