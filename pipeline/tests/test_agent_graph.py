from fakes import PROFILE, FakeLLM, FakeSpotify, cat, ref, sug

from tastepipe.agent.graph import Deps, generate, refine
from tastepipe.agent.models import (
    EditPlan,
    PlaylistRequest,
    ProposeResult,
    ReferencePick,
    ReferencePicks,
)

MIN = 60_000


def req(minutes=10, **kw):
    return PlaylistRequest(
        source_username="zara", intent="workout", mood="upbeat", target_minutes=minutes, **kw
    )


def ids(result):
    return [t.spotify_track_id for t in result.tracks]


def catalog(n=8, duration_ms=200_000):
    return [cat(i, f"Song {i}", "Artist", duration_ms=duration_ms) for i in range(1, n + 1)]


def proposal(*pairs, title=None):
    return ProposeResult(playlist_title=title, suggestions=[sug(t, a) for t, a in pairs])


# ------------------------------------------------------------------------- generate


def test_generate_keeps_only_verified_songs_and_records_the_rest():
    spotify = FakeSpotify(catalog())
    llm = FakeLLM(
        [
            proposal(
                ("Song 1", "Artist"),
                ("Song 2", "Artist"),
                ("Song 3", "Artist"),
                ("Ghost Song", "Nobody"),  # hallucinated: nothing comes back
                ("Song 4", "Wrong Artist"),  # right title, wrong artist
                title="Gym Fuel",
            )
        ]
    )
    result = generate(Deps(llm, spotify), req(10), PROFILE)

    assert ids(result)[:3] == [f"{i:022d}" for i in (1, 2, 3)]
    assert result.title == "Gym Fuel"
    reasons = {(d["title"], d["reason"]) for d in result.dropped}
    assert ("Ghost Song", "not_found") in reasons
    assert ("Song 4", "low_confidence") in reasons  # results came back, but by a different artist
    assert result.stats["suggested"] == 5 and result.stats["verified"] == 3
    assert result.stats["unverified_rate"] == 0.4
    assert result.stats["llm_calls"] == 1


def test_generate_tops_up_when_short_and_does_not_repeat_songs():
    spotify = FakeSpotify(catalog(10))
    llm = FakeLLM(
        [
            proposal(("Song 1", "Artist"), ("Song 2", "Artist"), ("Song 3", "Artist"), title="T"),
            proposal(("Song 1", "Artist"), ("Song 4", "Artist"), ("Song 5", "Artist"), ("Song 6", "Artist")),
        ]
    )
    result = generate(Deps(llm, spotify), req(20), PROFILE)

    assert result.stats["llm_calls"] == 2 and result.stats["rounds"] == 2
    assert len(set(ids(result))) == len(ids(result))  # Song 1 suggested twice, kept once
    second = llm.propose_ctx[1]
    assert not second.first_round
    assert "Artist - Song 1" in second.avoid
    assert result.stats["duplicates_removed"] == 1


def test_generate_stops_after_max_rounds_with_a_partial_playlist():
    spotify = FakeSpotify(catalog(3))
    llm = FakeLLM([proposal(("Song 1", "Artist"))] * 5)
    result = generate(Deps(llm, spotify, max_rounds=3), req(60), PROFILE)
    assert result.stats["llm_calls"] == 3
    assert len(result.tracks) == 1  # honest partial result, not an infinite loop


def test_generate_with_nothing_verifiable_returns_an_empty_playlist():
    llm = FakeLLM([proposal(("Ghost", "Nobody"))] * 3)
    result = generate(Deps(llm, FakeSpotify([])), req(10), PROFILE)
    assert result.tracks == [] and result.stats["unverified_rate"] == 1.0


def test_same_recording_under_two_ids_is_deduplicated():
    a = cat(1, "Song", "Artist", isrc="USAAA0000001", duration_ms=190_000)
    b = cat(2, "Song", "Artist", isrc="USAAA0000001", duration_ms=190_000)  # re-release
    # Both suggestions verify to real tracks; the second resolves to the re-release's ID.
    llm = FakeLLM([ProposeResult(suggestions=[sug("Song", "Artist"), sug("Song", "Artist")])])
    result = generate(Deps(llm, FakeSpotify([a, b])), req(3), PROFILE)
    assert len(result.tracks) == 1


def test_live_only_song_is_dropped_for_a_studio_request():
    spotify = FakeSpotify([cat(1, "Song - Live", "Artist", duration_ms=190_000)])
    result = generate(Deps(FakeLLM([proposal(("Song - Live", "Artist"))]), spotify), req(3), PROFILE)
    # suggestion carries the live tag, catalog has the live version: accepted.
    assert len(result.tracks) == 1
    result = generate(Deps(FakeLLM([proposal(("Song", "Artist"))] * 3), spotify), req(3), PROFILE)
    assert result.tracks == []  # plain "Song" must not resolve to the live take


# -------------------------------------------------------------------------- refine


def current(n=4):
    return [ref(i, f"Song {i}", "Artist") for i in range(1, n + 1)]  # 4 x 3:20 = 13:20


def test_refine_removes_and_adds_and_ignores_invented_positions():
    spotify = FakeSpotify(catalog(10))
    plan = EditPlan(
        remove_positions=[2, 99, 2],
        add=[sug("Song 7", "Artist", "more energy")],
        summary="Swapped a slow one for something punchier.",
    )
    result = refine(Deps(FakeLLM(edits=[plan]), spotify), req(13), PROFILE, current(4), "more energy")

    got = ids(result)
    assert f"{2:022d}" not in got and f"{7:022d}" in got
    assert got[-1] == f"{7:022d}"  # additions land at the end
    assert result.summary.startswith("Swapped")


def test_refine_that_only_removes_is_topped_back_up_to_length():
    spotify = FakeSpotify(catalog(10))
    llm = FakeLLM(
        edits=[EditPlan(remove_positions=[1, 2], summary="Dropped two.")],
        proposals=[proposal(("Song 8", "Artist"), ("Song 9", "Artist"), ("Song 10", "Artist"))],
    )
    result = refine(Deps(llm, spotify), req(13), PROFILE, current(4), "drop the first two")
    assert result.stats["llm_calls"] == 2
    assert f"{1:022d}" not in ids(result) and f"{8:022d}" in ids(result)


def test_refine_feedback_reaches_the_model_and_current_playlist_is_numbered():
    llm = FakeLLM(edits=[EditPlan()])
    refine(Deps(llm, FakeSpotify([])), req(13), PROFILE, current(4), "less slow")
    ctx = llm.edit_ctx[0]
    assert ctx.feedback == "less slow" and len(ctx.current) == 4


def test_refine_with_a_reference_playlist_pulls_real_tracks_from_it():
    soundtrack = [cat(50 + i, f"Show Song {i}", f"Band {i}") for i in range(1, 6)]
    spotify = FakeSpotify(catalog(4), playlists={"pl1": ("Entourage Soundtrack", soundtrack)})
    llm = FakeLLM(
        edits=[EditPlan(reference_query="Entourage soundtrack", summary="Added Entourage vibes.")],
        picks=[
            ReferencePicks(
                picks=[
                    ReferencePick(index=2, reason="Swagger."),
                    ReferencePick(index=99, reason="invented index"),
                    ReferencePick(index=4, reason="Late-night drive."),
                ]
            )
        ],
    )
    result = refine(Deps(llm, spotify), req(13), PROFILE, current(3), "same mood as the Entourage soundtrack")

    origins = {t.title: t.origin for t in result.tracks}
    assert origins["Show Song 2"] == "reference" and origins["Show Song 4"] == "reference"
    assert "Show Song 3" not in origins
    assert any("Entourage Soundtrack" in n for n in result.notes)
    assert llm.pick_ctx[0].candidates[0] == ("Band 1", "Show Song 1")


def test_reference_that_cannot_be_found_is_reported_not_fatal():
    llm = FakeLLM(edits=[EditPlan(reference_query="Nonexistent Show")])
    result = refine(Deps(llm, FakeSpotify([])), req(13), PROFILE, current(4), "like Nonexistent Show")
    assert any("Couldn't find" in n for n in result.notes)
    assert llm.pick_ctx == []
