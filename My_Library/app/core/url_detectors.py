"""URL 타입 감지 모듈 (YouTube, Google Docs, 웹페이지)."""

import re
from urllib.parse import urlparse, parse_qs


GOOGLE_DOC_PATTERNS = {
    "docs": re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)"),
    "sheets": re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)"),
    "slides": re.compile(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)"),
}

YOUTUBE_PATTERNS = [
    re.compile(
        r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/live/)([a-zA-Z0-9_-]{11})"
    ),
]


def detect_google_doc_url(text: str) -> dict | None:
    text = text.strip()
    for doc_type, pattern in GOOGLE_DOC_PATTERNS.items():
        match = pattern.search(text)
        if match:
            doc_id = match.group(1)
            return {"type": doc_type, "doc_id": doc_id, "url": text}
    return None


def detect_youtube_url(text: str) -> dict | None:
    text = text.strip()
    for pattern in YOUTUBE_PATTERNS:
        match = pattern.search(text)
        if match:
            return {"video_id": match.group(1), "url": text}
    return None


def detect_url_type(text: str) -> dict | None:
    """텍스트에서 URL을 감지하고 타입을 판별한다."""
    text = text.strip()
    google = detect_google_doc_url(text)
    if google:
        return {"type": "google", "google_type": google["type"], "doc_id": google["doc_id"], "url": google["url"]}

    yt = detect_youtube_url(text)
    if yt:
        return {"type": "youtube", **yt}

    if re.match(r"https?://", text):
        return {"type": "webpage", "url": text}

    return None
