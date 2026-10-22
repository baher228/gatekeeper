from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "sms_spam_sample.json"
DATA_SOURCE = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=ucirvine/sms_spam&config=plain_text&split=train"
)
DATA_LICENCE = "UCI SMS Spam Collection; original dataset CC BY 4.0"

_MODEL: Pipeline | None = None
_MODEL_LOCK = asyncio.Lock()


def _normalize_rows(rows: list[dict]) -> list[dict[str, str]]:
    normalized = []
    for row in rows:
        text = row.get("text", row.get("sms"))
        label = row.get("label")
        if isinstance(label, int) or str(label) in ("0", "1"):
            label = "spam" if str(label) == "1" else "ham"
        elif isinstance(label, str):
            label = label.lower()
        if text and label in ("ham", "spam"):
            normalized.append({"text": str(text), "label": label})
    return normalized


def _cached_rows() -> list[dict[str, str]]:
    try:
        data = json.loads(DATA_PATH.read_text())
    except (OSError, ValueError):
        return []
    return _normalize_rows(data.get("rows", []))


async def _fetch_rows() -> list[dict[str, str]]:
    async with httpx.AsyncClient(timeout=10) as client:
        async def fetch_page(offset: int) -> list[dict]:
            response = await client.get(
                DATA_SOURCE,
                params={
                    "dataset": "ucirvine/sms_spam",
                    "config": "plain_text",
                    "split": "train",
                    "offset": offset,
                    "length": 100,
                },
            )
            response.raise_for_status()
            return [
                item.get("row", {})
                for item in response.json().get("rows", [])
            ]

        pages = await asyncio.gather(
            *(fetch_page(offset) for offset in range(0, 1000, 100))
        )
    return _normalize_rows([row for page in pages for row in page])


async def _load_training_rows() -> list[dict[str, str]]:
    rows = _cached_rows()
    if len(rows) >= 1000 and {row["label"] for row in rows} == {"ham", "spam"}:
        return rows

    try:
        rows = await _fetch_rows()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise RuntimeError("Could not fetch the SMS spam training corpus") from exc
    if len(rows) < 1000 or {row["label"] for row in rows} != {"ham", "spam"}:
        raise RuntimeError("SMS spam training corpus has insufficient labeled rows")

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(
            {
                "source": DATA_SOURCE,
                "licence": DATA_LICENCE,
                "rows": rows,
                "fallback_used": False,
            },
            indent=2,
        )
        + "\n"
    )
    return rows


def _train(rows: list[dict[str, str]]) -> Pipeline:
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=20000, stop_words="english")),
            ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
        ]
    )
    model.fit(
        [row["text"] for row in rows],
        [row["label"] for row in rows],
    )
    return model


async def _get_model() -> Pipeline:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    async with _MODEL_LOCK:
        if _MODEL is None:
            _MODEL = _train(await _load_training_rows())
    return _MODEL


async def check_message(text: str) -> dict:
    model = await _get_model()
    probabilities = model.predict_proba([text])[0]
    spam_index = list(model.classes_).index("spam")
    probability = float(probabilities[spam_index])

    vectorizer = model.named_steps["tfidf"]
    classifier = model.named_steps["classifier"]
    vector = vectorizer.transform([text]).toarray()[0]
    contributions = vector * classifier.coef_[0]
    terms = vectorizer.get_feature_names_out()
    top_indexes = sorted(
        range(len(terms)),
        key=lambda index: abs(contributions[index]),
        reverse=True,
    )[:5]
    return {
        "scam_probability": round(probability, 4),
        "label": "spam" if probability >= 0.5 else "ham",
        "top_terms": [
            {"term": str(terms[index]), "weight": round(float(contributions[index]), 4)}
            for index in top_indexes
            if contributions[index] != 0
        ],
        "draft_removal": (
            f"This message has a {probability:.0%} spam probability. "
            "Please review it before taking action."
        ),
    }
