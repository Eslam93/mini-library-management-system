async def test_root_explains_when_the_frontend_is_not_built(client):
    response = await client.get("/")

    assert response.status_code == 200
    assert "not built" in response.json()["message"]


async def test_api_docs_are_served_outside_production(client):
    response = await client.get("/api/docs")

    assert response.status_code == 200
    assert "cdn.jsdelivr.net" in response.headers["content-security-policy"]


async def test_api_docs_are_disabled_in_production(make_app, serve):
    async with serve(make_app(app_env="production", session_secret="p" * 40)) as http:
        docs = await http.get("/api/docs")
        schema = await http.get("/api/openapi.json")

    assert docs.status_code == 404
    assert schema.status_code == 404
