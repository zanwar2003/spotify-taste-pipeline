import pytest

from tastepipe.silver.normalize import clean_isrc, normalize_artist, normalize_title


@pytest.mark.parametrize(
    "title",
    [
        "Under Pressure",
        "Under Pressure - Remastered 2011",
        "Under Pressure (2011 Remaster)",
        "Under Pressure - Radio Edit",
        "Under Pressure [Mono]",
        "UNDER PRESSURE (feat. Someone)",
        "Under Pressure - Deluxe Edition",
    ],
)
def test_re_releases_normalize_to_the_same_title(title):
    assert normalize_title(title) == ("under pressure", "")


@pytest.mark.parametrize(
    ("title", "tag"),
    [
        ("Hey Jude - Live at Wembley", "live"),
        ("Hey Jude (Remix)", "remix"),
        ("Hey Jude - Acoustic", "acoustic"),
        ("Hey Jude (Instrumental)", "instrumental"),
        ("Hey Jude - Sped Up", "altered"),
        ("Love Story (Taylor's Version)", "rerecording"),
        ("Love Story (Taylor’s Version)", "rerecording"),
    ],
)
def test_different_recordings_get_a_version_tag(title, tag):
    assert normalize_title(title)[1] == tag


def test_unknown_parenthetical_stays_in_the_title():
    assert normalize_title("(I Can't Get No) Satisfaction") == ("i cant get no satisfaction", "")


def test_live_remaster_keeps_the_live_tag():
    assert normalize_title("Song - Live (2009 Remaster)") == ("song", "live")


def test_accents_and_ampersands_fold():
    assert normalize_title("Beyoncé & Jay") == ("beyonce and jay", "")
    assert normalize_artist("Sigur Rós") == "sigur ros"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("USRC17607839", "USRC17607839"),
        ("us-rc1-76-07839", "USRC17607839"),
        ("usrc17607839", "USRC17607839"),
        ("USRC1760783", None),  # too short
        ("12RC17607839", None),  # country code must be letters
        ("", None),
        (None, None),
    ],
)
def test_clean_isrc(raw, expected):
    assert clean_isrc(raw) == expected
