from helpers import raw_item, sid

from tastepipe.silver import parse
from tastepipe.silver.parse import parse_item


def codes(result):
    return [(i.code, i.severity) for i in result.issues]


def test_valid_item_parses_and_normalizes():
    r = parse_item(raw_item(name="Song - 2011 Remaster", artist="Sigur Rós"))
    assert r.track is not None and r.issues == []
    assert (r.track.title_norm, r.track.artist_norm) == ("song", "sigur ros")
    assert r.track.isrc == "USRC17607839"


def test_deleted_track_is_quarantined():
    assert codes(parse_item({"added_at": None, "is_local": False, "track": None})) == [
        (parse.NULL_TRACK, "error")
    ]


def test_local_file_is_quarantined():
    item = raw_item()
    item["is_local"] = True
    assert codes(parse_item(item)) == [(parse.LOCAL_TRACK, "error")]


def test_podcast_episode_is_quarantined():
    assert codes(parse_item(raw_item(type="episode"))) == [(parse.NOT_A_TRACK, "error")]


def test_missing_and_malformed_ids():
    assert codes(parse_item(raw_item(id=None))) == [(parse.MISSING_ID, "error")]
    assert codes(parse_item(raw_item(id="short"))) == [(parse.BAD_ID_FORMAT, "error")]


def test_missing_title_and_artist():
    assert codes(parse_item(raw_item(name="  "))) == [(parse.MISSING_TITLE, "error")]
    assert codes(parse_item(raw_item(artists=[]))) == [(parse.MISSING_ARTIST, "error")]


def test_title_that_normalizes_to_nothing_is_rejected():
    assert codes(parse_item(raw_item(name="(Remastered)"))) == [(parse.MISSING_TITLE, "error")]


def test_implausible_durations_are_rejected():
    for bad in (0, 1_000, None, "200000", 10**9, True):
        assert codes(parse_item(raw_item(duration_ms=bad))) == [(parse.BAD_DURATION, "error")], bad


def test_bad_isrc_is_a_warning_and_the_row_survives():
    r = parse_item(raw_item(isrc="NOT-AN-ISRC"))
    assert r.track is not None and r.track.isrc is None
    assert codes(r) == [(parse.BAD_ISRC, "warning")]


def test_bad_timestamp_is_a_warning_and_the_row_survives():
    r = parse_item(raw_item(added_at="yesterday-ish"))
    assert r.track is not None and r.track.added_at is None
    assert codes(r) == [(parse.BAD_ADDED_AT, "warning")]


def test_accepts_item_key_variant():
    raw = raw_item(5)
    raw["item"] = raw.pop("track")
    r = parse_item(raw)
    assert r.track is not None and r.track.spotify_track_id == sid(5)


def test_non_object_items_do_not_crash():
    for junk in (None, 5, "x", []):
        assert codes(parse_item(junk)) == [(parse.SCHEMA_ERROR, "error")]
