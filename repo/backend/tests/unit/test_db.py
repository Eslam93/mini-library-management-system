import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import CreateTable

from app.db.base import Base, TimestampMixin
from app.db.session import DbSession


@pytest.fixture
def app(make_app):
    app = make_app()

    @app.get("/api/test/session")
    async def session_info(session: DbSession) -> dict[str, bool]:
        return {"uses_app_engine": session.bind is app.state.engine}

    return app


async def test_session_dependency_uses_the_app_engine(client):
    response = await client.get("/api/test/session")

    assert response.json() == {"uses_app_engine": True}


def test_models_get_timestamps_and_named_constraints():
    class Probe(TimestampMixin, Base):
        __tablename__ = "probe"
        id: Mapped[int] = mapped_column(primary_key=True)

    try:
        ddl = str(CreateTable(Probe.__table__).compile(dialect=postgresql.dialect()))
    finally:
        Base.metadata.remove(Probe.__table__)

    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "CONSTRAINT pk_probe PRIMARY KEY (id)" in ddl
