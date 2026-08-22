from __future__ import annotations

import pytest

from ccm_casework.canonical import (
    CanonicalizationError,
    canonical_json,
    require_digest,
    sha256_digest,
    stable_identifier,
)


def test_canonical_json_orders_keys_and_hashes_deterministically() -> None:
    assert canonical_json({"b": 2, "a": [True, None]}) == b'{"a":[true,null],"b":2}'
    assert sha256_digest({"a": 1, "b": 2}) == sha256_digest({"b": 2, "a": 1})


def test_canonical_rejects_unsafe_values_digests_and_identifiers() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json(1.5)
    with pytest.raises(CanonicalizationError):
        canonical_json(9_007_199_254_740_992)
    with pytest.raises(CanonicalizationError):
        canonical_json({1: "not a string key"})
    with pytest.raises(CanonicalizationError):
        require_digest("sha256:UPPER")
    with pytest.raises(CanonicalizationError):
        stable_identifier("Bad", {"value": 1})
