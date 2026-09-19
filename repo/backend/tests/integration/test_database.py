import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_health_is_ok_with_a_live_database(make_app, db_engine, serve):
    app = make_app(database_url=db_engine.url.render_as_string(hide_password=False))

    async with serve(app) as http:
        response = await http.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


async def test_db_session_commits_stay_inside_the_test_transaction(db_session):
    await db_session.execute(text("CREATE TABLE rollback_probe (id integer)"))
    await db_session.commit()

    result = await db_session.execute(text("SELECT count(*) FROM rollback_probe"))

    assert result.scalar_one() == 0
