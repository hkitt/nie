import time
import re


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def score_article(title: str, summary: str, source_weight: float, categories: list[dict]) -> float:
    text = normalize(title + " " + (summary or ""))

    base = 0.0
    # Title bonus
    base += min(3.0, max(0.0, len(title) / 60.0))

    # Keyword/category scoring
    cat_score = 0.0
    for c in categories:
        if not c["enabled"]:
            continue
        keywords = [k.strip().lower() for k in (c["keywords"] or "").split(",") if k.strip()]
        hits = sum(1 for k in keywords if k in text)
        if hits:
            cat_score += (hits ** 0.8) * float(c["weight"])  # diminishing returns

    # Source weight multiplier
    score = (base + cat_score) * float(source_weight)

    return float(score)


def recency_boost(published_ts: int | None) -> float:
    if not published_ts:
        return 0.0
    age_sec = max(0, int(time.time()) - int(published_ts))
    # boost within last 24h
    if age_sec <= 3600:
        return 2.0
    if age_sec <= 6 * 3600:
        return 1.2
    if age_sec <= 24 * 3600:
        return 0.6
    return 0.0
