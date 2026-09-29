from helpers import parsed, sid

from tastepipe.silver.resolve import resolve


def test_same_isrc_merges_and_uses_isrc_key():
    res = resolve([parsed(1, isrc="USRC17607839"), parsed(2, isrc="USRC17607839", title="other")])
    assert list(res.tracks) == ["isrc:USRC17607839"]
    assert {r for _, r in res.aliases.values()} == {"same_isrc"}
    assert res.aliases_merged == 1


def test_remaster_with_new_isrc_merges_by_name_and_duration():
    res = resolve(
        [
            parsed(1, isrc="GBUM71029601", duration_ms=248_000),
            parsed(2, isrc="GBUM71100001", duration_ms=249_500),  # remaster: new ISRC
        ]
    )
    assert len(res.tracks) == 1
    reasons = {tid: reason for tid, (_, reason) in res.aliases.items()}
    assert sorted(reasons.values()) == ["normalized_match", "same_isrc"]


def test_live_and_studio_versions_stay_distinct():
    res = resolve([parsed(1, tag=""), parsed(2, tag="live")])
    assert len(res.tracks) == 2 and res.aliases_merged == 0


def test_same_name_far_apart_in_duration_is_not_merged():
    res = resolve([parsed(1, duration_ms=200_000), parsed(2, duration_ms=320_000)])
    assert len(res.tracks) == 2
    assert res.review == []  # gap far too large to even suggest


def test_modest_duration_gap_goes_to_review_not_merge():
    res = resolve([parsed(1, duration_ms=200_000), parsed(2, duration_ms=207_000)])
    assert len(res.tracks) == 2
    assert [p.reason for p in res.review] == ["same_name_duration_gap"]


def test_similar_title_goes_to_review():
    res = resolve([parsed(1, title="dont stop believing"), parsed(2, title="dont stop believin")])
    assert len(res.tracks) == 2
    assert [p.reason for p in res.review] == ["similar_title"]
    assert res.review[0].key_a < res.review[0].key_b


def test_different_artists_never_review_or_merge():
    res = resolve([parsed(1, artist="a"), parsed(2, artist="b")])
    assert len(res.tracks) == 2 and res.review == []


def test_repeated_spotify_id_counts_once():
    res = resolve([parsed(1), parsed(1), parsed(1)])
    assert len(res.tracks) == 1 and len(res.aliases) == 1 and res.aliases_merged == 0


def test_result_is_independent_of_input_order():
    tracks = [
        parsed(1, isrc="AAAA00000001", duration_ms=200_000),
        parsed(2, isrc="AAAA00000002", duration_ms=200_900),
        parsed(3, title="x", duration_ms=100_000),
    ]
    a = resolve(tracks)
    b = resolve(list(reversed(tracks)))
    assert a.aliases == b.aliases and set(a.tracks) == set(b.tracks)


def test_name_key_clusters_in_the_same_block_get_distinct_keys():
    res = resolve([parsed(1, duration_ms=200_000), parsed(2, duration_ms=320_000)])
    assert len(set(res.tracks)) == 2
    assert res.aliases[sid(1)][0] != res.aliases[sid(2)][0]
