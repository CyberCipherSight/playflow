"""Generate the public manifest schema from its single source of truth."""

import argparse
import json
from pathlib import Path

from playflow.models import Manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "schemas/play-manifest.schema.json"
    schema = Manifest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    content = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            parser.exit(1, "Schema is stale. Run: python tools/export_schema.py\n")
    else:
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
