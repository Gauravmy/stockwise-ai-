import os
import tempfile
from pathlib import Path

# Configure an isolated database BEFORE the app modules are imported.
_TMP = Path(tempfile.mkdtemp(prefix="stockwise-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'import.db').as_posix()}"
os.environ["AUTO_MIGRATE"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"

from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import build_engine, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def engine(tmp_path):
    eng = build_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def client(session_factory):
    def _get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_csv(rows: list[dict], columns: list[str] | None = None) -> bytes:
    columns = columns or list(rows[0].keys())
    lines = [",".join(columns)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")) for c in columns))
    return ("\n".join(lines) + "\n").encode("utf-8")


def daily_rows(product_id: str, days: int, qty_fn, start: date = date(2024, 1, 1)) -> list[dict]:
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "product_id": product_id, "quantity": qty_fn(i)}
        for i in range(days)
    ]
