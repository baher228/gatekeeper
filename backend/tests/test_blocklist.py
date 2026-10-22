import pytest
import psycopg

from app.db import as_community, connect
from app.services.blocklist import identifier_hash


def test_phone_hash_normalization_matches_gb_formats():
    hashes = {
        identifier_hash("phone", "07700 900123"),
        identifier_hash("phone", "+447700900123"),
        identifier_hash("phone", "+44 7700 900123"),
    }
    assert len(hashes) == 1


def test_rls_scopes_pending_reports_and_blocks_cross_community_writes():
    with connect() as conn:
        communities = {
            row["slug"]: row["id"]
            for row in conn.execute("select id,slug from communities").fetchall()
        }
        a, b = communities["shoreditch-builders"], communities["grok-night-london"]
        a_hash = identifier_hash("email", "rls-pending-a@example.com")
        b_hash = identifier_hash("email", "rls-pending-b@example.com")
        confirmed = identifier_hash("email", "dave.profits@example.com")
        with as_community(conn, a):
            conn.execute(
                """insert into blocklist_entries(identifier_hash,identifier_type,evidence,reporting_community_id,status)
                values (%s,'email','test pending A',%s,'pending')""",
                (a_hash, a),
            )
        with as_community(conn, b):
            conn.execute(
                """insert into blocklist_entries(identifier_hash,identifier_type,evidence,reporting_community_id,status)
                values (%s,'email','test pending B',%s,'pending')""",
                (b_hash, b),
            )
            visible = {
                row["identifier_hash"]
                for row in conn.execute("select identifier_hash from blocklist_entries").fetchall()
            }
            assert a_hash not in visible
            assert b_hash in visible
            assert confirmed in visible
            updated = conn.execute(
                "update blocklist_entries set evidence='tampered' where identifier_hash=%s returning id",
                (a_hash,),
            ).fetchone()
            assert updated is None
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with as_community(conn, b):
                conn.execute(
                    """insert into blocklist_entries(identifier_hash,identifier_type,evidence,reporting_community_id,status)
                    values (%s,'email','forged',%s,'pending')""",
                    (identifier_hash("email", "forged@example.com"), a),
                )
