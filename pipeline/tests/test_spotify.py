import httpx
import respx

from tastepipe.spotify import API_BASE, TOKEN_URL, SpotifyClient


def make_client(sleeps):
    return SpotifyClient("id", "secret", sleep=sleeps.append)


def token_route():
    return respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )


@respx.mock
def test_paginates_until_next_is_null():
    token_route()
    url = f"{API_BASE}/users/alice/playlists"
    respx.get(url, params={"limit": "50"}).mock(
        return_value=httpx.Response(200, json={"items": [{"id": "a"}], "next": f"{url}?offset=50"})
    )
    respx.get(f"{url}?offset=50").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "b"}], "next": None})
    )
    pages = list(make_client([]).user_playlists("alice"))
    assert [p["items"][0]["id"] for p in pages] == ["a", "b"]


@respx.mock
def test_retries_on_429_and_respects_retry_after():
    token_route()
    url = f"{API_BASE}/users/alice/playlists"
    route = respx.get(url).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"items": [], "next": None}),
        ]
    )
    sleeps: list = []
    pages = list(make_client(sleeps).user_playlists("alice"))
    assert len(pages) == 1
    assert route.call_count == 2
    assert sleeps and sleeps[0] >= 2


@respx.mock
def test_private_or_missing_user_yields_no_pages():
    token_route()
    respx.get(f"{API_BASE}/users/ghost/playlists").mock(return_value=httpx.Response(404))
    assert list(make_client([]).user_playlists("ghost")) == []
