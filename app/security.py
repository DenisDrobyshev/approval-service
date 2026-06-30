"""Redaction helpers.

The product around this service handles secrets, tokens, emails, storage
keys and signed/provider URLs. This service must never let any of those
leak into public responses, logs or events. It only ever stores opaque
identifiers plus client-supplied free text (title/description), but we still
scrub free text defensively before it reaches logs and events.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = "[REDACTED]"

# Ordered list of (compiled pattern, replacement). Order matters: more
# specific patterns run before the broad URL catch-all.
_RULES: list[tuple[re.Pattern[str], str]] = [
    # Authorization: Bearer <token>
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED]"),
    # Emails
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    # Common API/secret token shapes (Stripe, GitHub, Slack, generic sk-/pk-).
    # Body allows internal '-'/'_' so multi-segment keys (sk_live_...) match.
    (
        re.compile(
            r"(?i)\b(?:sk|pk|rk|ghp|gho|ghs|ghu|xox[baprs])[-_][A-Za-z0-9][A-Za-z0-9_\-]{6,}"
        ),
        "[REDACTED_TOKEN]",
    ),
    # AWS access key id
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    # JWT-ish (three base64url segments)
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
        "[REDACTED_JWT]",
    ),
    # Any URL (covers signed URLs, provider URLs, storage URLs)
    (re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^\s\"'<>]+"), "[REDACTED_URL]"),
]

# Object keys whose values are always dropped, regardless of content.
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "api_key",
        "apikey",
        "email",
        "storage_key",
        "signed_url",
        "provider_url",
        "provider_payload",
        "x-scopes",
    }
)


def redact_text(value: str | None) -> str | None:
    """Scrub a free-text string of anything that looks sensitive."""
    if value is None:
        return None
    result = value
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)
    return result


def redact_obj(obj: Any) -> Any:
    """Recursively redact a JSON-like structure.

    Sensitive keys are replaced wholesale; every other string is passed
    through :func:`redact_text`.
    """
    if isinstance(obj, dict):
        return {
            key: (_PLACEHOLDER if key.lower() in _SENSITIVE_KEYS else redact_obj(val))
            for key, val in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj
