import feedparser
from dateutil import parser as dtparser


def _to_unix_seconds(published_str: str | None) -> int | None:
    if not published_str:
        return None
    try:
        dt = dtparser.parse(published_str)
        return int(dt.timestamp())
    except Exception:
        return None


def fetch_feed(url: str) -> list[dict[str, object]]:
    d = feedparser.parse(url)
    items = []
    for e in d.entries:
        guid = getattr(e, "id", None) or getattr(e, "guid", None) or getattr(e, "link", None)
        title = getattr(e, "title", "").strip()
        link = getattr(e, "link", "").strip()
        summary = getattr(e, "summary", "") or getattr(e, "description", "")
        published = getattr(e, "published", None) or getattr(e, "updated", None)
        published_ts = _to_unix_seconds(published)

        if title and link:
            items.append(
                {
                    "guid": guid,
                    "title": title,
                    "link": link,
                    "summary": summary[:2000] if summary else "",
                    "published_ts": published_ts,
                }
            )
    return items
