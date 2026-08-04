"""FastAPI application factory for the procedure-scheduling prototype.

Run it either way:

    uv run python app.py [--host 0.0.0.0] [--port 8000] [--db-path ...]
    uv run uvicorn app.main:app [--host 0.0.0.0] [--port 8000]

Everything lives under ``/session_schedule``; the interactive OpenAPI page
is at ``/docs``.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

# Make `scripts/` importable when running under uvicorn from the project dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import DEFAULT_DB_PATH, Database  # noqa: E402
from app.read_api import router as read_router  # noqa: E402

DESCRIPTION = """
Prototype procedure-scheduling system for AIND acquisitions
([aind-scientific-computing#624](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/624)).

A self-contained reference implementation of the schema and API proposed for
Microsoft Dataverse: local DuckDB store, synthetic seed data, read-only public
API. Every scheduled procedure's `id` is a time-sortable UUIDv7 — the
persistent acquisition token minted at scheduling time.
"""


def create_app(
    db_path: str | Path = DEFAULT_DB_PATH,
    seed_if_empty: bool = True,
) -> FastAPI:
    """Build the app: open the store (creating the schema idempotently),
    seed it on first run so the demo is never empty, and mount the routers."""
    database = Database(db_path)

    if seed_if_empty:
        empty = (
            database.conn.execute("SELECT count(*) FROM procedure_types").fetchone()[0]
            == 0
        )
        if empty:
            from scripts.seed import seed_database

            seed_database(database)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        database.close()

    application = FastAPI(
        title="Procedure Scheduling Prototype",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.db = database
    application.include_router(read_router)
    return application


# Lazy module attribute so `uvicorn app.main:app` works without importing
# this module causing side effects (creating/seeding the default database)
# for everyone else who imports create_app — e.g. the tests.
_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
