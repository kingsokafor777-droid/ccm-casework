"""Strict canonical JSON and deterministic identity primitives for ccm-casework."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias

CANONICALIZATION_PROFILE = "ccm-jcs/v1"
HASH_ALGORITHM = "sha256"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

JsonPrimitive: TypeAlias = bool | int | str | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


class CanonicalizationError(ValueError):
    """Raised when an input cannot enter the ccm-casework canonicalization profile."""


def _validate_string(value: str) -> None:
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise CanonicalizationError("strings must not contain lone Unicode surrogates") from exc


def _utf16_sort_key(value: str) -> bytes:
    _validate_string(value)
    return value.encode("utf-16-be")


def _encode_string(value: str) -> str:
    _validate_string(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalizationError(
                "integers outside the I-JSON safe range must be represented as strings"
            )
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("non-finite numbers are not valid canonical JSON")
        raise CanonicalizationError(
            "floating-point values are forbidden by ccm-jcs/v1; use a normalized decimal string"
        )
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalizationError("object keys must be strings")
        fields: list[str] = []
        for key in sorted(value.keys(), key=_utf16_sort_key):
            fields.append(f"{_encode_string(key)}:{_canonicalize(value[key])}")
        return "{" + ",".join(fields) + "}"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return "[" + ",".join(_canonicalize(item) for item in value) + "]"
    raise CanonicalizationError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Return UTF-8 bytes for the strict ccm-casework canonical JSON profile."""

    return _canonicalize(value).encode("utf-8")


def sha256_digest(value: Any) -> str:
    """Return a prefixed SHA-256 digest over canonical JSON bytes."""

    return f"{HASH_ALGORITHM}:{hashlib.sha256(canonical_json(value)).hexdigest()}"


def require_digest(value: str) -> str:
    """Validate a lower-case, algorithm-prefixed digest."""

    if not HASH_PATTERN.fullmatch(value):
        message = "digest must be a sha256:<64 lowercase hexadecimal characters> value"
        raise CanonicalizationError(message)
    return value


def stable_identifier(prefix: str, value: Any, *, length: int = 24) -> str:
    """Derive a deterministic, non-secret identifier from a canonical projection."""

    if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", prefix):
        raise CanonicalizationError("identifier prefix must be lower-case snake_case")
    if not 12 <= length <= 64:
        raise CanonicalizationError("identifier digest length must be between 12 and 64")
    digest = sha256_digest(value).split(":", 1)[1]
    return f"{prefix}_{digest[:length]}"
