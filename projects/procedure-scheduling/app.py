#!/usr/bin/env python
"""Convenience entry point for the procedure-scheduling prototype.

    uv run python app.py [--host 0.0.0.0] [--port 8000] [--db-path PATH]

Note: this file coexists with the ``app/`` package (packages win import
precedence, so ``from app.main import ...`` below resolves to the package).
It exists so the house-style ``uv run python app.py`` works; the equivalent
is ``uv run uvicorn app.main:app``.
"""

from __future__ import annotations

import argparse

import uvicorn

from app.db import DEFAULT_DB_PATH
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the procedure-scheduling prototype "
        "(API + calendar under /session_schedule, OpenAPI at /docs)."
    )
    parser.add_argument("--host", default="0.0.0.0",
                        help="bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000,
                        help="port (default: 8000)")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH),
                        help=f"DuckDB file (default: {DEFAULT_DB_PATH})")
    args = parser.parse_args()

    uvicorn.run(create_app(db_path=args.db_path), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
