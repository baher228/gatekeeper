from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/gatekeeper_test"
os.environ["DISABLE_SCHEDULER"] = "1"

import psycopg
import pytest

ADMIN_URL = "postgresql://postgres:postgres@localhost:5432/postgres"


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        exists = conn.execute("select 1 from pg_database where datname='gatekeeper_test'").fetchone()
        if not exists:
            conn.execute("create database gatekeeper_test")
    from app.db import migrate
    from app.seed import seed

    migrate()
    seed()
    yield


@pytest.fixture
def client(database):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
