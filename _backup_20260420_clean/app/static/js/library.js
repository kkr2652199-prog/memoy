/* === 도서관 탭 === */

const librarySearch = document.getElementById("librarySearch");
const btnSearch = document.getElementById("btnSearch");
const filterCategoryLarge = document.getElementById("filterCategoryLarge");
const filterCategoryMedium = document.getElementById("filterCategoryMedium");
const filterSort = document.getElementById("filterSort");
const filterStatus = document.getElementById("filterStatus");
const importanceFilter = document.getElementById("importanceFilter");
const libraryRange = document.getElementById("libraryRange");
const libraryPagination = document.getElementById("libraryPagination");
const btnTreeViewAll = document.getElementById("btnTreeViewAll");

let currentLibraryView = "list";
let categoryTreeData = [];
/** 마지막으로 불러온 목록 API 응답(트리 접기/펼치기 시 재렌더용) */
let lastLibraryListPayload = {
  items: [],
  total: 0,
  page: 1,
  per_page: 20,
  total_pages: 1,
};

let selectedMaterialIds = new Set();

function updateBulkBar() {
  let bar = document.getElementById("bulkActionBar");
  if (selectedMaterialIds.size === 0) {
    if (bar) bar.style.display = "none";
    return;
  }
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "bulkActionBar";
    bar.className = "bulk-action-bar";
    const statsBar = document.getElementById("statsBar");
    if (statsBar) statsBar.parentElement.insertBefore(bar, statsBar.nextSibling);
  }
  bar.style.display = "flex";
  bar.innerHTML = `
    <span class="bulk-count">${selectedMaterialIds.size}건 선택</span>
    <button type="button" class="btn btn-small btn-secondary" onclick="selectAllCards()">전체 선택</button>
    <button type="button" class="btn btn-small btn-secondary" onclick="deselectAllCards()">선택 해제</button>
    <button type="button" class="btn btn-small btn-danger" onclick="bulkAction('delete')">🗑️ 일괄 삭제</button>
    <button type="button" class="btn btn-small btn-secondary" onclick="bulkAction('archive')">📦 일괄 보관</button>
  `;
}

function selectAllCards() {
  document.querySelectorAll(".lib-card").forEach(c => {
    const id = Number.parseInt(c.dataset.id, 10);
    selectedMaterialIds.add(id);
    const cb = c.querySelector(".bulk-cb");
    if (cb) cb.checked = true;
    c.classList.add("bulk-selected");
  });
  updateBulkBar();
}

function deselectAllCards() {
  selectedMaterialIds.clear();
  document.querySelectorAll(".lib-card").forEach(c => {
    const cb = c.querySelector(".bulk-cb");
    if (cb) cb.checked = false;
    c.classList.remove("bulk-selected");
  });
  updateBulkBar();
}

async function bulkAction(action) {
  if (selectedMaterialIds.size === 0) return;
  const label = action === "delete" ? "삭제" : "보관";
  if (!confirm(`선택한 ${selectedMaterialIds.size}건을 ${label}하시겠습니까?`)) return;
  try {
    await api("/api/library/materials/bulk-action", {
      method: "POST",
      body: { ids: [...selectedMaterialIds], action },
    });
    showToast(`${selectedMaterialIds.size}건 ${label} 완료`, "success");
    selectedMaterialIds.clear();
    updateBulkBar();
    await loadLibrary();
    await syncLibraryGraphIfVisible();
  } catch (err) {
    showToast(`일괄 ${label} 실패: ${err.message}`, "error");
  }
}

/** 대분류 행 접기(선택은 유지). 중·소분류 선택 시 해당 대분류는 항상 펼침 */
let libState = {
  page: 1,
  size: 20,
  q: "",
  categoryLarge: "",
  categoryMedium: "",
  categorySmall: "",
  sort: "newest",
  importance: 0,
  status: "active",
  materialType: "information",
  dateFrom: "",
  dateTo: "",
  entityId: 0,
  conceptId: 0,
  treeSel: { large: "", medium: "", small: "" },
  treeCollapsed: {},
  /** 사이드바 주요 태그 필터 (단일 태그) */
  tagFilter: "",
  /** /api/library/categories 의 top_tags */
  sidebarTopTags: [],
  /** /api/library/stats 의 total_materials (기본 뷰·그래프 모드 분기) */
  totalMaterials: 0,
};

/** 현재 필터 대분류에 해당하는 트리 플랫폼 행이 접혀 있으면 true */
function isCurrentPlatformTreeCollapsed() {
  const L = (libState.categoryLarge || "").trim();
  if (!L) return false;
  return libState.treeCollapsed[L] === true;
}

function refreshLibraryListFromTreeState() {
  renderMaterialList(lastLibraryListPayload);
  renderPagination(lastLibraryListPayload);
}

const LIB_STRIP_COLORS = {
  경제: "#4a90d9",
  시사: "#2ed573",
  기술: "#9b59b6",
  개인: "#e17055",
  정치: "#ff6b6b",
  사회: "#ffd93d",
  문화: "#fd79a8",
  과학: "#00b894",
  스포츠: "#e17055",
  기타: "#636e72",
};

function escapeHtml(text) {
  if (text === null || text === undefined) return "";
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

function escapeAttr(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

/** 자료 상세 모달: 제목·분류 편집 (1차 클릭 편집, 2차 클릭 저장) */
async function _toggleDetailEditMode(materialId, currentTitle, catLarge, catMedium, catSmall) {
  const titleEl = document.getElementById("detailTitle");
  const catEl = document.getElementById("detailCategory");
  const btn = document.getElementById("detailEditBtn");
  if (!titleEl || !catEl || !btn) return;

  const srcLarge = catLarge != null ? String(catLarge) : "";
  const srcMedium = catMedium != null ? String(catMedium) : "";
  const srcSmall = catSmall != null ? String(catSmall) : "";

  if (btn.dataset.editing === "true") {
    const newTitle = document.getElementById("editTitle")?.value?.trim();
    const newLarge = document.getElementById("editCatLarge")?.value?.trim();
    const newMedium = document.getElementById("editCatMedium")?.value?.trim();
    const newSmall = document.getElementById("editCatSmall")?.value?.trim() ?? "";

    if (!newTitle) {
      alert("제목을 입력하세요.");
      return;
    }
    if (!newLarge || !newMedium) {
      alert("대분류·중분류를 입력하세요.");
      return;
    }

    const body = {};
    if (newTitle !== (btn.dataset.origTitle || "")) body.title = newTitle;
    if (newLarge !== (btn.dataset.origLarge || "")) body.category_large = newLarge;
    if (newMedium !== (btn.dataset.origMedium || "")) body.category_medium = newMedium;
    if (newSmall !== (btn.dataset.origSmall || "")) body.category_small = newSmall;

    if (Object.keys(body).length === 0) {
      await showMaterialDetail(materialId);
      return;
    }

    try {
      const res = await api(`/api/library/material/${materialId}/meta`, {
        method: "PATCH",
        body,
      });
      if (res.success) {
        await showMaterialDetail(materialId);
        loadLibrary();
      } else {
        alert("수정 실패: 알 수 없는 오류");
      }
    } catch (e) {
      alert(`수정 중 오류: ${e.message || String(e)}`);
    }
    return;
  }

  btn.dataset.editing = "true";
  btn.dataset.origTitle = currentTitle;
  btn.dataset.origLarge = srcLarge;
  btn.dataset.origMedium = srcMedium;
  btn.dataset.origSmall = srcSmall;
  btn.textContent = "💾";

  titleEl.innerHTML = `<input type="text" id="editTitle" class="detail-edit-input" value="${escapeAttr(currentTitle)}" style="width:100%;font-size:18px;padding:4px 8px;background:rgba(255,255,255,0.1);color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:4px;box-sizing:border-box;">`;

  catEl.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px;">
      <input type="text" id="editCatLarge" class="detail-edit-input" value="${escapeAttr(srcLarge)}" placeholder="대분류"
        style="min-width:100px;padding:4px 8px;background:rgba(255,255,255,0.1);color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:4px;">
      <span style="color:#888;">&gt;</span>
      <input type="text" id="editCatMedium" class="detail-edit-input" value="${escapeAttr(srcMedium)}" placeholder="중분류"
        style="min-width:100px;padding:4px 8px;background:rgba(255,255,255,0.1);color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:4px;">
      <span style="color:#888;">&gt;</span>
      <input type="text" id="editCatSmall" class="detail-edit-input" value="${escapeAttr(srcSmall)}" placeholder="소분류(선택)"
        style="min-width:100px;flex:1;padding:4px 8px;background:rgba(255,255,255,0.1);color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:4px;">
    </div>`;
}

/** 그래프 패널 위키 스니펫: 남은 YAML 키 형태 줄 제거 */
function cleanWikiPanelContent(text) {
  if (!text || typeof text !== "string") return "";
  return text
    .split("\n")
    .filter((line) => {
      const t = line.trim();
      if (t === "") return true;
      return !/^(type|name|related_materials)\s*:/i.test(t);
    })
    .join("\n")
    .trim();
}

/** ISO 또는 YYYY-MM-DD 문자열을 KST 기준 날짜+요일로 표시 (예: 2026-04-11 (금)) */
function formatKstDateWithWeekday(raw) {
  if (raw == null || raw === "") return "";
  const s = String(raw).trim();
  let d;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    d = new Date(s + "T12:00:00+09:00");
  } else {
    d = new Date(s);
  }
  if (Number.isNaN(d.getTime())) return s.slice(0, 10);
  const ymd = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
  const wk = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    weekday: "narrow",
  }).format(d);
  return wk ? `${ymd} (${wk})` : ymd;
}

function kstTodayYmd() {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function getStripColor(cat) {
  return LIB_STRIP_COLORS[cat] || LIB_STRIP_COLORS.기타;
}

/** API platform 키 또는 DB 플랫폼명(한글) → 이모지 */
const PLATFORM_ICONS = {
  youtube: "🎬",
  news: "📰",
  news_broadcast: "📺",
  news_online: "📰",
  blog: "📝",
  sns: "💬",
  direct: "✏️",
  unknown: "📁",
  유튜브: "🎬",
  뉴스: "📰",
  블로그: "📝",
  SNS: "💬",
  직접입력: "✏️",
  기타: "📁",
};

function platformIcon(platform) {
  if (!platform) return PLATFORM_ICONS.unknown;
  const k = String(platform).trim();
  return PLATFORM_ICONS[k] || PLATFORM_ICONS.unknown;
}

/** 검색어가 없으면 관련도순 비활성·최신순으로 폴백 */
function syncSortRelevanceOption() {
  const hasQ = !!(librarySearch && librarySearch.value.trim());
  const opt = document.getElementById("optSortRelevance");
  if (!filterSort) return;
  if (opt) {
    opt.disabled = !hasQ;
    opt.classList.toggle("sort-relevance-disabled", !hasQ);
  }
  if (!hasQ && filterSort.value === "relevance") {
    filterSort.value = "newest";
    libState.sort = "newest";
  }
}

function switchLibraryView(view) {
  currentLibraryView = view;
  if (view === "graph") {
    try {
      sessionStorage.setItem("libraryUserChoseGraph", "1");
    } catch (e) {
      /* ignore */
    }
  }
  document.getElementById("btnListView").classList.toggle("active", view === "list");
  document.getElementById("btnGraphView").classList.toggle("active", view === "graph");
  const filters = document.getElementById("libraryListViewFilters");
  if (filters) filters.style.display = view === "list" ? "" : "none";
  document.getElementById("libraryListView").style.display = view === "list" ? "" : "none";
  const lgv = document.getElementById("libraryGraphView");
  if (lgv) {
    lgv.style.display = view === "graph" ? "" : "none";
    lgv.classList.toggle("graph-view-expanded", view === "graph");
  }
  if (view === "graph") {
    document.body.classList.add("library-graph-fullscreen");
    requestAnimationFrame(() => {
      if (currentLibraryView === "graph") {
        _initGraphSettingsPanel();
        loadGraph();
      }
    });
  } else {
    document.body.classList.remove("library-graph-fullscreen");
  }
}

function buildMaterialsQuery() {
  const p = new URLSearchParams();
  p.set("page", String(libState.page));
  p.set("size", String(libState.size));
  if (libState.q) p.set("q", libState.q);
  if (libState.categoryLarge) p.set("category_large", libState.categoryLarge);
  if (libState.categoryMedium) p.set("category_medium", libState.categoryMedium);
  if (libState.categorySmall) p.set("category_small", libState.categorySmall);
  p.set("sort", libState.sort);
  p.set("status", libState.status);
  if (libState.importance >= 1 && libState.importance <= 5) {
    p.set("importance", String(libState.importance));
  }
  if (libState.materialType) p.set("material_type", libState.materialType);
  if (libState.dateFrom) p.set("date_from", libState.dateFrom);
  if (libState.dateTo) p.set("date_to", libState.dateTo);
  if (libState.entityId) p.set("entity_id", String(libState.entityId));
  if (libState.conceptId) p.set("concept_id", String(libState.conceptId));
  if (libState.tagFilter) p.set("tag", libState.tagFilter);
  return p.toString();
}

/** 구버전 서버에 /api/library/materials 가 없을 때 /api/library/search 로 대체 */
function buildSearchFallbackQuery() {
  const p = new URLSearchParams();
  p.set("page", String(libState.page));
  p.set("per_page", String(libState.size));
  if (libState.q) p.set("q", libState.q);
  if (libState.categoryLarge) p.set("category_large", libState.categoryLarge);
  if (libState.categoryMedium) p.set("category_medium", libState.categoryMedium);
  const st = libState.status === "all" ? "all" : libState.status;
  p.set("status", st);
  if (libState.materialType) p.set("material_type", libState.materialType);
  return p.toString();
}

async function fetchLibraryMaterialsList() {
  try {
    return await api(`/api/library/materials?${buildMaterialsQuery()}`);
  } catch (e) {
    const msg = String(e.message || "");
    const isNotFound = msg === "Not Found" || /\b404\b/i.test(msg);
    if (!isNotFound) throw e;
    return await api(`/api/library/search?${buildSearchFallbackQuery()}`);
  }
}

async function loadLibrary(opts) {
  if (!librarySearch || !filterCategoryLarge || !filterCategoryMedium) {
    console.error("도서관 필수 DOM(#librarySearch 등)이 없습니다. index.html을 확인하세요.");
    return;
  }
  if (opts && opts.search !== undefined && opts.search !== null) {
    libState.q = String(opts.search).trim();
    if (librarySearch) librarySearch.value = libState.q;
    libState.page = 1;
  } else {
    libState.q = librarySearch.value.trim();
  }
  syncSortRelevanceOption();
  try {
    const [listRes, catRes, statsRes] = await Promise.all([
      fetchLibraryMaterialsList(),
      api(`/api/library/categories${libState.materialType ? '?material_type=' + libState.materialType : ''}`),
      api(`/api/library/stats${libState.materialType ? '?material_type=' + libState.materialType : ''}`),
    ]);

    const rawCat = catRes.data;
    let tree = [];
    if (Array.isArray(rawCat)) {
      tree = rawCat;
      libState.sidebarTopTags = [];
    } else if (rawCat && typeof rawCat === "object") {
      tree = rawCat.categories || [];
      libState.sidebarTopTags = rawCat.top_tags || [];
    } else {
      libState.sidebarTopTags = [];
    }
    categoryTreeData = tree;
    fillCategoryFilterDropdowns();
    const st = statsRes && statsRes.data ? statsRes.data : null;
    const listPayloadForTotal = listRes && listRes.data ? listRes.data : null;
    libState.totalMaterials =
      st && typeof st.total_materials === "number"
        ? st.total_materials
        : (listPayloadForTotal && listPayloadForTotal.total != null
          ? listPayloadForTotal.total
          : libState.totalMaterials);
    renderStats(st);
    renderCategoryTree(categoryTreeData);
    await renderKnowledgeSidebar();
    const listPayload = listRes && listRes.data ? listRes.data : { items: [], total: 0, page: 1, per_page: libState.size, total_pages: 1 };
    lastLibraryListPayload = listPayload;
    renderMaterialList(listPayload);
    renderPagination(listPayload);
    highlightTreeSelection();
    if (libState.totalMaterials < 30 && !sessionStorage.getItem("libraryUserChoseGraph")) {
      switchLibraryView("list");
    }
  } catch (err) {
    console.error(err);
    showToast(`도서관 로드 실패: ${err.message}`, "error");
  }
}

/** 자료 삭제·보관 등으로 목록이 바뀐 뒤, 그래프 뷰가 열려 있으면 서버에서 그래프를 다시 받아 삭제된 노드·엣지를 반영한다. */
async function syncLibraryGraphIfVisible() {
  if (typeof resetLibraryGraphCache === "function") {
    resetLibraryGraphCache();
  }
  if (currentLibraryView === "graph") {
    await loadGraph();
  }
}

/** 섭취·기존 자료 업데이트 직후 도서관 데이터 갱신(숨겨진 탭 포함). 1페이지로 맞춰 신규 자료가 목록 상단에 오도록 함 */
async function refreshLibraryAfterIngest() {
  libState.page = 1;
  await loadLibrary();
  await syncLibraryGraphIfVisible();
}
window.refreshLibraryAfterIngest = refreshLibraryAfterIngest;

function fillCategoryFilterDropdowns() {
  const largeSel = filterCategoryLarge;
  const medSel = filterCategoryMedium;
  if (!largeSel || !medSel) return;
  const currentLarge = libState.categoryLarge;
  const currentMed = libState.categoryMedium;

  const tree = Array.isArray(categoryTreeData) ? categoryTreeData : [];
  const larges = tree.map((c) => c.name);
  largeSel.innerHTML = "";
  const z = document.createElement("option");
  z.value = "";
  z.textContent = "대분류 전체";
  largeSel.appendChild(z);
  larges.forEach((n) => {
    const o = document.createElement("option");
    o.value = n;
    o.textContent = n;
    largeSel.appendChild(o);
  });

  largeSel.value = currentLarge && larges.includes(currentLarge) ? currentLarge : "";

  const largeObj = tree.find((c) => c.name === largeSel.value);
  medSel.innerHTML = "";
  const mz = document.createElement("option");
  mz.value = "";
  mz.textContent = "중분류 전체";
  medSel.appendChild(mz);
  if (largeObj && largeObj.subcategories) {
    medSel.disabled = false;
    largeObj.subcategories.forEach((sub) => {
      const o = document.createElement("option");
      o.value = sub.name;
      o.textContent = `${sub.name} (${sub.count})`;
      medSel.appendChild(o);
    });
    medSel.value = currentMed && largeObj.subcategories.some((s) => s.name === currentMed) ? currentMed : "";
  } else {
    medSel.disabled = true;
    medSel.value = "";
  }
}

function renderStats(stats) {
  const bar = document.getElementById("statsBar");
  if (!bar) return;
  if (!stats || typeof stats !== "object") {
    bar.innerHTML = '<div class="stat-pill"><span class="sp-val">—</span><span class="sp-lbl">통계 없음</span></div>';
    return;
  }
  const top = stats.top_category_name != null
    ? `${escapeHtml(stats.top_category_name)}`
    : "—";
  const weekAdd = stats.added_this_week ?? 0;
  const weekBadge = weekAdd > 0 ? `<span class="sp-badge-new">+${weekAdd}</span>` : "";

  bar.innerHTML = `
    <div class="stat-pill sp-primary"><span class="sp-val">${stats.total_materials}</span><span class="sp-lbl">자료</span>${weekBadge}</div>
    <div class="stat-pill"><span class="sp-val">${stats.total_categories}</span><span class="sp-lbl">분류</span></div>
    <div class="stat-pill"><span class="sp-val">${stats.total_cross_references}</span><span class="sp-lbl">교차참조</span></div>
    <div class="stat-pill sp-wide"><span class="sp-icon">📂</span><span class="sp-lbl">${top}</span></div>
  `;
}

function renderCategoryTree(categories) {
  const container = document.getElementById("treeContent");
  if (!container) {
    console.error("#treeContent 요소가 없습니다. aside.category-tree 안에 <div id=\"treeContent\">가 있는지 확인하세요.");
    return;
  }

  const mtFilterHtml = `
    <div class="mt-tree-filter">
      <button type="button" class="mt-filter-btn ${!libState.materialType ? 'active' : ''}" data-mt="">📚 전체</button>
      <button type="button" class="mt-filter-btn mt-f-info ${libState.materialType === 'information' ? 'active' : ''}" data-mt="information">📰 정보</button>
      <button type="button" class="mt-filter-btn mt-f-user ${libState.materialType === 'user' ? 'active' : ''}" data-mt="user">👤 사용자</button>
    </div>
  `;

  const catsVisible = (categories || []).filter((c) => (c.count || 0) > 0);
  const totalAll = catsVisible.reduce((acc, c) => acc + (c.count || 0), 0);
  const allRootActive = !libState.treeSel.large;
  const treeAllHtml = `
    <button type="button" class="tree-all-root brand-item ${allRootActive ? "active" : ""}" data-action="tree-all" title="모든 출처·주제">
      <span class="brand-icon">📁</span>
      <span class="brand-name">전체</span>
      <span class="brand-count">${totalAll}</span>
    </button>
  `;

  const bindMtFilters = () => {
    container.querySelectorAll(".mt-filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        libState.materialType = btn.dataset.mt || "";
        libState.page = 1;
        loadLibrary();
      });
    });
  };

  const bindTreeAll = () => {
    const allBtn = container.querySelector(".tree-all-root");
    if (allBtn) {
      allBtn.addEventListener("click", () => {
        libState.treeSel = { large: "", medium: "", small: "" };
        libState.categoryLarge = "";
        libState.categoryMedium = "";
        libState.categorySmall = "";
        libState.treeCollapsed = {};
        libState.page = 1;
        if (filterCategoryLarge) filterCategoryLarge.value = "";
        if (filterCategoryMedium) filterCategoryMedium.value = "";
        loadLibrary();
      });
    }
  };

  if (!catsVisible || catsVisible.length === 0) {
    container.innerHTML = mtFilterHtml + treeAllHtml
      + '<p class="placeholder-text tree-empty-hint">자료를 섭취하면 여기에 출처별 폴더가 자동 생성됩니다.</p>';
    bindMtFilters();
    bindTreeAll();
    return;
  }

  container.innerHTML = mtFilterHtml + treeAllHtml + catsVisible
    .map((cat) => {
      const largeCount =
        cat.count != null
          ? cat.count
          : (cat.subcategories || []).reduce((acc, s) => acc + (s.count || 0), 0);
      const plat = cat.platform || "unknown";
      const pIcon = platformIcon(plat);
      const subHtml = (cat.subcategories || [])
        .map((sub) => `
          <div class="tree-medium-block">
            <div class="tree-item tree-item-medium topic-item ${libState.treeSel.large === cat.name && libState.treeSel.medium === sub.name ? "active" : ""}"
              data-large="${escapeHtml(cat.name)}" data-medium="${escapeHtml(sub.name)}" data-small="">
              ${escapeHtml(sub.name)} <span class="tree-count">(${sub.count ?? 0})</span>
            </div>
          </div>`)
        .join("");

      const underThisLarge = libState.treeSel.large === cat.name;
      const largeOnlySel = underThisLarge && !libState.treeSel.medium;
      const largeOpen = !libState.treeCollapsed[cat.name];

      return `
    <div class="tree-large" data-large="${escapeHtml(cat.name)}">
      <button type="button" class="tree-toggle tree-toggle-large brand-item ${largeOpen ? "open" : ""} ${largeOnlySel ? "active" : ""}" data-large="${escapeHtml(cat.name)}" data-medium="" data-small="" title="${escapeAttr(plat)}" aria-expanded="${largeOpen ? "true" : "false"}">
        <span class="arrow">▶</span>
        <span class="brand-icon" aria-hidden="true">${pIcon}</span>
        <span class="brand-name">${escapeHtml(cat.name)}</span>
        <span class="brand-count">${largeCount}</span>
      </button>
      <div class="tree-sub ${largeOpen ? "open" : ""}"${largeOpen ? "" : " hidden"}>${subHtml}</div>
    </div>`;
    })
    .join("");

  container.querySelectorAll(".tree-toggle-large").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const l = btn.dataset.large || "";
      if (libState.treeSel.large === l) {
        libState.treeCollapsed[l] = !libState.treeCollapsed[l];
        renderCategoryTree(categoryTreeData);
        highlightTreeSelection();
        refreshLibraryListFromTreeState();
        return;
      }
      libState.treeCollapsed[l] = false;
      applyTreeFilter(l, "", "");
    });
  });

  container.querySelectorAll(".tree-item-medium").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const large = el.dataset.large;
      const medium = el.dataset.medium || "";
      applyTreeFilter(large, medium, "");
    });
  });

  bindMtFilters();
  bindTreeAll();
}

let _keSidebarGen = 0;
async function renderKnowledgeSidebar() {
  const container = document.getElementById("treeContent");
  if (!container) return;

  const gen = ++_keSidebarGen;

  if (libState.materialType === "user") {
    const existing = container.querySelector(".ke-block");
    if (existing) existing.remove();
    return;
  }

  let tagHtml = "";
  let synHtml = "";
  try {
    const synRes = await api("/api/knowledge/synthesis");
    if (gen !== _keSidebarGen) return;
    const synthesis = synRes.data || [];

    const allTags = libState.sidebarTopTags || [];
    if (allTags.length) {
      const top10 = allTags.slice(0, 10);
      const rest = allTags.slice(10);
      const moreN = rest.length;
      const maxC = Math.max(...allTags.map((t) => t.count || 0), 1);
      function tagChipSize(c) {
        const ratio = c / maxC;
        if (ratio > 0.65) return "ke-chip-lg";
        if (ratio > 0.3) return "ke-chip-md";
        return "ke-chip-sm";
      }
      tagHtml = `
      <div class="ke-section">
        <div class="ke-section-header" data-ke="tags">
          <span class="ke-section-title">📌 주요 태그</span>
          <span class="ke-section-count">${allTags.length}</span>
        </div>
        <div class="ke-chips-wrap ke-chips-open" data-ke="tags">
          ${top10.map((t) => {
            const nm = t.name;
            const active = libState.tagFilter === nm;
            return `
            <button type="button" class="ke-chip ke-chip-tag ${tagChipSize(t.count || 0)} ${active ? "ke-chip-active" : ""}" data-tag-name="${escapeAttr(nm)}" title="${escapeHtml(nm)} (${t.count})">
              ${escapeHtml(nm)}<span class="ke-chip-n">${t.count}</span>
            </button>`;
          }).join("")}
          ${moreN ? `<button type="button" class="ke-chip ke-chip-more" data-tag-more="1">+${moreN}</button>` : ""}
          ${libState.tagFilter ? `<button type="button" class="ke-chip ke-chip-tag-clear">태그 해제</button>` : ""}
          ${moreN ? `<div class="ke-tag-rest" style="display:none">${rest.map((t) => {
            const nm = t.name;
            const active = libState.tagFilter === nm;
            return `<button type="button" class="ke-chip ke-chip-tag ${tagChipSize(t.count || 0)} ${active ? "ke-chip-active" : ""}" data-tag-name="${escapeAttr(nm)}" title="${escapeHtml(nm)} (${t.count})">
              ${escapeHtml(nm)}<span class="ke-chip-n">${t.count}</span>
            </button>`;
          }).join("")}</div>` : ""}
        </div>
      </div>`;
    }

    if (synthesis.length) {
      synHtml = `
      <div class="ke-section">
        <div class="ke-section-header" data-ke="synthesis">
          <span class="ke-section-title">📊 종합</span>
          <span class="ke-section-count">${synthesis.length}</span>
        </div>
        <div class="ke-chips-wrap ke-chips-open" data-ke="synthesis">
          ${synthesis.map((s) => {
            const fn = s.filename;
            const safeFn = escapeAttr(fn);
            return `
            <div class="ke-synth-wrap">
              <button type="button" class="ke-chip ke-chip-synth" data-ke-type="synthesis" data-ke-id="${safeFn}">
                ${escapeHtml(s.title || s.filename)}
              </button>
              <button type="button" class="ke-synth-delete" data-synth-filename="${safeFn}" title="이 종합 분석 삭제" aria-label="삭제">×</button>
            </div>`;
          }).join("")}
        </div>
      </div>`;
    }
  } catch (_) { /* silent */ }

  const keBlock = tagHtml + synHtml;
  if (!keBlock) {
    const existing = container.querySelector(".ke-block");
    if (existing) existing.remove();
    return;
  }

  let keContainer = container.querySelector(".ke-block");
  if (!keContainer) {
    keContainer = document.createElement("div");
    keContainer.className = "ke-block";
    container.appendChild(keContainer);
  }
  keContainer.innerHTML = '<div class="ke-divider"></div>' + keBlock;

  keContainer.querySelectorAll(".ke-section-header").forEach(hdr => {
    hdr.addEventListener("click", () => {
      const key = hdr.dataset.ke;
      const wrap = keContainer.querySelector(`.ke-chips-wrap[data-ke="${key}"]`);
      if (wrap) wrap.classList.toggle("ke-chips-open");
      hdr.classList.toggle("collapsed");
    });
  });

  keContainer.querySelectorAll(".ke-chip-more[data-tag-more]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const rest = btn.parentElement && btn.parentElement.querySelector(".ke-tag-rest");
      if (rest) rest.style.display = "";
      btn.remove();
    });
  });

  keContainer.querySelectorAll(".ke-chip-tag-clear").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      libState.tagFilter = "";
      libState.page = 1;
      loadLibrary();
    });
  });

  keContainer.querySelectorAll(".ke-chip-tag").forEach((chip) => {
    chip.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const nm = (chip.dataset.tagName || "").trim();
      if (!nm) return;
      if (libState.tagFilter === nm) {
        libState.tagFilter = "";
      } else {
        libState.tagFilter = nm;
        libState.entityId = 0;
        libState.conceptId = 0;
      }
      libState.page = 1;
      loadLibrary();
    });
  });

  keContainer.querySelectorAll(".ke-chip-synth").forEach((chip) => {
    chip.addEventListener("click", () => {
      const keId = chip.dataset.keId;
      showKnowledgeDetail("synthesis", keId);
    });
  });

  keContainer.querySelectorAll(".ke-synth-delete").forEach((delBtn) => {
    delBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      e.preventDefault();
      const fn = (delBtn.dataset.synthFilename || delBtn.getAttribute("data-synth-filename") || "").trim();
      if (!fn) return;
      if (!confirm(`종합 분석 파일을 삭제하시겠습니까?\n\n${fn}\n\n위키 폴더의 .md 파일이 영구 삭제됩니다.`)) return;
      try {
        await api("/api/knowledge/remove-synthesis", {
          method: "POST",
          body: { filename: fn },
        });
        showToast("종합 분석이 삭제되었습니다.", "success");
        await renderKnowledgeSidebar();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });
}

function _parseWikiFrontmatter(raw) {
  if (!raw) return { meta: {}, body: "" };

  let m = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/);
  if (!m) {
    m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  }

  if (m) {
    const meta = {};
    m[1].split(/\r?\n/).forEach((line) => {
      const kv = line.match(/^(\w[\w_]*):\s*(.+)$/);
      if (kv) meta[kv[1].trim()] = kv[2].replace(/^["']|["']$/g, "").trim();
    });
    return { meta, body: (m[2] || "").trim() };
  }

  const lines = raw.split(/\r?\n/);
  const bodyLines = [];
  let inYaml = false;
  for (const line of lines) {
    if (line.trim() === "---") {
      inYaml = !inYaml;
      continue;
    }
    if (inYaml) continue;
    if (/^[a-z_]+\s*:/.test(line.trim()) && bodyLines.length === 0) continue;
    bodyLines.push(line);
  }
  return { meta: {}, body: bodyLines.join("\n").trim() };
}

function _renderKeMeta(type, d, meta) {
  const icon = type === "entity" ? "👤" : "💡";
  const typeLabel = type === "entity" ? "핵심 태그" : "주제";
  const cat = meta.category || (type === "entity" ? (d.entity_type || d.type || "") : "");
  const firstSeen = meta.first_mentioned || d.first_seen || "";
  const matCount = d.mention_count || 0;
  return `
    <div class="ke-detail-header">
      <div class="ke-detail-icon">${icon}</div>
      <div class="ke-detail-info">
        <h2 class="ke-detail-name">${escapeHtml(d.name)}</h2>
        <div class="ke-detail-badges">
          <span class="ke-badge ke-badge-type">${escapeHtml(typeLabel)}</span>
          ${cat ? `<span class="ke-badge ke-badge-cat">${escapeHtml(cat)}</span>` : ""}
          <span class="ke-badge ke-badge-count">📄 ${matCount}개 자료에서 언급</span>
          ${firstSeen ? `<span class="ke-badge ke-badge-date">📅 ${escapeHtml(firstSeen)}</span>` : ""}
        </div>
      </div>
    </div>`;
}

/** marked.parse 직후: [[이름]] → 클릭 가능한 위키 링크 */
function _convertWikiLinks(containerElement) {
  if (!containerElement) return;
  const re = /\[\[([^\]]+)\]\]/g;
  const textNodes = [];
  const walk = document.createTreeWalker(containerElement, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue || !/\[\[/.test(node.nodeValue)) return NodeFilter.FILTER_REJECT;
      const par = node.parentElement;
      if (!par || par.closest("a, script, style, pre, code")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let tn;
  while ((tn = walk.nextNode())) textNodes.push(tn);
  for (const textNode of textNodes) {
    const text = textNode.nodeValue;
    re.lastIndex = 0;
    if (!re.test(text)) continue;
    const frag = document.createDocumentFragment();
    let last = 0;
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(text)) !== null) {
      frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      const a = document.createElement("a");
      a.href = "#";
      a.className = "wiki-link";
      const nm = (m[1] || "").trim();
      a.dataset.name = nm;
      a.textContent = nm;
      frag.appendChild(a);
      last = m.index + m[0].length;
    }
    frag.appendChild(document.createTextNode(text.slice(last)));
    textNode.parentNode.replaceChild(frag, textNode);
  }
}

async function buildKnowledgeDetailHtml(type, id, options = {}) {
  const includeClose = options.includeClose !== false;
  const closeAction = options.closeAction || "closeMaterialModal()";
  const closeBtn = includeClose
    ? `<button class="modal-close" onclick="${closeAction}">&times;</button>`
    : "";

  let res;
  if (type === "entity") {
    res = await api(`/api/knowledge/entities/${id}`);
  } else if (type === "concept") {
    res = await api(`/api/knowledge/concepts/${id}`);
  } else if (type === "synthesis") {
    res = await api(`/api/knowledge/synthesis/${encodeURIComponent(id)}`);
  } else {
    return "";
  }

  const d = res.data;

  if (type === "entity" || type === "concept") {
    const { meta, body: mdBody } = _parseWikiFrontmatter(d.wiki_content);
    const wikiHtml = mdBody && typeof marked !== "undefined"
      ? marked.parse(mdBody)
      : `<pre>${escapeHtml(mdBody || "")}</pre>`;
    const matList = (d.materials || []).map(m =>
      `<li class="ke-mat-item"><a href="#" onclick="showMaterialDetail(${m.id}); return false;">${escapeHtml(m.title)}</a><span class="ke-mat-date">${m.date || ""}</span></li>`
    ).join("");
    return `
      ${closeBtn}
      ${_renderKeMeta(type, d, meta)}
      <div class="ke-detail-content">
        <div class="wiki-md-body">${wikiHtml}</div>
        ${matList ? `<div class="ke-mat-section"><h3 class="ke-mat-title">📚 관련 자료</h3><ul class="ke-mat-list">${matList}</ul></div>` : ""}
      </div>
    `;
  }

  if (type === "synthesis") {
    const { body: mdBody } = _parseWikiFrontmatter(d.content);
    const wikiHtml = mdBody && typeof marked !== "undefined"
      ? marked.parse(mdBody)
      : `<pre>${escapeHtml(mdBody || "")}</pre>`;
    return `
      ${closeBtn}
      <div class="ke-detail-header">
        <div class="ke-detail-icon">📊</div>
        <div class="ke-detail-info"><h2 class="ke-detail-name">종합 분석</h2></div>
      </div>
      <div class="ke-detail-content"><div class="wiki-md-body">${wikiHtml}</div></div>
    `;
  }

  return "";
}

function _applyWikiLinksToRoots(container) {
  if (!container) return;
  container.querySelectorAll(".wiki-md-body").forEach((el) => _convertWikiLinks(el));
}

async function showKnowledgeDetail(type, id) {
  const modal = document.getElementById("materialModal");
  const content = document.getElementById("modalContent");
  if (!modal || !content) return;

  try {
    const body = await buildKnowledgeDetailHtml(type, id, {
      includeClose: false,
      closeAction: "closeMaterialModal()",
    });
    content.innerHTML = `
      <button type="button" class="modal-close" onclick="closeMaterialModal()" aria-label="닫기">&times;</button>
      <div class="modal-detail-body knowledge-modal-scroll">${body}</div>
    `;
    _applyWikiLinksToRoots(content);
    modal.classList.add("show");
    modal.querySelector(".modal-overlay").onclick = closeMaterialModal;
  } catch (err) {
    showToast("상세 보기 실패: " + err.message, "error");
  }
}

async function navigateWikiLinkByName(name, inWikiModal) {
  const q = (name || "").trim();
  if (!q) return;
  try {
    const entRes = await api("/api/knowledge/entities");
    const entities = entRes.data || [];
    const hitE = entities.find((e) => e.name === q);
    if (hitE) {
      if (inWikiModal) await showWikiContent("entity", hitE.id);
      else await showKnowledgeDetail("entity", hitE.id);
      return;
    }
    const conRes = await api("/api/knowledge/concepts");
    const concepts = conRes.data || [];
    const hitC = concepts.find((c) => c.name === q);
    if (hitC) {
      if (inWikiModal) await showWikiContent("concept", hitC.id);
      else await showKnowledgeDetail("concept", hitC.id);
      return;
    }
    await loadLibrary({ search: q });
  } catch (err) {
    showToast("위키 링크 이동 실패: " + err.message, "error");
  }
}

function openWikiViewer() {
  const modal = document.getElementById("wikiViewerModal");
  const main = document.getElementById("wikiViewerMain");
  if (!modal) return;
  if (main) {
    main.innerHTML = '<p class="placeholder-text wiki-v-placeholder">왼쪽에서 항목을 선택하세요.</p>';
  }
  modal.classList.add("show");
  loadWikiTab("entities");
}

function closeWikiViewerModal() {
  const modal = document.getElementById("wikiViewerModal");
  if (!modal) return;
  modal.classList.remove("show");
}

let _wikiViewerActiveTab = "entities";

async function loadWikiTab(type) {
  _wikiViewerActiveTab = type || "entities";
  const listEl = document.getElementById("wikiViewerList");
  const tabs = document.querySelectorAll(".wiki-v-tab");
  tabs.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.wikiTab === _wikiViewerActiveTab);
  });
  if (!listEl) return;
  listEl.innerHTML = '<p class="placeholder-text wiki-v-loading">불러오는 중...</p>';
  try {
    if (_wikiViewerActiveTab === "entities") {
      const r = await api("/api/knowledge/entities");
      const items = r.data || [];
      listEl.innerHTML = items.length
        ? items.map((e) => `<button type="button" class="wiki-v-item" data-wiki-type="entity" data-wiki-id="${e.id}">${escapeHtml(e.name)} <span class="wiki-v-n">${e.mention_count}</span></button>`).join("")
        : '<p class="placeholder-text">핵심 태그가 없습니다.</p>';
    } else if (_wikiViewerActiveTab === "concepts") {
      const r = await api("/api/knowledge/concepts");
      const items = r.data || [];
      listEl.innerHTML = items.length
        ? items.map((c) => `<button type="button" class="wiki-v-item" data-wiki-type="concept" data-wiki-id="${c.id}">${escapeHtml(c.name)} <span class="wiki-v-n">${c.mention_count}</span></button>`).join("")
        : '<p class="placeholder-text">주제가 없습니다.</p>';
    } else {
      const r = await api("/api/knowledge/synthesis");
      const items = r.data || [];
      listEl.innerHTML = items.length
        ? items.map((s) => {
            const fn = String(s.filename || "");
            const safeFn = fn.replace(/\\/g, "\\\\").replace(/"/g, "&quot;");
            return `<button type="button" class="wiki-v-item" data-wiki-type="synthesis" data-wiki-file="${safeFn}">${escapeHtml(s.title || s.filename)}</button>`;
          }).join("")
        : '<p class="placeholder-text">종합 페이지가 없습니다.</p>';
    }
    listEl.querySelectorAll(".wiki-v-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const wt = btn.dataset.wikiType;
        if (wt === "synthesis") showWikiContent("synthesis", btn.getAttribute("data-wiki-file") || "");
        else showWikiContent(wt, parseInt(btn.dataset.wikiId, 10));
      });
    });
  } catch (err) {
    listEl.innerHTML = `<p class="placeholder-text">목록 로드 실패: ${escapeHtml(err.message)}</p>`;
  }
}

async function showWikiContent(type, id) {
  const main = document.getElementById("wikiViewerMain");
  if (!main) return;
  try {
    main.innerHTML = '<p class="placeholder-text">불러오는 중...</p>';
    const body = await buildKnowledgeDetailHtml(type, id, {
      includeClose: false,
    });
    main.innerHTML = body;
    _applyWikiLinksToRoots(main);
  } catch (err) {
    main.innerHTML = `<p class="placeholder-text">내용을 불러올 수 없습니다: ${escapeHtml(err.message)}</p>`;
  }
}

document.addEventListener("click", (ev) => {
  const a = ev.target.closest(".wiki-link");
  if (!a) return;
  const inMat = a.closest("#materialModal.show");
  const inWiki = a.closest("#wikiViewerModal.show");
  if (!inMat && !inWiki) return;
  ev.preventDefault();
  navigateWikiLinkByName(a.dataset.name, Boolean(inWiki));
});

document.getElementById("btnOpenWikiViewer")?.addEventListener("click", () => openWikiViewer());
document.getElementById("wikiViewerModalClose")?.addEventListener("click", () => closeWikiViewerModal());
document.querySelector("#wikiViewerModal .wiki-viewer-overlay")?.addEventListener("click", () => closeWikiViewerModal());
document.querySelectorAll(".wiki-v-tab").forEach((btn) => {
  btn.addEventListener("click", () => loadWikiTab(btn.dataset.wikiTab));
});

function highlightTreeSelection() {
  const container = document.getElementById("treeContent");
  if (!container) return;
  container.querySelectorAll(".tree-all-root, .tree-toggle-large, .topic-item").forEach((el) => {
    el.classList.remove("active");
  });
  const { large, medium } = libState.treeSel;
  if (!large) {
    const root = container.querySelector(".tree-all-root");
    if (root) root.classList.add("active");
    return;
  }
  if (!medium) {
    container.querySelectorAll(".tree-toggle-large").forEach((b) => {
      if (b.dataset.large === large) b.classList.add("active");
    });
    return;
  }
  container.querySelectorAll(".tree-item-medium").forEach((el) => {
    if (el.dataset.large === large && el.dataset.medium === medium) el.classList.add("active");
  });
}

function applyTreeFilter(large, medium, small) {
  libState.tagFilter = "";
  libState.treeSel = { large, medium: medium || "", small: small || "" };
  libState.categoryLarge = large || "";
  libState.categoryMedium = medium || "";
  libState.categorySmall = small || "";
  libState.page = 1;
  if (libState.categoryMedium) {
    libState.sort = "newest";
    if (filterSort) filterSort.value = "newest";
  }
  if (large && (medium || small)) {
    libState.treeCollapsed[large] = false;
  }
  if (filterCategoryLarge) filterCategoryLarge.value = libState.categoryLarge;
  if (filterCategoryMedium) filterCategoryMedium.value = libState.categoryMedium;
  loadLibrary();
}

if (btnTreeViewAll) {
  btnTreeViewAll.addEventListener("click", () => {
    libState.tagFilter = "";
    libState.treeSel = { large: "", medium: "", small: "" };
    libState.categoryLarge = "";
    libState.categoryMedium = "";
    libState.categorySmall = "";
    libState.treeCollapsed = {};
    libState.page = 1;
    loadLibrary();
  });
}

if (btnSearch) {
  btnSearch.addEventListener("click", () => {
    libState.page = 1;
    loadLibrary();
  });
}
if (librarySearch) {
  librarySearch.addEventListener("input", () => {
    syncSortRelevanceOption();
  });
  librarySearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      libState.page = 1;
      loadLibrary();
    }
  });
}

if (filterCategoryLarge) {
  filterCategoryLarge.addEventListener("change", () => {
    libState.categoryLarge = filterCategoryLarge.value;
    libState.categoryMedium = "";
    libState.categorySmall = "";
    libState.treeSel = { large: libState.categoryLarge, medium: "", small: "" };
    libState.page = 1;
    loadLibrary();
  });
}

if (filterCategoryMedium) {
  filterCategoryMedium.addEventListener("change", () => {
    libState.categoryMedium = filterCategoryMedium.value;
    libState.categorySmall = "";
    libState.treeSel = {
      large: libState.categoryLarge,
      medium: libState.categoryMedium,
      small: "",
    };
    if (libState.categoryLarge && libState.categoryMedium) {
      libState.treeCollapsed[libState.categoryLarge] = false;
    }
    libState.page = 1;
    loadLibrary();
  });
}

if (filterSort) {
  filterSort.addEventListener("change", () => {
    libState.sort = filterSort.value;
    libState.page = 1;
    loadLibrary();
  });
}

if (filterStatus) {
  filterStatus.addEventListener("change", () => {
    libState.status = filterStatus.value;
    libState.page = 1;
    loadLibrary();
  });
}

if (importanceFilter) {
  importanceFilter.querySelectorAll("[data-imp]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const v = parseInt(btn.dataset.imp, 10);
      libState.importance = v;
      importanceFilter.querySelectorAll("[data-imp]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      libState.page = 1;
      loadLibrary();
    });
  });
}

const filterDateRange = document.getElementById("filterDateRange");
const customDateRange = document.getElementById("customDateRange");
const filterDateFrom = document.getElementById("filterDateFrom");
const filterDateTo = document.getElementById("filterDateTo");

function computeDateRange(val) {
  const today = new Date();
  const fmt = (d) => d.toISOString().slice(0, 10);
  if (val === "today") return { from: fmt(today), to: fmt(today) };
  if (val === "week") {
    const d = new Date(today);
    d.setDate(d.getDate() - d.getDay());
    return { from: fmt(d), to: fmt(today) };
  }
  if (val === "month") {
    return { from: `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`, to: fmt(today) };
  }
  return { from: "", to: "" };
}

if (filterDateRange) {
  filterDateRange.addEventListener("change", () => {
    const val = filterDateRange.value;
    if (val === "custom") {
      customDateRange.style.display = "flex";
      libState.dateFrom = filterDateFrom?.value || "";
      libState.dateTo = filterDateTo?.value || "";
    } else {
      customDateRange.style.display = "none";
      const r = computeDateRange(val);
      libState.dateFrom = r.from;
      libState.dateTo = r.to;
    }
    libState.page = 1;
    loadLibrary();
  });
}
if (filterDateFrom) {
  filterDateFrom.addEventListener("change", () => {
    libState.dateFrom = filterDateFrom.value;
    libState.page = 1;
    loadLibrary();
  });
}
if (filterDateTo) {
  filterDateTo.addEventListener("change", () => {
    libState.dateTo = filterDateTo.value;
    libState.page = 1;
    loadLibrary();
  });
}

document.addEventListener("click", (e) => {
  if (e.target.closest(".lib-card-menu-wrap")) return;
  document.querySelectorAll(".lib-card-dropdown").forEach((d) => {
    d.style.display = "none";
  });
});

function renderPagination(data) {
  if (!libraryRange || !libraryPagination) return;
  if (isCurrentPlatformTreeCollapsed()) {
    libraryRange.textContent = "";
    libraryPagination.innerHTML = "";
    return;
  }
  const total = data.total || 0;
  const page = data.page || 1;
  const per = data.per_page || libState.size;
  const totalPages = data.total_pages || 1;
  const from = total === 0 ? 0 : (page - 1) * per + 1;
  const to = Math.min(page * per, total);

  libraryRange.textContent = `전체 ${total}개 자료 중 ${from}-${to}`;

  if (totalPages <= 1) {
    libraryPagination.innerHTML = "";
    return;
  }

  const pages = [];
  const windowSize = 10;
  let start = Math.max(1, page - 4);
  let end = Math.min(totalPages, start + windowSize - 1);
  if (end - start < windowSize - 1) start = Math.max(1, end - windowSize + 1);

  for (let i = start; i <= end; i++) {
    pages.push(
      `<button type="button" class="page-btn ${i === page ? "active" : ""}" data-page="${i}">${i}</button>`
    );
  }

  libraryPagination.innerHTML = `
    <button type="button" class="page-btn page-nav" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>이전</button>
    ${pages.join("")}
    <button type="button" class="page-btn page-nav" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>다음</button>
  `;

  libraryPagination.querySelectorAll("[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const np = parseInt(btn.dataset.page, 10);
      if (np < 1 || np > totalPages || np === page) return;
      libState.page = np;
      loadLibrary();
    });
  });
}

function renderMaterialList(data) {
  const container = document.getElementById("libraryList");
  if (!container) return;
  if (isCurrentPlatformTreeCollapsed()) {
    container.innerHTML =
      '<p class="placeholder-text library-list-collapsed-hint">왼쪽에서 플랫폼을 펼치면 자료 목록이 표시됩니다.</p>';
    return;
  }
  const items = data.items || [];
  if (items.length === 0) {
    container.innerHTML = '<p class="placeholder-text">자료가 없습니다.</p>';
    return;
  }

  container.innerHTML = items
    .map((item) => {
      const strip = getStripColor(item.category_small || item.category_medium);
      const path = [item.category_large, item.category_medium, item.category_small].filter(Boolean).join(" > ");
      const imp = item.importance != null ? item.importance : 3;
      const starHtml = Array.from({ length: 5 }, (_, i) => {
        const n = i + 1;
        return `<span class="star-slot" data-star="${n}" role="button" tabindex="0">${n <= imp ? "★" : "☆"}</span>`;
      }).join("");
      const summaryText = (item.summary || "").replace(/\s+/g, " ").trim();
      const summaryShort = summaryText.length > 120 ? summaryText.slice(0, 120) + "…" : summaryText;
      const tagsHtml = (item.tags || []).slice(0, 5).map((t) => `<span class="tag" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`).join("");
      const moreTagsCount = (item.tags || []).length - 5;
      const moreTagsHtml = moreTagsCount > 0 ? `<span class="tag tag-more">+${moreTagsCount}</span>` : "";

      const isChecked = selectedMaterialIds.has(item.id);
      const mtDot = item.material_type === "user"
        ? '<span class="lc-type-dot lc-type-user" title="사용자"></span>'
        : '<span class="lc-type-dot lc-type-info" title="정보"></span>';
      const srcShort = (item.source || "").length > 25 ? (item.source || "").slice(0, 25) + "…" : (item.source || "");
      const platLabel = (item.category_large || "").trim() || "기타";
      const brandLabel = (item.category_medium || "").trim() || "미분류";
      const pform = item.platform || "unknown";
      const brandBadge = `<button type="button" class="material-brand-badge" data-plat="${escapeAttr(platLabel)}" data-brand="${escapeAttr(brandLabel)}" title="${escapeAttr(platLabel)} · ${escapeAttr(brandLabel)} 필터">${platformIcon(pform)} ${escapeHtml(brandLabel)}</button>`;
      const origRaw = (item.original_date || "").toString().trim();
      const ingestLine = item.ingested_date
        ? `📥 입고: ${escapeHtml(formatKstDateWithWeekday(item.ingested_date))}`
        : "";
      const origLine = origRaw ? `📅 원본: ${escapeHtml(formatKstDateWithWeekday(origRaw))}` : "";
      let dateBlock = "";
      if (ingestLine && origLine) {
        dateBlock = `<div class="material-date-info"><span class="ingest-date">${ingestLine}</span><span class="pipe">|</span><span class="original-date">${origLine}</span></div>`;
      } else if (ingestLine) {
        dateBlock = `<div class="material-date-info"><span class="ingest-date">${ingestLine}</span></div>`;
      } else if (origLine) {
        dateBlock = `<div class="material-date-info"><span class="original-date">${origLine}</span></div>`;
      }
      const ingYmdKst = item.ingested_date
        ? new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(item.ingested_date))
        : "";
      const isNew = ingYmdKst && ingYmdKst === kstTodayYmd();

      return `
    <div class="lib-card ${isChecked ? "bulk-selected" : ""}" data-id="${item.id}">
      <div class="lib-card-strip" style="background:${strip}"></div>
      <div class="lib-card-inner">
        <div class="lc-row1">
          <label class="bulk-cb-wrap" onclick="event.stopPropagation()">
            <input type="checkbox" class="bulk-cb" ${isChecked ? "checked" : ""}>
          </label>
          ${mtDot}
          ${brandBadge}
          ${isNew ? '<span class="lib-card-badge-new">NEW</span>' : ""}
          ${item.has_contradiction ? '<span class="lc-warn" title="모순 발견">⚠️</span>' : ""}
          <button type="button" class="lib-card-title-btn" data-action="detail">${escapeHtml(item.title)}</button>
          <div class="lc-right">
            <div class="lib-card-stars" data-action="stars" title="중요도">${starHtml}</div>
            <div class="lib-card-menu-wrap">
              <button type="button" class="lib-card-menu-btn" data-action="menu" aria-label="더보기">⋮</button>
              <div class="lib-card-dropdown" style="display:none;">
                <button type="button" data-m="detail"><span class="dm-icon">📄</span> 상세보기</button>
                <button type="button" data-m="raw"><span class="dm-icon">📎</span> 원본보기</button>
                <button type="button" data-m="project"><span class="dm-icon">📁</span> 프로젝트에 추가</button>
                <button type="button" data-m="copy"><span class="dm-icon">📋</span> 요약 복사</button>
                <div class="dropdown-divider"></div>
                <button type="button" data-m="delete" class="dropdown-danger"><span class="dm-icon">🗑️</span> 삭제</button>
              </div>
            </div>
          </div>
        </div>
        <p class="lib-card-summary">${escapeHtml(summaryShort)}</p>
        <div class="lc-footer">
          <span class="lc-cat">${escapeHtml(path)}</span>
          ${dateBlock || ""}
          ${srcShort ? `<span class="lc-meta" title="${escapeHtml(item.source || "")}">${escapeHtml(srcShort)}</span>` : ""}
          <div class="lc-tags">${tagsHtml}${moreTagsHtml}</div>
        </div>
      </div>
    </div>`;
    })
    .join("");

  container.querySelectorAll(".lib-card").forEach((card) => {
    const id = parseInt(card.dataset.id, 10);

    const bulkCb = card.querySelector(".bulk-cb");
    if (bulkCb) {
      bulkCb.addEventListener("change", () => {
        if (bulkCb.checked) {
          selectedMaterialIds.add(id);
          card.classList.add("bulk-selected");
        } else {
          selectedMaterialIds.delete(id);
          card.classList.remove("bulk-selected");
        }
        updateBulkBar();
      });
    }

    card.querySelector(".lib-card-title-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      showMaterialDetail(id);
    });

    const brandBadgeEl = card.querySelector(".material-brand-badge");
    if (brandBadgeEl) {
      brandBadgeEl.addEventListener("click", (e) => {
        e.stopPropagation();
        const plat = (brandBadgeEl.dataset.plat || "").trim();
        const b = (brandBadgeEl.dataset.brand || "").trim();
        if (!plat || !b || b === "미분류") return;
        applyTreeFilter(plat, b, "");
      });
    }

    card.querySelector(".lib-card-strip").addEventListener("click", (e) => {
      e.stopPropagation();
      showMaterialDetail(id);
    });

    card.querySelectorAll(".star-slot").forEach((slot) => {
      slot.addEventListener("click", async (e) => {
        e.stopPropagation();
        const star = parseInt(slot.dataset.star, 10);
        try {
          await api(`/api/library/material/${id}/importance`, {
            method: "PUT",
            body: { importance: star },
          });
          showToast("중요도가 변경되었습니다.", "success");
          loadLibrary();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    const menuBtn = card.querySelector(".lib-card-menu-btn");
    const dropdown = card.querySelector(".lib-card-dropdown");
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      document.querySelectorAll(".lib-card-dropdown").forEach((d) => {
        if (d !== dropdown) d.style.display = "none";
      });
      dropdown.style.display = dropdown.style.display === "none" ? "block" : "none";
    });

    dropdown.querySelectorAll("button[data-m]").forEach((b) => {
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        dropdown.style.display = "none";
        handleCardAction(b.dataset.m, id, card);
      });
    });

    card.querySelectorAll(".qa-btn").forEach((b) => {
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        handleCardAction(b.dataset.qa, id, card);
      });
    });

    card.querySelectorAll(".tag[data-tag]").forEach((tagEl) => {
      tagEl.addEventListener("click", (e) => {
        e.stopPropagation();
        const searchInput = document.getElementById("librarySearch");
        if (searchInput) {
          searchInput.value = tagEl.dataset.tag;
          libState.q = tagEl.dataset.tag;
          libState.page = 1;
          loadLibrary();
        }
      });
    });
  });
}

async function handleCardAction(action, id, card) {
  const title = card.querySelector(".lib-card-title-btn").textContent;
  if (action === "detail") {
    showMaterialDetail(id);
  } else if (action === "project") {
    openProjectPicker(id);
  } else if (action === "raw") {
    try {
      const info = await api(`/api/library/material/${id}/raw-info`);
      if (info.data && info.data.download_url) {
        window.open(info.data.download_url, "_blank");
      } else {
        showToast("원본 파일을 찾을 수 없습니다.", "error");
      }
    } catch (err) {
      showToast(err.message, "error");
    }
  } else if (action === "copy") {
    try {
      const resp = await api(`/api/library/material/${id}`);
      const d = resp.data || resp;
      const text = `[${d.title}]\n${d.summary || ""}`;
      await navigator.clipboard.writeText(text);
      showToast("요약이 클립보드에 복사되었습니다.", "success");
    } catch (err) {
      showToast("복사 실패: " + err.message, "error");
    }
  } else if (action === "delete") {
    openMaterialDeleteModal(id, title);
  }
}

let pendingDeleteId = null;
let pendingProjectMaterialId = null;

function openMaterialDeleteModal(id, title) {
  pendingDeleteId = id;
  const actionTitle = document.getElementById("materialActionTitle");
  if (actionTitle) actionTitle.textContent = `자료 처리: ${title}`;
  document.getElementById("materialActionText").textContent =
    `정말 삭제하시겠습니까?\n\n「${title}」\n\n이 작업은 되돌릴 수 없습니다.\n(위키 페이지, 원본 파일, DB 기록이 모두 삭제됩니다.)`;
  document.getElementById("materialActionModal").style.display = "flex";
}

function closeMaterialActionModal() {
  document.getElementById("materialActionModal").style.display = "none";
  pendingDeleteId = null;
}

document.getElementById("btnConfirmSoftDelete").addEventListener("click", async () => {
  if (!pendingDeleteId) return;
  try {
    await api(`/api/library/material/${pendingDeleteId}`, { method: "DELETE" });
    showToast("자료가 완전히 삭제되었습니다.", "success");
    closeMaterialActionModal();
    await loadLibrary();
    await syncLibraryGraphIfVisible();
  } catch (err) {
    showToast(err.message, "error");
  }
});

document.getElementById("btnConfirmArchive").addEventListener("click", async () => {
  if (!pendingDeleteId) return;
  try {
    await api(`/api/library/material/${pendingDeleteId}/status`, {
      method: "PUT",
      body: { status: "archive" },
    });
    showToast("보관함으로 이동했습니다.", "success");
    closeMaterialActionModal();
    await loadLibrary();
    await syncLibraryGraphIfVisible();
  } catch (err) {
    showToast(err.message, "error");
  }
});

async function openProjectPicker(materialId) {
  pendingProjectMaterialId = materialId;
  try {
    const res = await api("/api/projects/");
    const sel = document.getElementById("projectPickSelect");
    sel.innerHTML = (res.data || [])
      .map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)
      .join("");
    if (!res.data || res.data.length === 0) {
      showToast("먼저 작업실에서 프로젝트를 만드세요.", "info");
      return;
    }
    document.getElementById("projectPickModal").style.display = "flex";
  } catch (err) {
    showToast(err.message, "error");
  }
}

function closeProjectPickModal() {
  document.getElementById("projectPickModal").style.display = "none";
  pendingProjectMaterialId = null;
}

document.getElementById("btnProjectPickConfirm").addEventListener("click", async () => {
  const pid = document.getElementById("projectPickSelect").value;
  if (!pid || !pendingProjectMaterialId) return;
  try {
    await api(`/api/projects/${pid}/materials`, {
      method: "POST",
      body: { material_id: pendingProjectMaterialId },
    });
    showToast("프로젝트에 추가되었습니다.", "success");
    closeProjectPickModal();
  } catch (err) {
    showToast(err.message, "error");
  }
});

function formatFileSize(bytes) {
  if (bytes == null || isNaN(bytes)) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderSheetTables(tables) {
  if (!tables || !tables.length) return '<p class="placeholder-text">표 데이터가 없습니다.</p>';
  return tables
    .map((sheet) => {
      const rows = sheet.rows || [];
      const body = rows
        .map(
          (row) =>
            `<tr>${row.map((c) => `<td>${escapeHtml(String(c ?? ""))}</td>`).join("")}</tr>`
        )
        .join("");
      return `<div class="sheet-block"><h4 class="sheet-title">${escapeHtml(sheet.name)}</h4><div class="table-scroll"><table class="preview-table"><tbody>${body}</tbody></table></div></div>`;
    })
    .join("");
}

function setDetailTab(modalEl, tabName) {
  modalEl.querySelectorAll(".detail-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  modalEl.querySelectorAll(".detail-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === tabName);
  });
}

/** 원본 전문: 문단 단위 HTML (이스케이프 적용) */
function formatOriginalContent(text) {
  if (!text) return "";
  if (text.includes("\n\n")) {
    return text
      .split("\n\n")
      .map((p) => `<p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`)
      .join("");
  }
  return text
    .replace(/([.?!…])\s+/g, "$1\n\n")
    .split("\n\n")
    .filter((p) => p.trim())
    .map((p) => `<p>${escapeHtml(p.trim())}</p>`)
    .join("");
}

function _detailImportanceStars(n) {
  const v = n != null ? Math.min(5, Math.max(1, Number(n))) : 3;
  return `${"★".repeat(v)}${"☆".repeat(5 - v)}`;
}

function _renderGradedEntitySection(items) {
  if (!items.length) return "";
  const a = items.filter((e) => (e.grade || "B") === "A");
  const b = items.filter((e) => (e.grade || "B") === "B");
  const chipA = (e) =>
    `<span class="related-chip entity grade-a" role="button" tabindex="0" onclick="showKnowledgeDetail('entity',${e.id})"><strong>${escapeHtml(e.name)}</strong> <span class="related-chip-sub">(${escapeHtml(e.type || "")})</span></span>`;
  const chipB = (e) =>
    `<span class="related-chip entity grade-b" role="button" tabindex="0" onclick="showKnowledgeDetail('entity',${e.id})">${escapeHtml(e.name)} <span class="related-chip-sub">(${escapeHtml(e.type || "")})</span></span>`;
  let inner = "";
  if (a.length) inner += `<div class="related-chips">${a.map(chipA).join("")}</div>`;
  if (b.length) {
    inner += `<div class="related-chips-subtitle">기타 관련 항목</div><div class="related-chips">${b.map(chipB).join("")}</div>`;
  }
  return `<div class="summary-section"><div class="summary-section-title">🔖 관련 핵심 태그</div>${inner}</div>`;
}

function _renderGradedConceptSection(items) {
  if (!items.length) return "";
  const a = items.filter((c) => (c.grade || "B") === "A");
  const b = items.filter((c) => (c.grade || "B") === "B");
  const chipA = (c) =>
    `<span class="related-chip concept grade-a" role="button" tabindex="0" onclick="showKnowledgeDetail('concept',${c.id})"><strong>${escapeHtml(c.name)}</strong></span>`;
  const chipB = (c) =>
    `<span class="related-chip concept grade-b" role="button" tabindex="0" onclick="showKnowledgeDetail('concept',${c.id})">${escapeHtml(c.name)}</span>`;
  let inner = "";
  if (a.length) inner += `<div class="related-chips">${a.map(chipA).join("")}</div>`;
  if (b.length) {
    inner += `<div class="related-chips-subtitle">기타 관련 항목</div><div class="related-chips">${b.map(chipB).join("")}</div>`;
  }
  return `<div class="summary-section"><div class="summary-section-title">💎 관련 주제</div>${inner}</div>`;
}

async function showMaterialDetail(id) {
  try {
    const detailRes = await api(`/api/library/material/${id}`);
    const m = detailRes.data;

    let full = {
      content: m.content || "",
      format: "text",
      tables: null,
    };
    try {
      const fullRes = await api(`/api/library/material/${id}/full-content`);
      full = fullRes.data;
    } catch (e) {
      const msg = String(e.message || "");
      if (!msg.includes("Not Found") && !/\b404\b/i.test(msg)) throw e;
    }

    let raw = null;
    try {
      const rawRes = await api(`/api/library/material/${id}/raw-info`);
      raw = rawRes.data;
    } catch {
      raw = null;
    }

    let keEntities = [], keConcepts = [], keContradictions = [];
    try {
      const [entR, conR, ctrR] = await Promise.all([
        api(`/api/knowledge/material/${id}/entities`),
        api(`/api/knowledge/material/${id}/concepts`),
        api(`/api/knowledge/material/${id}/contradictions`),
      ]);
      keEntities = entR.data || [];
      keConcepts = conR.data || [];
      keContradictions = ctrR.data || [];
    } catch { /* silent */ }
    const modal = document.getElementById("materialModal");
    const content = document.getElementById("modalContent");

    const crossRefsHtml = (m.cross_references || [])
      .map(
        (r) => `<div class="cross-ref-item" role="button" tabindex="0" onclick="showMaterialDetail(${r.id})">
        <strong>${escapeHtml(r.title)}</strong> <span class="summary-tag" style="margin-left:6px;">${escapeHtml(r.relation_type)}</span>
        ${r.description ? `<div class="cross-ref-desc">${escapeHtml(r.description)}</div>` : ""}
      </div>`
      )
      .join("");

    const platIcon = platformIcon(m.platform || "unknown");
    const ingestedStr = m.ingested_date ? formatKstDateWithWeekday(m.ingested_date) : "—";
    const origStr = (m.original_date || "").toString().trim();
    const origRow = origStr
      ? `<tr><td>원본일</td><td>${escapeHtml(formatKstDateWithWeekday(origStr))}</td></tr>`
      : "";
    const wikiBody = m.wiki_body || "";
    const summarySource = wikiBody || m.summary || "요약 없음";
    const summaryMd =
      typeof marked !== "undefined" && marked.parse
        ? marked.parse(summarySource)
        : escapeHtml(summarySource);

    let fullBody = "";
    if (full.format === "tabular" && full.tables && full.tables.length) {
      const nSheets = full.tables.length;
      fullBody = `
        <div class="original-content-header">
          <span>📊 표 형식 원본</span>
          <span class="char-count">${nSheets}개 시트</span>
        </div>
        <div class="full-tabular">${renderSheetTables(full.tables)}</div>`;
    } else {
      const rawFullContent = full.content || "";
      const translatedP = (
        (m.translated_content || full.translated_content || "") + ""
      ).trim();
      const displayText = translatedP || rawFullContent;
      const n = displayText.length;
      const asciiCount = [...rawFullContent.slice(0, 500)].filter((c) => c.charCodeAt(0) < 128).length;
      const isEnglish =
        rawFullContent.length > 100 &&
        asciiCount / Math.min(rawFullContent.length, 500) > 0.7;
      const hasTranslation = translatedP.length > 0;

      let translateBtn = "";
      if (hasTranslation) {
        translateBtn = `<span class="btn-translate-done" style="margin-left:12px; padding:4px 12px; border-radius:6px; background:#2d8a4e; color:white; font-size:13px; display:inline-block;">✅ 번역됨</span>`;
      } else if (isEnglish) {
        translateBtn = `
          <button type="button" class="btn-translate" onclick="translateFullContent(${id})"
                  style="margin-left:12px; padding:4px 12px; border-radius:6px;
                         background:#4a6fa5; color:white; border:none; cursor:pointer; font-size:13px;">
            🌐 한국어 번역
          </button>`;
      }

      const header = `
        <div class="original-content-header">
          <span>📄 원본 전문</span>
          <span class="char-count">총 ${n.toLocaleString()}자</span>
          ${translateBtn}
        </div>`;
      // 마크다운 감지: ##, -, *, ** 등이 있으면 마크다운으로 판단 (멀티라인: 각 줄 시작 기준)
      const hasMarkdown = /^#{1,3}\s|^\s*[-*]\s|\*\*/m.test(displayText);

      if (hasMarkdown && typeof marked !== "undefined" && marked.parse) {
        fullBody = `${header}<div class="original-content-reader"><div class="wiki-md-body">${marked.parse(displayText)}</div></div>`;
      } else {
        const lines = displayText.split("\n").filter((l) => l.trim().length > 0);
        const paragraphs = [];
        let buffer = [];

        for (const line of lines) {
          const trimmed = line.trim();
          buffer.push(trimmed);

          if (
            /[.?!。？！~]\s*$/.test(trimmed) ||
            /[다요죠네요습니까]\s*[.?!]?\s*$/.test(trimmed) ||
            trimmed.startsWith("[") ||
            buffer.join(" ").length > 200
          ) {
            paragraphs.push(buffer.join(" "));
            buffer = [];
          }
        }
        if (buffer.length > 0) {
          paragraphs.push(buffer.join(" "));
        }

        const formatted = paragraphs
          .map((p) => `<p class="plain-paragraph">${escapeHtml(p)}</p>`)
          .join("");
        fullBody = `${header}<div class="original-content-reader"><div class="plain-text-body">${formatted}</div></div>`;
      }
    }

    const sourceUrl = ((m.source_url || "") + "").trim();
    const sourceLinkRow = sourceUrl
      ? `<div class="file-info-label">원본 URL</div><div class="file-info-value"><a href="${escapeAttr(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceUrl)}</a></div>`
      : "";

    let rawBody = "";
    if (!raw) {
      rawBody = '<p class="placeholder-text">원본 파일 정보를 불러올 수 없습니다.</p>';
    } else {
      rawBody = `
        <div class="file-info-card">
          <div class="file-info-grid">
            <div class="file-info-label">파일명</div>
            <div class="file-info-value">${escapeHtml(raw.filename)}</div>
            <div class="file-info-label">크기</div>
            <div class="file-info-value">${formatFileSize(raw.size_bytes)}</div>
            <div class="file-info-label">형식</div>
            <div class="file-info-value">${escapeHtml(raw.extension)} (${escapeHtml(raw.mime_type)})</div>
            <div class="file-info-label">저장 경로</div>
            <div class="file-info-value"><code class="raw-path">${escapeHtml(raw.relative_path || "")}</code></div>
            <div class="file-info-label">정적 URL</div>
            <div class="file-info-value"><a href="${escapeAttr(raw.static_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(raw.static_url)}</a></div>
            ${sourceLinkRow}
          </div>
          <a class="file-download-btn" href="${escapeAttr(raw.download_url)}" download="${escapeAttr(raw.filename)}">📥 원본 파일 다운로드</a>
        </div>`;
    }

    content.innerHTML = `
      <button type="button" class="modal-close" onclick="closeMaterialModal()" aria-label="닫기">&times;</button>
      <div class="material-modal-layout">
        <div class="modal-detail-header">
          <div class="detail-title-row" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <h2 class="detail-title" id="detailTitle" style="margin:0;flex:0 1 auto;min-width:0;">${escapeHtml(m.title)}</h2>
            <button type="button" class="detail-edit-btn" id="detailEditBtn" data-mid="${m.id}" data-editing="false" title="수정"
              style="display:inline-block;background:none;border:none;cursor:pointer;font-size:16px;opacity:0.6;padding:4px;flex-shrink:0;margin-left:8px;vertical-align:middle;"
              onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.6'">✏️</button>
          </div>
          <div class="detail-category-row">
            <span id="detailCategory">📂 ${escapeHtml(m.category_large)} &gt; ${escapeHtml(m.category_medium)}${m.category_small ? " &gt; " + escapeHtml(m.category_small) : ""}</span>
          </div>
          <div class="detail-meta">
            <span>📰 ${escapeHtml(m.source || "")}</span>
          </div>
        </div>
        <div class="detail-tabs modal-detail-tabs" role="tablist">
          <button type="button" class="detail-tab active" data-tab="summary" role="tab">요약</button>
          <button type="button" class="detail-tab" data-tab="full" role="tab">원본 전문</button>
          <button type="button" class="detail-tab" data-tab="raw" role="tab">원본 파일</button>
        </div>
        <div class="modal-detail-body">
          <div class="detail-panel active" data-panel="summary" role="tabpanel">
            <div class="summary-section">
              <div class="summary-section-title">📋 기본 정보</div>
              <table class="summary-info-table">
                <tr><td>플랫폼</td><td>${platIcon} ${escapeHtml(m.category_large || "—")}</td></tr>
                <tr><td>채널</td><td>${escapeHtml(m.category_medium || "—")}</td></tr>
                <tr><td>입고일</td><td>${escapeHtml(ingestedStr)}</td></tr>
                ${origRow}
                <tr><td>출처</td><td>${escapeHtml(m.source || "—")}</td></tr>
                <tr><td>중요도</td><td>${_detailImportanceStars(m.importance)}</td></tr>
              </table>
            </div>
            <div class="summary-section">
              <div class="summary-section-title">📝 요약</div>
              <div class="summary-content-box"><div class="wiki-md-body">${summaryMd}</div></div>
            </div>
            <div class="summary-section">
              <div class="summary-section-title">🏷️ 태그</div>
              <div class="summary-tags">${(m.tags || []).length ? (m.tags || []).map((t) => `<span class="summary-tag">${escapeHtml(t)}</span>`).join("") : '<span class="placeholder-text" style="display:inline;">태그 없음</span>'}</div>
            </div>
            ${crossRefsHtml ? `<div class="summary-section"><div class="summary-section-title">🔗 교차 참조</div>${crossRefsHtml}</div>` : ""}
            ${_renderGradedEntitySection(keEntities)}
            ${_renderGradedConceptSection(keConcepts)}
            ${keContradictions.length ? `<div class="summary-section"><div class="summary-section-title">⚠️ 모순</div>${keContradictions.map((c) => `<div class="ke-contradiction"><strong>${escapeHtml(c.other_material.title)}</strong>: ${escapeHtml(c.description)} <span class="tag ${c.status === "resolved" ? "tag-ok" : "tag-warn"}">${c.status === "resolved" ? "해결됨" : "미해결"}</span></div>`).join("")}</div>` : ""}
            <div class="detail-actions">
              <button type="button" class="btn btn-secondary" onclick="showVersionHistory(${m.id})">📜 버전 이력</button>
            </div>
          </div>
          <div class="detail-panel" data-panel="full" role="tabpanel">${fullBody}</div>
          <div class="detail-panel" data-panel="raw" role="tabpanel">${rawBody}</div>
        </div>
      </div>
    `;

    content.querySelectorAll(".detail-tab").forEach((btn) => {
      btn.addEventListener("click", () => setDetailTab(modal, btn.dataset.tab));
    });
    content.querySelectorAll(".wiki-md-body").forEach((el) => _convertWikiLinks(el));

    document.getElementById("detailEditBtn")?.addEventListener("click", () => {
      _toggleDetailEditMode(
        m.id,
        m.title,
        m.category_large,
        m.category_medium,
        m.category_small || "",
      );
    });

    modal.classList.add("show");
    modal.querySelector(".modal-overlay").onclick = closeMaterialModal;
  } catch (err) {
    showToast(`상세 로드 실패: ${err.message}`, "error");
  }
}

function closeMaterialModal() {
  document.getElementById("materialModal").classList.remove("show");
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const wikiModal = document.getElementById("wikiViewerModal");
    if (wikiModal && wikiModal.classList.contains("show")) {
      closeWikiViewerModal();
      return;
    }
    const modal = document.getElementById("materialModal");
    if (modal && modal.classList.contains("show")) {
      closeMaterialModal();
    }
  }
});

async function translateFullContent(materialId) {
  const btn = document.querySelector(".btn-translate");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "번역 중...";
  }
  try {
    const res = await fetch(`/api/library/material/${materialId}/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json();
    if (data.success && data.translated_content) {
      if (btn) {
        btn.textContent = "✅ 번역 완료";
        btn.style.background = "#2d8a4e";
      }
      await showMaterialDetail(materialId);
    } else {
      if (btn) {
        btn.textContent = "번역 실패";
        btn.style.background = "#c0392b";
      }
    }
  } catch (e) {
    if (btn) {
      btn.textContent = "번역 실패";
      btn.style.background = "#c0392b";
    }
  }
}


