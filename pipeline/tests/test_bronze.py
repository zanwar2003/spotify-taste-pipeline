from tastepipe.bronze import canonical_json, payload_sha256


def test_hash_ignores_key_order():
    a = {"id": "1", "items": [{"x": 1, "y": 2}]}
    b = {"items": [{"y": 2, "x": 1}], "id": "1"}
    assert payload_sha256(a) == payload_sha256(b)


def test_hash_changes_when_payload_changes():
    assert payload_sha256({"a": 1}) != payload_sha256({"a": 2})


def test_canonical_json_keeps_unicode():
    assert canonical_json({"name": "Beyoncé"}) == '{"name":"Beyoncé"}'
