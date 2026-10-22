from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import UUID

import psycopg
from psycopg import sql
from dotenv import load_dotenv
from psycopg.rows import dict_row

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = Path(os.getenv("ENV_FILE", ".env"))
if not ENV_FILE.is_absolute():
    ENV_FILE = BACKEND_DIR / ENV_FILE
load_dotenv(ENV_FILE)
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/gatekeeper"
)
DB_SCHEMA = os.getenv("DB_SCHEMA", "gatekeeper")
if DB_SCHEMA != "gatekeeper":
    raise ValueError("This backend is restricted to the gatekeeper schema")


def connect(*, autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=autocommit)
    try:
        conn.execute(
            sql.SQL("set search_path to {}").format(sql.Identifier(DB_SCHEMA))
        )
        if not autocommit:
            conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


@contextmanager
def as_community(conn: psycopg.Connection, community_id: str | UUID) -> Iterator[psycopg.Connection]:
    """Run blocklist operations with the database-enforced community role and scope."""
    with conn.transaction():
        conn.execute("set local role gatekeeper_community")
        conn.execute(
            sql.SQL("set local search_path to {}").format(sql.Identifier(DB_SCHEMA))
        )
        conn.execute(
            "select set_config('app.community_id', %s, true)", (str(community_id),)
        )
        yield conn
        if conn.info.transaction_status.name != "INERROR":
            conn.execute("reset role")


def migrate() -> None:
    with connect() as conn:
        conn.execute(
            sql.SQL("create schema if not exists {}").format(
                sql.Identifier(DB_SCHEMA)
            )
        )
        conn.execute(
            "create table if not exists schema_migrations "
            "(name text primary key, applied_at timestamptz not null default now())"
        )
        for path in sorted((BACKEND_DIR / "migrations").glob("*.sql")):
            already = conn.execute(
                "select 1 from schema_migrations where name = %s", (path.name,)
            ).fetchone()
            if already:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute(
                    "insert into schema_migrations(name) values (%s)", (path.name,)
                )


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1 or sys.argv[1] == "migrate":
        migrate()
