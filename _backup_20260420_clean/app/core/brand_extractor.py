"""출처 브랜드·플랫폼 추출 모듈."""

import re
from urllib.parse import urlparse

from app.core.url_detectors import detect_youtube_url

# ──────── 도메인-브랜드 매핑 상수 ────────

DOMAIN_BRAND_MAP: dict[str, tuple[str, str]] = {
    "sbs.co.kr": ("SBS", "news_broadcast"),
    "kbs.co.kr": ("KBS", "news_broadcast"),
    "mbc.co.kr": ("MBC", "news_broadcast"),
    "jtbc.co.kr": ("JTBC", "news_broadcast"),
    "ytn.co.kr": ("YTN", "news_broadcast"),
    "tvn.co.kr": ("tvN", "news_broadcast"),
    "news1.kr": ("뉴스1", "news_online"),
    "newsis.com": ("뉴시스", "news_online"),
    "yna.co.kr": ("연합뉴스", "news_online"),
    "yonhapnews.co.kr": ("연합뉴스", "news_online"),
    "mk.co.kr": ("매일경제", "news_online"),
    "mt.co.kr": ("머니투데이", "news_online"),
    "hankyung.com": ("한국경제", "news_online"),
    "sedaily.com": ("서울경제", "news_online"),
    "chosun.com": ("조선일보", "news_online"),
    "donga.com": ("동아일보", "news_online"),
    "hani.co.kr": ("한겨레", "news_online"),
    "khan.co.kr": ("경향신문", "news_online"),
    "joongang.co.kr": ("중앙일보", "news_online"),
    "joins.com": ("중앙일보", "news_online"),
    "biz.chosun.com": ("조선비즈", "news_online"),
    "zdnet.co.kr": ("ZDNet", "news_online"),
    "bloter.net": ("블로터", "news_online"),
    "etnews.com": ("전자신문", "news_online"),
    "edaily.co.kr": ("이데일리", "news_online"),
    "fnnews.com": ("파이낸셜뉴스", "news_online"),
    "asiae.co.kr": ("아시아경제", "news_online"),
    "herald.co.kr": ("헤럴드경제", "news_online"),
    "hankookilbo.com": ("한국일보", "news_online"),
    "kmib.co.kr": ("국민일보", "news_online"),
    "segye.com": ("세계일보", "news_online"),
    "reuters.com": ("Reuters", "news_online"),
    "bloomberg.com": ("Bloomberg", "news_online"),
    "cnbc.com": ("CNBC", "news_broadcast"),
    "bbc.com": ("BBC", "news_broadcast"),
    "nytimes.com": ("NYT", "news_online"),
    "wsj.com": ("WSJ", "news_online"),
}

BLOG_PLATFORMS: dict[str, str] = {
    "blog.naver.com": "네이버블로그",
    "m.blog.naver.com": "네이버블로그",
    "tistory.com": "티스토리",
    "brunch.co.kr": "브런치",
    "velog.io": "velog",
    "medium.com": "Medium",
}

SNS_PLATFORMS: dict[str, str] = {
    "x.com": "X(Twitter)",
    "twitter.com": "X(Twitter)",
    "instagram.com": "Instagram",
    "threads.net": "Threads",
    "tiktok.com": "TikTok",
    "facebook.com": "Facebook",
}

_DOMAIN_LABELS_FALLBACK: dict[str, tuple[str, str]] = {
    "news.naver.com": ("news_online", "네이버뉴스"),
    "n.news.naver.com": ("news_online", "네이버뉴스"),
    "v.daum.net": ("news_online", "다음뉴스"),
    "news.daum.net": ("news_online", "다음뉴스"),
    "biz.chosun.com": ("news_online", "조선비즈"),
    "www.chosun.com": ("news_online", "조선일보"),
    "www.hani.co.kr": ("news_online", "한겨레"),
    "www.donga.com": ("news_online", "동아일보"),
    "wowtv.co.kr": ("news_broadcast", "한국경제TV"),
    "www.wowtv.co.kr": ("news_broadcast", "한국경제TV"),
    "www.hankyung.com": ("news_online", "한국경제"),
    "www.mk.co.kr": ("news_online", "매일경제"),
    "www.sedaily.com": ("news_online", "서울경제"),
    "www.edaily.co.kr": ("news_online", "이데일리"),
    # 포탈
    "www.naver.com": ("portal", "네이버"),
    "m.naver.com": ("portal", "네이버"),
    "www.google.com": ("portal", "구글"),
    "www.google.co.kr": ("portal", "구글"),
    "www.daum.net": ("portal", "다음"),
    "www.nate.com": ("portal", "네이트"),
    # AI 서비스
    "cursor.com": ("service", "Cursor"),
    "www.cursor.com": ("service", "Cursor"),
    "claude.ai": ("service", "Claude"),
    "chat.openai.com": ("service", "ChatGPT"),
    "openai.com": ("service", "OpenAI"),
    "www.midjourney.com": ("service", "Midjourney"),
    "gemini.google.com": ("service", "Gemini"),
    "genspark.ai": ("service", "GenSpark"),
    "www.genspark.ai": ("service", "GenSpark"),
    "github.com": ("service", "GitHub"),
    "www.github.com": ("service", "GitHub"),
    "huggingface.co": ("service", "HuggingFace"),
}


# ──────── 헬퍼 함수 ────────

def _normalize_host(netloc: str) -> str:
    """netloc에서 www. 제거 후 소문자."""
    try:
        h = (netloc or "").strip().lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _host_matches_map_key(host: str, key: str) -> bool:
    """서브도메인 허용: host가 key와 같거나 key로 끝나면 참."""
    try:
        h = _normalize_host(host)
        k = _normalize_host(key)
        return h == k or h.endswith("." + k)
    except Exception:
        return False


def _lookup_domain_brand(netloc: str) -> tuple[str, str] | None:
    """DOMAIN_BRAND_MAP에서 (brand, platform) 또는 None."""
    try:
        for domain_key, pair in DOMAIN_BRAND_MAP.items():
            if _host_matches_map_key(netloc, domain_key):
                return pair
    except Exception:
        pass
    return None


def _lookup_blog_platform(host: str) -> str | None:
    try:
        h = _normalize_host(host)
        for key, label in BLOG_PLATFORMS.items():
            if h == key.lower() or h.endswith("." + key.lower()):
                return label
    except Exception:
        pass
    return None


def _lookup_sns_platform(host: str) -> str | None:
    try:
        h = _normalize_host(host)
        for key, label in SNS_PLATFORMS.items():
            if h == key.lower() or h.endswith("." + key.lower()):
                return label
    except Exception:
        pass
    return None


def _lookup_domain_labels_fallback(netloc: str) -> tuple[str, str] | None:
    try:
        for key, val in _DOMAIN_LABELS_FALLBACK.items():
            if _host_matches_map_key(netloc, key):
                return val
    except Exception:
        pass
    return None


def _extract_press_name(html: str, _url: str) -> str | None:
    """네이버/다음 뉴스 기사에서 실제 언론사명을 추출."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        og_author = soup.find("meta", attrs={"property": "og:article:author"})
        if og_author and og_author.get("content"):
            author = og_author["content"].split("|")[0].strip()
            if len(author) >= 2:
                return author

        logo = soup.select_one("a.media_end_head_top_logo")
        if logo:
            text = logo.get_text(strip=True)
            if len(text) >= 2:
                return text
            img = logo.find("img", alt=True)
            if img:
                alt = (img.get("alt") or "").strip()
                if len(alt) >= 2:
                    return alt

        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author and meta_author.get("content"):
            author = meta_author["content"].split("|")[0].strip()
            if len(author) >= 2:
                return author

        return None
    except Exception:
        return None


def _fetch_html_for_brand(url: str) -> str:
    """출처 추출용 HTML만 가져온다. 실패 시 빈 문자열."""
    try:
        import requests

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text or ""
    except Exception:
        pass
    return ""


def _extract_og_site_name(html: str) -> str:
    """og:site_name 또는 application-name 메타에서 사이트명 추출."""
    if not html or not html.strip():
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        og = soup.find("meta", attrs={"property": "og:site_name"})
        if og and og.get("content"):
            return (og.get("content") or "").strip()
        app = soup.find("meta", attrs={"name": "application-name"})
        if app and app.get("content"):
            return (app.get("content") or "").strip()
    except Exception:
        pass
    return ""


def _extract_naver_blog_nickname(html: str) -> str:
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        og = _extract_og_site_name(html)
        if og:
            return og.strip()
        tit = soup.find("title")
        if tit:
            t = tit.get_text(strip=True)
            if " : 네이버 블로그" in t:
                return t.split(" : 네이버 블로그")[0].strip()
            if ": 네이버 블로그" in t:
                return t.split(": 네이버 블로그")[0].strip()
    except Exception:
        pass
    return ""


def _clean_naver_blog_nick(nick: str) -> str:
    try:
        s = (nick or "").strip()
        if not s:
            return ""
        for sep in (":", "："):
            if sep in s:
                s = s.split(sep, 1)[0].strip()
        s = re.sub(r"(의)?\s*블로그\s*$", "", s, flags=re.I).strip()
        s = re.sub(r"\s+", " ", s)
        if len(s) > 60:
            return ""
        return s
    except Exception:
        return ""


# ──────── 메인 함수 ────────

def platform_hint_from_source(source: str | None, category_large: str | None = None) -> str:
    """저장된 source·브랜드명으로 UI용 플랫폼 키."""
    s = (source or "").strip()
    cl = (category_large or "").strip()
    if cl == "직접입력" or s.startswith("직접입력"):
        return "direct"
    slow = s.lower()
    if "youtube:" in slow or "youtu.be" in slow or "youtube.com" in slow:
        return "youtube"
    url_re = re.compile(r"https?://[^\s<>\"']+")
    for mo in url_re.finditer(s):
        try:
            loc = urlparse(mo.group(0)).netloc
        except Exception:
            continue
        hit = _lookup_domain_brand(loc)
        if hit:
            return hit[1]
        if _lookup_blog_platform(loc):
            return "blog"
        if _lookup_sns_platform(loc):
            return "sns"
        fb = _lookup_domain_labels_fallback(loc)
        if fb:
            return fb[0]
    if "blog.naver" in slow or "tistory.com" in slow or "brunch.co.kr" in slow or "velog.io" in slow:
        return "blog"
    if re.search(r"\bblog\b", slow) and "youtube" not in slow:
        return "blog"
    return "unknown"


def platform_code_to_korean(code: str) -> str:
    """extract_source_brand 등의 platform 코드 → DB·UI용 한글 플랫폼명."""
    lut = {
        "youtube": "유튜브",
        "news_broadcast": "뉴스",
        "news_online": "뉴스",
        "blog": "블로그",
        "sns": "SNS",
        "portal": "포탈",
        "service": "서비스",
        "document": "문서",
        "direct": "직접입력",
        "unknown": "기타",
    }
    return lut.get((code or "").strip().lower(), "기타")


def extract_source_brand(url: str, html: str | None = None) -> dict:
    """URL(및 선택적 HTML)에서 출처 브랜드·플랫폼을 추출한다."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or ""
        host_norm = _normalize_host(netloc)
        path = parsed.path or ""

        yt_info = None
        try:
            yt_info = detect_youtube_url(url)
        except Exception:
            yt_info = None
        is_yt_host = "youtube.com" in host_norm or "youtu.be" in host_norm
        if yt_info or is_yt_host:
            page_html = html if html else ""
            if not page_html.strip() and yt_info:
                try:
                    vid = yt_info["video_id"]
                    page_html = _fetch_html_for_brand(f"https://www.youtube.com/watch?v={vid}")
                except Exception:
                    page_html = ""
            elif not page_html.strip():
                page_html = _fetch_html_for_brand(url)

            channel_raw = ""
            brand = ""
            method = "html_parse"
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(page_html, "lxml") if page_html else None
                if soup:
                    author_link = soup.find("link", attrs={"itemprop": "name"})
                    if author_link and author_link.get("content"):
                        channel_raw = author_link.get("content", "") or ""
                    if not channel_raw:
                        m_auth = soup.find("meta", attrs={"name": "author"})
                        if m_auth and m_auth.get("content"):
                            channel_raw = m_auth.get("content", "") or ""
                    if not channel_raw:
                        og_sn = _extract_og_site_name(page_html)
                        if og_sn:
                            channel_raw = og_sn
                            method = "meta_og"
            except Exception:
                pass

            brand = (channel_raw or "").strip() or "YouTube 미확인채널"
            if not (channel_raw or "").strip():
                method = "fallback"
            return {
                "platform": "youtube",
                "brand": brand,
                "brand_raw": channel_raw or "",
                "extraction_method": method,
            }

        hit = _lookup_domain_brand(netloc)
        if hit:
            brand, plat_key = hit[0], hit[1]
            return {
                "platform": plat_key,
                "brand": brand,
                "brand_raw": brand,
                "extraction_method": "domain_map",
            }

        blog_label = _lookup_blog_platform(netloc)
        if blog_label:
            blog_name = ""
            raw = ""
            try:
                page_html = html if html else _fetch_html_for_brand(url)
                if "네이버" in blog_label or "naver" in host_norm:
                    m = re.search(r"^/([^/?#]+)", path or "")
                    blog_id = m.group(1) if m else ""
                    nick = _clean_naver_blog_nick(_extract_naver_blog_nickname(page_html))
                    if "\n" in nick:
                        nick = ""
                    blog_name = (blog_id or nick or "unknown").strip()
                    raw = nick or blog_id
                elif "tistory.com" in host_norm:
                    parts = host_norm.split(".")
                    blog_name = parts[0] if parts[0] not in ("www", "m", "") else (parts[1] if len(parts) > 1 else "")
                    raw = blog_name
                elif "brunch.co.kr" in host_norm:
                    m = re.search(r"@([^/?#]+)", path)
                    blog_name = m.group(1) if m else ""
                    raw = blog_name
                elif "velog.io" in host_norm:
                    m = re.search(r"@([^/?#]+)", path)
                    blog_name = m.group(1) if m else ""
                    raw = blog_name
                elif "medium.com" in host_norm:
                    m = re.search(r"@([^/?#]+)", path)
                    blog_name = m.group(1) if m else ""
                    raw = blog_name
                else:
                    blog_name = "unknown"
                    raw = ""
            except Exception:
                blog_name = blog_name or "unknown"
            if not (blog_name or "").strip():
                blog_name = "unknown"
            sep = f"{blog_label}-{blog_name}"
            return {
                "platform": "blog",
                "brand": sep,
                "brand_raw": raw or blog_name,
                "extraction_method": "url_parse" if (raw or "").strip() else "html_parse",
            }

        sns_label = _lookup_sns_platform(netloc)
        if sns_label:
            return {
                "platform": "sns",
                "brand": sns_label,
                "brand_raw": sns_label,
                "extraction_method": "domain_map",
            }

        page_html = html if html else ""
        if not page_html.strip():
            page_html = _fetch_html_for_brand(url)

        fallback = _lookup_domain_labels_fallback(netloc)
        if fallback:
            platform_code, brand_label = fallback
            if brand_label in ("네이버뉴스", "다음뉴스"):
                real_press = _extract_press_name(page_html, url)
                if real_press:
                    brand_label = real_press
            return {
                "platform": platform_code,
                "brand": brand_label,
                "brand_raw": brand_label,
                "extraction_method": "domain_map",
            }

        og = _extract_og_site_name(page_html)
        if og:
            return {
                "platform": "unknown",
                "brand": og.strip(),
                "brand_raw": og,
                "extraction_method": "meta_og",
            }

        brand_dom = host_norm or netloc or "unknown"
        return {
            "platform": "unknown",
            "brand": brand_dom,
            "brand_raw": brand_dom,
            "extraction_method": "url_parse",
        }
    except Exception:
        try:
            hn = _normalize_host(urlparse(url).netloc)
        except Exception:
            hn = ""
        return {
            "platform": "unknown",
            "brand": hn or "unknown",
            "brand_raw": "",
            "extraction_method": "fallback",
        }
