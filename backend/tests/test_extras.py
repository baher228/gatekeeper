from datetime import date

from app.db import as_community, connect
from app.services.blocklist import identifier_hash
from app.services.extras import identity_extras, score_adjustment
from app.services.router import route


def _communities():
    with connect() as conn:
        rows = conn.execute(
            "select id,slug from communities where slug in ('grok-night-london','shoreditch-builders')"
        ).fetchall()
    return {row["slug"]: row["id"] for row in rows}


def test_attendance_adjustment_and_router_score():
    community_id = _communities()["grok-night-london"]
    applicant = {"name": "Attendance test", "email": "attendance-extras@example.test"}
    digest = identifier_hash("email", applicant["email"])
    with connect() as conn:
        with as_community(conn, community_id):
            with conn.cursor() as cursor:
                cursor.executemany(
                    """insert into attendance
                    (community_id,identity_hash,event_name,event_date,status)
                    values (%s,%s,%s,%s,'attended')""",
                    [
                        (community_id, digest, f"Past event {index}", date(2026, index, 1))
                        for index in (1, 2, 3)
                    ],
                )
        extras = identity_extras(conn, community_id, applicant)
        adjustment, reason = score_adjustment(extras["attendance"])
        assert extras["attendance"]["attended"] == 3
        assert adjustment == 0.05
        assert reason == "Attended 3 of your past events"
    base = route(
        {"what_build": "A sufficiently detailed project description for this applicant."},
        [], 0.6, {}, {}, {"remaining": 2},
    )["recommendation"]["final_score"]
    adjusted = route(
        {"what_build": "A sufficiently detailed project description for this applicant."},
        [], 0.6, {}, {}, {"remaining": 2}, adjustment=adjustment,
    )["recommendation"]["final_score"]
    assert adjusted == base + 0.05
    with connect() as conn:
        conn.execute("delete from attendance where identity_hash=%s", (digest,))


def test_private_bans_are_isolated_by_community():
    communities = _communities()
    applicant = {"email": "ban-extras@example.test"}
    digest = identifier_hash("email", applicant["email"])
    with connect() as conn:
        with as_community(conn, communities["grok-night-london"]):
            conn.execute(
                """insert into community_bans
                (community_id,identity_hash,identifier_type,reason)
                values (%s,%s,'email','test ban')""",
                (communities["grok-night-london"], digest),
            )
        assert identity_extras(conn, communities["grok-night-london"], applicant)["ban"]
        assert identity_extras(conn, communities["shoreditch-builders"], applicant)["ban"] is None
        with as_community(conn, communities["shoreditch-builders"]):
            visible = conn.execute("select count(*) as n from community_bans").fetchone()["n"]
            assert visible == 0
        conn.execute("delete from community_bans where identity_hash=%s", (digest,))


def test_private_and_shared_notes_follow_community_visibility():
    communities = _communities()
    applicant = {"email": "notes-extras@example.test"}
    digest = identifier_hash("email", applicant["email"])
    a_id = communities["grok-night-london"]
    b_id = communities["shoreditch-builders"]
    with connect() as conn:
        with as_community(conn, a_id):
            with conn.cursor() as cursor:
                cursor.executemany(
                    """insert into attendee_notes
                    (community_id,identity_hash,flag,note,visibility)
                    values (%s,%s,%s,%s,%s)""",
                    [
                        (a_id, digest, "watch", "private note", "private"),
                        (a_id, digest, "vip", "shared note", "shared"),
                    ],
                )
        a_extras = identity_extras(conn, a_id, applicant)
        b_extras = identity_extras(conn, b_id, applicant)
        assert len(a_extras["own_notes"]) == 2
        assert len(b_extras["shared_notes"]) == 1
        assert b_extras["shared_notes"][0]["note"] == "shared note"
        with as_community(conn, b_id):
            visible = conn.execute(
                "select note from attendee_notes where identity_hash=%s", (digest,)
            ).fetchall()
            assert [row["note"] for row in visible] == ["shared note"]
        conn.execute("delete from attendee_notes where identity_hash=%s", (digest,))
