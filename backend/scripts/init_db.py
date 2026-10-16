"""Create or upgrade the database schema (Alembic upgrade head).

Usage (from backend/):  python -m scripts.init_db [--reset]
"""

import argparse
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db.migrate import upgrade_to_head


def reset_sqlite(url: str) -> None:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        raise SystemExit("--reset is only supported for file-based SQLite databases.")
    path = Path(parsed.database)
    if path.exists():
        path.unlink()
        print(f"Removed {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete the SQLite file first")
    args = parser.parse_args()
    url = get_settings().database_url
    if args.reset:
        reset_sqlite(url)
    upgrade_to_head(url)
    print(f"Database ready: {url}")


if __name__ == "__main__":
    main()
