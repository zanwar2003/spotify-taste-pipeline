from fakes import cat, ref, sug

from tastepipe.agent.fit import fit_length, is_short, total_ms
from tastepipe.agent.match import build_query, pick_match

MIN = 60_000


# ------------------------------------------------------------------ verification guard


def test_exact_match_is_accepted():
    m = pick_match(sug("Song", "Artist"), [cat(1, "Song", "Artist")])
    assert m is not None and m.parsed.title_norm == "song"


def test_remaster_in_spotify_title_still_matches_plain_suggestion():
    assert pick_match(sug("Song", "Artist"), [cat(1, "Song - 2011 Remaster", "Artist")])


def test_wrong_artist_is_rejected():
    assert pick_match(sug("Song", "Artist"), [cat(1, "Song", "Somebody Else")]) is None


def test_different_song_is_rejected():
    assert pick_match(sug("Song", "Artist"), [cat(1, "Completely Different", "Artist")]) is None


def test_live_version_is_not_accepted_for_a_studio_request():
    assert pick_match(sug("Song", "Artist"), [cat(1, "Song - Live", "Artist")]) is None


def test_live_request_requires_a_live_version():
    assert pick_match(sug("Song (Live)", "Artist"), [cat(1, "Song", "Artist")]) is None
    assert pick_match(sug("Song (Live)", "Artist"), [cat(2, "Song - Live", "Artist")])


def test_collaboration_suggestion_matches_either_credited_artist():
    assert pick_match(sug("Song", "Artist & Guest"), [cat(1, "Song", "Artist")])


def test_best_scoring_candidate_wins():
    close = cat(1, "Songs", "Artist")  # 0.909 title similarity
    exact = cat(2, "Song", "Artist")
    m = pick_match(sug("Song", "Artist"), [close, exact])
    assert m is not None and m.raw is exact


def test_invalid_candidates_are_skipped():
    bad = cat(1, "Song", "Artist")
    bad["duration_ms"] = 0
    assert pick_match(sug("Song", "Artist"), [bad]) is None


def test_quotes_cannot_break_out_of_the_query():
    q = build_query(sug('He said "hi"', 'Art"ist'))
    assert q.count('"') == 4


# --------------------------------------------------------------------- length fitting


def dur(n, minutes):
    return ref(n, duration_ms=int(minutes * MIN))


def test_fills_to_target_without_big_overshoot():
    tracks = [dur(i, 3) for i in range(1, 8)]
    out = fit_length([], tracks, 10 * MIN, prefer_new=False)
    assert 9 * MIN <= total_ms(out) <= 11 * MIN
    assert [t.spotify_track_id for t in out] == [t.spotify_track_id for t in tracks[: len(out)]]


def test_skips_a_track_that_would_overshoot_and_uses_a_shorter_one():
    tracks = [dur(1, 4), dur(2, 9), dur(3, 3)]
    out = fit_length([], tracks, 8 * MIN, prefer_new=False)
    assert [t.spotify_track_id for t in out] == [tracks[0].spotify_track_id, tracks[2].spotify_track_id]


def test_prefer_new_keeps_additions_and_trims_older_tracks():
    kept = [dur(i, 3) for i in range(1, 5)]  # 12 min
    new = [dur(10, 3), dur(11, 3)]
    out = fit_length(kept, new, 12 * MIN, prefer_new=True)
    ids = [t.spotify_track_id for t in out]
    assert dur(10, 3).spotify_track_id in ids and dur(11, 3).spotify_track_id in ids
    assert total_ms(out) <= 12 * MIN * 1.1
    # display order: older tracks first, additions last
    assert ids[-2:] == [new[0].spotify_track_id, new[1].spotify_track_id]


def test_without_prefer_new_the_tail_is_trimmed():
    kept = [dur(i, 3) for i in range(1, 5)]
    out = fit_length(kept, [dur(10, 3)], 12 * MIN, prefer_new=False)
    assert dur(10, 3).spotify_track_id not in [t.spotify_track_id for t in out]


def test_is_short():
    assert is_short([dur(1, 3)], 10 * MIN)
    assert not is_short([dur(1, 3), dur(2, 3), dur(3, 3)], 10 * MIN)


def test_a_credited_name_inside_a_longer_different_name_is_not_a_match():
    # "Artist" appears inside "Wrong Artist" but they are different acts
    assert pick_match(sug("Song", "Wrong Artist"), [cat(1, "Song", "Artist")]) is None


def test_band_names_containing_and_still_match_themselves():
    assert pick_match(sug("Song", "Simon & Garfunkel"), [cat(1, "Song", "Simon and Garfunkel")])
