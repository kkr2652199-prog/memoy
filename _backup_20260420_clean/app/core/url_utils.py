"""URL 정규화 및 파일명 정제 유틸리티."""

import re
from urllib.parse import quote, urlparse, urlunparse


def normalize_web_url(url: str) -> str:
    """웹 URL: 스킴·호스트 소문자, 프래그먼트(#) 제거. 쿼리는 유지."""
    p = urlparse((url or "").strip())
    return urlunparse((
        (p.scheme or "https").lower(),
        p.netloc.lower(),
        p.path or "",
        p.params,
        p.query,
        "",
    ))


def normalize_youtube_url(url: str, video_id: str | None = None) -> str:
    """동일 영상: youtu.be / watch?v= / &t= 등을 watch?v=VIDEO_ID 로 통일."""
    from app.core.file_parsers import detect_youtube_url

    vid = (video_id or "").strip()
    if not vid:
        info = detect_youtube_url(url or "")
        vid = (info.get("video_id") or "") if info else ""
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return (url or "").strip()


def source_url_for_google_sheet(base_normalized: str, sheet_name: str) -> str:
    """같은 스프레드시트 내 시트별로 구분되는 source_url."""
    return f"{base_normalized}#sheet={quote(sheet_name, safe='')}"


def _sanitize_filename(name: str) -> str:
    """Windows·기타 OS에서 파일명으로 쓸 수 없는 문자 및 제어 문자(개행 등) 제거."""
    s = name or ""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    return (cleaned[:100] if cleaned else "") or "untitled"


def _sanitize_wiki_path_segment(name: str, fallback: str = "미분류") -> str:
    """위키 디렉터리 세그먼트용 (OS 금지 문자 제거)."""
    s = (name or "").strip()
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s)
    cleaned = cleaned.strip(" ._") or fallback
    return cleaned[:150]
