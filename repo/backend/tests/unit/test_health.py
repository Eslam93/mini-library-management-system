import pytest

# Nothing listens on port 1, so connections are refused.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://library:library@127.0.0.1:1/library"


@pytest.fixture
def app(make_app):
    return make_app(database_url=UNREACHABLE_DATABASE_URL)


async def test_health_is_degraded_when_the_database_is_unreachable(client):
    response = await client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"database": "unavailable"}}
