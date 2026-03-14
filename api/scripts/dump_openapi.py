"""Dump the OpenAPI schema from the FastAPI application to a JSON file.

Usage:
    python -m scripts.dump_openapi [--out path/to/openapi.json]

Default output: ../api/openapi.json (relative to repo root).

The schema includes *all* auth routes (passkey + password) regardless of
the runtime ``H4CKATH0N_PASSWORD_AUTH_ENABLED`` flag so that the generated
TypeScript types cover the full API surface.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump OpenAPI JSON from the app")
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "openapi.json"),
        help="Output path for the OpenAPI JSON file",
    )
    args = parser.parse_args()

    # Ensure password auth routes are included in the generated schema.
    os.environ.setdefault("H4CKATH0N_PASSWORD_AUTH_ENABLED", "true")

    # Import the app to extract its OpenAPI schema
    from app.main import app  # noqa: E402

    schema = app.openapi()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"OpenAPI schema written to {out_path}")


if __name__ == "__main__":
    main()
