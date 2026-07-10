"""웹페이지·유튜브·구글 문서 콘텐츠 패칭 모듈.

동기 fetch 함수와 asyncio.to_thread 기반 async 래퍼를 모두 제공한다.
"""

import asyncio
import logging
import random
import re
import subprocess
import time
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from app.core.url_detectors import detect_youtube_url
from app.core.brand_extractor import (
    extract_source_brand,
    _extract_og_site_name,
    _DOMAIN_LABELS_FALLBACK,
)

log = logging.getLogger(__name__)
logger = log  # 모듈 로거 별칭 (레이트리밋 등)

# ──────── 구글 문서 ────────

def build_google_export_url(doc_type: str, doc_id: str) -> str:
    if doc_type == "docs":
        return f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    elif doc_type == "sheets":
        return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=xlsx"
    elif doc_type == "slides":
        return f"https://docs.google.com/presentation/d/{doc_id}/export?format=txt"
    raise ValueError(f"지원하지 않는 구글 문서 타입: {doc_type}")


async def fetch_google_doc(doc_type: str, doc_id: str) -> str:
    """구글 문서/슬라이드의 텍스트를 반환한다."""
    import aiohttp
    from app.core.file_parsers import _parse_excel_bytes

    url = build_google_export_url(doc_type, doc_id)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type and "accounts.google.com" in str(resp.url):
                    raise PermissionError(
                        "이 문서는 비공개입니다. 공유 설정을 확인하세요."
                    )
                raw = await resp.read()
                if doc_type == "sheets":
                    return _parse_excel_bytes(raw)
                return raw.decode("utf-8", errors="replace")
            elif resp.status == 401 or resp.status == 403:
                raise PermissionError(
                    "이 문서는 비공개입니다. 공유 설정을 확인하세요."
                )
            else:
                raise RuntimeError(
                    f"구글 문서 다운로드 실패 (HTTP {resp.status})"
                )


async def fetch_google_sheets_xlsx(doc_id: str) -> bytes:
    """구글 스프레드시트를 xlsx 바이트로 다운로드한다."""
    import aiohttp

    url = build_google_export_url("sheets", doc_id)
    timeout = aiohttp.ClientTimeout(total=180)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type and "accounts.google.com" in str(resp.url):
                    raise PermissionError(
                        "이 문서는 비공개입니다. 공유 설정을 확인하세요."
                    )
                return await resp.read()
            elif resp.status in (401, 403):
                raise PermissionError("이 문서는 비공개입니다. 공유 설정을 확인하세요.")
            else:
                raise RuntimeError(f"구글 스프레드시트 다운로드 실패 (HTTP {resp.status})")


# ──────── 웹페이지 ────────

def _bs4_extract_body(soup) -> str:
    """BeautifulSoup 기반 본문 추출 (폴백용)."""
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "iframe", "noscript"]):
        tag.decompose()
    for cls in ["ad", "advertisement", "sidebar", "comment", "related",
                "sitemap", "breadcrumb", "copyright", "social", "share",
                "popup", "banner", "cookie", "newsletter", "subscribe"]:
        for el in soup.find_all(class_=re.compile(cls, re.I)):
            el.decompose()
    for el in soup.find_all(id=re.compile(
            r"sitemap|footer|sidebar|comment|ad-|cookie|popup|banner", re.I)):
        el.decompose()

    article = (soup.find("article")
               or soup.find("div", class_=re.compile(r"article|content|body", re.I))
               or soup.body)
    text = article.get_text(separator="\n", strip=True) if article else soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 5]
    return "\n".join(lines)


def fetch_webpage(url: str) -> dict:
    """웹페이지를 가져와 본문/제목/날짜/출처를 추출한다."""
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text

    soup = BeautifulSoup(html, "lxml")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

    date = ""
    for attr in ["article:published_time", "date", "publishedDate", "DC.date"]:
        meta = soup.find("meta", attrs={"property": attr}) or soup.find("meta", attrs={"name": attr})
        if meta and meta.get("content"):
            date = meta["content"][:10]
            break
    if not date:
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            date = time_tag["datetime"][:10]

    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    domain_labels = {
        "news.naver.com": "네이버뉴스", "n.news.naver.com": "네이버뉴스",
        "v.daum.net": "다음뉴스", "news.daum.net": "다음뉴스",
        "biz.chosun.com": "조선비즈", "www.chosun.com": "조선일보",
        "www.hani.co.kr": "한겨레", "www.donga.com": "동아일보",
        "wowtv.co.kr": "한국경제TV", "www.wowtv.co.kr": "한국경제TV",
        "www.hankyung.com": "한국경제", "www.mk.co.kr": "매일경제",
        "www.sedaily.com": "서울경제", "www.edaily.co.kr": "이데일리",
    }
    source = domain_labels.get(parsed.netloc, domain)

    body = ""
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
            deduplicate=True,
        )
        if extracted and len(extracted.strip()) > 100:
            body = extracted.strip()
            log.info("trafilatura 본문 추출 성공 (%d자): %s", len(body), url)
            if not date:
                try:
                    traf_date = trafilatura.extract_metadata(html)
                    if traf_date and traf_date.date:
                        date = str(traf_date.date)[:10]
                except Exception:
                    pass
    except Exception as e:
        log.warning("trafilatura 추출 실패, BS4 폴백 사용: %s", e)

    if not body:
        body = _bs4_extract_body(BeautifulSoup(html, "lxml"))
        log.info("BS4 폴백 본문 추출 (%d자): %s", len(body), url)

    brand_info: dict = {}
    try:
        brand_info = extract_source_brand(url, html)
    except Exception:
        brand_info = {
            "platform": "unknown",
            "brand": "",
            "brand_raw": "",
            "extraction_method": "fallback",
        }

    return {
        "title": title,
        "date": date,
        "source": source,
        "body": body,
        "html": html,
        "url": url,
        "brand_info": brand_info,
    }


# ──────── 유튜브 ────────

# YouTube 레이트리밋 — 모듈 레벨
_last_youtube_request_time: float = 0.0
_YOUTUBE_MIN_INTERVAL: float = 10.0  # 최소 10초 간격


def _youtube_rate_limit():
    """YouTube 요청 전 최소 간격을 보장하고 랜덤 지연 추가."""
    global _last_youtube_request_time
    now = time.time()
    elapsed = now - _last_youtube_request_time
    if elapsed < _YOUTUBE_MIN_INTERVAL:
        wait = _YOUTUBE_MIN_INTERVAL - elapsed + random.uniform(1, 3)
        logger.info("YouTube 레이트리밋: %.1f초 대기", wait)
        time.sleep(wait)
    _last_youtube_request_time = time.time()


def fetch_youtube_transcript(url: str) -> dict:
    """유튜브 영상의 자막과 메타데이터를 추출한다."""
    import requests
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        VideoUnavailable,
        IpBlocked,
    )

    _youtube_rate_limit()

    info = detect_youtube_url(url)
    if not info:
        raise ValueError("올바른 유튜브 URL이 아닙니다.")
    video_id = info["video_id"]

    title = ""
    channel = ""
    channel_raw = ""
    date = ""
    try:
        _yt_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        page_resp = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=_yt_headers,
            timeout=15,
        )
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_resp.text, "lxml")
        title_tag = soup.find("meta", attrs={"name": "title"})
        if title_tag:
            title = title_tag.get("content", "")
        author_tag = soup.find("link", attrs={"itemprop": "name"})
        if author_tag and author_tag.get("content"):
            channel_raw = author_tag.get("content", "") or ""
            channel = channel_raw.strip()
        if not channel:
            m_author = soup.find("meta", attrs={"name": "author"})
            if m_author and m_author.get("content"):
                channel_raw = m_author.get("content", "") or ""
                channel = channel_raw.strip()
        if not channel:
            og_ch = _extract_og_site_name(page_resp.text)
            if og_ch:
                channel_raw = og_ch
                channel = og_ch.strip()
        date_tag = soup.find("meta", attrs={"itemprop": "datePublished"})
        if date_tag:
            date = date_tag.get("content", "")[:10]
    except Exception:
        pass

    transcript_text = ""
    try:
        from requests import Session as _ReqSession

        _yt_session = _ReqSession()
        _yt_session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        ytt_api = YouTubeTranscriptApi(http_client=_yt_session)

        # 1) 사용 가능한 자막 목록 먼저 확인
        available_langs = []
        try:
            transcript_list = ytt_api.list(video_id)
            available_langs = [t.language_code for t in transcript_list]
            log.info("[YouTube] %s 사용 가능 자막: %s", video_id, available_langs)
        except Exception as e:
            log.warning("[YouTube] %s 자막 목록 조회 실패: %s", video_id, e)

        # 2) 선호 언어 순서: ko → en → 목록에 있는 아무 언어
        preferred = ["ko", "en"]
        try_order = []
        for lang in preferred:
            if lang in available_langs:
                try_order.append(lang)
        for lang in available_langs:
            if lang not in try_order:
                try_order.append(lang)

        # 목록 조회 실패 시 기존 방식 유지
        if not try_order:
            try_order = ["ko", "en"]

        # 3) 순서대로 시도
        transcript = None
        last_error = None
        for lang in try_order:
            try:
                time.sleep(random.uniform(2, 4))
                fetched = ytt_api.fetch(video_id, languages=[lang])
                transcript = fetched.to_raw_data()
                log.info("[YouTube] %s 자막 성공: %s", video_id, lang)
                break
            except Exception as e:
                last_error = e
                log.debug("[YouTube] %s 자막 %s 실패: %s", video_id, lang, e)
                continue

        # 4) 전부 실패 시 languages 없이 마지막 시도
        if not transcript:
            try:
                time.sleep(random.uniform(3, 5))
                fetched = ytt_api.fetch(video_id)
                transcript = fetched.to_raw_data()
                log.info("[YouTube] %s 자막 성공: default", video_id)
            except Exception as e:
                last_error = e
                log.warning("[YouTube] %s 모든 자막 시도 실패", video_id)

        # ── yt-dlp fallback ──
        if not transcript:
            log.info("[YouTube] %s yt-dlp fallback 시도", video_id)
            time.sleep(random.uniform(5, 8))
            try:
                yt_dlp_text = _fetch_transcript_via_ytdlp(video_id)
                if yt_dlp_text and len(yt_dlp_text.strip()) > 50:
                    log.info(
                        "[YouTube] %s yt-dlp 성공: %d자",
                        video_id,
                        len(yt_dlp_text),
                    )
                    transcript_text = yt_dlp_text
                else:
                    log.warning("[YouTube] %s yt-dlp 결과 비어있음", video_id)
            except Exception as ytdlp_err:
                log.warning(
                    "[YouTube] %s yt-dlp 실패: %s",
                    video_id,
                    ytdlp_err,
                )

        if (
            not transcript
            and not transcript_text.strip()
            and last_error is not None
        ):
            raise last_error

        if transcript:
            transcript_text = "\n".join(entry["text"] for entry in transcript)
    except TranscriptsDisabled:
        transcript_text = "(이 영상은 자막이 비활성화되어 있습니다)"
    except VideoUnavailable:
        raise RuntimeError("영상을 찾을 수 없습니다.")
    except IpBlocked:
        transcript_text = "(YouTube IP 차단으로 자막을 가져올 수 없습니다. 잠시 후 다시 시도해주세요.)"
        log.warning("[YouTube] %s IP 차단됨", video_id)
    except Exception as e:
        transcript_text = f"(자막 추출 실패: {e})"

    return {
        "title": title or f"YouTube_{video_id}",
        "channel": channel,
        "channel_raw": channel_raw,
        "date": date,
        "transcript": transcript_text,
        "video_id": video_id,
        "url": url,
    }


def _fetch_transcript_via_ytdlp(video_id: str) -> str:
    """yt-dlp로 YouTube 자막 추출 (youtube-transcript-api 실패 시 fallback)"""
    import shutil

    ytdlp_path = shutil.which("yt-dlp")
    if not ytdlp_path:
        raise RuntimeError("yt-dlp가 설치되어 있지 않습니다")

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = str(Path(tmpdir) / "sub")

        # 자막 다운로드 (ko 우선, 없으면 en, 없으면 auto-generated)
        cmd = [
            ytdlp_path,
            "--skip-download",
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang",
            "ko,en",
            "--sub-format",
            "vtt",
            "--output",
            output_template,
            url,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp 오류: {result.stderr[:200]}")

        # 생성된 자막 파일 찾기 (ko 우선)
        tmppath = Path(tmpdir)
        sub_files = sorted(tmppath.glob("sub*.vtt"))

        if not sub_files:
            # .srt도 확인
            sub_files = sorted(tmppath.glob("sub*.srt"))

        if not sub_files:
            raise RuntimeError("yt-dlp: 자막 파일 없음")

        # ko 파일 우선 선택
        chosen = sub_files[0]
        for f in sub_files:
            if ".ko." in f.name:
                chosen = f
                break

        raw_text = chosen.read_text(encoding="utf-8")

        # VTT/SRT → 순수 텍스트 변환
        lines = []
        for line in raw_text.splitlines():
            line = line.strip()
            # 타임코드, WEBVTT 헤더, 빈 줄, 숫자만 줄 스킵
            if not line:
                continue
            if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                continue
            if "-->" in line:
                continue
            if line.isdigit():
                continue
            # HTML 태그 제거
            line = re.sub(r"<[^>]+>", "", line)
            if line and line not in lines[-1:]:  # 연속 중복 제거
                lines.append(line)

        return "\n".join(lines)


# ──────── async 래퍼 (이벤트 루프 비차단) ────────

async def fetch_webpage_async(url: str) -> dict:
    """fetch_webpage의 async 래퍼. 스레드 풀에서 실행하여 이벤트 루프를 막지 않는다."""
    return await asyncio.to_thread(fetch_webpage, url)


async def fetch_youtube_transcript_async(url: str) -> dict:
    """fetch_youtube_transcript의 async 래퍼."""
    return await asyncio.to_thread(fetch_youtube_transcript, url)
