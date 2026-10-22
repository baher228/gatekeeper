from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.db import connect
from app.services.history import feature_vector
from app.services.rules import calculate_rule_score, heuristic_checks
from app.services.router import route

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TESTSET_PATH = DATA_DIR / "testset.json"
SMS_SAMPLE_PATH = DATA_DIR / "sms_spam_sample.json"
REPORT_PATH = DATA_DIR / "eval_report.json"

_SYNTHETIC_SPAM = [
    "URGENT! You have won a free prize. Call now to claim your guaranteed reward.",
    "Earn guaranteed money from home. Send your bank details and claim your bonus today.",
    "Exclusive crypto investment: guaranteed 100x returns, DM now before this offer ends.",
]


def _fetch_spam_rows() -> list[str]:
    if SMS_SAMPLE_PATH.exists():
        try:
            data = json.loads(SMS_SAMPLE_PATH.read_text())
            rows = data.get("rows", [])
            if rows:
                return [item["text"] for item in rows if item.get("label") in (1, "spam", "ham")]
        except (OSError, ValueError, KeyError):
            pass
    import httpx

    collected = []
    for offset in (0, 100, 500):
        try:
            response = httpx.get(
                "https://datasets-server.huggingface.co/rows",
                params={
                    "dataset": "ucirvine/sms_spam",
                    "config": "plain_text",
                    "split": "train",
                    "offset": offset,
                    "length": 100,
                },
                timeout=5,
            )
            response.raise_for_status()
            for item in response.json().get("rows", []):
                row = item.get("row", {})
                text = row.get("text") or row.get("sms") or row.get("message")
                label = row.get("label", row.get("category"))
                if text and ("spam" in str(label).lower() or str(label) == "1"):
                    collected.append({"text": text, "label": "spam"})
        except Exception:
            continue
    if not collected:
        collected = [{"text": item, "label": "spam"} for item in _SYNTHETIC_SPAM]
    SMS_SAMPLE_PATH.write_text(
        json.dumps(
            {
                "source": "https://datasets-server.huggingface.co/rows?dataset=ucirvine/sms_spam&config=plain_text&split=train",
                "licence": "UCI SMS Spam Collection; original dataset CC BY 4.0",
                "rows": collected[:100],
                "fallback_used": not any(item["text"] not in _SYNTHETIC_SPAM for item in collected),
            },
            indent=2,
        )
        + "\n"
    )
    return [item["text"] for item in collected]


def generate_testset() -> list[dict]:
    rng = random.Random(7)
    spam_texts = _fetch_spam_rows()
    items = []
    names = {
        "typical_builder": ("accept", 30),
        "typical_decline": ("decline", 25),
        "scammer": ("decline", 15),
        "edge_real_unusual": ("accept", 15),
        "edge_spammy_real": ("accept", 15),
    }
    for tag, (label, count) in names.items():
        for i in range(count):
            if tag == "typical_builder":
                body = "I shipped a working AI demo for London community gardens. The repo is public, I test it weekly, and I will share feedback and help others build."
                evidence = {"github": {"status": "simulated", "account_age_days": 1200, "public_repos": 8, "followers": 14, "recent_push_days": 6}, "devpost": {"status": "simulated", "projects": 1, "wins": 0}, "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0}}
                category = "builder"
            elif tag == "typical_decline":
                body = "I am interested in joining and networking with people in London."
                evidence = {"github": {"status": "simulated", "account_age_days": 0, "public_repos": 0, "followers": 0}, "devpost": {"status": "simulated", "projects": 0, "wins": 0}, "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0}}
                category = "builder"
            elif tag == "scammer":
                body = rng.choice(spam_texts or _SYNTHETIC_SPAM)
                evidence = {"github": {"status": "simulated", "account_age_days": 20, "public_repos": 1, "followers": 1, "recent_push_days": 12}, "devpost": {"status": "simulated", "projects": 0, "wins": 0}, "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0}}
                category = "builder"
            elif tag == "edge_real_unusual":
                category = "researcher" if i % 2 else "first_timer"
                body = "I wrote a careful paper and built a small demo to evaluate language models for accessible public services. I have no established GitHub yet, but I can present the work and welcome critique from London researchers."
                evidence = {"github": {"status": "simulated", "account_age_days": 6, "public_repos": 0, "followers": 0, "recent_push_days": 2}, "devpost": {"status": "simulated", "projects": 1, "wins": 1}, "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0}}
            else:
                category = "first_timer"
                body = "I study scam messages and want to build a community workshop that teaches people to recognize spam and protect one another. I will share a demo and give feedback."
                evidence = {"github": {"status": "simulated", "account_age_days": 0, "public_repos": 0, "followers": 0}, "devpost": {"status": "simulated", "projects": 0, "wins": 0}, "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0}}
            blocklisted = tag == "scammer" and i < 8
            items.append(
                {
                    "id": f"eval-{tag}-{i+1:03}",
                    "name": f"Evaluation Person {len(items)+1:03}",
                    "email": f"eval{len(items)+1}@example.com",
                    "github": f"eval-user-{i}" if evidence["github"].get("public_repos") else None,
                    "devpost": "demo-project" if evidence["devpost"].get("projects") else None,
                    "chat_handle": f"eval-handle-{i}",
                    "what_build": body,
                    "category": category,
                    "label": label,
                    "tag": tag,
                    "evidence": evidence,
                    "blocklist": [
                        {"entry_id": "synthetic-confirmed", "identifier_type": "handle", "status": "confirmed", "reporting_community": "Synthetic test community", "evidence": "Synthetic fixture", "links": [], "reported_at": None}
                    ] if blocklisted else [],
                }
            )
    rng.shuffle(items)
    TESTSET_PATH.write_text(json.dumps(items, indent=2) + "\n")
    return items


def load_testset() -> list[dict]:
    if not TESTSET_PATH.exists():
        return generate_testset()
    return json.loads(TESTSET_PATH.read_text())


def _seed_history_model(community_id: str, categories: list[str]):
    with connect() as conn:
        rows = conn.execute(
            """select features,verdict from decisions where community_id=%s and source='seed'
            and verdict in ('accept','decline')""",
            (community_id,),
        ).fetchall()
    if len(rows) < 10 or len({row["verdict"] for row in rows}) < 2:
        return None, len(rows)
    names = list(rows[0]["features"].keys())
    base = ["rule_score", "rule_min", "gh_account_age_years", "gh_repos_log", "gh_followers_log", "gh_recent_push", "devpost_projects", "devpost_wins", "sfs_appears", "has_github", "has_devpost", "what_build_len_log"]
    names = base + [f"category_{category}" for category in categories]
    x = np.asarray([[float((row["features"] or {}).get(name, 0)) for name in names] for row in rows])
    y = np.asarray([int(row["verdict"] == "accept") for row in rows])
    model = Pipeline([("scale", StandardScaler()), ("logistic", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000))])
    model.fit(x, y)
    return (model, names), len(rows)


def _metrics(name: str, items: list[dict], outcomes: list[str]) -> dict:
    tp_a = sum(i["label"] == "accept" and o in ("accepted", "waitlisted") for i, o in zip(items, outcomes))
    fp_a = sum(i["label"] == "decline" and o in ("accepted", "waitlisted") for i, o in zip(items, outcomes))
    fn_a = sum(i["label"] == "accept" and o in ("declined",) for i, o in zip(items, outcomes))
    tp_d = sum(i["label"] == "decline" and o == "declined" for i, o in zip(items, outcomes))
    fp_d = sum(i["label"] == "accept" and o == "declined" for i, o in zip(items, outcomes))
    fn_d = sum(i["label"] == "decline" and o in ("accepted", "waitlisted") for i, o in zip(items, outcomes))
    decided = [(item, outcome) for item, outcome in zip(items, outcomes) if outcome != "ask"]
    correct = sum(
        (item["label"] == "accept" and outcome in ("accepted", "waitlisted"))
        or (item["label"] == "decline" and outcome == "declined")
        for item, outcome in decided
    )
    accuracy = sum(
        (item["label"] == "accept" and outcome in ("accepted", "waitlisted"))
        or (item["label"] == "decline" and outcome == "declined")
        for item, outcome in zip(items, outcomes)
    ) / max(1, len(items))
    n_accept = sum(item["label"] == "accept" for item in items)
    return {
        "name": name, "accuracy": accuracy,
        "accept_precision": tp_a / max(1, tp_a + fp_a),
        "accept_recall": tp_a / max(1, tp_a + fn_a),
        "decline_precision": tp_d / max(1, tp_d + fp_d),
        "decline_recall": tp_d / max(1, tp_d + fn_d),
        "false_block_rate": fp_d / max(1, n_accept),
        "ask_rate": sum(o == "ask" for o in outcomes) / max(1, len(outcomes)),
        "accuracy_on_decided": correct / max(1, len(decided)),
        "confusion": {"accept_tp": tp_a, "accept_fp": fp_a, "accept_fn": fn_a, "decline_tp": tp_d, "decline_fp": fp_d, "decline_fn": fn_d, "ask": sum(o == "ask" for o in outcomes)},
        "n": len(items),
    }


def run() -> dict:
    DATA_DIR.mkdir(exist_ok=True)
    items = load_testset()
    with connect() as conn:
        community = conn.execute("select id from communities where slug='grok-night-london'").fetchone()
        if not community:
            raise RuntimeError("Run app.seed before evaluation")
        community_id = str(community["id"])
        categories = [row["slug"] for row in conn.execute("select slug from categories where community_id=%s order by slug", (community_id,)).fetchall()]
    model, n_training = _seed_history_model(community_id, categories)
    outputs = {"rules_only": [], "rules_plus_history": []}
    captures = {variant: {} for variant in outputs}
    for item in items:
        checks = heuristic_checks(RULES_FOR_EVAL, item, item["evidence"])
        score = calculate_rule_score(checks, item["evidence"], item["category"])
        quota = {"slug": item["category"], "quota": 100000, "used": 0, "remaining": 100000, "waitlisted": 0, "bypass_quota": True}
        base_history = {"available": False, "p_accept": None, "n_training": 0, "top_features": []}
        first = route(item, checks, score, item["evidence"], base_history, quota, item["blocklist"])
        outputs["rules_only"].append(first["status"])
        if model:
            vector = feature_vector(item, {"rule_score": score, "rule_checks": checks}, item["evidence"], categories)
            names = model[1]
            p = float(model[0].predict_proba([[float(vector.get(name, 0)) for name in names]])[0][1])
            history = {"available": True, "p_accept": p, "n_training": n_training, "top_features": []}
        else:
            history = base_history
        second = route(item, checks, score, item["evidence"], history, quota, item["blocklist"])
        outputs["rules_plus_history"].append(second["status"])
        for variant, result in (("rules_only", first), ("rules_plus_history", second)):
            if item["tag"] in ("edge_real_unusual", "edge_spammy_real") and item["id"] not in captures[variant]:
                captures[variant][item["id"]] = result["status"]
    variants = [
        _metrics(name, items, outcomes)
        for name, outcomes in outputs.items()
    ]
    edge_cases = []
    for tag in ("edge_real_unusual", "edge_spammy_real"):
        item = next(i for i in items if i["tag"] == tag)
        edge_cases.append({
            "name": tag, "label": item["label"],
            "rules_only": outputs["rules_only"][items.index(item)],
            "rules_plus_history": outputs["rules_plus_history"][items.index(item)],
        })
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_set": {
            "n": len(items), "n_accept": sum(i["label"] == "accept" for i in items),
            "n_decline": sum(i["label"] == "decline" for i in items),
            "n_scam": sum(i["tag"] == "scammer" for i in items),
            "n_edge": sum(i["tag"].startswith("edge") for i in items),
            "source": "Synthetic held-out fixtures (random.Random(7)); scam message samples from cached UCI SMS Spam rows when available.",
        },
        "train_set": {"n": n_training, "source": "Grok Night London seed decisions only"},
        "variants": variants,
        "notes": [
            "Both variants use deterministic heuristic rule checks; no Grok/LLM calls were made.",
            "Ask counts as incorrect in overall accuracy and is excluded from accuracy_on_decided.",
            "Thresholds were not tuned using the held-out test set.",
            "Blocklist fixtures cover about half of synthetic scammers; the remainder rely on text and evidence.",
        ],
        "edge_cases": edge_cases,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print("variant              accuracy  acc.decided  accept P/R  decline P/R  false-block  ask-rate")
    for row in variants:
        print(
            f"{row['name']:20} {row['accuracy']:.3f}     {row['accuracy_on_decided']:.3f}      "
            f"{row['accept_precision']:.3f}/{row['accept_recall']:.3f}   "
            f"{row['decline_precision']:.3f}/{row['decline_recall']:.3f}      "
            f"{row['false_block_rate']:.3f}       {row['ask_rate']:.3f}"
        )
    return report


RULES_FOR_EVAL = [
    {"id": "ship", "text": "Has shipped something real (repo, demo, product, paper)"},
    {"id": "ai", "text": "Builds with AI/LLMs or wants to start"},
    {"id": "london", "text": "Based in or regularly in London"},
    {"id": "contribute", "text": "Will contribute: demo, help others, give feedback"},
    {"id": "spam", "text": "No recruiting/selling spam, no crypto pumping"},
]


if __name__ == "__main__":
    run()
