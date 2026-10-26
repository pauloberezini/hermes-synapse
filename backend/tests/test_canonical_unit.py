from backend.canonical import canonical_json, sha256_hex


def test_key_order_does_not_change_hash():
    assert sha256_hex(canonical_json({"b": 1, "a": 2})) == sha256_hex(canonical_json({"a": 2, "b": 1}))


def test_unicode_kept_not_escaped():
    assert canonical_json({"t": "שלום"}) == '{"t":"שלום"}'


def test_no_whitespace():
    assert " " not in canonical_json({"a": [1, 2]})
