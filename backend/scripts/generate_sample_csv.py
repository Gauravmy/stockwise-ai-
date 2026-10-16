"""Write the deterministic synthetic sample dataset to data/sample_sales.csv.

Usage (from backend/):  python -m scripts.generate_sample_csv
"""

from app.config import REPO_DIR
from app.services.sample_data import SAMPLE_FILENAME, SAMPLE_SEED, sample_csv_bytes


def main() -> None:
    out = REPO_DIR / "data" / SAMPLE_FILENAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sample_csv_bytes())
    print(f"Wrote {out} (synthetic, seed={SAMPLE_SEED})")


if __name__ == "__main__":
    main()
