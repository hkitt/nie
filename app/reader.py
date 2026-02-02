from __future__ import annotations

import html
import importlib
import importlib.util
import re
from typing import Optional

import requests

from db import get_cached_article, set_cached_article


USER_AGENT = "NIE-Reader/1.0 (+https://github.com/example/nie)"
MIN_TEXT_LENGTH = 200


def html_to_simple_markup(raw_html: str) -> str:
    if not raw_html:
        return ""

    text = html.unescape(raw_html)
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", text)

    def replace_heading(match):
        inner = _strip_tags(match.group(1))
        return f"[b]{inner}[/b]\n\n" if inner else ""

    text = re.sub(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", replace_heading, text)

    def replace_li(match):
        inner = _strip_tags(match.group(1))
        return f"• {inner}\n" if inner else ""

    text = re.sub(r"(?is)<li[^>]*>(.*?)</li>", replace_li, text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)<p\b[^>]*>", "", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)

    text = _normalize_whitespace(text)
    text = _escape_kivy(text)
    text = text.replace("\\[b\\]", "[b]").replace("\\[/b\\]", "[/b]")
    return text


def fetch_article_content(url: str, rss_summary: str = "", rss_image_url: str | None = None):
    cached = get_cached_article(url, max_age_hours=24)
    if cached:
        return {"text": cached["text"], "image_url": cached.get("image_url"), "from_cache": True}

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        html_doc = response.text
    except Exception:
        return {"text": rss_summary or "", "image_url": rss_image_url, "used_fallback": True}

    text = ""
    trafilatura = _optional_module("trafilatura")
    if trafilatura:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded) or ""
        except Exception:
            text = ""

    if not text:
        text = _extract_with_readability(html_doc)

    if len(text.strip()) < MIN_TEXT_LENGTH and rss_summary:
        text = rss_summary
        used_fallback = True
    else:
        used_fallback = False

    image_url = rss_image_url or _extract_og_image(html_doc)
    if text.strip():
        set_cached_article(url, text, image_url)
    return {"text": text, "image_url": image_url, "used_fallback": used_fallback}


def _extract_with_readability(html_doc: str) -> str:
    readability = _optional_module("readability")
    if not readability:
        return ""

    try:
        doc = readability.Document(html_doc)
        summary_html = doc.summary(html_partial=True)
    except Exception:
        return ""
    return html_to_simple_markup(summary_html)


def _extract_og_image(html_doc: str) -> Optional[str]:
    match = re.search(
        r'<meta[^>]+property=["\\\']og:image["\\\'][^>]*>',
        html_doc,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r'<meta[^>]+name=["\\\']twitter:image["\\\'][^>]*>',
            html_doc,
            re.IGNORECASE,
        )
    if not match:
        return None
    tag = match.group(0)
    content_match = re.search(r'content=["\\\']([^"\\\']+)["\\\']', tag, re.IGNORECASE)
    if content_match:
        return content_match.group(1)
    return None


def _strip_tags(value: str) -> str:
    text = re.sub(r"(?is)<[^>]+>", "", value or "")
    return _escape_kivy(text.strip())


def _escape_kivy(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def _normalize_whitespace(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _optional_module(module_name: str):
    if importlib.util.find_spec(module_name) is None:
        return None
    return importlib.import_module(module_name)
