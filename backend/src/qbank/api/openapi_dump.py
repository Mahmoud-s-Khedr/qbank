import json
from pathlib import Path

from qbank.api.main import app


def main() -> None:
    path = Path(__file__).resolve().parents[3] / "openapi.json"
    path.write_text(json.dumps(app.openapi(), sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
