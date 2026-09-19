import pytest

INDEX_HTML = "<!doctype html><title>Library</title><div id=root></div>"


@pytest.fixture
def dist_dir(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML)
    (dist / "assets" / "main-3f9a1c.js").write_text("console.log('app')")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (tmp_path / "outside.txt").write_text("not part of the build")
    return dist


@pytest.fixture
def app(make_app, dist_dir):
    return make_app(frontend_dist_dir=dist_dir)


@pytest.mark.parametrize("path", ["/", "/catalog", "/books/42/copies", "/login?next=/loans"])
async def test_app_routes_return_index_html_without_caching(client, path):
    response = await client.get(path)

    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    assert "default-src 'self'" in response.headers["content-security-policy"]


async def test_head_request_for_an_app_route_succeeds(client):
    response = await client.head("/catalog")

    assert response.status_code == 200
    assert response.text == ""


async def test_hashed_assets_are_cached_forever(client):
    response = await client.get("/assets/main-3f9a1c.js")

    assert response.status_code == 200
    assert response.text == "console.log('app')"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_missing_asset_is_a_404_not_index_html(client):
    response = await client.get("/assets/main-old.js")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_top_level_build_files_are_served(client):
    response = await client.get("/favicon.svg")

    assert response.status_code == 200
    assert response.text.startswith("<svg")
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api"), ("GET", "/api/unknown"), ("GET", "/api/v2/books"), ("POST", "/api/unknown")],
)
async def test_unknown_api_paths_are_json_404s_never_index_html(client, method, path):
    response = await client.request(method, path)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "not_found"


async def test_non_get_request_to_an_app_route_is_a_404(client):
    response = await client.post("/catalog")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_api_routes_take_precedence_over_the_app(client):
    response = await client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]


async def test_paths_outside_the_build_folder_are_not_served(client):
    response = await client.get("/..%2Foutside.txt")

    assert "not part of the build" not in response.text
    assert response.text == INDEX_HTML
