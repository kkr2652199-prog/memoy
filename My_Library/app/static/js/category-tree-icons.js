/**
 * 카테고리 트리 파비콘/아이콘 표시 모듈
 * site_registry API에서 파비콘 URL을 가져와 트리에 표시
 */

// 사이트 레지스트리 캐시
let _siteRegistryCache = null;
let _siteRegistryCacheTime = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5분

/**
 * site_registry 데이터를 가져온다 (캐시 적용)
 */
async function fetchSiteRegistry() {
  const now = Date.now();
  if (_siteRegistryCache && (now - _siteRegistryCacheTime) < CACHE_TTL) {
    return _siteRegistryCache;
  }
  try {
    const res = await api("/api/library/site-registry");
    if (res.success && res.data) {
      _siteRegistryCache = res.data;
      _siteRegistryCacheTime = now;
      return res.data;
    }
  } catch (e) {
    console.warn("site-registry fetch 실패:", e);
  }
  return _siteRegistryCache || [];
}

/**
 * domain → site_name 매핑 생성
 */
function buildSiteNameToFavicon(registryData) {
  const map = {};
  for (const site of registryData) {
    if (site.site_name && site.favicon_url) {
      map[site.site_name] = {
        favicon: site.favicon_url,
        description: site.description || "",
        followerCount: site.follower_count,
        categoryLarge: site.category_large,
      };
    }
  }
  return map;
}

/**
 * 카테고리 대분류용 기본 아이콘 매핑
 */
const CATEGORY_ICONS = {
  "유튜브": "🎬",
  "뉴스": "📰",
  "블로그": "📝",
  "SNS": "💬",
  "포탈": "🌐",
  "서비스": "⚙️",
  "문서": "📄",
  "직접입력": "✏️",
  "AI서비스": "🤖",
  "개발도구": "💻",
  "쇼핑": "🛒",
  "여행": "✈️",
  "교육": "📚",
  "금융": "💰",
  "커뮤니티": "👥",
  "엔터테인먼트": "🎭",
  "음식/배달": "🍔",
  "종합사이트": "🌍",
  "기타": "📁",
};

/**
 * 중분류(언론·포탈·앱명)별 이모지 — site_registry에 파비콘이 없을 때도 트리에 표시
 */
const MEDIUM_SITE_EMOJIS = {
  연합뉴스: "📡",
  SBS: "📺",
  MBC: "📺",
  KBS: "📺",
  JTBC: "📺",
  YTN: "📺",
  tvN: "📺",
  한국경제TV: "📈",
  전자신문: "📰",
  이데일리: "📰",
  파이낸셜뉴스: "📰",
  아시아경제: "📰",
  헤럴드경제: "📰",
  뉴스1: "📰",
  뉴시스: "📰",
  조선일보: "📰",
  동아일보: "📰",
  한겨레: "📰",
  경향신문: "📰",
  중앙일보: "📰",
  매일경제: "📰",
  서울경제: "📰",
  한국경제: "📰",
  매일신문: "📰",
  국민일보: "📰",
  ZDNet: "💻",
  블로터: "📰",
  네이버: "🌿",
  다음: "🔵",
  구글: "🔍",
  네이트: "✨",
  Obsidian: "📝",
  Squoosh: "🖼️",
  iLoveIMG: "🖼️",
  GitHub: "🐙",
  Cursor: "🖱️",
  Ollama: "🦙",
  노트북LM: "📓",
};

/**
 * 파비콘 <img> 태그 생성. 로드 실패 시 이모지 폴백.
 */
function faviconImgTag(faviconUrl, fallbackEmoji, siteName) {
  if (!faviconUrl) {
    return `<span class="tree-favicon tree-favicon-emoji" title="${siteName || ''}">${fallbackEmoji || "📁"}</span>`;
  }
  return `<img class="tree-favicon tree-favicon-img" 
    src="${faviconUrl}" 
    alt="${siteName || ''}" 
    title="${siteName || ''}"
    onerror="this.style.display='none';this.nextElementSibling.style.display='inline-block';"
  /><span class="tree-favicon tree-favicon-emoji" style="display:none">${fallbackEmoji || "📁"}</span>`;
}

/**
 * 구독자 수 포맷 (예: 450000 → "45만")
 */
function formatFollowerCount(count) {
  if (!count && count !== 0) return "";
  if (count >= 10000) {
    const man = Math.floor(count / 10000);
    return `${man}만`;
  }
  if (count >= 1000) {
    const k = (count / 1000).toFixed(1);
    return `${k}K`;
  }
  return String(count);
}

/**
 * renderCategoryTree 호출 후, 트리 DOM에 파비콘을 주입한다.
 * 이 함수를 loadLibrary 또는 renderCategoryTree 완료 후 호출하면 된다.
 */
async function injectTreeFavicons() {
  const registry = await fetchSiteRegistry();
  const regList = Array.isArray(registry) ? registry : [];
  // site_registry가 비어 있어도 대분류/유튜브 등 이모지는 반드시 주입

  const siteMap = buildSiteNameToFavicon(regList);

  // 대분류(tree-toggle-large)에 카테고리 아이콘 적용
  document.querySelectorAll(".tree-toggle-large").forEach((btn) => {
    const largeName = btn.dataset.large || "";
    const iconSpan = btn.querySelector(".brand-icon");
    if (!iconSpan) return;

    const catIcon = CATEGORY_ICONS[largeName];
    if (catIcon && iconSpan.textContent.trim() === "📁") {
      iconSpan.innerHTML = catIcon;
    }
  });

  // 중분류(tree-item-medium)에 파비콘·이모지 적용
  const ytPlatformMark = () =>
    typeof getYoutubeBrandMarkHtml === "function"
      ? getYoutubeBrandMarkHtml("tree-favicon tree-yt-cat yt-tree-brand")
      : `<span class="tree-favicon tree-favicon-emoji tree-yt-cat" title="YouTube" aria-hidden="true">${
          CATEGORY_ICONS["유튜브"] || "🎬"
        }</span>`;

  document.querySelectorAll(".tree-item-medium").forEach((el) => {
    const mediumName = (el.dataset.medium || "").trim();
    if (!mediumName) return;

    const largeName = (el.dataset.large || "").trim();
    const isYoutubeLarge = largeName === "유튜브";
    const topicFallback =
      MEDIUM_SITE_EMOJIS[mediumName] || CATEGORY_ICONS[largeName] || "📁";

    const siteInfo = siteMap[mediumName];

    // 유튜브 중분류: 채널마다 동일한 youtube.com 파비콘이 붙지 않도록 이모지(🎬)만 사용
    if (isYoutubeLarge) {
      if (el.querySelector(".tree-yt-cat")) return;
      let extraInfo = "";
      if (siteInfo && siteInfo.followerCount) {
        extraInfo = `<span class="tree-follower-count" title="구독자 수">${formatFollowerCount(siteInfo.followerCount)}</span>`;
      }
      const textContent = el.innerHTML;
      el.innerHTML = ytPlatformMark() + textContent + extraInfo;
      if (siteInfo && siteInfo.description) {
        el.title = siteInfo.description.substring(0, 100);
      }
      return;
    }

    if (el.querySelector(".tree-favicon")) return;

    if (siteInfo) {
      const fallback =
        MEDIUM_SITE_EMOJIS[mediumName] ||
        CATEGORY_ICONS[siteInfo.categoryLarge] ||
        topicFallback;
      const faviconHtml = faviconImgTag(siteInfo.favicon, fallback, mediumName);

      let extraInfo = "";
      if (siteInfo.followerCount) {
        extraInfo = `<span class="tree-follower-count" title="구독자 수">${formatFollowerCount(siteInfo.followerCount)}</span>`;
      }

      const textContent = el.innerHTML;
      el.innerHTML = faviconHtml + textContent + extraInfo;

      if (siteInfo.description) {
        el.title = siteInfo.description.substring(0, 100);
      }
    } else {
      el.innerHTML = `<span class="tree-favicon tree-favicon-emoji" aria-hidden="true">${topicFallback}</span>${el.innerHTML}`;
    }
  });
}

// 전역 노출
window.injectTreeFavicons = injectTreeFavicons;
window.fetchSiteRegistry = fetchSiteRegistry;
