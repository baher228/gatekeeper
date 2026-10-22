from __future__ import annotations

import math
from datetime import datetime

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from psycopg.types.json import Jsonb

from app.db import connect

BASE_FEATURES = [
    "rule_score", "rule_min", "gh_account_age_years", "gh_repos_log",
    "gh_followers_log", "gh_recent_push", "devpost_projects", "devpost_wins",
    "sfs_appears", "has_github", "has_devpost", "what_build_len_log",
]
_cache: dict[str, tuple[Pipeline, list[str], int]] = {}


def feature_vector(applicant: dict, recommendation: dict, evidence: dict, categories: list[str]) -> dict:
    gh, dp, sfs = evidence.get("github", {}), evidence.get("devpost", {}), evidence.get("stopforumspam", {})
    age = gh.get("account_age_days") or 0
    values = {
        "rule_score": recommendation.get("rule_score", 0),
        "rule_min": min((c["score"] for c in recommendation.get("rule_checks", [])), default=0),
        "gh_account_age_years": min(10, age / 365.25),
        "gh_repos_log": math.log1p(gh.get("public_repos") or 0),
        "gh_followers_log": math.log1p(gh.get("followers") or 0),
        "gh_recent_push": int(gh.get("recent_push_days") is not None and gh["recent_push_days"] <= 90),
        "devpost_projects": float(dp.get("projects") or 0),
        "devpost_wins": float(dp.get("wins") or 0),
        "sfs_appears": int(bool(sfs.get("email_appears") or sfs.get("username_appears"))),
        "has_github": int(bool(applicant.get("github"))),
        "has_devpost": int(bool(applicant.get("devpost"))),
        "what_build_len_log": math.log1p(len(applicant.get("what_build", ""))),
    }
    values.update({f"category_{name}": int(applicant.get("category") == name) for name in categories})
    return values


def train_model(community_id: str, categories: list[str] | None = None) -> dict:
    with connect() as conn:
        rows = conn.execute(
            "select features, verdict, created_at from decisions where community_id=%s "
            "and source in ('lead','seed') and verdict in ('accept','decline') order by created_at",
            (community_id,),
        ).fetchall()
        categories = categories or [
            row["slug"] for row in conn.execute(
                "select slug from categories where community_id=%s order by slug", (community_id,)
            ).fetchall()
        ]
        n_accept = sum(row["verdict"] == "accept" for row in rows)
        n_decline = sum(row["verdict"] == "decline" for row in rows)
        features = BASE_FEATURES + [f"category_{name}" for name in categories]
        latest = rows[-1]["created_at"] if rows else None
        if len(rows) < 10 or not n_accept or not n_decline:
            return {"available": False, "n_decisions": len(rows), "n_accept": n_accept, "n_decline": n_decline, "trained_at": latest, "coefficients": []}
        matrix = np.array([[float((row["features"] or {}).get(f, 0)) for f in features] for row in rows])
        labels = np.array([int(row["verdict"] == "accept") for row in rows])
        pipeline = Pipeline([("scale", StandardScaler()), ("logistic", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000))])
        pipeline.fit(matrix, labels)
        _cache[community_id] = (pipeline, features, len(rows))
        coefficients = [
            {"feature": name, "weight": float(weight)}
            for name, weight in zip(features, pipeline.named_steps["logistic"].coef_[0])
        ]
        conn.execute(
            "insert into model_runs(community_id,n_decisions,n_accept,n_decline,trained_at,coefficients) "
            "values (%s,%s,%s,%s,now(),%s)",
            (community_id, len(rows), n_accept, n_decline, Jsonb(coefficients)),
        )
        return {"available": True, "n_decisions": len(rows), "n_accept": n_accept, "n_decline": n_decline, "trained_at": datetime.now().astimezone(), "coefficients": coefficients}


def predict(community_id: str, vector: dict, categories: list[str] | None = None) -> dict:
    cached = _cache.get(community_id)
    if not cached:
        info = train_model(community_id, categories)
        cached = _cache.get(community_id)
        if not cached:
            return {"available": False, "p_accept": None, "n_training": info["n_decisions"], "top_features": []}
    model, names, n = cached
    scaled = model.named_steps["scale"].transform([[float(vector.get(name, 0)) for name in names]])[0]
    contributions = model.named_steps["logistic"].coef_[0] * scaled
    top = sorted(
        ({"feature": name, "value": float(vector.get(name, 0)), "contribution": float(contribution)}
         for name, contribution in zip(names, contributions)),
        key=lambda item: abs(item["contribution"]), reverse=True,
    )[:4]
    return {"available": True, "p_accept": float(model.predict_proba([[float(vector.get(name, 0)) for name in names]])[0, 1]), "n_training": n, "top_features": top}
