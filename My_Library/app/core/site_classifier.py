"""
사이트 유형 자동 분류기
- 도메인 매핑 테이블로 1차 분류
- 미등록 사이트는 None 반환 (호출측에서 LLM 판단 후 DB 저장)
"""
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

# 도메인 → (category_large, site_name) 매핑
SITE_TYPE_MAP: dict[str, tuple[str, str]] = {
    # 포탈
    "naver.com": ("포탈", "네이버"),
    "blog.naver.com": ("블로그", "네이버블로그"),
    "m.blog.naver.com": ("블로그", "네이버블로그"),
    "daum.net": ("포탈", "다음"),
    "nate.com": ("포탈", "네이트"),
    "google.com": ("포탈", "구글"),
    "google.co.kr": ("포탈", "구글"),
    "notebooklm.google.com": ("AI서비스", "노트북LM"),
    "yahoo.com": ("포탈", "야후"),
    "yahoo.co.jp": ("포탈", "야후재팬"),
    "bing.com": ("포탈", "빙"),
    "zum.com": ("포탈", "줌"),
    "baidu.com": ("포탈", "바이두"),
    # AI서비스
    "grok.com": ("AI서비스", "Grok"),
    "x.ai": ("AI서비스", "xAI"),
    "chat.openai.com": ("AI서비스", "ChatGPT"),
    "openai.com": ("AI서비스", "OpenAI"),
    "claude.ai": ("AI서비스", "Claude"),
    "anthropic.com": ("AI서비스", "Anthropic"),
    "gemini.google.com": ("AI서비스", "Gemini"),
    "copilot.microsoft.com": ("AI서비스", "Copilot"),
    "perplexity.ai": ("AI서비스", "Perplexity"),
    "midjourney.com": ("AI서비스", "Midjourney"),
    "runway.ml": ("AI서비스", "Runway"),
    "huggingface.co": ("AI서비스", "HuggingFace"),
    "stability.ai": ("AI서비스", "Stability AI"),
    "poe.com": ("AI서비스", "Poe"),
    "character.ai": ("AI서비스", "Character.AI"),
    "suno.ai": ("AI서비스", "Suno"),
    "elevenlabs.io": ("AI서비스", "ElevenLabs"),
    "leonardo.ai": ("AI서비스", "Leonardo AI"),
    "civitai.com": ("AI서비스", "CivitAI"),
    "ollama.com": ("AI서비스", "Ollama"),
    # 개발도구
    "github.com": ("개발도구", "GitHub"),
    "gitlab.com": ("개발도구", "GitLab"),
    "stackoverflow.com": ("개발도구", "StackOverflow"),
    "cursor.com": ("개발도구", "Cursor"),
    "vercel.com": ("개발도구", "Vercel"),
    "netlify.com": ("개발도구", "Netlify"),
    "replit.com": ("개발도구", "Replit"),
    "codepen.io": ("개발도구", "CodePen"),
    "npmjs.com": ("개발도구", "npm"),
    "pypi.org": ("개발도구", "PyPI"),
    "docker.com": ("개발도구", "Docker"),
    "figma.com": ("개발도구", "Figma"),
    "iloveimg.com": ("개발도구", "iLoveIMG"),
    "squoosh.app": ("개발도구", "Squoosh"),
    # 쇼핑
    "coupang.com": ("쇼핑", "쿠팡"),
    "gmarket.co.kr": ("쇼핑", "G마켓"),
    "11st.co.kr": ("쇼핑", "11번가"),
    "auction.co.kr": ("쇼핑", "옥션"),
    "amazon.com": ("쇼핑", "아마존"),
    "amazon.co.jp": ("쇼핑", "아마존재팬"),
    "aliexpress.com": ("쇼핑", "알리익스프레스"),
    "temu.com": ("쇼핑", "테무"),
    "musinsa.com": ("쇼핑", "무신사"),
    "oliveyoung.co.kr": ("쇼핑", "올리브영"),
    # 여행
    "booking.com": ("여행", "부킹닷컴"),
    "agoda.com": ("여행", "아고다"),
    "airbnb.com": ("여행", "에어비앤비"),
    "airbnb.co.kr": ("여행", "에어비앤비"),
    "tripadvisor.com": ("여행", "트립어드바이저"),
    "skyscanner.co.kr": ("여행", "스카이스캐너"),
    "yanolja.com": ("여행", "야놀자"),
    "goodchoice.kr": ("여행", "여기어때"),
    "klook.com": ("여행", "클룩"),
    # 교육
    "coursera.org": ("교육", "Coursera"),
    "udemy.com": ("교육", "Udemy"),
    "inflearn.com": ("교육", "인프런"),
    "nomadcoders.co": ("교육", "노마드코더"),
    "edx.org": ("교육", "edX"),
    "khanacademy.org": ("교육", "칸아카데미"),
    "class101.net": ("교육", "클래스101"),
    "coloso.global": ("교육", "콜로소"),
    # 금융
    "toss.im": ("금융", "토스"),
    "kbstar.com": ("금융", "국민은행"),
    "shinhan.com": ("금융", "신한은행"),
    "hana.com": ("금융", "하나은행"),
    "wooribank.com": ("금융", "우리은행"),
    "samsung.com": ("금융", "삼성증권"),
    "kiwoom.com": ("금융", "키움증권"),
    # SNS
    "twitter.com": ("SNS", "X(트위터)"),
    "x.com": ("SNS", "X(트위터)"),
    "instagram.com": ("SNS", "인스타그램"),
    "threads.net": ("SNS", "스레드"),
    "reddit.com": ("SNS", "레딧"),
    "facebook.com": ("SNS", "페이스북"),
    "linkedin.com": ("SNS", "링크드인"),
    "discord.com": ("SNS", "디스코드"),
    # 블로그/커뮤니티
    "medium.com": ("블로그", "미디엄"),
    "velog.io": ("블로그", "벨로그"),
    "tistory.com": ("블로그", "티스토리"),
    "brunch.co.kr": ("블로그", "브런치"),
    "dev.to": ("블로그", "dev.to"),
    "hashnode.dev": ("블로그", "Hashnode"),
    "dcinside.com": ("커뮤니티", "디시인사이드"),
    "fmkorea.com": ("커뮤니티", "에펨코리아"),
    "clien.net": ("커뮤니티", "클리앙"),
    "ppomppu.co.kr": ("커뮤니티", "뽐뿌"),
    # 문서/위키
    "notion.so": ("문서", "노션"),
    "notion.site": ("문서", "노션"),
    "wikipedia.org": ("문서", "위키피디아"),
    "namu.wiki": ("문서", "나무위키"),
    "obsidian.md": ("개발도구", "Obsidian"),
    # 엔터테인먼트
    "netflix.com": ("엔터테인먼트", "넷플릭스"),
    "watcha.com": ("엔터테인먼트", "왓챠"),
    "tving.com": ("엔터테인먼트", "티빙"),
    "wavve.com": ("엔터테인먼트", "웨이브"),
    "twitch.tv": ("엔터테인먼트", "트위치"),
    "spotify.com": ("엔터테인먼트", "스포티파이"),
    # 음식/배달
    "baemin.com": ("음식/배달", "배달의민족"),
    "yogiyo.co.kr": ("음식/배달", "요기요"),
    "coupangeats.com": ("음식/배달", "쿠팡이츠"),
}

# 뉴스 도메인은 기존 domain_labels가 처리하므로 여기서 제외
NEWS_DOMAINS = {
    "news.naver.com", "n.news.naver.com", "v.daum.net", "news.daum.net",
    "biz.chosun.com", "chosun.com", "hani.co.kr", "donga.com",
    "wowtv.co.kr", "hankyung.com", "mk.co.kr", "sedaily.com", "edaily.co.kr",
    "etnews.com", "zdnet.co.kr", "mt.co.kr", "yonhapnews.co.kr",
    "yna.co.kr", "sbs.co.kr", "kbs.co.kr", "mbc.co.kr",
}


def _extract_domain(url: str) -> str:
    """URL에서 www. 제거한 도메인 추출."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "").lower().strip()
        return domain
    except Exception:
        return ""


def _find_base_domain(domain: str) -> str:
    """서브도메인 포함 매칭 시도 후, 베이스 도메인으로 폴백.
    예: news.naver.com → naver.com"""
    parts = domain.split(".")
    for i in range(len(parts)):
        candidate = ".".join(parts[i:])
        if candidate in SITE_TYPE_MAP:
            return candidate
    return ""


def _is_news_domain(domain: str) -> bool:
    """뉴스 도메인인지 확인. 뉴스는 기존 로직이 처리."""
    for nd in NEWS_DOMAINS:
        if nd in domain:
            return True
    return False


def classify_site(url: str) -> tuple[str, str] | None:
    """URL → (category_large, site_name) 반환. 매칭 안 되면 None."""
    domain = _extract_domain(url)
    if not domain:
        return None
    # 뉴스 도메인은 기존 로직에 위임
    if _is_news_domain(domain):
        return None
    # 정확한 도메인 매칭
    if domain in SITE_TYPE_MAP:
        return SITE_TYPE_MAP[domain]
    # 서브도메인 → 베이스 도메인 폴백
    base = _find_base_domain(domain)
    if base:
        return SITE_TYPE_MAP[base]
    # DB에 학습된 사이트가 있는지 조회
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 async 컨텍스트면 동기 조회로 폴백
            from app.db.database import get_db_session
            from app.db.models import SiteRegistry

            with get_db_session() as session:
                record = session.query(SiteRegistry).filter_by(domain=domain).first()
                if record:
                    return (record.category_large, record.site_name)
        else:
            result = loop.run_until_complete(lookup_site_registry(domain))
            if result:
                return result
    except Exception:
        # DB 조회 실패 시 None 반환하여 기존 로직 유지
        pass
    return None


def get_homepage_url(url: str) -> str:
    """URL에서 홈페이지(루트) URL 추출. 예: https://grok.com/some/page → https://grok.com"""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return url


async def lookup_site_registry(domain: str) -> tuple[str, str] | None:
    """site_registry DB에서 도메인 조회. 있으면 (category_large, site_name) 반환."""
    from app.db.database import get_db_session
    from app.db.models import SiteRegistry

    try:
        with get_db_session() as session:
            record = session.query(SiteRegistry).filter_by(domain=domain).first()
            if record:
                return (record.category_large, record.site_name)
    except Exception as e:
        logger.warning("site_registry 조회 실패: %s", e)
    return None


async def register_site(
    domain: str, category_large: str, site_name: str, description: str = ""
) -> None:
    """새 사이트를 site_registry에 저장."""
    from app.db.database import get_db_session
    from app.db.models import SiteRegistry

    try:
        with get_db_session() as session:
            existing = session.query(SiteRegistry).filter_by(domain=domain).first()
            if existing:
                return
            new_site = SiteRegistry(
                domain=domain,
                category_large=category_large,
                site_name=site_name,
                description=description,
                homepage_ingested=False,
            )
            session.add(new_site)
            session.commit()
            logger.info("새 사이트 등록: %s → %s/%s", domain, category_large, site_name)
    except Exception as e:
        logger.warning("site_registry 저장 실패: %s", e)


async def ingest_homepage_once(url: str, *, registry_domain: str | None = None) -> None:
    """사이트 홈페이지를 1회만 fetch하여 site_registry에 설명 저장.
    이미 섭취했으면 스킵. materials 테이블에는 저장하지 않는다.
    registry_domain: URL의 netloc과 다른 site_registry.domain(예: youtube.com/@handle)을 쓸 때."""
    from app.db.database import get_db_session
    from app.db.models import SiteRegistry

    domain = (registry_domain or "").strip() or _extract_domain(url)
    if not domain:
        return

    try:
        with get_db_session() as session:
            record = session.query(SiteRegistry).filter_by(domain=domain).first()
            if not record:
                return  # 등록 안 된 사이트는 스킵
            if record.homepage_ingested:
                return  # 이미 섭취함

            # 홈페이지 fetch
            homepage_url = get_homepage_url(url)
            logger.info("홈페이지 1회 섭취 시작: %s", homepage_url)

            import httpx

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(homepage_url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    logger.warning("홈페이지 fetch 실패: %s (status %s)", homepage_url, resp.status_code)
                    return
                html = resp.text[:50000]  # 최대 50KB만

            # 간단한 설명 추출: <meta name="description"> 또는 <title>
            import re as _re

            desc = ""
            meta_match = _re.search(
                r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
                html,
                _re.IGNORECASE,
            )
            if meta_match:
                desc = meta_match.group(1).strip()[:500]
            if not desc:
                title_match = _re.search(r"<title>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL)
                if title_match:
                    desc = title_match.group(1).strip()[:500]
            if not desc:
                desc = f"{domain} 홈페이지"

            # 파비콘 URL 추출
            favicon_url = ""
            fav_match = _re.search(
                r'<link[^>]*rel=["\'](?:shortcut )?icon["\'][^>]*href=["\'](.*?)["\']',
                html,
                _re.IGNORECASE,
            )
            if fav_match:
                fav_href = fav_match.group(1).strip()
                if fav_href.startswith("http"):
                    favicon_url = fav_href
                elif fav_href.startswith("//"):
                    favicon_url = f"https:{fav_href}"
                elif fav_href.startswith("/"):
                    base = homepage_url.rstrip("/")
                    favicon_url = f"{base}{fav_href}"
            if not favicon_url:
                base = homepage_url.rstrip("/")
                favicon_url = f"{base}/favicon.ico"

            # DB 업데이트
            record.description = desc
            record.favicon_url = favicon_url
            record.homepage_ingested = True
            session.commit()
            logger.info("홈페이지 섭취 완료: %s → 설명: %s, 파비콘: %s", domain, desc[:50], favicon_url)
    except Exception as e:
        logger.warning("홈페이지 섭취 실패: %s — %s", domain, e)


async def fetch_youtube_channel_meta(channel_name: str, video_url: str = "") -> dict:
    """yt-dlp로 유튜브 채널의 메타정보를 수집한다.
    video_url이 있으면 영상 메타에서 채널 정보를 추출 (더 안정적).
    반환: {channel, follower_count, channel_id, channel_url, description}"""
    import json
    import subprocess

    result = {
        "channel": channel_name,
        "follower_count": None,
        "channel_id": "",
        "channel_url": "",
        "description": "",
    }

    if not channel_name or channel_name == "미확인채널":
        return result

    # 방법 1: 영상 URL에서 채널 메타 추출 (가장 안정적)
    target_url = video_url if video_url else f"https://www.youtube.com/@{channel_name}"
    yt_args = (
        ["yt-dlp", "--dump-json", "--no-download", target_url]
        if video_url
        else ["yt-dlp", "--dump-json", "--playlist-items", "1", target_url]
    )

    try:
        proc = subprocess.run(
            yt_args,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            logger.warning("yt-dlp 채널 메타 실패: %s (code %s)", channel_name, proc.returncode)
            return result

        if not proc.stdout.strip():
            return result

        data = json.loads(proc.stdout)
        result["channel"] = data.get("channel", channel_name)
        result["follower_count"] = data.get("channel_follower_count")
        result["channel_id"] = data.get("channel_id", "")
        result["channel_url"] = data.get("uploader_url") or data.get("channel_url") or ""
        result["description"] = (data.get("description") or "")[:500]

        logger.info(
            "유튜브 채널 메타 수집: %s → 구독자 %s, URL %s",
            channel_name,
            result["follower_count"],
            result["channel_url"],
        )
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp 채널 메타 타임아웃: %s", channel_name)
    except Exception as e:
        logger.warning("yt-dlp 채널 메타 오류: %s — %s", channel_name, e)

    return result
