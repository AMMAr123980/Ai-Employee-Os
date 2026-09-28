"""
Test fixtures.

These run against the real `app` package — no stubs — with the database pointed
at a temporary SQLite file. The environment variables are set before anything
from `app` is imported, because `settings` is instantiated at import time and
would otherwise pick up a developer's real .env.

Nothing here talks to a network: every test that would reach a model patches
`voice_llm.plan_json` or the transcription call, so the suite is fast, free and
deterministic.
"""
import os
import tempfile

import pytest

_tmpdir = tempfile.mkdtemp(prefix="aieos-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["OPENAI_API_KEY"] = ""                      # nothing should call out
os.environ["VOICE_AUDIO_BACKEND"] = "none"             # don't write files during tests
os.environ["DEFAULT_CURRENCY"] = "PKR"
os.environ["DEFAULT_TAX_RATE"] = "0"

from app.database import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401
from app import ai_employee_models, task_models, voice_models, document_models  # noqa: E402,F401


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """A session whose rows are removed afterwards, so tests can't leak state
    into each other through a shared file."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture()
def company(db):
    row = models.Company(name="Test Co", plan=models.Plan.BASIC, timezone="Asia/Karachi")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def user(db, company):
    row = models.User(
        company_id=company.id, email="sana@test.co", hashed_password="x",
        name="Sana Malik", role=models.UserRole.OWNER,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def customer(db, company):
    row = models.Customer(
        company_id=company.id, name="Acme Corp", company="Acme Corp",
        email="ap@acme.test", phone="+92 321 7654321",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def planned(monkeypatch):
    """Hand it a dict and every planner call in the test returns that JSON."""
    from app import voice_llm

    def _install(payload: dict):
        monkeypatch.setattr(voice_llm, "plan_json", lambda *a, **k: payload)

    return _install
