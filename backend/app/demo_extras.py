from __future__ import annotations

from datetime import date

from app.db import connect, migrate
from app.services.extras import primary_hash


def seed_demo_extras() -> None:
    migrate()
    with connect() as conn:
        grok = conn.execute(
            "select id from communities where slug='grok-night-london'"
        ).fetchone()
        shoreditch = conn.execute(
            "select id from communities where slug='shoreditch-builders'"
        ).fetchone()
        if not grok or not shoreditch:
            raise RuntimeError("Demo communities are missing")
        queue = conn.execute(
            """select a.* from applicants a where a.community_id=%s
            and a.status='ask' and a.is_seed order by a.created_at limit 2""",
            (grok["id"],),
        ).fetchall()
        accepted = conn.execute(
            """select a.* from applicants a where a.community_id=%s
            and a.status='accepted' and a.is_seed order by a.created_at limit 1""",
            (grok["id"],),
        ).fetchone()
        if len(queue) < 2 or not accepted:
            raise RuntimeError("Seed queue or accepted demo applicant is missing")

        first, second = queue
        identities = {
            "first": primary_hash(first),
            "second": primary_hash(second),
            "accepted": primary_hash(accepted),
        }
        hashes = list({digest for digest in identities.values() if digest})
        conn.execute(
            "delete from attendance where is_seed and identity_hash=any(%s)",
            (hashes,),
        )
        conn.execute(
            "delete from attendee_notes where is_seed and identity_hash=any(%s)",
            (hashes,),
        )

        with conn.cursor() as cursor:
            cursor.executemany(
                """insert into attendance(community_id,identity_hash,event_name,event_date,status,is_seed)
                values (%s,%s,%s,%s,%s,true)""",
                [
                    (grok["id"], identities["first"], f"Grok Night London #{number}", event_date, "attended")
                    for number, event_date in [
                        (3, date(2026, 3, 12)),
                        (4, date(2026, 5, 14)),
                        (5, date(2026, 7, 16)),
                    ]
                ] + [
                    (grok["id"], identities["second"], f"Grok Night London #{number}", event_date, "no_show")
                    for number, event_date in [
                        (4, date(2026, 5, 14)),
                        (5, date(2026, 7, 16)),
                    ]
                ] + [
                    (grok["id"], identities["accepted"], "Grok Night London #5", date(2026, 7, 16), "attended")
                ],
            )
            cursor.executemany(
                """insert into attendee_notes
                (community_id,identity_hash,flag,note,visibility,author,is_seed)
                values (%s,%s,%s,%s,%s,'lead',true)""",
                [
                    (
                        shoreditch["id"], identities["second"], "no_show",
                        "Didn't turn up twice, no message", "shared",
                    ),
                    (grok["id"], identities["second"], "watch", "", "private"),
                    (
                        shoreditch["id"], identities["accepted"], "great_volunteer",
                        "Reliable volunteer who helped other builders", "shared",
                    ),
                ],
            )


if __name__ == "__main__":
    seed_demo_extras()
