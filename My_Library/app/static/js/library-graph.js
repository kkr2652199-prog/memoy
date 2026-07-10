/* === D3 graph view (library-graph.js) — load after library.js === */

let _graphSettingsPanelInited = false;

function _initGraphSettingsPanel() {
  if (_graphSettingsPanelInited) return;
  const wrap = document.getElementById("libraryGraphView");
  if (!wrap) return;
  const panel = document.createElement("div");
  panel.id = "graphSettingsPanel";
  panel.className = "graph-settings-panel";
  panel.innerHTML = `
    <div class="graph-settings-toggle" onclick="this.parentElement.classList.toggle('is-open')" title="그래프 물리 설정">⚙️</div>
    <span class="gs-title">Live 물리 엔진 (Obsidian style)</span>
    <div class="gs-control">
      <label>노드 반발력 <span id="valCharge">-120</span></label>
      <input type="range" id="inputCharge" min="-1000" max="-20" value="-120">
    </div>
    <div class="gs-control">
      <label>연결 거리 <span id="valDistance">70</span></label>
      <input type="range" id="inputDistance" min="20" max="400" value="70">
    </div>
    <div class="gs-control">
      <label>충돌 방지 <span id="valCollide">25</span></label>
      <input type="range" id="inputCollide" min="5" max="150" value="25">
    </div>
    <div style="margin-top:12px; font-size:11px; color:#aaa; line-height:1.4;">
      * 조절 시 실시간으로 군집 형상이 변합니다.<br>
      * 청록색 선(Pulse)은 AI가 발견한 지식입니다.
    </div>
  `;
  wrap.appendChild(panel);
  _graphSettingsPanelInited = true;

  const updateForce = () => {
    if (!_graphSim) return;
    const charge = +document.getElementById("inputCharge").value;
    const dist = +document.getElementById("inputDistance").value;
    const coll = +document.getElementById("inputCollide").value;

    document.getElementById("valCharge").textContent = charge;
    document.getElementById("valDistance").textContent = dist;
    document.getElementById("valCollide").textContent = coll;

    _graphSim.force("charge").strength(charge);
    _graphSim.force("link").distance(l => (l.relation_type === "소속" ? 50 : dist));
    _graphSim.force("collide").radius(d => {
       const nt = _nodeTypeOf(d);
       const baseR = (d._graphR != null ? d._graphR : (nt === "material" ? 12 : 18));
       return baseR + coll / 2;
    });
    _graphSim.alpha(0.3).restart();
  };

  panel.querySelectorAll("input").forEach(inp => inp.addEventListener("input", updateForce));
}
/* === D3 그래프 뷰 === */

const CATEGORY_COLORS = {
  "경제": "#4ecdc4", "정치": "#ff6b6b", "사회": "#ffd93d", "기술": "#6c5ce7",
  "문화": "#fd79a8", "과학": "#00b894", "스포츠": "#e17055", "기타": "#636e72",
  "디지털마케팅": "#0984e3", "디지털 마케팅": "#0984e3", "콘텐츠제작": "#e84393",
  "콘텐츠 제작": "#e84393", "자기계발": "#fdcb6e", "미분류": "#636e72",
  "시사": "#2ed573", "개인": "#f39c12", "교육": "#00cec9", "건강": "#55efc4",
  "핵심 태그": "#ffd700", "주제": "#00bcd4",
};

function getCategoryColor(cat) {
  if (cat === "핵심 태그") return "#ffd700";
  if (cat === "주제") return "#00bcd4";
  return CATEGORY_COLORS[cat] || CATEGORY_COLORS["기타"];
}

/** 출처(브랜드) 허브 노드 색 — 플랫폼(대분류) 기준 */
function getBrandHubColor(platform) {
  const p = (platform || "").trim();
  if (p === "유튜브") return "#ff4444";
  if (p === "뉴스") return "#4488ff";
  if (p === "블로그") return "#44bb44";
  return "#666666";
}

/** 클러스터 그래프: 채널(브랜드)별 고유 색 — _graphBrandColorMap 채움 후 사용 */
const BRAND_COLORS = [
  "#e74c3c",
  "#3498db",
  "#2ecc71",
  "#f39c12",
  "#9b59b6",
  "#1abc9c",
  "#e67e22",
  "#e84393",
  "#00b894",
  "#6c5ce7",
  "#fdcb6e",
  "#74b9ff",
];

let _graphBrandColorMap = {};

function getBrandColor(group) {
  const g = group || "미분류";
  return _graphBrandColorMap[g] || "#888888";
}

function _platformEmoji(platform) {
  const p = (platform || "").trim();
  if (p === "유튜브") return "🎬";
  if (p === "뉴스") return "📰";
  if (p === "블로그") return "📝";
  return "📌";
}

/** #rrggbb → rgba (그래프 자료 노드·소속 엣지용) */
function _hexToRgba(hex, alpha) {
  if (!hex || hex[0] !== "#") return `rgba(102,102,102,${alpha})`;
  const h = hex.slice(1);
  const full = h.length === 3
    ? h.split("").map(c => c + c).join("")
    : h;
  if (full.length !== 6) return `rgba(102,102,102,${alpha})`;
  const r = Number.parseInt(full.slice(0, 2), 16);
  const g = Number.parseInt(full.slice(2, 4), 16);
  const b = Number.parseInt(full.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function _materialGraphFill(d) {
  const g = d.group || d.brand_label || "미분류";
  return _hexToRgba(getBrandColor(g), 0.7);
}

/** 자료 노드 라벨 — 성능 최적화를 위해 고정 길이 설정 (줌에 따른 DOM 텍스트 내용 갱신 방지) */
function _materialGraphLabelText(d) {
  const t = (d.title || "").trim();
  if (!t) return "";
  const maxLen = 30; // 옵시디언 렌더링 방식: 고정 텍스트를 두고 display none 으로 성능 관리
  return t.length > maxLen ? `${t.slice(0, maxLen)}…` : t;
}

/** 링크 색 — relation_type별 페인트 */
function _edgeStrokeForLink(l, nodeList) {
  return _graphRelationEdgePaint(l.relation_type).stroke;
}

/** 모든 엣지 타입별 선 색 */
function _edgeLineStroke(l, nodeList) {
  const rt = l.relation_type;
  return _graphEdgeStrokeForRelation(rt);
}

function _edgeLineWidthAttr(d) {
  return _graphRelationEdgePaint(d.relation_type).width;
}

function _edgeDashAttr(_d) {
  return null;
}

function _edgeOpacityAttr(d) {
  const rt = d.relation_type;
  if (rt === "소속" || rt === "shared_topic" || rt === "shared_entity" || rt === "shared_concept") return 1;
  return _edgeOpacity(rt);
}

/** 엣지 중앙 라벨 글자색 (shared_topic / shared_entity / shared_concept) */
function _edgeTagLabelFill(rt) {
  if (rt === "shared_topic") return "rgba(255, 215, 0, 0.95)";
  if (rt === "shared_entity") return "rgba(255, 143, 163, 0.95)";
  if (rt === "shared_concept") return "rgba(100, 200, 100, 0.95)";
  return "rgba(255, 215, 0, 0.95)";
}

let _graphRaw = null;
let _graphSim = null;

function resetLibraryGraphCache() {
  _graphRaw = null;
  _graphSim = null;
}

let _graphZoomBehavior = null;
let _graphG = null;
let _graphSvgSel = null;
let _graphZoomK = 1;
let _graphSimpleMode = false;
let _graphMiniConstellationMode = false;
let _graphHoveredNodeId = null;
/** 클릭으로 고정된 노드 id — 이웃 라벨 표시 기준 (배경 클릭 시 해제) */
let _graphSelectedNodeId = null;
/** full_cluster: Progressive Disclosure로 펼친 자료 id (null이면 KE 미주입) */
let _graphProgressiveMaterialId = null;
/** 브랜드/자료 클릭 시 이웃 자료 번호 뱃지 앵커 노드 id (해제 시 null) */
let _graphNeighborBadgeAnchorId = null;
/** material id → { num } — 이웃 자료 원형 뱃지 번호 */
let _graphNeighborBadgeByMatId = null;
/** 뱃지/펄스 페이드아웃 후 finalize 타이머 */
let _graphNeighborVizClearTimer = null;
/** full_cluster 주입·동기화용 컨텍스트 (미니/그리드에서는 null) */
let _fullClusterCtx = null;
let _graphTooltipHideTimer = null;
/** 마지막으로 그려진 그래프 필터(통계·패널·검색 이웃용) */
let _lastGraphFiltered = null;

/** 토글 ON 시 엣지 색 (OFF면 해당 <g>는 display:none으로 숨김) */
const EDGE_COLORS = {
  소속: "rgba(100,149,237,0.5)",
  shared_entity: "rgba(255,182,193,0.7)",
  shared_concept: "rgba(144,238,144,0.7)",
  shared_topic: "rgba(255,215,0,0.5)",
};

/** relation_type별 엣지 스타일(풀 클러스터·호버 등) — stroke/width/dash/기본 불투명도 */
const GRAPH_RT_PAINT = {
  의미연결: { stroke: "#8b5cf6", width: 2.5, dash: null, opacity: 0.55 },
  "공통 태그": { stroke: "#3b82f6", width: 1.5, dash: null, opacity: 0.5 },
  공통태그: { stroke: "#3b82f6", width: 1.5, dash: null, opacity: 0.5 },
  모순: { stroke: "#ef4444", width: 3, dash: "6,3", opacity: 0.65 },
  대체: { stroke: "#f97316", width: 2, dash: "4,4", opacity: 0.55 },
  브릿지: { stroke: "#22c55e", width: 2, dash: null, opacity: 0.55 },
  "같은 출처": { stroke: "#6b7280", width: 1, dash: null, opacity: 0.5 },
  "같은 주제": { stroke: "#6366f1", width: 1.5, dash: null, opacity: 0.5 },
  자동연결: { stroke: "#eab308", width: 1.5, dash: null, opacity: 0.5 },
  엔티티연결: { stroke: "#14b8a6", width: 2, dash: null, opacity: 0.5 },
  shared_topic: { stroke: "#3b82f6", width: 1, dash: null, opacity: 0.4 },
  shared_entity: { stroke: "#14b8a6", width: 1.5, dash: null, opacity: 0.5 },
  shared_concept: { stroke: "#8b5cf6", width: 1.5, dash: null, opacity: 0.5 },
};

const GRAPH_RT_PAINT_DEFAULT = { stroke: "#9ca3af", width: 1, dash: null, opacity: 0.5 };

/** graph-panel·사이드 패널: relation_type → 배지(아이콘/색/라벨/설명) */
const GRAPH_PANEL_RT_META = {
  의미연결: { icon: "🧠", color: "#8b5cf6", label: "의미연결", desc: "내용이 비슷한 자료 (임베딩 분석)" },
  "공통 태그": { icon: "🏷️", color: "#3b82f6", label: "공통태그", desc: "같은 핵심태그를 공유하는 자료" },
  공통태그: { icon: "🏷️", color: "#3b82f6", label: "공통태그", desc: "같은 핵심태그를 공유하는 자료" },
  모순: { icon: "⚠️", color: "#ef4444", label: "모순", desc: "서로 반대되는 주장이 있는 자료" },
  대체: { icon: "🔄", color: "#f97316", label: "대체", desc: "이 자료를 업데이트하거나 대신하는 자료" },
  브릿지: { icon: "🌉", color: "#22c55e", label: "브릿지", desc: "서로 다른 주제를 연결하는 자료" },
  "같은 출처": { icon: "📎", color: "#6b7280", label: "같은출처", desc: "같은 채널/출처에서 온 자료" },
  "같은 주제": { icon: "📂", color: "#6366f1", label: "같은주제", desc: "같은 주제로 분류된 자료" },
  자동연결: { icon: "⚡", color: "#eab308", label: "자동연결", desc: "자동 분석으로 발견된 연결" },
  엔티티연결: { icon: "👤", color: "#14b8a6", label: "엔티티연결", desc: "같은 인물/조직이 언급된 자료" },
  shared_topic: { icon: "🏷️", color: "#3b82f6", label: "같은주제", desc: "같은 주제로 분류된 자료" },
  shared_entity: { icon: "👤", color: "#14b8a6", label: "엔티티연결", desc: "같은 인물/조직이 언급된 자료" },
  shared_concept: { icon: "🧠", color: "#8b5cf6", label: "개념연결", desc: "같은 개념이 포함된 자료" },
};

const GRAPH_PANEL_GROUP_ORDER = [
  "의미연결", "공통 태그", "모순", "대체", "브릿지", "같은 출처", "같은 주제", "자동연결", "엔티티연결",
  "shared_concept", "shared_entity", "shared_topic",
];

function _graphRelationTypeAlias(rt) {
  if (rt == null) return "";
  const s = String(rt).trim();
  if (s === "공통태그") return "공통 태그";
  return s;
}

/**
 * @returns {{ stroke: string, width: number, dash: string|null, opacity: number }}
 */
function _graphRelationEdgePaint(rt) {
  if (rt === "소속") {
    return { stroke: EDGE_COLORS.소속, width: 2, dash: null, opacity: 0.7 };
  }
  const t = _graphRelationTypeAlias(rt) || (rt == null ? "" : String(rt).trim());
  const raw = (rt == null) ? "" : String(rt).trim();
  if (t && Object.prototype.hasOwnProperty.call(GRAPH_RT_PAINT, t)) {
    return { ...GRAPH_RT_PAINT_DEFAULT, ...GRAPH_RT_PAINT[t] };
  }
  if (raw && Object.prototype.hasOwnProperty.call(GRAPH_RT_PAINT, raw)) {
    return { ...GRAPH_RT_PAINT_DEFAULT, ...GRAPH_RT_PAINT[raw] };
  }
  return { ...GRAPH_RT_PAINT_DEFAULT };
}

function _graphPanelConnMeta(rt) {
  const t = _graphRelationTypeAlias(rt) || (rt == null ? "" : String(rt).trim());
  const raw = (rt == null) ? "" : String(rt).trim();
  if (t && GRAPH_PANEL_RT_META[t]) return GRAPH_PANEL_RT_META[t];
  if (raw && GRAPH_PANEL_RT_META[raw]) return GRAPH_PANEL_RT_META[raw];
  return {
    icon: "🔗",
    color: "#9ca3af",
    label: (raw || "연결"),
    desc: "교차참조로 연결된 자료",
  };
}

/** graph-panel connections 한 행 li (제목 → 출처 1행 → 설명 1행) */
function _graphConnSingleItemHtml(it) {
  const oid = it.other_id;
  const t = (it.other_title != null) ? String(it.other_title) : "자료";
  const fromApi = it ? (it.other_source ?? it.otherSource) : undefined;
  const br = it ? (it.other_brand ?? it.otherBrand) : undefined;
  const sFromApi = (fromApi != null && String(fromApi).trim()) ? String(fromApi).trim() : "";
  const sFromBrand = (br != null && String(br).trim()) ? String(br).trim() : "";
  const sourceLine = sFromApi || sFromBrand;
  const descRaw = (it.description && String(it.description).trim()) ? String(it.description).trim() : "";
  const bodyParts = [];
  if (sourceLine) {
    bodyParts.push(`<div class="gdp-conn-source-line">${escapeHtml(sourceLine)}</div>`);
  }
  if (descRaw) {
    bodyParts.push(`<div class="gdp-conn-desc">${escapeHtml(descRaw)}</div>`);
  }
  const detailHtml = bodyParts.length
    ? `<div class="gdp-conn-detail">${bodyParts.join("")}</div>`
    : "";
  return `<li class="gdp-conn-item">`
    + `<a class="gdp-conn-title gdp-conn-jump" href="#" data-mid="${oid}" data-id="${oid}">${escapeHtml(t)}</a>`
    + detailHtml
    + `</li>`;
}

function _graphBuildConnectionsPanelSectionHtml(connections) {
  const conns = Array.isArray(connections) ? connections : [];
  if (!conns.length) return "";
  const byKey = new Map();
  for (let i = 0; i < conns.length; i++) {
    const c = conns[i];
    const gk = _graphRelationTypeAlias(c.relation_type) || c.relation_type || "";
    if (!byKey.has(gk)) byKey.set(gk, []);
    byKey.get(gk).push(c);
  }
  const keys = Array.from(byKey.keys()).sort((a, b) => {
    const ia = GRAPH_PANEL_GROUP_ORDER.indexOf(a);
    const ib = GRAPH_PANEL_GROUP_ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return String(a).localeCompare(String(b), "ko");
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
  const blocks = [];
  for (let g = 0; g < keys.length; g++) {
    const key = keys[g];
    const items = byKey.get(key) || [];
    const firstRt = (items[0] && items[0].relation_type) || key;
    const meta = _graphPanelConnMeta(firstRt);
    const head = `${escapeHtml(meta.icon)} ${escapeHtml(meta.label)} (${items.length}건) — <span class="gdp-conn-group-desc">${escapeHtml(meta.desc != null ? meta.desc : "")}</span>`;
    let listBlock = "";
    if (items.length > 5) {
      const vis = items.slice(0, 3);
      const more = items.slice(3);
      const rem = more.length;
      const liVis = vis.map((it) => _graphConnSingleItemHtml(it)).join("");
      const liMore = more.map((it) => _graphConnSingleItemHtml(it)).join("");
      const btn = `<button type="button" class="gdp-conn-more-btn" data-rem="${rem}" onclick="var b=this;var m=b.previousElementSibling;if(!m)return;var isHidden=m.style.display==='none';m.style.display=isHidden?'':'none';var r=b.getAttribute('data-rem')||'0';b.textContent=isHidden?'접기':('▼ 나머지 '+r+'건 더 보기');">▼ 나머지 ${rem}건 더 보기</button>`;
      listBlock = `<ul class="gdp-conn-list">${liVis}</ul>`
        + `<div class="gdp-conn-more" style="display:none"><ul class="gdp-conn-list gdp-conn-list--more">${liMore}</ul></div>${btn}`;
    } else {
      listBlock = `<ul class="gdp-conn-list">${items.map((it) => _graphConnSingleItemHtml(it)).join("")}</ul>`;
    }
    blocks.push(
      `<div class="gdp-conn-group" style="--gdp-conn-accent:${meta.color}">`
      + `<button type="button" class="gdp-conn-group-head" aria-expanded="true">`
      + `<span class="gdp-conn-group-title">`
      + head
      + `</span><span class="gdp-conn-group-chev" aria-hidden="true">▼</span></button>`
      + `<div class="gdp-conn-group-body">`
      + listBlock
      + `</div></div>`,
    );
  }
  return (
    `<section class="gdp-card gdp-card--open" data-gdp-section="conn-reasons">`
    + `<button type="button" class="gdp-card-head" aria-expanded="true">`
    + `<span class="gdp-card-title">🔗 연결 관계</span><span class="gdp-card-icon" aria-hidden="true">▼</span></button>`
    + `<div class="gdp-card-panel"><div class="gdp-card-inner gdp-conn-reasons-inner">${blocks.join("")}</div></div></section>`
  );
}

let _graphEdgeToggleBelongs = true;
let _graphEdgeToggleThumb = true;
let _graphEdgeToggleKeyword = true;
let _graphEdgeToggleBarBound = false;

function _graphEdgeToggleAny() {
  return _graphEdgeToggleBelongs || _graphEdgeToggleThumb || _graphEdgeToggleKeyword;
}

function _graphEdgeToggleControlsType(rt) {
  return rt === "소속" || rt === "shared_entity" || rt === "shared_concept" || rt === "shared_topic";
}

function _graphEdgeTypeActiveByToggle(rt) {
  if (rt === "소속") return _graphEdgeToggleBelongs;
  if (rt === "shared_entity") return _graphEdgeToggleThumb;
  if (rt === "shared_concept" || rt === "shared_topic") return _graphEdgeToggleKeyword;
  return false;
}

function _graphEdgeIncidentTo(lnk, nodeId) {
  if (nodeId == null) return false;
  const [sid, tid] = _graphLinkSidTid(lnk);
  return sid === nodeId || tid === nodeId;
}

/** 포커스가 소속(브랜드 허브)일 때: 소속 엣지 색은 유지하고 굵기·불투명도만 공유선 incident와 동일(선명도 맞춤) */
function _graphBaselineFocusIsBrand(selId) {
  if (selId == null || !_fullClusterCtx || !_fullClusterCtx.fdNodes) return false;
  const n = _fullClusterCtx.fdNodes.find((x) => x.id === selId);
  return !!(n && _nodeTypeOf(n) === "brand");
}

/** 호버·뱃지가 아닐 때: 엣지 <g> 표시 여부 (토글 전부 OFF + 노드 미선택이면 전부 숨김) */
/** @param {number|null|undefined} [effectiveSel] 베이스라인 갱신 시 포커스(예: 호버 id). 생략 시 클릭 선택 id */
function _graphEdgeVisibleBaseline(lnk, effectiveSel) {
  const anyOn = _graphEdgeToggleAny();
  const sel = effectiveSel !== undefined ? effectiveSel : _graphSelectedNodeId;
  const rt = lnk.relation_type;
  const incidentSel = _graphEdgeIncidentTo(lnk, sel);
  if (!anyOn) {
    if (sel == null) return false;
    return incidentSel;
  }
  if (!_graphEdgeToggleControlsType(rt)) return false;
  if (!_graphEdgeTypeActiveByToggle(rt)) return false;
  if (sel != null && !incidentSel) return false;
  return true;
}

function _graphEdgeStrokeColorForVisiblePaint(rt) {
  return _graphRelationEdgePaint(rt).stroke;
}

/** 토글 ON + 노드 선택 시: 선택 노드·ON 타입 교차 엣지만 강조(opacity) */
function _graphEdgeStrongHighlight(lnk) {
  if (!_graphEdgeToggleAny()) return false;
  const sel = _graphSelectedNodeId;
  if (sel == null) return false;
  const rt = lnk.relation_type;
  return _graphEdgeIncidentTo(lnk, sel) && _graphEdgeToggleControlsType(rt) && _graphEdgeTypeActiveByToggle(rt);
}

function _graphEdgeStrokeForRelation(rt) {
  return _graphRelationEdgePaint(rt).stroke;
}

/** 호버 시 강조된 엣지 색 (선택·뱃지 외 풀클러스터 엣지 호버 페인트) */
function _graphEdgeStrokeHoverHit(rt) {
  return _graphRelationEdgePaint(rt).stroke;
}

/** @param {number|null|undefined} [selOverride] 클릭 없이 호버만 있을 때 포커스 노드 id (클릭 선택과 동일한 엣지 강조) */
function _graphSyncFullClusterEdgesBaselineCore(selOverride) {
  if (!_fullClusterCtx || !_fullClusterCtx.linkG) return;
  const shownLabels = new Set();
  const sel = selOverride !== undefined ? selOverride : _graphSelectedNodeId;
  _fullClusterCtx.linkG.selectAll("g.graph-edge").each(function (lnk) {
    const gg = d3.select(this);
    const line = gg.select("line.graph-edge-line");
    if (line.empty()) return;
    const rt = lnk.relation_type;
    const vis = _graphEdgeVisibleBaseline(lnk, sel);
    if (!vis) {
      gg.style("display", null);
      line.attr("stroke", "rgba(255,255,255,0.08)")
        .attr("stroke-width", 0.5)
        .attr("stroke-opacity", 1)
        .attr("stroke-dasharray", null);
      const midHidden = gg.select("text.graph-edge-tag-label");
      if (!midHidden.empty()) midHidden.attr("opacity", 0);
      return;
    }
    if (sel === null) {
      gg.style("display", null);
      if (rt === "소속") {
        line.attr("stroke", "rgba(180,200,220,0.12)")
          .attr("stroke-width", 0.4)
          .attr("stroke-opacity", 1)
          .attr("stroke-dasharray", null);
      } else {
        const p = _graphRelationEdgePaint(rt);
        const w0 = Math.max(0.45, p.width * 0.55);
        line.attr("stroke", p.stroke)
          .attr("stroke-width", w0)
          .attr("stroke-opacity", p.opacity)
          .attr("stroke-dasharray", p.dash || null);
      }
      const midUnsel = gg.select("text.graph-edge-tag-label");
      if (!midUnsel.empty()) midUnsel.attr("opacity", 0);
      return;
    }
    gg.style("display", null);
    const incidentSel = _graphEdgeIncidentTo(lnk, sel);
    if (incidentSel) {
      if (rt === "소속") {
        /* 색은 소속 규칙 유지 · 굵기·불투명도만 공유(incident)와 동일: width 2, opacity 0.7 */
        const belStroke = _graphBaselineFocusIsBrand(sel) ? EDGE_COLORS.소속 : "rgba(180,200,220,0.5)";
        line.attr("stroke", belStroke)
          .attr("stroke-width", 2)
          .attr("stroke-opacity", 0.7)
          .attr("stroke-dasharray", null);
      } else {
        const p = _graphRelationEdgePaint(rt);
        line.attr("stroke", p.stroke)
          .attr("stroke-width", p.width)
          .attr("stroke-opacity", 0.85)
          .attr("stroke-dasharray", p.dash || null);
      }
    } else if (rt === "소속") {
      line.attr("stroke", "rgba(180,200,220,0.08)")
        .attr("stroke-width", 0.22)
        .attr("stroke-opacity", 1)
        .attr("stroke-dasharray", null);
    } else {
      const p = _graphRelationEdgePaint(rt);
      const wFaint = Math.max(0.2, p.width * 0.2);
      line.attr("stroke", p.stroke)
        .attr("stroke-width", wFaint)
        .attr("stroke-opacity", 0.1)
        .attr("stroke-dasharray", p.dash || null);
    }
    const mid = gg.select("text.graph-edge-tag-label");
    if (!mid.empty()) {
      const shouldShow = _graphEdgeTagVisible(lnk);
      const labelText = lnk.edge_label || "";
      if (shouldShow && !shownLabels.has(labelText)) {
        shownLabels.add(labelText);
        mid.attr("opacity", 1);
      } else {
        mid.attr("opacity", 0);
      }
    }
  });
}

function _graphRepaintMainEdgesBaselines() {
  if (!_fullClusterCtx || !_fullClusterCtx.linkG) return;
  if (_graphNeighborBadgeAnchorId) return;
  _graphSyncFullClusterEdgesBaselineCore();
}

function _graphApplySelectionToggleEdgeDim() {
  if (!_fullClusterCtx || !_fullClusterCtx.linkG) return;
  if (_graphNeighborBadgeAnchorId) return;
  _graphRepaintMainEdgesBaselines();
}

function _graphEdgeToggleCountsFromEdges(edgeList) {
  const edges = edgeList || [];
  let nBel = 0;
  let nEnt = 0;
  let nKey = 0;
  for (let i = 0; i < edges.length; i++) {
    const rt = edges[i].relation_type;
    if (rt === "소속") nBel += 1;
    else if (rt === "shared_entity") nEnt += 1;
    else if (rt === "shared_concept" || rt === "shared_topic") nKey += 1;
  }
  return { nBel, nEnt, nKey };
}

function _graphEnsureEdgeToggleBar() {
  const inner = document.querySelector("#graphLegendPanel .graph-legend-inner");
  if (!inner) return null;
  let bar = document.getElementById("graphEdgeToggleWrap");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "graphEdgeToggleWrap";
    bar.className = "graph-edge-toggle-bar";
    inner.insertBefore(bar, inner.firstChild);
  }
  if (!bar.querySelector("button.graph-edge-toggle")) {
    bar.innerHTML = `
<button type="button" class="graph-edge-toggle is-on" data-toggle="belongs" aria-pressed="true"><span class="ge-preview ge-preview-belongs" aria-hidden="true"></span><span class="ge-label">소속 <span class="ge-count">0</span></span></button>
<button type="button" class="graph-edge-toggle is-on" data-toggle="thumb" aria-pressed="true"><span class="ge-preview ge-preview-thumb" aria-hidden="true"></span><span class="ge-label">핵심 태그 <span class="ge-count">0</span></span></button>
<button type="button" class="graph-edge-toggle is-on" data-toggle="keyword" aria-pressed="true"><span class="ge-preview ge-preview-keyword" aria-hidden="true"></span><span class="ge-label">주제 <span class="ge-count">0</span></span></button>`;
  }
  bar.querySelectorAll("button.graph-edge-toggle").forEach((b) => {
    const bk = b.getAttribute("data-toggle");
    const on =
      (bk === "belongs" && _graphEdgeToggleBelongs) ||
      (bk === "thumb" && _graphEdgeToggleThumb) ||
      (bk === "keyword" && _graphEdgeToggleKeyword);
    b.classList.toggle("is-on", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (!_graphEdgeToggleBarBound) {
    _graphEdgeToggleBarBound = true;
    bar.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button.graph-edge-toggle");
      if (!btn || !bar.contains(btn)) return;
      const k = btn.getAttribute("data-toggle");
      if (k === "belongs") _graphEdgeToggleBelongs = !_graphEdgeToggleBelongs;
      else if (k === "thumb") _graphEdgeToggleThumb = !_graphEdgeToggleThumb;
      else if (k === "keyword") _graphEdgeToggleKeyword = !_graphEdgeToggleKeyword;
      bar.querySelectorAll("button.graph-edge-toggle").forEach((b) => {
        const bk = b.getAttribute("data-toggle");
        const on =
          (bk === "belongs" && _graphEdgeToggleBelongs) ||
          (bk === "thumb" && _graphEdgeToggleThumb) ||
          (bk === "keyword" && _graphEdgeToggleKeyword);
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      _graphRepaintMainEdgesBaselines();
      _graphApplyNeighborBadgeEdges();
      _graphApplySelectionToggleEdgeDim();
    });
  }
  return bar;
}

function _graphUpdateEdgeToggleLabels(edgeList) {
  const bar = _graphEnsureEdgeToggleBar();
  if (!bar) return;
  const { nBel, nEnt, nKey } = _graphEdgeToggleCountsFromEdges(edgeList);
  const b0 = bar.querySelector('[data-toggle="belongs"]');
  const b1 = bar.querySelector('[data-toggle="thumb"]');
  const b2 = bar.querySelector('[data-toggle="keyword"]');
  if (b0) b0.querySelector(".ge-count").textContent = String(nBel);
  if (b1) b1.querySelector(".ge-count").textContent = String(nEnt);
  if (b2) b2.querySelector(".ge-count").textContent = String(nKey);
}

const gf = {
  categories: null,
  impMin: 1,
  edgeTypes: new Set(["관련", "인과관계", "모순", "소속", "shared_topic", "shared_entity", "shared_concept"]),
  nodeTypes: new Set(["material", "brand", "entity", "concept"]),
  search: "",
  hideOrphans: false,
  sidebarCollapsed: false,
  _toolbarDelegation: false,
  _graphControlsBound: false,
  _orphanToggleBound: false,
  _sidebarToggleBound: false,
  _graphDetailBound: false,
};

function _isNewNode(d) {
  if (!d.ingested_date) return false;
  const diff = (Date.now() - new Date(d.ingested_date).getTime()) / 86400000;
  return diff <= 7;
}

/** mini_constellation: importance 3단계 fill */
function _miniImportanceFill(d) {
  const imp = d.importance != null ? Number(d.importance) : 3;
  if (imp >= 4) return "#4FC3F7";
  if (imp === 3) return "#81C784";
  return "#B0BEC5";
}

function _miniEdgeCountMaterial(mid, edgeList) {
  let c = 0;
  edgeList.forEach((e) => {
    if (e.relation_type !== "소속" && e.relation_type !== "shared_topic") return;
    if (e.source_id === mid || e.target_id === mid) c += 1;
  });
  return c;
}

function _miniSharedTopicCountMaterial(mid, edgeList) {
  let c = 0;
  edgeList.forEach((e) => {
    if (e.relation_type !== "shared_topic") return;
    if (e.source_id === mid || e.target_id === mid) c += 1;
  });
  return c;
}

function _miniMaterialNodeRadius(d, edgeList) {
  const ec = _miniEdgeCountMaterial(d.id, edgeList);
  return Math.max(3, 2 + Math.sqrt(ec) * 2);
}

function _miniBrandNodeRadius(brandId, edgeList) {
  let ec = 0;
  (edgeList || []).forEach((e) => {
    if (e.relation_type !== "소속" && e.relation_type !== "shared_topic") return;
    if (e.source_id === brandId || e.target_id === brandId) ec += 1;
  });
  return Math.max(8, 4 + Math.sqrt(ec) * 3) * 1.3;
}

/** 필터된 노드 집합과 엣지 양끜이 모두 포함될 때 연결 수 */
function _computeLinkCountMap(nodes, edges) {
  const ids = new Set(nodes.map((n) => n.id));
  const m = new Map();
  nodes.forEach((n) => m.set(n.id, 0));
  (edges || []).forEach((e) => {
    if (!ids.has(e.source_id) || !ids.has(e.target_id)) return;
    m.set(e.source_id, (m.get(e.source_id) || 0) + 1);
    m.set(e.target_id, (m.get(e.target_id) || 0) + 1);
  });
  return m;
}

/** 선택 노드 기준 이웃 id — API 원본 엣지 사용(KE·언급·관련주제 포함), 필터는 엣지 타입만 */
function _graphNeighborsOf(nodeId) {
  const edges = (_graphRaw && _graphRaw.edges) || (_lastGraphFiltered && _lastGraphFiltered.edges) || [];
  const s = new Set([nodeId]);
  for (let i = 0; i < edges.length; i++) {
    const e = edges[i];
    const rt = e.relation_type;
    if (!gf.edgeTypes.has(rt) && rt !== "언급" && rt !== "관련주제") continue;
    if (e.source_id === nodeId) s.add(e.target_id);
    else if (e.target_id === nodeId) s.add(e.source_id);
  }
  return s;
}

function _graphMaterialTextVisible(id) {
  return false;
}

/** KE gl-text: 호버 우선, 비호버 시 선택+이웃 */
function _graphKeConceptTextVisible(id) {
  const S = _graphSelectedNodeId;
  const H = _graphHoveredNodeId;
  if (H != null) return id === H;
  if (S != null) return _graphNeighborsOf(S).has(id);
  return false;
}

/** 미니 뷰 자료 라벨 — _graphMaterialLabelVisible 호환 */
function _graphMaterialLabelVisible(id) {
  return _graphMaterialTextVisible(id);
}

/** 필터된 그래프에서 앵커와 엣지로 직접 연결된 이웃 자료만, 최신 ingested_date 순 */
function _graphNeighborMaterialNodes(anchorId) {
  const fd = _lastGraphFiltered;
  if (!fd || !fd.edges || !fd.nodes) return [];
  const nodeById = new Map(fd.nodes.map((n) => [n.id, n]));
  const ids = new Set(fd.nodes.map((n) => n.id));
  const outIds = new Set();
  for (let i = 0; i < fd.edges.length; i++) {
    const e = fd.edges[i];
    if (!gf.edgeTypes.has(e.relation_type)) continue;
    if (e.source_id === anchorId && ids.has(e.target_id) && e.target_id !== anchorId) {
      outIds.add(e.target_id);
    }
    if (e.target_id === anchorId && ids.has(e.source_id) && e.source_id !== anchorId) {
      outIds.add(e.source_id);
    }
  }
  const out = [];
  outIds.forEach((mid) => {
    const n = nodeById.get(mid);
    if (n && _nodeTypeOf(n) === "material") out.push(n);
  });
  out.sort((a, b) => {
    const da = a.ingested_date ? new Date(a.ingested_date).getTime() : 0;
    const db = b.ingested_date ? new Date(b.ingested_date).getTime() : 0;
    return db - da;
  });
  return out;
}

function _graphNeighborListTitle20(t) {
  const s = (t || "").trim();
  if (s.length <= 20) return s;
  return `${s.slice(0, 20)}…`;
}

function _graphNeighborListDateLine(d) {
  if (!d || !d.ingested_date) return "—";
  const t = String(d.ingested_date).trim();
  const m = t.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : t.slice(0, 10);
}

function _graphCircledNumberStr(n) {
  if (n >= 1 && n <= 20) return String.fromCharCode(0x2460 + n - 1);
  return `(${n})`;
}

function _finalizeGraphNeighborVizClear() {
  if (_graphNeighborVizClearTimer) {
    clearTimeout(_graphNeighborVizClearTimer);
    _graphNeighborVizClearTimer = null;
  }
  _graphNeighborBadgeAnchorId = null;
  _graphNeighborBadgeByMatId = null;
  if (_graphG) {
    _graphG.selectAll("g.gn").each(function () {
      d3.select(this).select("circle.gn-shape").style("display", null);
    });
    _graphG.selectAll("g.graph-neighbor-badge").remove();
    _graphG.selectAll("g.graph-anchor-pulse").remove();
  }
  _graphApplyNeighborBadgeEdges();
  _graphApplyNeighborBadgeEdgesMini();
}

function _clearGraphNeighborBadgeState() {
  if (_graphNeighborVizClearTimer) {
    clearTimeout(_graphNeighborVizClearTimer);
    _graphNeighborVizClearTimer = null;
  }
  if (!_graphG || !_graphNeighborBadgeAnchorId) {
    _finalizeGraphNeighborVizClear();
    return;
  }
  _graphG.selectAll("g.graph-neighbor-badge, g.graph-anchor-pulse").classed("graph-viz-fade-out", true);
  _graphNeighborVizClearTimer = setTimeout(() => {
    _graphNeighborVizClearTimer = null;
    _finalizeGraphNeighborVizClear();
  }, 200);
}

function _graphLinkSidTid(lnk) {
  const sid = typeof lnk.source === "object" && lnk.source != null ? lnk.source.id : lnk.source;
  const tid = typeof lnk.target === "object" && lnk.target != null ? lnk.target.id : lnk.target;
  return [sid, tid];
}

/** 뱃지 모드 엣지 강조(풀 클러스터). 다른 노드 호버 미리보기 중만 스킵 — 앵커와 같은 노드에 올린 채 클릭해도 파란 뱃지 선이 그려지게 */
function _graphApplyNeighborBadgeEdges() {
  if (!_graphG || !_fullClusterCtx) return;
  if (_graphNeighborBadgeAnchorId != null && _graphHoveredNodeId != null && _graphHoveredNodeId !== _graphNeighborBadgeAnchorId) return;
  const linkWrap = _fullClusterCtx.linkG.selectAll("g.graph-edge");
  if (_graphNeighborBadgeAnchorId != null && _graphNeighborBadgeByMatId && _graphNeighborBadgeByMatId.size) {
    linkWrap.each(function (lnk) {
      const gg = d3.select(this);
      const line = gg.select("line.graph-edge-line");
      if (line.empty()) return;
      const rt = lnk.relation_type;
      const [sid, tid] = _graphLinkSidTid(lnk);
      const A = _graphNeighborBadgeAnchorId;
      let badgeNum = null;
      if (sid === A && _graphNeighborBadgeByMatId.has(tid)) badgeNum = _graphNeighborBadgeByMatId.get(tid).num;
      else if (tid === A && _graphNeighborBadgeByMatId.has(sid)) badgeNum = _graphNeighborBadgeByMatId.get(sid).num;
      if (badgeNum != null) {
        gg.style("display", null);
        const op = Math.max(0.15, 0.6 - (badgeNum - 1) * 0.05);
        if (rt === "소속") {
          line.attr("stroke", EDGE_COLORS.소속)
            .attr("stroke-width", 2)
            .attr("stroke-opacity", op)
            .attr("stroke-dasharray", null);
        } else {
          const p = _graphRelationEdgePaint(rt);
          line.attr("stroke", p.stroke)
            .attr("stroke-width", p.width)
            .attr("stroke-opacity", op)
            .attr("stroke-dasharray", p.dash || null);
        }
        return;
      }
      gg.style("display", "none");
    });
    return;
  }
  if (_graphHoveredNodeId) return;
  _graphSyncFullClusterEdgesBaselineCore();
}

function _graphApplyNeighborBadgeEdgesMini() {
  if (!_graphG || !_graphMiniConstellationMode) return;
  if (_graphNeighborBadgeAnchorId != null && _graphHoveredNodeId != null && _graphHoveredNodeId !== _graphNeighborBadgeAnchorId) return;
  const linkWrap = _graphG.selectAll("g.graph-edge-mini");
  linkWrap.each(function (lnk) {
    const path = d3.select(this).select("path.graph-mini-link");
    if (path.empty()) return;
    const [sid, tid] = _graphLinkSidTid(lnk);
    if (_graphNeighborBadgeAnchorId != null && _graphNeighborBadgeByMatId && _graphNeighborBadgeByMatId.size) {
      const A = _graphNeighborBadgeAnchorId;
      let badgeNum = null;
      if (sid === A && _graphNeighborBadgeByMatId.has(tid)) badgeNum = _graphNeighborBadgeByMatId.get(tid).num;
      else if (tid === A && _graphNeighborBadgeByMatId.has(sid)) badgeNum = _graphNeighborBadgeByMatId.get(sid).num;
      if (badgeNum != null) {
        path.attr("stroke-opacity", Math.max(0.15, 0.6 - (badgeNum - 1) * 0.05));
        return;
      }
      path.attr("stroke-opacity", 0.05);
      return;
    }
    const isBel = lnk.relation_type === "소속";
    path.attr("stroke-opacity", isBel ? 0.12 : 0.2);
  });
}

function _applyGraphNeighborBadgeState(anchorId, orderedMaterials) {
  if (_graphNeighborVizClearTimer) {
    clearTimeout(_graphNeighborVizClearTimer);
    _graphNeighborVizClearTimer = null;
  }
  _graphNeighborBadgeAnchorId = anchorId;
  const m = new Map();
  orderedMaterials.forEach((mat, i) => {
    m.set(mat.id, { num: i + 1 });
  });
  _graphNeighborBadgeByMatId = m;
  _syncGraphNeighborViz();
}

function _syncGraphNeighborViz() {
  _syncGraphNeighborBadges();
  _syncGraphAnchorPulse();
  _graphApplyNeighborBadgeEdges();
  _graphApplyNeighborBadgeEdgesMini();
  _graphApplySelectionToggleEdgeDim();
  if (_fullClusterCtx && !_graphSimpleMode && !_graphMiniConstellationMode) {
    _graphSyncMainNodeSelectionOutline();
  }
}

function _syncGraphAnchorPulse() {
  if (!_graphG) return;
  _graphG.selectAll("g.gn").each(function () {
    d3.select(this).selectAll("g.graph-anchor-pulse").remove();
  });
}

function _syncGraphNeighborBadges() {
  if (!_graphG) return;
  _graphG.selectAll("g.gn").each(function (d) {
    const gg = d3.select(this);
    gg.selectAll("g.graph-neighbor-badge").remove();

    if (!_graphNeighborBadgeByMatId || !_graphNeighborBadgeByMatId.has(d.id)) {
      gg.select("circle.gn-shape").style("display", null);
      return;
    }
    const info = _graphNeighborBadgeByMatId.get(d.id);
    if (_nodeTypeOf(d) !== "material") {
      gg.select("circle.gn-shape").style("display", null);
      return;
    }

    gg.select("circle.gn-shape").style("display", "none");

    const bx = 0;
    const by = 0;

    const bg = gg.append("g")
      .attr("class", "graph-neighbor-badge graph-viz-enter")
      .attr("transform", `translate(${bx},${by})`);

    bg.append("circle")
      .attr("r", 7)
      .attr("fill", "rgba(90,90,100,0.9)")
      .attr("stroke", "rgba(255,255,255,0.25)")
      .attr("stroke-width", 0.65);

    bg.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("fill", "rgba(220,220,230,0.95)")
      .attr("font-size", 8)
      .attr("font-weight", "600")
      .style("pointer-events", "none")
      .text(String(info.num));
  });
}

function _bindGraphNeighborAnchorListItems(body) {
  if (!body) return;
  body.querySelectorAll(".gdp-neighbor-item[data-mid]").forEach((row) => {
    const go = () => {
      const mid = Number.parseInt(row.dataset.mid, 10);
      if (mid) openGraphDetailPanelMaterial(mid);
    };
    row.addEventListener("click", go);
    row.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        go();
      }
    });
  });
}

async function openGraphDetailPanelNeighborAnchor(d) {
  const nt = _nodeTypeOf(d);
  const anchorId = d.id;
  const materials = _graphNeighborMaterialNodes(anchorId);
  const body = document.getElementById("graphDetailBody");
  if (nt === "brand") {
    const header =
      (d.brand_label || d.group || d.title || "")
        .replace(/\s*\(\d+건\)\s*$/, "")
        .trim() || "출처";
    setGraphDetailOpen(true);
    if (!body) return;
    let html = `<h2 class="gdp-panel-title">${escapeHtml(header)}</h2>`;
    html += `<ul class="gdp-neighbor-list">`;
    if (!materials.length) {
      html += `<li class="gdp-neighbor-empty">연결된 이웃 자료가 없습니다.</li>`;
    } else {
      materials.forEach((m, idx) => {
        const n = idx + 1;
        const circ = _graphCircledNumberStr(n);
        const title = _graphNeighborListTitle20(m.title);
        const dateStr = _graphNeighborListDateLine(m);
        const dotCol = getBrandColor(m.group || m.brand_label || "미분류");
        html += `<li class="gdp-neighbor-item" data-mid="${m.id}" role="button" tabindex="0">`
          + `<span class="gdp-neighbor-dot" style="background:${dotCol}"></span>`
          + `<span class="gdp-neighbor-line">${circ} ${escapeHtml(title)} (${escapeHtml(dateStr)})</span>`
          + `</li>`;
      });
    }
    html += `</ul>`;
    body.innerHTML = html;
    _bindGraphNeighborAnchorListItems(body);
    return;
  }

  setGraphDetailOpen(true);
  if (!body) return;
  body.innerHTML = "<h2 class=\"gdp-panel-title\">자료</h2>"
    + "<p class=\"gdp-meta\">불러오는 중…</p>";
  try {
    const brandLabel = d.brand_label || d.group || "";
    const detailHtml = await _buildGraphDetailMaterialPanelHtml(anchorId, brandLabel);
    let neighborHtml = `<hr class="gdp-rule"><div class="gdp-subhead">📍 그래프 이웃 (간접 연결)</div>`
      + `<ul class="gdp-neighbor-list">`;
    if (!materials.length) {
      neighborHtml += `<li class="gdp-neighbor-empty">연결된 이웃 자료가 없습니다.</li>`;
    } else {
      materials.forEach((m, idx) => {
        const n = idx + 1;
        const circ = _graphCircledNumberStr(n);
        const title = _graphNeighborListTitle20(m.title);
        const dateStr = _graphNeighborListDateLine(m);
        const dotCol = getBrandColor(m.group || m.brand_label || "미분류");
        neighborHtml += `<li class="gdp-neighbor-item" data-mid="${m.id}" role="button" tabindex="0">`
          + `<span class="gdp-neighbor-dot" style="background:${dotCol}"></span>`
          + `<span class="gdp-neighbor-line">${circ} ${escapeHtml(title)} (${escapeHtml(dateStr)})</span>`
          + `</li>`;
      });
    }
    neighborHtml += `</ul>`;
    body.innerHTML = detailHtml + neighborHtml;
    _gdpInitGraphDetailPanelCards(body);
    _bindGraphNeighborAnchorListItems(body);
  } catch (e) {
    body.innerHTML = "<h2 class=\"gdp-panel-title\">자료</h2>"
      + `<p class="gdp-meta">로드 실패: ${escapeHtml(e.message || String(e))}</p>`;
  }
}

/** 엣지 중앙 태그 라벨: 포커스 노드(마우스 호버 우선 → 클릭 선택)에 닿은 엣지만 — 호버=클릭과 동일 */
function _graphEdgeTagVisible(lnk) {
  const S = _graphHoveredNodeId != null ? _graphHoveredNodeId : _graphSelectedNodeId;
  if (S == null) return false;
  const sid = typeof lnk.source === "object" && lnk.source != null ? lnk.source.id : lnk.source;
  const tid = typeof lnk.target === "object" && lnk.target != null ? lnk.target.id : lnk.target;
  return sid === S || tid === S;
}

/** API 원본에서 자료 1건에 직접 연결된 entity/concept 노드·엣지 (언급/관련주제) */
function _graphKeNodesAndEdgesForMaterial(materialId, raw) {
  if (!raw || !raw.nodes || !raw.edges) return { nodes: [], edges: [] };
  const nodeById = new Map(raw.nodes.map((n) => [n.id, n]));
  const keNodeIds = new Set();
  const outEdges = [];
  for (let i = 0; i < raw.edges.length; i++) {
    const e = raw.edges[i];
    if (e.relation_type !== "언급" && e.relation_type !== "관련주제") continue;
    let other = null;
    if (e.source_id === materialId) other = e.target_id;
    else if (e.target_id === materialId) other = e.source_id;
    else continue;
    const on = nodeById.get(other);
    if (!on) continue;
    const nt = _nodeTypeOf(on);
    if (nt !== "entity" && nt !== "concept") continue;
    keNodeIds.add(other);
    outEdges.push(e);
  }
  const keNodes = raw.nodes
    .filter((n) => keNodeIds.has(n.id))
    .map((n) => Object.assign({}, n));
  return { nodes: keNodes, edges: outEdges };
}

/**
 * 레이아웃에 올린 노드 집합 기준 연결 수 — fd 전체 엣지 사용(KE 미표시 시에도 자료 반지름 유지)
 */
function _linkCountMapForLayoutNodes(layoutNodes, fdNodes, fdEdges) {
  const idsLayout = new Set(layoutNodes.map((n) => n.id));
  const idsFull = new Set((fdNodes || []).map((n) => n.id));
  const m = new Map();
  layoutNodes.forEach((n) => m.set(n.id, 0));
  (fdEdges || []).forEach((e) => {
    if (!gf.edgeTypes.has(e.relation_type)) return;
    if (!idsFull.has(e.source_id) || !idsFull.has(e.target_id)) return;
    if (idsLayout.has(e.source_id)) m.set(e.source_id, (m.get(e.source_id) || 0) + 1);
    if (idsLayout.has(e.target_id)) m.set(e.target_id, (m.get(e.target_id) || 0) + 1);
  });
  return m;
}

/** 7일/30일 신선도 테두리 (mini) */
function _miniIngestedStrokeAttrs(d) {
  if (!d.ingested_date) return null;
  const days = (Date.now() - new Date(d.ingested_date).getTime()) / 86400000;
  if (days <= 7) return { stroke: "#FFD54F", width: 2 };
  if (days <= 30) return { stroke: "#FFD54F", width: 1 };
  return null;
}

function _miniBelongsPath(l) {
  const s = l.source;
  const t = l.target;
  if (typeof s !== "object" || typeof t !== "object") return "";
  const sx = s.x;
  const sy = s.y;
  const tx = t.x;
  const ty = t.y;
  const mx = (sx + tx) / 2;
  const my = (sy + ty) / 2;
  const dx = tx - sx;
  const dy = ty - sy;
  const len = Math.hypot(dx, dy) || 1e-6;
  const px = (-dy / len) * 24;
  const py = (dx / len) * 24;
  return `M${sx},${sy} Q${mx + px},${my + py} ${tx},${ty}`;
}

function _miniSharedPath(l) {
  const s = l.source;
  const t = l.target;
  if (typeof s !== "object" || typeof t !== "object") return "";
  return `M${s.x},${s.y} L${t.x},${t.y}`;
}

/** full_cluster: 클러스터 간 shared_topic 곡선 */
function _fullClusterSharedArcPath(l) {
  const s = l.source;
  const t = l.target;
  if (typeof s !== "object" || typeof t !== "object") return "";
  const sx = s.x;
  const sy = s.y;
  const tx = t.x;
  const ty = t.y;
  const mx = (sx + tx) / 2;
  const my = (sy + ty) / 2;
  const dx = tx - sx;
  const dy = ty - sy;
  const len = Math.hypot(dx, dy) || 1e-6;
  const off = Math.min(80, len * 0.35);
  const cx = mx - (dy / len) * off;
  const cy = my + (dx / len) * off;
  return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`;
}

/** shared_topic 곡선 상의 한 점(라벨 위치) */
function _sharedArcLabelMid(d) {
  const s = d.source;
  const t = d.target;
  if (typeof s !== "object" || typeof t !== "object") return [0, 0];
  const sx = s.x;
  const sy = s.y;
  const tx = t.x;
  const ty = t.y;
  const mx = (sx + tx) / 2;
  const my = (sy + ty) / 2;
  const dx = tx - sx;
  const dy = ty - sy;
  const len = Math.hypot(dx, dy) || 1e-6;
  const off = Math.min(80, len * 0.35);
  const cx = mx - (dy / len) * off;
  const cy = my + (dx / len) * off;
  const u = 0.5;
  const lx = (1 - u) * (1 - u) * sx + 2 * (1 - u) * u * cx + u * u * tx;
  const ly = (1 - u) * (1 - u) * sy + 2 * (1 - u) * u * cy + u * u * ty;
  return [lx, ly];
}

function _nodeTypeOf(n) {
  return n.node_type || "material";
}

/** 엔티티/개념 그래프 노드: grade 없으면 A(기존 동작). */
function _graphKeGrade(d) {
  if (!d || d.grade === "B") return "B";
  return "A";
}

function _nodeRadius(d) {
  const nt = _nodeTypeOf(d);
  if (nt === "material") {
    const base = 7;
    const imp = d.importance || 1;
    const mc = d.mention_count || 1;
    // 중요도 5성은 아주 크게, 1성은 작게 (7 ~ 22px 사이)
    return base + (imp * 2.2) + Math.min(mc * 0.5, 6);
  }
  if (nt === "brand") return 15;
  if (nt === "entity") return 12;
  if (nt === "concept") return 10;
  return 8;
}

function _edgeColor(rt) {
  if (rt === "모순") return "#e94560";
  if (rt === "인과관계") return "#4ecdc4";
  if (rt === "소속") return "rgba(180, 180, 210, 0.65)";
  if (rt === "언급") return "rgba(255, 215, 0, 0.55)";
  if (rt === "관련주제") return "rgba(0, 188, 212, 0.55)";
  return "#555";
}

function _edgeOpacity(rt) {
  if (rt === "소속") return 0.55;
  if (rt === "언급" || rt === "관련주제") return 0.75;
  return 0.6;
}

function _parseGraphKeDbId(idStr, prefix) {
  const s = String(idStr);
  const p = prefix + "_";
  if (s.startsWith(p)) return parseInt(s.slice(p.length), 10);
  return parseInt(s, 10);
}

function openListForBrandChannel(brandLabel) {
  const label = (brandLabel || "").trim() || "미분류";
  libState.tagFilter = "";
  libState.entityId = 0;
  libState.conceptId = 0;
  libState.treeSel = { large: "", medium: label, small: "" };
  libState.categoryLarge = "";
  libState.categoryMedium = label;
  libState.categorySmall = "";
  libState.page = 1;
  switchLibraryView("list");
  loadLibrary();
}

/**
 * full_cluster: Progressive 시뮬에서 주입됐던 KE 노드 제거(null). 엔티티/개념은 그래프에 추가하지 않음(패널 위키만).
 */
function _fullClusterSyncProgressive(_materialId) {
  const ctx = _fullClusterCtx;
  if (!ctx || !ctx.sim) return;
  const sim = ctx.sim;
  const nodesArr = sim.nodes();
  const baseCount = ctx.baseNodeCount;
  while (nodesArr.length > baseCount) nodesArr.pop();

  const extraEdges = [];

  const simEdgeList = ctx.baseSimEdgeList.concat(extraEdges);
  const linkData = simEdgeList.map((e, idx) => ({
    source: e.source_id,
    target: e.target_id,
    relation_type: e.relation_type,
    edge_label: e.edge_label,
    shared_tags: e.shared_tags,
    weight: e.weight,
    _linkKey: `${e.source_id}-${e.target_id}-${e.relation_type}-${idx}`,
  }));
  const links = linkData.map((d) => ({ ...d }));
  const defaultDist = +document.getElementById("inputDistance")?.value || 70;
  const linkStrengthFn = (lnk) => {
    const rt = lnk.relation_type;
    if (rt === "소속") return 0.7;
    if (rt === "shared_topic") return 0.1;
    return 0.1;
  };
  sim.force("link", d3.forceLink(links)
    .id((d) => d.id)
    .distance((lnk) => {
      const rt = lnk.relation_type;
      if (rt === "소속") return 40;
      return defaultDist;
    })
    .strength(linkStrengthFn)
    .iterations(1));
  sim.nodes(nodesArr);

  const linkWrap = ctx.linkG.selectAll("g.graph-edge").data(links, (d) => d._linkKey).join("g")
    .attr("class", (d) => `graph-edge ge-${d.relation_type}`);
  linkWrap.each(function (d) {
    const el = d3.select(this);
    el.selectAll("*").remove();
    const rt = d.relation_type;
    const line = el.append("line").attr("class", "graph-edge-line");
    if (rt === "소속") {
      line.attr("stroke", "rgba(255,255,255,0.08)")
        .attr("stroke-width", 0.5)
        .attr("stroke-opacity", 1)
        .attr("stroke-dasharray", null);
    } else {
      const p = _graphRelationEdgePaint(rt);
      line.attr("stroke", p.stroke)
        .attr("stroke-width", Math.max(0.45, p.width * 0.55))
        .attr("stroke-opacity", p.opacity * 0.4)
        .attr("stroke-dasharray", p.dash || null);
    }
    if ((rt === "shared_topic" || rt === "shared_entity" || rt === "shared_concept") && d.edge_label) {
      el.append("text")
        .attr("class", "graph-edge-tag-label")
        .attr("font-size", 8)
        .attr("fill", _edgeTagLabelFill(rt))
        .attr("text-anchor", "middle")
        .style("pointer-events", "none")
        .style("display", _graphEdgeTagVisible(d) ? null : "none")
        .attr("opacity", 0)
        .text(d.edge_label);
    }
  });
  linkWrap
    .filter((d) => d.relation_type === "shared_topic")
    .style("cursor", "crosshair")
    .on("mouseenter", (ev, d) => _showSharedTopicEdgeTooltip(ev, d))
    .on("mouseleave", () => { _hideSharedTopicHoverTooltip(); _hideTooltip(); });

  const nodeSel = ctx.nodeG.selectAll("g.gn").data(nodesArr, (d) => d.id).join("g")
    .attr("class", "gn")
    .call(d3.drag()
      .filter(function (event, d) {
        const nt = _nodeTypeOf(d);
        return nt !== "brand";
      })
      .on("start", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0.25).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (ev, d) => {
        d.fx = ev.x;
        d.fy = ev.y;
      })
      .on("end", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      }));
  _appendNodeShape(nodeSel);
  nodeSel.on("click", _graphNodeClick);
  nodeSel.on("mouseover", (ev, d) => {
    if (_nodeTypeOf(d) === "material") {
      const matR = 6;
      d3.select(ev.currentTarget).select("circle.graph-mat-node")
        .attr("r", matR * 1.12)
        .attr("fill", "rgba(200,200,210,0.9)");
    }
    const c = _fullClusterCtx;
    if (c) {
      _hoverNode(d, c.nodeG.selectAll("g.gn"), c.linkG.selectAll("g.graph-edge"), c.labelG.selectAll("text.gl-text-node"), true);
    }
    _showGraphHoverTitleTooltip(ev, d);
  });
  nodeSel.on("mouseout", (ev, d) => {
    if (_nodeTypeOf(d) === "material") {
      const matR = 6;
      d3.select(ev.currentTarget).select("circle.graph-mat-node")
        .attr("r", matR)
        .attr("fill", "rgba(200,200,210,0.9)");
    }
    const c = _fullClusterCtx;
    if (c) {
      _hoverNode(d, c.nodeG.selectAll("g.gn"), c.linkG.selectAll("g.graph-edge"), c.labelG.selectAll("text.gl-text-node"), false);
    }
    _hideTooltip();
  });

  const labelNodes = nodesArr.filter((n) => _nodeTypeOf(n) === "material");
  ctx.labelG.selectAll("text.gl-text-node").data(labelNodes, (d) => d.id).join("text")
    .attr("class", "gl-text gl-text-node gl-text-material")
    .attr("font-size", 11)
    .attr("text-anchor", "middle")
    .attr("dy", (d) => {
      const base = d._graphR != null ? d._graphR : 12;
      return base + 10;
    })
    .attr("fill", "#cccccc")
    .each((d) => {
      if (d._graphLabelFull == null) d._graphLabelFull = d.title || "";
    })
    .text((d) => _materialGraphLabelText(d));

  sim.alpha(0.35).restart();
  _syncGraphNeighborViz();
}

function _graphNodeClick(ev, d) {
  ev.stopPropagation();
  const nt = _nodeTypeOf(d);
  if (
    _fullClusterCtx &&
    !_graphMiniConstellationMode &&
    !_graphSimpleMode &&
    nt === "material" &&
    _graphProgressiveMaterialId === d.id
  ) {
    _fullClusterSyncProgressive(null);
    _graphProgressiveMaterialId = null;
    _graphSelectedNodeId = null;
    _clearGraphNeighborBadgeState();
    _updateGraphLabelVisibility();
    _hideTooltip();
    setGraphDetailOpen(false);
    _graphApplySelectionToggleEdgeDim();
    return;
  }
  if ((nt === "brand" || nt === "material") && _graphNeighborBadgeAnchorId === d.id) {
    _clearGraphNeighborBadgeState();
    _graphSelectedNodeId = null;
    if (_fullClusterCtx && !_graphMiniConstellationMode && !_graphSimpleMode && nt === "brand") {
      _fullClusterSyncProgressive(null);
      _graphProgressiveMaterialId = null;
    }
    if (_fullClusterCtx && !_graphMiniConstellationMode && !_graphSimpleMode && nt === "material") {
      _fullClusterSyncProgressive(null);
      _graphProgressiveMaterialId = null;
    }
    _updateGraphLabelVisibility();
    _hideTooltip();
    setGraphDetailOpen(false);
    _graphApplySelectionToggleEdgeDim();
    return;
  }
  _graphSelectedNodeId = d.id;
  if (_fullClusterCtx && !_graphMiniConstellationMode && !_graphSimpleMode) {
    if (nt === "material") {
      _graphProgressiveMaterialId = d.id;
    } else if (nt === "brand") {
      _fullClusterSyncProgressive(null);
      _graphProgressiveMaterialId = null;
    }
  }
  const mats = (nt === "brand" || nt === "material") ? _graphNeighborMaterialNodes(d.id) : [];
  if (nt === "brand" || nt === "material") {
    _applyGraphNeighborBadgeState(d.id, mats);
  }
  _updateGraphLabelVisibility();
  _hideTooltip();
  if (nt === "material" || nt === "brand") {
    openGraphDetailPanelNeighborAnchor(d);
  }
  _graphApplySelectionToggleEdgeDim();
}

function _countRelMaterialsForKe(d, edges) {
  const nt = _nodeTypeOf(d);
  const id = d.id;
  if (nt === "entity") {
    return edges.filter(e => e.relation_type === "언급" && (e.source_id === id || e.target_id === id)).length;
  }
  if (nt === "concept") {
    return edges.filter(e => e.relation_type === "관련주제" && (e.source_id === id || e.target_id === id)).length;
  }
  return 0;
}

function _connectionDegree(id, edges) {
  let c = 0;
  edges.forEach(e => {
    if (e.source_id === id || e.target_id === id) c += 1;
  });
  return c;
}

/** Phase 4-B: 허브 Top3, 고립(소속만 1연결), 브릿지(shared_topic으로 서로 다른 브랜드 2+) */
function _graphMetricsForBar(nodes, edges) {
  const mats = nodes.filter((n) => _nodeTypeOf(n) === "material");
  const deg = new Map();
  nodes.forEach((n) => deg.set(n.id, 0));
  edges.forEach((e) => {
    if (!deg.has(e.source_id) || !deg.has(e.target_id)) return;
    deg.set(e.source_id, (deg.get(e.source_id) || 0) + 1);
    deg.set(e.target_id, (deg.get(e.target_id) || 0) + 1);
  });
  const hubs = mats
    .map((m) => ({ id: m.id, title: (m.title || "").trim() || "(제목 없음)", d: deg.get(m.id) || 0 }))
    .sort((a, b) => b.d - a.d)
    .slice(0, 3);
  let isolated = 0;
  for (const m of mats) {
    const mid = m.id;
    const inc = edges.filter((e) => e.source_id === mid || e.target_id === mid);
    if (inc.length !== 1) continue;
    if (inc[0].relation_type === "소속") isolated += 1;
  }
  let bridge = 0;
  for (const m of mats) {
    const brands = new Set();
    edges.forEach((e) => {
      if (e.relation_type !== "shared_topic") return;
      let oid = null;
      if (e.source_id === m.id) oid = e.target_id;
      else if (e.target_id === m.id) oid = e.source_id;
      if (oid == null) return;
      const other = nodes.find((x) => x.id === oid);
      if (other && _nodeTypeOf(other) === "material") {
        brands.add(other.group || other.brand_label || "미분류");
      }
    });
    if (brands.size >= 2) bridge += 1;
  }
  return { hubs, isolated, bridge };
}

function _neighborMaterialTitles(materialId) {
  const fd = _lastGraphFiltered;
  if (!fd) return [];
  const { nodes, edges } = fd;
  const seen = new Set();
  const out = [];
  edges.forEach((e) => {
    if (e.source_id !== materialId && e.target_id !== materialId) return;
    const oid = e.source_id === materialId ? e.target_id : e.source_id;
    if (seen.has(oid)) return;
    const n = nodes.find((x) => x.id === oid);
    if (n && _nodeTypeOf(n) === "material") {
      seen.add(oid);
      out.push({
        id: oid,
        title: (n.title || "").trim() || "(제목 없음)",
        group: (n.group || n.brand_label || "미분류"),
        ingested_date: n.ingested_date || "",
      });
    }
  });
  return out;
}

/** 위키 2줄 미리보기용 평문(마크다운 원문 기준) */
function _gdpWikiPlainPreview(md) {
  if (!md || !String(md).trim()) return "";
  const t = String(md).trim().replace(/\s+/g, " ");
  return t.length > 160 ? `${t.slice(0, 157)}…` : t;
}

/** marked + DOMPurify — 위키 카드 본문 전용 */
function _gdpRenderMarkdown(md) {
  if (!md || typeof md !== "string") return "";
  try {
    const parseFn =
      typeof marked !== "undefined" && typeof marked.parse === "function"
        ? marked.parse.bind(marked)
        : typeof marked === "function"
          ? marked
          : null;
    if (!parseFn) return `<p class="gdp-meta">Markdown 라이브러리를 불러오지 못했습니다.</p>`;
    const rawHtml = parseFn(md, { breaks: true });
    if (typeof DOMPurify !== "undefined" && typeof DOMPurify.sanitize === "function") {
      return DOMPurify.sanitize(rawHtml, { USE_PROFILES: { html: true } });
    }
    return rawHtml;
  } catch (err) {
    return `<p class="gdp-meta">${escapeHtml(err.message || String(err))}</p>`;
  }
}

function _gdpInitGraphDetailPanelCards(body) {
  if (!body) return;
  body.querySelectorAll(".gdp-card").forEach((card) => {
    const head = card.querySelector(".gdp-card-head");
    if (!head) return;
    head.addEventListener("click", () => {
      const wiki = card.getAttribute("data-gdp-wiki") === "1";
      const wasOpen = card.classList.contains("gdp-card--open");
      const open = !wasOpen;
      card.classList.toggle("gdp-card--open", open);
      head.setAttribute("aria-expanded", open ? "true" : "false");
      const icon = head.querySelector(".gdp-card-icon");
      if (icon) icon.textContent = open ? "▼" : "▲";
      if (wiki) {
        const prev = card.querySelector(".gdp-wiki-preview-wrap");
        const panel = card.querySelector(".gdp-wiki-panel");
        if (prev) prev.hidden = open;
        if (panel) panel.hidden = !open;
      }
    });
  });
  const _gdpBindMaterialJump = (row) => {
    const go = (ev) => {
      if (ev) ev.preventDefault();
      const mid = Number.parseInt(
        row.getAttribute("data-mid") || row.getAttribute("data-id") || "",
        10,
      );
      if (mid) openGraphDetailPanelMaterial(mid);
    };
    row.addEventListener("click", go);
    row.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        go(ev);
      }
    });
  };
  body.querySelectorAll(".gdp-neighbor-mini[data-mid]").forEach(_gdpBindMaterialJump);
  body.querySelectorAll(".gdp-conn-jump[data-mid]").forEach(_gdpBindMaterialJump);
  body.querySelectorAll(".gdp-conn-group").forEach((gEl) => {
    const head = gEl.querySelector(".gdp-conn-group-head");
    const bEl = gEl.querySelector(".gdp-conn-group-body");
    const chev = gEl.querySelector(".gdp-conn-group-chev");
    if (!head || !bEl) return;
    const setOpen = (open) => {
      head.setAttribute("aria-expanded", open ? "true" : "false");
      bEl.hidden = !open;
      if (chev) chev.textContent = open ? "▼" : "▲";
    };
    head.addEventListener("click", () => {
      const open = head.getAttribute("aria-expanded") === "true";
      setOpen(!open);
    });
    head.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        const open = head.getAttribute("aria-expanded") === "true";
        setOpen(!open);
      }
    });
  });
  body.querySelectorAll(".gdp-wiki-ke-link[data-gdp-ke-id]").forEach((el) => {
    const go = () => {
      const id = Number.parseInt(el.getAttribute("data-gdp-ke-id"), 10);
      const t = el.getAttribute("data-gdp-ke-type");
      if (!id || (t !== "entity" && t !== "concept")) return;
      showKnowledgeDetail(t, id);
    };
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      go();
    });
    el.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        go();
      }
    });
  });
}

function setGraphDetailOpen(open) {
  const v = document.getElementById("libraryGraphView");
  const p = document.getElementById("graphDetailPanel");
  if (v) v.classList.toggle("graph-detail-open", !!open);
  if (p) p.setAttribute("aria-hidden", open ? "false" : "true");
}

/** graph-panel API와 동일한 자료 상세 HTML (요약·태그·위키·연결된 자료 미니그리드). */
async function _buildGraphDetailMaterialPanelHtml(id, brandLabel) {
  const res = await api(`/api/library/material/${id}/graph-panel`);
  const payload = res.data;
  const material = payload.material;
  const wikiSnippets = payload.wiki_snippets || [];
  const connections = payload.connections || [];
  const neighbors = _neighborMaterialTitles(id);
  const titleText = (material.title || "").trim() || "자료";
  const datePart = (material.ingested_date || "").trim()
    ? escapeHtml(String(material.ingested_date).trim())
    : "";
  const dateLine = datePart
    ? `${datePart} · 중요도 ${material.importance ?? "—"}`
    : `중요도 ${material.importance ?? "—"}`;

  const summaryInner = material.summary
    ? `<div class="gdp-prose">${escapeHtml(String(material.summary))}</div>`
    : `<div class="gdp-prose gdp-prose--empty">요약이 없습니다.</div>`;

  const tagsInner =
    material.tags && material.tags.length
      ? `<div class="gdp-tags">${material.tags.slice(0, 24).map((t) =>
        `<span class="gdp-tag">${escapeHtml(String(t))}</span>`).join("")}</div>`
      : `<p class="gdp-meta gdp-meta--flush">태그가 없습니다.</p>`;

  const wikiBlocks = [];
  wikiSnippets.forEach((w) => {
    const content = cleanWikiPanelContent(w.snippet || "");
    if (!content) return;
    const sym = w.kind === "entity" ? "◆" : "▲";
    const name = (w.name || "").trim() || "—";
    wikiBlocks.push(`## ${sym} ${name}\n\n${content.trim()}`);
  });
  const wikiMd = wikiBlocks.join("\n\n---\n\n");

  let wikiSectionHtml = "";
  if (!wikiMd.trim()) {
    wikiSectionHtml =
      `<section class="gdp-card gdp-card--open" data-gdp-section="wiki">`
      + `<button type="button" class="gdp-card-head" aria-expanded="true">`
      + `<span class="gdp-card-title">위키 내용</span><span class="gdp-card-icon" aria-hidden="true">▼</span></button>`
      + `<div class="gdp-card-panel"><div class="gdp-card-inner">`
      + `<p class="gdp-meta gdp-meta--flush">연결된 위키 스니펫이 없습니다.</p>`
      + `</div></div></section>`;
  } else {
    const wikiHtmlParts = [];
    wikiSnippets.forEach((w) => {
      const content = cleanWikiPanelContent(w.snippet || "");
      if (!content) return;
      const sym = w.kind === "entity" ? "◆" : "▲";
      const name = (w.name || "").trim() || "—";
      const keId = Number(w.id);
      const keType = w.kind === "entity" ? "entity" : "concept";
      const h2Class = keType === "entity" ? "gdp-wiki-h2-entity" : "gdp-wiki-h2-concept";
      const linkCls = keType === "entity"
        ? "gdp-wiki-ke-link gdp-wiki-ke-link--entity"
        : "gdp-wiki-ke-link gdp-wiki-ke-link--concept";
      const bodyHtml = _gdpRenderMarkdown(content.trim());
      let headingHtml;
      if (Number.isFinite(keId) && keId > 0) {
        headingHtml =
          `<h2 class="${h2Class}"><span class="${linkCls}" role="button" tabindex="0" data-gdp-ke-type="${keType}" data-gdp-ke-id="${keId}">${escapeHtml(`${sym} ${name}`)}</span></h2>`;
      } else {
        headingHtml = `<h2 class="${h2Class}">${escapeHtml(`${sym} ${name}`)}</h2>`;
      }
      wikiHtmlParts.push(headingHtml + bodyHtml);
    });
    const wikiHtml = wikiHtmlParts.join("<hr>");
    const wikiPrev = escapeHtml(_gdpWikiPlainPreview(wikiMd));
    wikiSectionHtml =
      `<section class="gdp-card" data-gdp-wiki="1" data-gdp-section="wiki">`
      + `<button type="button" class="gdp-card-head" aria-expanded="false">`
      + `<span class="gdp-card-title">위키 내용</span><span class="gdp-card-icon" aria-hidden="true">▲</span></button>`
      + `<div class="gdp-wiki-preview-wrap"><div class="gdp-wiki-preview-text">${wikiPrev}</div></div>`
      + `<div class="gdp-card-panel gdp-wiki-panel" hidden>`
      + `<div class="gdp-card-inner gdp-prose gdp-md">${wikiHtml}</div></div></section>`;
  }

  let neighborsHtml = "";
  if (!neighbors.length) {
    neighborsHtml = `<p class="gdp-meta gdp-meta--flush">📎 직접 연결된 자료가 없습니다.</p>`;
  } else {
    neighborsHtml =
      `<div class="gdp-neighbor-minigrid">${
        neighbors.map((n) => {
          const dotCol = getBrandColor(n.group);
          const nbBrandEsc = escapeHtml(String(n.group || "미분류"));
          const titleLine = escapeHtml(_graphNeighborListTitle20(n.title));
          const dateN = escapeHtml(_graphNeighborListDateLine(n));
          return `<div class="gdp-neighbor-mini" data-mid="${n.id}" role="button" tabindex="0">`
            + `<div class="gdp-neighbor-mini-r1">`
            + `<span class="gdp-neighbor-mini-dot" style="background:${dotCol}"></span>`
            + `<span class="gdp-neighbor-mini-brand" style="color:${dotCol}">${nbBrandEsc}</span>`
            + `</div>`
            + `<div class="gdp-neighbor-mini-title">${titleLine}</div>`
            + `<div class="gdp-neighbor-mini-date">${dateN}</div>`
            + `</div>`;
        }).join("")
      }</div>`;
  }

  const brandStr = (brandLabel != null && String(brandLabel).trim()) ? String(brandLabel).trim() : "";
  const brandBadge = brandStr
    ? `<div class="gdp-brand-badge" style="
      display:inline-block;
      padding:3px 10px;
      margin-bottom:6px;
      border-radius:10px;
      background:rgba(80,80,90,0.8);
      color:rgba(180,200,220,0.9);
      font-size:11px;
      font-weight:500;
      letter-spacing:0.02em;
    ">${escapeHtml(brandStr)}</div>`
    : "";

  const connectionsSectionHtml = _graphBuildConnectionsPanelSectionHtml(connections);

  return (
    brandBadge
    + `<h2 class="gdp-panel-title">${escapeHtml(titleText)}</h2>`
    + `<div class="gdp-panel-date">${dateLine}</div>`
    + `<section class="gdp-card gdp-card--open" data-gdp-section="summary">`
    + `<button type="button" class="gdp-card-head" aria-expanded="true">`
    + `<span class="gdp-card-title">요약</span><span class="gdp-card-icon" aria-hidden="true">▼</span></button>`
    + `<div class="gdp-card-panel"><div class="gdp-card-inner">${summaryInner}</div></div></section>`
    + `<section class="gdp-card gdp-card--open" data-gdp-section="tags">`
    + `<button type="button" class="gdp-card-head" aria-expanded="true">`
    + `<span class="gdp-card-title">태그</span><span class="gdp-card-icon" aria-hidden="true">▼</span></button>`
    + `<div class="gdp-card-panel"><div class="gdp-card-inner">${tagsInner}</div></div></section>`
    + wikiSectionHtml
    + connectionsSectionHtml
    + `<section class="gdp-card gdp-card--open" data-gdp-section="linked">`
    + `<button type="button" class="gdp-card-head" aria-expanded="true">`
    + `<span class="gdp-card-title">📎 직접 연결된 자료</span><span class="gdp-card-icon" aria-hidden="true">▼</span></button>`
    + `<div class="gdp-card-panel"><div class="gdp-card-inner">${neighborsHtml}</div></div></section>`
  );
}

async function openGraphDetailPanelMaterial(id) {
  setGraphDetailOpen(true);
  const body = document.getElementById("graphDetailBody");
  if (body) {
    body.innerHTML = "<h2 class=\"gdp-panel-title\">자료</h2>"
      + "<p class=\"gdp-meta\">불러오는 중…</p>";
  }
  try {
    const node = _fullClusterCtx
      ? _fullClusterCtx.sim.nodes().find((n) => n.id === id)
      : null;
    const brandLabel = node ? (node.brand_label || node.group || "") : "";
    const html = await _buildGraphDetailMaterialPanelHtml(id, brandLabel);
    if (body) {
      body.innerHTML = html;
      _gdpInitGraphDetailPanelCards(body);
    }
  } catch (e) {
    if (body) {
      body.innerHTML = "<h2 class=\"gdp-panel-title\">자료</h2>"
        + `<p class="gdp-meta">로드 실패: ${escapeHtml(e.message || String(e))}</p>`;
    }
  }
}

async function openGraphDetailPanelBrand(d) {
  setGraphDetailOpen(true);
  const label = (d.brand_label || d.group || "").trim() || "미분류";
  const body = document.getElementById("graphDetailBody");
  const plat = (d.platform != null && String(d.platform).trim()) ? String(d.platform).trim() : "—";
  const catLarge = (d.category_large != null && String(d.category_large).trim())
    ? String(d.category_large).trim()
    : "—";
  if (body) {
    body.innerHTML = `<h2 class="gdp-panel-title">${escapeHtml(label)}</h2>`
      + "<p class=\"gdp-meta\">불러오는 중…</p>";
  }
  const fd = _lastGraphFiltered || _getFilteredData();
  const materials = (fd.nodes || []).filter((n) => {
    if (_nodeTypeOf(n) !== "material") return false;
    return (n.group || n.brand_label || "미분류").trim() === label;
  });
  let synthSnippet = "";
  try {
    const listRes = await api("/api/knowledge/synthesis");
    const pages = listRes.data || [];
    const match = pages.find((p) =>
      (p.title || "").includes(label) || (p.filename || "").includes(label.replace(/[\\/]/g, "_"))
    );
    if (match && match.filename) {
      const pg = await api(`/api/knowledge/synthesis/${encodeURIComponent(match.filename)}`);
      const c = pg.data && pg.data.content;
      if (c) synthSnippet = String(c).slice(0, 500);
    }
  } catch (e) {
    synthSnippet = "";
  }
  let html = "";
  html += `<h2 class="gdp-panel-title">${escapeHtml(label)}</h2>`;
  html += `<div class="gdp-panel-date">${escapeHtml(plat)} · ${escapeHtml(catLarge)}</div>`;
  html += "<hr class=\"gdp-rule\">";
  html += "<div class=\"gdp-subhead\">요약</div>";
  html += `<div class="gdp-prose">이 출처·분류에 소속된 자료는 총 ${materials.length}건입니다.</div>`;
  html += "<hr class=\"gdp-rule\">";
  html += "<div class=\"gdp-subhead\">위키 내용</div>";
  if (synthSnippet) {
    html += `<div class="gdp-prose">${escapeHtml(synthSnippet)}</div>`;
  } else {
    html += "<p class=\"gdp-meta\">연결된 종합 페이지를 찾지 못했습니다.</p>";
  }
  html += "<hr class=\"gdp-rule\">";
  html += "<div class=\"gdp-subhead\">📎 직접 연결된 자료</div>";
  if (!materials.length) {
    html += "<p class=\"gdp-meta\">📎 직접 연결된 자료가 없습니다.</p>";
  } else {
    html += "<ul class=\"gdp-linked-list\">";
    materials.forEach((m) => {
      const g = m.group || m.brand_label || label;
      const dotCol = getBrandColor(g);
      html += `<li class="gdp-linked-item" data-mid="${m.id}" role="button" tabindex="0">`
        + `<span class="gdp-linked-dot" style="background:${dotCol}"></span>`
        + `<span class="gdp-linked-title">${escapeHtml((m.title || "").trim() || "(제목 없음)")}</span>`
        + "</li>";
    });
    html += "</ul>";
  }
  if (body) {
    body.innerHTML = html;
    body.querySelectorAll(".gdp-linked-item[data-mid]").forEach((row) => {
      const go = () => {
        const mid = Number.parseInt(row.dataset.mid, 10);
        if (mid) openGraphDetailPanelMaterial(mid);
      };
      row.addEventListener("click", go);
      row.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          go();
        }
      });
    });
  }
}

function _renderGraphStatsBarFiltered(nodes, edges, orphanN) {
  const el = document.getElementById("graphStatsBar");
  if (!el) return;
  const N = nodes.length;
  const n1 = nodes.filter(n => _nodeTypeOf(n) === "material").length;
  const nBr = nodes.filter(n => _nodeTypeOf(n) === "brand").length;
  const E = edges.length;
  const O = orphanN;
  let D = "0";
  if (N > 1) D = ((E / (N * (N - 1) / 2)) * 100).toFixed(2);
  const m = _graphMetricsForBar(nodes, edges);
  const hubLine = m.hubs.length
    ? m.hubs.map((h) => `${escapeHtml(h.title)}(${h.d}연결)`).join(", ")
    : "—";
  el.innerHTML = `<span class="gsb-line gsb-line-primary">`
    + `<span class="gsb-seg"><span class="gsb-lab">총 노드</span> <strong class="gsb-val gsb-val-nodes">${N}</strong><span class="gsb-unit">개</span></span>`
    + `<span class="gsb-div" aria-hidden="true">|</span>`
    + `<span class="gsb-seg"><span class="gsb-lab">자료</span> <strong class="gsb-val gsb-val-mat">${n1}</strong></span>`
    + `<span class="gsb-dot" aria-hidden="true">·</span>`
    + `<span class="gsb-seg"><span class="gsb-lab">출처</span> <strong class="gsb-val gsb-val-brand">${nBr}</strong></span>`
    + `<span class="gsb-div" aria-hidden="true">|</span>`
    + `<span class="gsb-seg"><span class="gsb-lab">연결</span> <strong class="gsb-val gsb-val-edges">${E}</strong><span class="gsb-unit">개</span></span>`
    + `<span class="gsb-div" aria-hidden="true">|</span>`
    + `<span class="gsb-seg"><span class="gsb-lab">고립</span> <strong class="gsb-val gsb-val-orphan">${O}</strong><span class="gsb-unit">개</span></span>`
    + `<span class="gsb-div" aria-hidden="true">|</span>`
    + `<span class="gsb-seg"><span class="gsb-lab">밀도</span> <strong class="gsb-val gsb-val-density">${D}</strong><span class="gsb-unit">%</span></span>`
    + `</span>`
    + `<span class="gsb-extra">`
    + `<span class="gsb-extra-row"><strong class="gsb-extra-h gsb-extra-h-hub">허브 Top3</strong> <span class="gsb-hub">${hubLine}</span></span>`
    + `<span class="gsb-extra-meta"><strong class="gsb-extra-h gsb-extra-h-iso">고립 자료</strong> <span class="gsb-val-iso">${m.isolated}</span>개`
    + ` <span class="gsb-extra-gap" aria-hidden="true">·</span> `
    + `<strong class="gsb-extra-h gsb-extra-h-bridge">브릿지</strong> <span class="gsb-val-bridge">${m.bridge}</span>개</span>`
    + `</span>`;
}

async function loadGraph() {
  try {
    const res = await api(`/api/library/graph${libState.materialType ? "?material_type=" + libState.materialType : ""}`);
    _graphRaw = res.data;
    gf.categories = null;
    _renderGraphStats(_graphRaw.stats);
    _initGraphFilters(_graphRaw);
    _buildGraph();
  } catch (err) {
    showToast(`그래프 로드 실패: ${err.message}`, "error");
  }
}

function _renderGraphStats(s) {
  if (!s) return;
  const $ = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  $("gsNodes", s.total_nodes);
  $("gsEdges", s.total_edges);
  $("gsOrphans", s.orphan_count);
  $("gsCats", Object.keys(s.category_distribution || {}).length);

  const hubEl = document.getElementById("gsHubList");
  if (hubEl) {
    hubEl.innerHTML = (s.hub_top5 || []).length
      ? (s.hub_top5 || []).map((h, i) =>
          `<div class="gs-hub-item" data-id="${h.id}"><span class="gs-hub-rank">${i + 1}</span><span class="gs-hub-name">${escapeHtml(h.title)}</span><span class="gs-hub-cnt">${h.connections}</span></div>`
        ).join("")
      : '<p class="gs-empty">연결된 자료가 없습니다</p>';
    hubEl.querySelectorAll(".gs-hub-item").forEach(el => {
      el.addEventListener("click", () => showMaterialDetail(parseInt(el.dataset.id, 10)));
    });
  }

  const chartEl = document.getElementById("gsCatChart");
  if (chartEl) {
    const cats = Object.entries(s.category_distribution || {}).sort((a, b) => b[1] - a[1]);
    const maxVal = cats.length ? cats[0][1] : 1;
    chartEl.innerHTML = cats.map(([cat, cnt]) =>
      `<div class="gs-bar-row"><span class="gs-bar-label">${escapeHtml(cat)}</span><div class="gs-bar-track"><div class="gs-bar-fill" style="width:${(cnt / maxVal) * 100}%;background:${getCategoryColor(cat)}"></div></div><span class="gs-bar-cnt">${cnt}</span></div>`
    ).join("");
  }

  const recEl = document.getElementById("gsRecentList");
  if (recEl) {
    recEl.innerHTML = (s.recent_materials || []).length
      ? s.recent_materials.map(r =>
          `<div class="gs-recent-item" data-id="${r.id}"><span class="gs-recent-name">${escapeHtml(r.title)}</span><span class="gs-recent-date">${r.date}</span></div>`
        ).join("")
      : '<p class="gs-empty">최근 자료 없음</p>';
    recEl.querySelectorAll(".gs-recent-item").forEach(el => {
      el.addEventListener("click", () => showMaterialDetail(parseInt(el.dataset.id, 10)));
    });
  }
}

function _initGraphToolbarOnce() {
  if (gf._toolbarDelegation) return;
  gf._toolbarDelegation = true;
  const tb = document.getElementById("graphToolbar");
  if (tb) {
    tb.addEventListener("change", (e) => {
      const el = e.target;
      if (el.matches?.("input[data-etype]")) {
        const t = el.dataset.etype;
        el.checked ? gf.edgeTypes.add(t) : gf.edgeTypes.delete(t);
        _buildGraph();
      }
      if (el.matches?.("input[data-ntype]")) {
        const t = el.dataset.ntype;
        el.checked ? gf.nodeTypes.add(t) : gf.nodeTypes.delete(t);
        _buildGraph();
      }
    });
  }
  const impRange = document.getElementById("graphImpRange");
  const impLabel = document.getElementById("graphImpValue");
  if (impRange && !impRange.dataset.bound) {
    impRange.dataset.bound = "1";
    impRange.addEventListener("input", () => {
      gf.impMin = parseInt(impRange.value, 10);
      if (impLabel) impLabel.textContent = gf.impMin + "+";
      _buildGraph();
    });
  }
  const searchIn = document.getElementById("graphSearchInput");
  if (searchIn && !searchIn.dataset.bound) {
    searchIn.dataset.bound = "1";
    let timer = null;
    const runSearch = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        gf.search = searchIn.value.trim().toLowerCase();
        _highlightSearch();
      }, 200);
    };
    searchIn.addEventListener("input", runSearch);
    searchIn.addEventListener("keyup", runSearch);
  }
  if (!gf._graphDetailBound) {
    gf._graphDetailBound = true;
    const closeBtn = document.getElementById("graphDetailPanelClose");
    if (closeBtn) closeBtn.addEventListener("click", () => setGraphDetailOpen(false));
  }
  /* 그래프 캔버스(줌·빈 SVG·스트립 배경 등) 클릭 시 상세 패널 닫기 — 노드 클릭은 _graphNodeClick에서 stopPropagation */
  if (!gf._graphCanvasCloseDetailBound) {
    gf._graphCanvasCloseDetailBound = true;
    const canvasWrap = document.getElementById("graphCanvasWrap");
    if (canvasWrap) {
      canvasWrap.addEventListener("click", () => {
        const lgv = document.getElementById("libraryGraphView");
        if (!lgv?.classList.contains("graph-detail-open")) return;
        setGraphDetailOpen(false);
      });
    }
  }
  if (!gf._graphControlsBound) {
    gf._graphControlsBound = true;
    const zIn = document.getElementById("gzIn");
    const zOut = document.getElementById("gzOut");
    const zFit = document.getElementById("gzFit");
    if (zIn) zIn.addEventListener("click", () => _graphZoomStep(1.3));
    if (zOut) zOut.addEventListener("click", () => _graphZoomStep(0.7));
    if (zFit) zFit.addEventListener("click", _graphZoomFit);
  }
  if (!gf._sidebarToggleBound) {
    gf._sidebarToggleBound = true;
    const btn = document.getElementById("btnGraphSidebarToggle");
    if (btn) {
      btn.addEventListener("click", () => {
        gf.sidebarCollapsed = !gf.sidebarCollapsed;
        const body = document.querySelector("#libraryGraphView .graph-body");
        if (body) body.classList.toggle("graph-sidebar-collapsed", gf.sidebarCollapsed);
        btn.textContent = gf.sidebarCollapsed ? "► 패널" : "◀ 패널";
        if (gf._sidebarReflowT) clearTimeout(gf._sidebarReflowT);
        gf._sidebarReflowT = setTimeout(() => {
          gf._sidebarReflowT = null;
          if (currentLibraryView === "graph") _buildGraph();
        }, 320);
      });
    }
  }
  if (!gf._orphanToggleBound) {
    gf._orphanToggleBound = true;
    const ob = document.getElementById("btnOrphanToggle");
    if (ob) {
      ob.addEventListener("click", () => {
        gf.hideOrphans = !gf.hideOrphans;
        ob.textContent = gf.hideOrphans ? "고립 노드 보이기" : "고립 노드 숨기기";
        const op = document.getElementById("graphOrphanPanel");
        if (op) {
          op.style.display = gf.hideOrphans ? "none" : "";
          op.classList.toggle("is-hidden", gf.hideOrphans);
        }
        _buildGraph();
      });
    }
  }
}

function _initGraphFilters(data) {
  _initGraphToolbarOnce();
  const cats = [...new Set((data.nodes || []).map(n => n.category_large))].sort();
  const catEl = document.getElementById("graphCatFilters");
  if (catEl) {
    catEl.innerHTML = cats.map(c =>
      `<label class="gt-cat-label"><input type="checkbox" checked data-gcat="${escapeHtml(c)}"><span class="gt-cat-dot" style="background:${getCategoryColor(c)}"></span>${escapeHtml(c)}</label>`
    ).join("");
    catEl.querySelectorAll("input[data-gcat]").forEach(cb => {
      cb.addEventListener("change", () => { gf.categories = _getActiveCategories(); _buildGraph(); });
    });
  }

  /* graphLegendNodes — _buildGraph()에서 브랜드별 색으로 갱신 */
}

function _updateGraphBrandLegend(brandList, edgeList) {
  _graphEnsureEdgeToggleBar();
  _graphUpdateEdgeToggleLabels(edgeList || (_lastGraphFiltered && _lastGraphFiltered.edges) || []);
  const legendNodes = document.getElementById("graphLegendNodes");
  if (!legendNodes) return;
  if (!brandList || !brandList.length) {
    legendNodes.innerHTML = "";
    return;
  }
  const dots = brandList.map((b) =>
    `<span class="gl-node-item"><span class="gl-dot" style="background:${getBrandColor(b)}"></span>${escapeHtml(b)}</span>`
  );
  legendNodes.innerHTML = dots.join("");
}

function _getActiveCategories() {
  const checks = document.querySelectorAll("#graphCatFilters input[data-gcat]");
  if (!checks.length) return null;
  const active = [];
  checks.forEach(cb => { if (cb.checked) active.push(cb.dataset.gcat); });
  return active.length === checks.length ? null : new Set(active);
}

function _getFilteredData() {
  if (!_graphRaw) {
    return { nodes: [], edges: [], mainNodes: [], stripNodes: [], orphanCount: 0 };
  }
  let nodes = _graphRaw.nodes.slice();
  nodes = nodes.filter((n) => {
    const nt = _nodeTypeOf(n);
    if (nt === "material" && !gf.nodeTypes.has("material")) return false;
    if (nt === "brand" && !gf.nodeTypes.has("brand")) return false;
    if (nt === "entity" && !gf.nodeTypes.has("entity")) return false;
    if (nt === "concept" && !gf.nodeTypes.has("concept")) return false;
    return true;
  });
  if (gf.categories) {
    nodes = nodes.filter(n => gf.categories.has(n.category_large));
  }
  if (gf.impMin > 1) {
    nodes = nodes.filter(n => _nodeTypeOf(n) !== "material" || (n.importance || 3) >= gf.impMin);
  }
  const nodeIds = new Set(nodes.map(n => n.id));
  const edges = _graphRaw.edges.filter(e =>
    nodeIds.has(e.source_id) && nodeIds.has(e.target_id) && gf.edgeTypes.has(e.relation_type)
  );

  const deg = new Map();
  nodes.forEach(n => deg.set(n.id, 0));
  edges.forEach(e => {
    deg.set(e.source_id, (deg.get(e.source_id) || 0) + 1);
    deg.set(e.target_id, (deg.get(e.target_id) || 0) + 1);
  });
  const orphanSet = new Set(nodes.filter(n => deg.get(n.id) === 0).map(n => n.id));
  const mainNodes = nodes.filter(n => !orphanSet.has(n.id));
  const stripNodes = nodes.filter(n => orphanSet.has(n.id));

  return {
    nodes,
    edges,
    mainNodes,
    stripNodes,
    orphanCount: orphanSet.size,
  };
}

function _drawClusterCirclesAndLabels(clusterG, labelG, materialNodesByCat, width, height) {
  clusterG.selectAll("circle.cluster-zone").remove();
  labelG.selectAll("text.cluster-label").remove();
  Object.keys(materialNodesByCat).forEach((cat) => {
    const list = materialNodesByCat[cat];
    if (!list || list.length === 0) return;
    let sx = 0;
    let sy = 0;
    list.forEach((n) => {
      sx += n.x;
      sy += n.y;
    });
    const cx = sx / list.length;
    const cy = sy / list.length;
    let maxd = 40;
    list.forEach((n) => {
      const dx = n.x - cx;
      const dy = n.y - cy;
      maxd = Math.max(maxd, Math.hypot(dx, dy) + _nodeRadius(n) + 24);
    });
    clusterG.append("circle")
      .attr("class", "cluster-zone")
      .attr("cx", cx)
      .attr("cy", cy)
      .attr("r", maxd)
      .attr("fill", getCategoryColor(cat))
      .attr("fill-opacity", 0.05)
      .attr("stroke", "none");
    labelG.append("text")
      .attr("class", "cluster-label")
      .attr("x", cx)
      .attr("y", cy - maxd + 4)
      .attr("text-anchor", "middle")
      .text(cat);
  });
}

function _brandGraphInnodeLabel(d) {
  const raw = (d.brand_label || d.title || d.group || "미분류").replace(/\s*\(\d+건\)\s*$/, "").trim();
  /* r=14 원 안 가독성: 긴 소속명은 말줄임 + clipPath로 원 밖 미표시 */
  const maxLen = 6;
  return raw.length > maxLen ? `${raw.slice(0, maxLen)}…` : raw;
}

function _graphSvgDefsEnsure(svgNode) {
  let defs = d3.select(svgNode).select("defs");
  if (defs.empty()) defs = d3.select(svgNode).insert("defs", ":first-child");
  return defs;
}

function _graphBrandInnodeClipIdForNode(nodeId) {
  return `gbic-${String(nodeId).replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}

/** 브랜드 허브 원(r=14) + 원 내부만 보이는 소속 텍스트 */
function _appendBrandHubCircleAndLabel(g, d, opts) {
  opts = opts || {};
  const hubClass = opts.mini
    ? "gn-shape graph-brand-hub-mini graph-node-brand"
    : "gn-shape graph-node-brand graph-brand-hub";
  g.append("circle")
    .attr("class", hubClass)
    .attr("r", 14)
    .attr("fill", "rgba(200,200,210,0.9)")
    .attr("stroke", "rgba(255,255,255,0.2)")
    .attr("stroke-width", 1)
    .attr("filter", null)
    .style("cursor", "pointer");
  const svgNode = g.node().ownerSVGElement;
  let clipUrl = null;
  if (svgNode) {
    const clipId = _graphBrandInnodeClipIdForNode(d.id);
    const existing = typeof document !== "undefined" ? document.getElementById(clipId) : null;
    if (existing) existing.remove();
    const defs = _graphSvgDefsEnsure(svgNode);
    defs.append("clipPath")
      .attr("id", clipId)
      .append("circle")
      .attr("cx", 0)
      .attr("cy", 0)
      .attr("r", 11);
    clipUrl = `url(#${clipId})`;
  }
  const te = g.append("text")
    .attr("class", "graph-brand-label-innode")
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .text(_brandGraphInnodeLabel(d));
  if (clipUrl) te.attr("clip-path", clipUrl);
}

/** 풀 클러스터 SVG defs: 소속(브랜드 허브) 선택·호버 동일 네온 글로우 — 소속 원만 한 단계 밝게 */
function _graphAppendBrandNeonGlowFilter(defsSel) {
  const f = defsSel.append("filter")
    .attr("id", "brand-neon-glow")
    .attr("x", "-50%")
    .attr("y", "-50%")
    .attr("width", "200%")
    .attr("height", "200%");
  f.append("feGaussianBlur")
    .attr("in", "SourceAlpha")
    .attr("stdDeviation", "1.55")
    .attr("result", "blur");
  f.append("feFlood")
    .attr("flood-color", "#b8e8ff")
    .attr("flood-opacity", "0.78")
    .attr("result", "neon");
  f.append("feComposite")
    .attr("in", "neon")
    .attr("in2", "blur")
    .attr("operator", "in")
    .attr("result", "glow1");
  f.append("feGaussianBlur")
    .attr("in", "glow1")
    .attr("stdDeviation", "2")
    .attr("result", "glow2");
  const mg = f.append("feMerge");
  mg.append("feMergeNode").attr("in", "glow2");
  mg.append("feMergeNode").attr("in", "SourceGraphic");
}

/** 풀 클러스터·그리드: 자료/브랜드 원 선택 테두리만 강조(번짐·펄스 링 없음) — 소속은 연한 파랑 네온, 호버=선택과 동일 */
function _graphSyncMainNodeSelectionOutline() {
  if (!_graphG || _graphSimpleMode || _graphMiniConstellationMode || !_fullClusterCtx) return;
  const selId = _graphSelectedNodeId;
  const hovId = _graphHoveredNodeId;
  const focusId = selId != null ? selId : hovId;
  _graphG.selectAll("g.gn").each(function (d) {
    const nt = _nodeTypeOf(d);
    if (nt !== "material" && nt !== "brand") return;
    const shape = d3.select(this).select("circle.gn-shape");
    if (shape.empty()) return;
    const isMatFocus = focusId != null && d.id === focusId;
    const isHubNeon = nt === "brand" && (
      (selId != null && d.id === selId)
      || (hovId != null && d.id === hovId)
    );
    if (nt === "material") {
      if (isMatFocus) {
        shape.attr("stroke", "rgba(255,255,255,0.6)").attr("stroke-width", 1.8).attr("filter", null);
      } else {
        shape.attr("stroke", "rgba(255,255,255,0.12)").attr("stroke-width", 0.5).attr("filter", null);
      }
    } else if (nt === "brand") {
      /* 클릭·호버 동일 네온( isHubNeon ); 자료(material)는 위 분기 유지 */
      if (isHubNeon) {
        shape
          .attr("stroke", "rgba(165, 230, 255, 1)")
          .attr("stroke-width", 2.35)
          .attr("fill", "rgba(215, 245, 255, 0.58)")
          .attr("filter", "url(#brand-neon-glow)");
      } else {
        shape
          .attr("stroke", "rgba(255,255,255,0.2)")
          .attr("stroke-width", 1)
          .attr("fill", "rgba(200,200,210,0.9)")
          .attr("filter", null);
      }
    }
  });
}

function _appendNodeShape(sel) {
  sel.each(function (d) {
    const g = d3.select(this);
    g.selectAll("g.graph-neighbor-badge,g.graph-anchor-pulse").remove();
    g.selectAll("circle,path.gn-shape,rect.gn-shape,text.graph-brand-label,text.graph-brand-label-innode,text.graph-mat-card-text").remove();
    const nt = _nodeTypeOf(d);
    if (nt === "material") {
      g.append("circle")
        .attr("class", "gn-shape graph-mat-node graph-node-material")
        .attr("r", 6)
        .attr("fill", "rgba(200,200,210,0.9)")
        .attr("stroke", "rgba(255,255,255,0.12)")
        .attr("stroke-width", 0.5)
        .attr("filter", null)
        .style("cursor", "pointer");
    } else if (nt === "brand") {
      _appendBrandHubCircleAndLabel(g, d, {});
    } else if (nt === "entity") {
      const s = _nodeRadius(d);
      const isB = _graphKeGrade(d) === "B";
      g.append("path")
        .attr("class", "gn-shape")
        .attr("d", `M0,-${s} L${s},0 L0,${s} L-${s},0 Z`)
        .attr("fill", isB ? "rgba(255, 215, 0, 0.5)" : "#ffd700")
        .attr("stroke", isB ? "none" : "#ff8c00")
        .attr("stroke-width", isB ? 0 : 2)
        .attr("cursor", "pointer");
    } else if (nt === "concept") {
      const s = _nodeRadius(d);
      const isB = _graphKeGrade(d) === "B";
      g.append("path")
        .attr("class", "gn-shape")
        .attr("d", `M0,-${s} L${s},${s * 0.65} L-${s},${s * 0.65} Z`)
        .attr("fill", isB ? "rgba(0, 188, 212, 0.5)" : "#00bcd4")
        .attr("stroke", isB ? "none" : "#0097a7")
        .attr("stroke-width", isB ? 0 : 2)
        .attr("cursor", "pointer");
    }
  });
}

function _buildOrphanStrip(stripNodes, opts) {
  opts = opts || {};
  if (opts.hideStrip) {
    const op = document.getElementById("graphOrphanPanel");
    if (op) {
      op.style.display = "none";
      op.classList.add("is-hidden");
    }
    const osvg = d3.select("#graphOrphanSvg");
    if (osvg.node()) osvg.selectAll("*").remove();
    const title = document.getElementById("graphOrphanTitle");
    if (title) title.textContent = "🔗 연결 대기 중 (0개)";
    return;
  }
  const svg = d3.select("#graphOrphanSvg");
  const op = document.getElementById("graphOrphanPanel");
  const title = document.getElementById("graphOrphanTitle");
  if (title) title.textContent = `🔗 연결 대기 중 (${stripNodes.length}개)`;
  if (!svg.node() || !op) return;
  op.classList.remove("is-hidden");
  svg.selectAll("*").remove();
  if (gf.hideOrphans) {
    op.style.display = "none";
    return;
  }
  op.style.display = stripNodes.length ? "" : "none";
  if (!stripNodes.length) return;
  const ow = op.clientWidth || 800;
  const oh = 56;
  svg.attr("width", ow).attr("height", oh);
  const pad = 24;
  const step = Math.min(48, (ow - 2 * pad) / Math.max(stripNodes.length, 1));
  const g = svg.append("g");
  stripNodes.forEach((d, i) => {
    const x = pad + i * step + step / 2;
    const y = oh / 2;
    const ng = g.append("g").attr("transform", `translate(${x},${y})`).style("cursor", "pointer");
    const nt = _nodeTypeOf(d);
    if (nt === "material") {
      const sc = getBrandColor(d.group || d.brand_label || "미분류");
      const rw = 28;
      const rh = 10;
      ng.append("rect")
        .attr("x", -rw / 2).attr("y", -rh / 2)
        .attr("width", rw).attr("height", rh)
        .attr("rx", 3).attr("ry", 3)
        .attr("fill", _hexToRgba(sc, 0.2))
        .attr("stroke", sc)
        .attr("stroke-width", 0.5);
    } else if (nt === "brand") {
      const cnt = d.brand_count || 1;
      const w = Math.min(24, cnt * 1.4 + 10);
      const h = w * 0.55;
      ng.append("rect")
        .attr("x", -w / 2).attr("y", -h / 2)
        .attr("width", w).attr("height", h)
        .attr("rx", 4).attr("ry", 4)
        .attr("fill", getBrandColor(d.brand_label || d.group || "미분류"))
        .attr("stroke", "rgba(0,0,0,0.25)").attr("stroke-width", 0.5);
    } else if (nt === "entity") {
      const s = Math.min(13, _nodeRadius(d) * 0.38);
      const isB = _graphKeGrade(d) === "B";
      ng.append("path").attr("d", `M0,-${s} L${s},0 L0,${s} L-${s},0 Z`)
        .attr("fill", isB ? "rgba(255, 215, 0, 0.5)" : "#ffd700")
        .attr("stroke", isB ? "none" : "#ff8c00")
        .attr("stroke-width", isB ? 0 : 1.5);
    } else if (nt === "concept") {
      const s = Math.min(12, _nodeRadius(d) * 0.38);
      const isB = _graphKeGrade(d) === "B";
      ng.append("path").attr("d", `M0,-${s} L${s},${s * 0.6} L-${s},${s * 0.6} Z`)
        .attr("fill", isB ? "rgba(0, 188, 212, 0.5)" : "#00bcd4")
        .attr("stroke", isB ? "none" : "#0097a7")
        .attr("stroke-width", isB ? 0 : 1.5);
    }
    ng.append("title").text(d.title);
    ng.on("click", (ev) => _graphNodeClick(ev, d));
    ng.on("mouseover", (ev) => _showGraphHoverTitleTooltip(ev, d));
    ng.on("mouseout", _hideTooltip);
  });
}

function _buildGraphGridView(svg, gridNodes, edges, width, height, materialCount, totalNodes) {
  _graphSimpleMode = false;
  document.getElementById("libraryGraphView")?.classList.remove("graph-view-simple");
  const tbx = document.getElementById("graphToolbar");
  if (tbx) tbx.style.display = "";
  _setGraphSimpleHintOff();
  const g = svg.append("g").attr("class", "graph-g");
  _graphG = g;
  _graphSim = null;

  const hintText =
    `자료 ${materialCount}개 표시 중 · 자료가 쌓이면 연결이 자동 생성됩니다`;
  g.append("text")
    .attr("class", "graph-grid-hint")
    .attr("x", width / 2)
    .attr("y", 28)
    .attr("text-anchor", "middle")
    .attr("fill", "#aab")
    .attr("font-size", 13)
    .text(totalNodes > 0 ? hintText : "");

  const defs = svg.append("defs");
  defs.append("filter").attr("id", "glow").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%")
    .append("feGaussianBlur").attr("stdDeviation", "4").attr("result", "glow");
  _graphAppendBrandNeonGlowFilter(defs);

  const cell = 80;
  const cols = Math.max(1, Math.floor((width - 48) / cell));
  const hintH = 44;
  gridNodes.forEach((d, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    d.fx = 24 + col * cell + cell / 2;
    d.fy = hintH + 24 + row * cell + cell / 2;
    d.x = d.fx;
    d.y = d.fy;
  });

  const zoom = d3.zoom().scaleExtent([0.12, 6])
    .on("zoom", (event) => {
      _graphZoomK = event.transform.k;
      g.attr("transform", event.transform);
    });
  svg.call(zoom);
  _graphZoomBehavior = zoom;

  const linkG = g.append("g").attr("class", "link-layer");
  const linkWrap = linkG.selectAll("g.graph-edge").data([]).join("g");
  const nodeG = g.append("g").attr("class", "node-layer");
  const labelG = g.append("g").attr("class", "label-layer");

  const nodeSel = nodeG.selectAll("g").data(gridNodes, d => d.id).join("g").attr("class", "gn")
    .attr("transform", d => `translate(${d.fx},${d.fy})`)
    .call(d3.drag()
      .on("drag", function (ev, d) {
        d.fx += ev.dx;
        d.fy += ev.dy;
        d3.select(this).attr("transform", `translate(${d.fx},${d.fy})`);
      }));

  const lcGrid = _computeLinkCountMap(gridNodes, edges);
  gridNodes.forEach((n) => {
    if (_nodeTypeOf(n) === "material") {
      const lc = lcGrid.get(n.id) || 0;
      n._graphR = Math.max(3, 2 + Math.sqrt(lc) * 2);
    }
  });

  _appendNodeShape(nodeSel);

  const labelSel = labelG.selectAll("text.gl-text").data([]).join("text");

  nodeSel.on("click", _graphNodeClick);
  nodeSel.on("mouseover", (ev, d) => {
    if (_nodeTypeOf(d) === "material") {
      const matR = 6;
      d3.select(ev.currentTarget).select("circle.graph-mat-node")
        .attr("r", matR * 1.12)
        .attr("fill", "rgba(200,200,210,0.9)");
    }
    _hoverNode(d, nodeSel, linkWrap, labelSel, true);
    _showGraphHoverTitleTooltip(ev, d);
  });
  nodeSel.on("mouseout", (ev, d) => {
    if (_nodeTypeOf(d) === "material") {
      const matR = 6;
      d3.select(ev.currentTarget).select("circle.graph-mat-node")
        .attr("r", matR)
        .attr("fill", "rgba(200,200,210,0.9)");
    }
    _hoverNode(d, nodeSel, linkWrap, labelSel, false);
    _hideTooltip();
  });

  svg.on("click", () => {
    _clearGraphNeighborBadgeState();
    _graphSelectedNodeId = null;
    _hoverNode(null, nodeSel, linkWrap, labelSel, false);
  });

  if (gf.search) setTimeout(_highlightSearch, 300);
  _syncGraphNeighborViz();
  _updateGraphLabelVisibility();
}

function _setGraphSimpleHint(materialTotal) {
  const wrap = document.getElementById("graphCanvasWrap");
  if (!wrap) return;
  let el = document.getElementById("graphSimpleHint");
  if (!el) {
    el = document.createElement("div");
    el.id = "graphSimpleHint";
    el.className = "graph-simple-hint";
    wrap.appendChild(el);
  }
  if (materialTotal >= 30) {
    el.style.display = "none";
    el.textContent = "";
    return;
  }
  el.style.display = "block";
  if (materialTotal < 15) {
    el.textContent = "자료를 더 모으면 연결이 보이기 시작합니다 📚";
  } else {
    el.textContent = "거의 다 왔습니다! 30건부터 주제 연결이 활성화됩니다 🔗";
  }
}

function _setGraphSimpleHintOff() {
  const el = document.getElementById("graphSimpleHint");
  if (el) {
    el.style.display = "none";
    el.textContent = "";
  }
}

function _latestThreeTitlesForBrandMaterials(mats) {
  const sorted = [...mats].sort((a, b) =>
    String(b.ingested_date || "").localeCompare(String(a.ingested_date || ""))
  );
  return sorted.slice(0, 3).map((m) => (m.title || "").trim()).filter(Boolean);
}

function _showBrandBubbleTooltip(ev, titles) {
  const tip = document.getElementById("graphTooltip");
  if (!tip) return;
  if (_graphTooltipHideTimer) {
    clearTimeout(_graphTooltipHideTimer);
    _graphTooltipHideTimer = null;
  }
  tip.classList.remove("graph-tooltip-minimal");
  const lines = titles.length
    ? titles.map((t) => `<div class="gtt-line">${escapeHtml(t.length > 48 ? `${t.slice(0, 48)}…` : t)}</div>`).join("")
    : '<div class="gtt-line">자료 제목 없음</div>';
  tip.innerHTML = `<div class="gtt-title">최신 자료</div>${lines}`;
  tip.style.display = "block";
  const rect = tip.parentElement.getBoundingClientRect();
  const mx = ev.clientX - rect.left + 12;
  const my = ev.clientY - rect.top - 10;
  tip.style.left = `${Math.min(mx, rect.width - 280)}px`;
  tip.style.top = `${Math.max(my, 0)}px`;
}

/** 왼쪽 통계 패널 너비를 반영한 forceCenter (SVG 로컬 좌표). */
function _graphForceCenterXY(svgWidth, svgHeight) {
  const panelW = document.querySelector(".graph-stats-panel")?.offsetWidth || 0;
  const cx = panelW + (svgWidth - panelW) / 2;
  const cy = svgHeight / 2;
  return { cx, cy };
}

/** 자료 30건 미만: mini_constellation — material·brand force, 소속/shared_topic, 다크 배경·글로우·호버 */
function _buildGraphMiniConstellation(svg, fdNodes, edges, width, height, libMaterialTotal) {
  _graphSimpleMode = true;
  _graphMiniConstellationMode = true;
  _graphSim = null;
  document.getElementById("libraryGraphView")?.classList.add("graph-view-simple");
  const tb = document.getElementById("graphToolbar");
  if (tb) tb.style.display = "";

  const simNodesAll = fdNodes
    .filter((n) => {
      const nt = _nodeTypeOf(n);
      return nt === "material" || nt === "brand";
    })
    .map((n) => Object.assign({}, n));

  const idSet = new Set(simNodesAll.map((n) => n.id));

  const miniEdges = edges.filter((e) => {
    if (!idSet.has(e.source_id) || !idSet.has(e.target_id)) return false;
    if (e.relation_type !== "소속" && e.relation_type !== "shared_topic") return false;
    return gf.edgeTypes.has(e.relation_type);
  });

  simNodesAll.forEach((n) => {
    const nt0 = _nodeTypeOf(n);
    if (nt0 === "material") {
      n._miniR = _miniMaterialNodeRadius(n, miniEdges);
      n._sharedTopicCount = _miniSharedTopicCountMaterial(n.id, miniEdges);
      n._isMiniOrphan = n._sharedTopicCount === 0;
      const ing = _miniIngestedStrokeAttrs(n);
      n._ingestStroke = ing ? ing.stroke : null;
      n._ingestStrokeW = ing ? ing.width : 0;
    } else if (nt0 === "brand") {
      n._brandR = _miniBrandNodeRadius(n.id, miniEdges);
    }
  });

  const { cx: cx0, cy: cy0 } = _graphForceCenterXY(width, height);
  simNodesAll.forEach((n) => {
    n.x = cx0 + (Math.random() - 0.5) * 200;
    n.y = cy0 + (Math.random() - 0.5) * 200;
    n.fx = null;
    n.fy = null;
  });

  const linkData = miniEdges.map((e, idx) => ({
    source: e.source_id,
    target: e.target_id,
    relation_type: e.relation_type,
    edge_label: e.edge_label,
    shared_tags: e.shared_tags,
    weight: e.weight,
    _linkKey: `mini-${e.source_id}-${e.target_id}-${e.relation_type}-${idx}`,
  }));
  const links = linkData.map((d) => ({ ...d }));

  const g = svg.append("g").attr("class", "graph-g graph-mini-constellation");
  _graphG = g;

  const defs = svg.append("defs");
  const miniFilt = defs.append("filter")
    .attr("id", "brandGlowMini")
    .attr("x", "-80%")
    .attr("y", "-80%")
    .attr("width", "260%")
    .attr("height", "260%");
  miniFilt.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", 3).attr("result", "blur");
  const miniMerge = miniFilt.append("feMerge");
  miniMerge.append("feMergeNode").attr("in", "blur");
  miniMerge.append("feMergeNode").attr("in", "SourceGraphic");

  const zoom = d3.zoom()
    .scaleExtent([0.35, 4])
    .on("zoom", (event) => {
      g.attr("transform", event.transform);
      _graphZoomK = event.transform.k;
    });
  svg.call(zoom);
  _graphZoomBehavior = zoom;

  const linkG = g.append("g").attr("class", "link-layer");
  const nodeG = g.append("g").attr("class", "node-layer");
  const labelG = g.append("g").attr("class", "label-layer");

  let sim = d3.forceSimulation(simNodesAll)
    .alpha(1)
    .alphaDecay(0.015)
    .velocityDecay(0.35)
    .force("charge", d3.forceManyBody().strength(-100))
    .force("center", d3.forceCenter(cx0, cy0).strength(0.3))
    .force("collide", d3.forceCollide()
      .radius((dd) => {
        const nt = _nodeTypeOf(dd);
        if (nt === "material") return (dd._miniR || 6) + 4;
        if (nt === "brand") return (dd._brandR || 8) + 2;
        return 20;
      })
      .strength(0.85)
      .iterations(2));
  if (links.length) {
    sim = sim.force("link", d3.forceLink(links)
      .id((dd) => dd.id)
      .distance((lnk) => (lnk.relation_type === "소속" ? 50 : 150))
      .strength((lnk) => (lnk.relation_type === "소속" ? 0.7 : 0.1))
      .iterations(2));
  }
  _graphSim = sim;

  const linkWrap = linkG.selectAll("g.graph-edge-mini").data(links, (d) => d._linkKey).join("g")
    .attr("class", (d) => `graph-edge-mini ge-mini-${d.relation_type === "소속" ? "belongs" : "shared"}`)
    .each(function (d) {
      const el = d3.select(this);
      el.selectAll("*").remove();
      const rt = d.relation_type;
      const isBel = rt === "소속";
      const pMini = isBel ? null : _graphRelationEdgePaint(rt);
      el.append("path")
        .attr("class", `graph-mini-link graph-edge-line ${isBel ? "graph-link-belongs" : "graph-link-shared"}`)
        .attr("fill", "none")
        .attr("stroke", isBel ? "#78909C" : pMini.stroke)
        .attr("stroke-width", isBel ? 1 : Math.max(0.6, pMini.width * 0.9))
        .attr("stroke-dasharray", !isBel && pMini.dash ? pMini.dash : null)
        .attr("stroke-opacity", isBel ? 0.12 : pMini.opacity);
    });

  linkWrap
    .filter((d) => d.relation_type === "shared_topic")
    .style("cursor", "crosshair")
    .on("mouseenter", (ev, d) => _showSharedTopicEdgeTooltip(ev, d))
    .on("mouseleave", () => { _hideSharedTopicHoverTooltip(); _hideTooltip(); });

  const materialNodes = simNodesAll.filter((n) => _nodeTypeOf(n) === "material");
  const labelMat = labelG.selectAll("text.gl-text-mini-material").data(materialNodes, (d) => d.id).join("text")
    .attr("class", "gl-text gl-text-material gl-text-mini-material")
    .attr("font-size", 10)
    .attr("text-anchor", "middle")
    .attr("dy", (d) => (d._miniR || 6) + 10)
    .attr("fill", "#c9d1d9")
    .text((d) => _materialGraphLabelText(d));

  labelG.selectAll("text.gl-text-mini-brand").remove();

  const nodeSel = nodeG.selectAll("g.gn").data(simNodesAll, (d) => d.id).join("g")
    .attr("class", (d) => {
      const base = "gn";
      if (_nodeTypeOf(d) === "material" && d._isMiniOrphan) return `${base} graph-node-orphan`;
      return base;
    })
    .attr("opacity", (d) => (_nodeTypeOf(d) === "material" && d._isMiniOrphan ? 0.5 : 1))
    .call(d3.drag()
      .filter((event, d) => {
        const nt = _nodeTypeOf(d);
        return nt !== "brand";
      })
      .on("start", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0.2).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (ev, d) => {
        d.fx = ev.x;
        d.fy = ev.y;
      })
      .on("end", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0.1);
        d.fx = null;
        d.fy = null;
      }));

  nodeSel.each(function (d) {
    const gg = d3.select(this);
    gg.selectAll("g.graph-neighbor-badge,g.graph-anchor-pulse").remove();
    gg.selectAll("circle, text.graph-brand-mini, text.graph-brand-label-innode").remove();
    const nt = _nodeTypeOf(d);
    if (nt === "material") {
      gg.append("circle")
        .attr("class", "gn-shape graph-mat-node graph-node-material")
        .attr("r", 6)
        .attr("fill", "rgba(200,200,210,0.9)")
        .attr("stroke", "rgba(255,255,255,0.12)")
        .attr("stroke-width", 0.5)
        .attr("filter", null)
        .attr("cursor", "pointer");
    } else if (nt === "brand") {
      _appendBrandHubCircleAndLabel(gg, d, { mini: true });
    }
  });

  sim.on("tick", () => {
    linkWrap.each(function (lnk) {
      const pathD = _miniSharedPath(lnk);
      d3.select(this).select("path.graph-mini-link").attr("d", pathD);
    });
    nodeSel.attr("transform", (dd) => `translate(${dd.x},${dd.y})`);
    labelMat.attr("x", (dd) => dd.x).attr("y", (dd) => dd.y);
    if (!_graphHoveredNodeId) _graphApplyNeighborBadgeEdgesMini();
  });

  nodeSel.on("click", _graphNodeClick);
  nodeSel.on("mouseover", (ev, d) => {
    _hoverMiniConstellation(d, nodeSel, linkWrap, labelMat, true);
    _showGraphHoverTitleTooltip(ev, d);
  });
  nodeSel.on("mouseout", (ev, d) => {
    _hoverMiniConstellation(d, nodeSel, linkWrap, labelMat, false);
    _hideTooltip();
  });

  svg.on("click", () => {
    _clearGraphNeighborBadgeState();
    _graphSelectedNodeId = null;
    _hoverMiniConstellation(null, nodeSel, linkWrap, labelMat, false);
  });

  if (gf.search) setTimeout(_highlightSearch, 300);
  _syncGraphNeighborViz();
  _updateGraphLabelVisibility();
  _setGraphSimpleHint(libMaterialTotal);
}

function _buildGraph() {
  _finalizeGraphNeighborVizClear();
  const fd = _getFilteredData();
  _lastGraphFiltered = fd;
  const { nodes, edges } = fd;
  /** graphSvg에 올리는 노드만 (자료·브랜드). 엔티티/개념은 API·패널용 nodes와 분리 */
  const nodesGraphSvg = nodes.filter((n) => {
    const nt = _nodeTypeOf(n);
    return nt === "material" || nt === "brand";
  });
  const libMaterialTotal =
    _graphRaw && _graphRaw.stats && typeof _graphRaw.stats.material_count === "number"
      ? _graphRaw.stats.material_count
      : (typeof libState.totalMaterials === "number" ? libState.totalMaterials : 0);
  const viewMode = libMaterialTotal < 30 ? "mini_constellation" : "full_cluster";
  const nodesLayout = nodesGraphSvg;
  const nodeIdsLayout = new Set(nodesLayout.map((n) => n.id));
  const degEdgesLayout = edges.filter((e) =>
    nodeIdsLayout.has(e.source_id) && nodeIdsLayout.has(e.target_id) && gf.edgeTypes.has(e.relation_type)
  );
  const deg = new Map();
  nodesLayout.forEach((n) => deg.set(n.id, 0));
  degEdgesLayout.forEach((e) => {
    deg.set(e.source_id, (deg.get(e.source_id) || 0) + 1);
    deg.set(e.target_id, (deg.get(e.target_id) || 0) + 1);
  });
  const orphanSet = new Set(nodesLayout.filter((n) => (deg.get(n.id) || 0) === 0).map((n) => n.id));
  const mainNodes = nodesLayout.filter((n) => !orphanSet.has(n.id));
  const stripNodes = nodesLayout.filter((n) => orphanSet.has(n.id));
  const orphanCount = orphanSet.size;

  if (nodesGraphSvg.length === 0) {
    _graphBrandColorMap = {};
    _updateGraphBrandLegend([], edges);
  } else {
    const brandListSortedEarly = [...new Set(nodesGraphSvg.map((n) => n.group || n.brand_label || "미분류"))].sort();
    _graphBrandColorMap = {};
    brandListSortedEarly.forEach((b, i) => {
      _graphBrandColorMap[b] = BRAND_COLORS[i % BRAND_COLORS.length];
    });
    _updateGraphBrandLegend(brandListSortedEarly, edges);
  }

  _renderGraphStatsBarFiltered(nodesGraphSvg, edges, orphanCount);
  const useGridOnly = mainNodes.length === 0 && stripNodes.length > 0;
  if (viewMode === "mini_constellation") {
    _buildOrphanStrip([], { hideStrip: true });
  } else {
    _buildOrphanStrip(useGridOnly ? [] : stripNodes, { hideStrip: useGridOnly });
  }

  const svgEl = document.getElementById("graphSvg");
  if (!svgEl) return;

  const svg = d3.select("#graphSvg");
  svg.selectAll("*").remove();
  if (_graphSim) { _graphSim.stop(); _graphSim = null; }
  _graphZoomK = 1;
  _graphSelectedNodeId = null;
  _graphProgressiveMaterialId = null;
  _fullClusterCtx = null;
  _graphSimpleMode = false;
  _graphMiniConstellationMode = false;
  document.getElementById("libraryGraphView")?.classList.remove("graph-view-simple");
  const _gtb = document.getElementById("graphToolbar");
  if (_gtb) _gtb.style.display = "";

  const wrap = svgEl.parentElement;
  const width = wrap.clientWidth || 900;
  let height = wrap.clientHeight || 600;
  if (height < 320) height = 600;

  svg.attr("width", width).attr("height", height).attr("viewBox", `0 0 ${width} ${height}`);
  _graphSvgSel = svg;

  if (nodesGraphSvg.length === 0) {
    _setGraphSimpleHintOff();
    svg.append("text").attr("x", width / 2).attr("y", height / 2)
      .attr("text-anchor", "middle").attr("fill", "#889").attr("font-size", 15)
      .text("표시할 노드가 없습니다. 필터를 조정하세요.");
    return;
  }

  const matCount = nodesGraphSvg.filter((n) => _nodeTypeOf(n) === "material").length;

  if (viewMode === "mini_constellation") {
    if (matCount === 0) {
      svg.append("text").attr("x", width / 2).attr("y", height / 2)
        .attr("text-anchor", "middle").attr("fill", "#889").attr("font-size", 15)
        .text("표시할 자료가 없습니다. 필터를 조정하세요.");
      _setGraphSimpleHint(libMaterialTotal);
      return;
    }
    _buildGraphMiniConstellation(svg, nodesGraphSvg, edges, width, height, libMaterialTotal);
    return;
  }

  _setGraphSimpleHintOff();

  if (useGridOnly) {
    const gridNodes = stripNodes.map((n) => Object.assign({}, n));
    _buildGraphGridView(svg, gridNodes, edges, width, height, matCount, nodesGraphSvg.length);
    return;
  }

  const simNodes = mainNodes.map((n) => Object.assign({}, n));
  const { cx: cx0, cy: cy0 } = _graphForceCenterXY(width, height);
  simNodes.forEach((n) => {
    n.x = cx0 + (Math.random() - 0.5) * 200;
    n.y = cy0 + (Math.random() - 0.5) * 200;
    n.fx = null;
    n.fy = null;
  });

  const simEdgeList = edges.filter((e) => {
    if (!simNodes.some((n) => n.id === e.source_id) || !simNodes.some((n) => n.id === e.target_id)) return false;
    if (e.relation_type === "소속") return true;
    if (e.relation_type === "shared_topic") {
      const a = nodesGraphSvg.find((n) => n.id === e.source_id);
      const b = nodesGraphSvg.find((n) => n.id === e.target_id);
      return a && b && (a.group || "미분류") !== (b.group || "미분류");
    }
    return true;
  });

  const linkData = simEdgeList.map((e, idx) => ({
    source: e.source_id,
    target: e.target_id,
    relation_type: e.relation_type,
    edge_label: e.edge_label,
    shared_tags: e.shared_tags,
    weight: e.weight,
    _linkKey: `${e.source_id}-${e.target_id}-${e.relation_type}-${idx}`,
  }));
  const links = linkData.map((d) => ({ ...d }));

  const lcMapFull = _linkCountMapForLayoutNodes(simNodes, nodesGraphSvg, edges);
  simNodes.forEach((n) => {
    const lc = lcMapFull.get(n.id) || 0;
    const nt = _nodeTypeOf(n);
    if (nt === "material") n._graphR = Math.max(3, 2 + Math.sqrt(lc) * 2);
    else if (nt === "brand") n._graphR = Math.max(8, 4 + Math.sqrt(lc) * 3) * 1.3;
  });

  const g = svg.append("g").attr("class", "graph-g");
  _graphG = g;

  const defs = svg.append("defs");
  defs.append("filter").attr("id", "glow").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%")
    .append("feGaussianBlur").attr("stdDeviation", "4").attr("result", "glow");
  _graphAppendBrandNeonGlowFilter(defs);

  const zoom = d3.zoom().scaleExtent([0.12, 6])
    .on("zoom", (event) => {
      _graphZoomK = event.transform.k;
      g.attr("transform", event.transform);
    });
  svg.call(zoom);
  _graphZoomBehavior = zoom;

  const linkG = g.append("g").attr("class", "link-layer");
  const nodeG = g.append("g").attr("class", "node-layer");
  const labelG = g.append("g").attr("class", "label-layer");

  const linkDistanceFn = (lnk) => {
    const rt = lnk.relation_type;
    if (rt === "소속") return 50;
    if (rt === "shared_topic") return 150;
    return 150;
  };
  const linkStrengthFn = (lnk) => {
    const rt = lnk.relation_type;
    if (rt === "소속") return 0.7;
    if (rt === "shared_topic") return 0.1;
    return 0.1;
  };

  let sim = d3.forceSimulation(simNodes)
    .alpha(1)
    .alphaDecay(0.035)
    .alphaMin(0.005)
    .velocityDecay(0.45)
    .force("center", d3.forceCenter(cx0, cy0).strength(0.25))
    .force("collide", d3.forceCollide()
      .radius((d) => {
        const nt = _nodeTypeOf(d);
        const baseR = (d._graphR != null ? d._graphR : (nt === "material" ? 12 : 18));
        const extra = (+document.getElementById("inputCollide")?.value || 20) / 2;
        return baseR + extra;
      })
      .strength(0.7)
      .iterations(2));

  if (links.length) {
    const defaultDist = +document.getElementById("inputDistance")?.value || 70;
    sim = sim.force("link", d3.forceLink(links)
      .id((d) => d.id)
      .distance((lnk) => {
          const rt = lnk.relation_type;
          if (rt === "소속") return 40;
          return defaultDist;
      })
      .strength(linkStrengthFn)
      .iterations(1));
  }
  const defaultCharge = +document.getElementById("inputCharge")?.value || -120;
  sim = sim.force("charge", d3.forceManyBody()
    .strength(defaultCharge)
    .distanceMax(400)
    .theta(0.9));
  _graphSim = sim;

  const labelNodes = simNodes.filter((n) => _nodeTypeOf(n) === "material");
  labelG.selectAll("text.gl-text-node").data(labelNodes, (d) => d.id).join("text")
    .attr("class", "gl-text gl-text-node gl-text-material")
    .attr("font-size", 11)
    .attr("text-anchor", "middle")
    .attr("dy", (d) => {
      const base = d._graphR != null ? d._graphR : 12;
      return base + 10;
    })
    .attr("fill", "#cccccc")
    .each((d) => {
      if (d._graphLabelFull == null) d._graphLabelFull = d.title || "";
    })
    .text((d) => _materialGraphLabelText(d));

  const linkWrap = linkG.selectAll("g.graph-edge").data(links, (d) => d._linkKey).join("g")
    .attr("class", (d) => `graph-edge ge-${d.relation_type}`);
  linkWrap.each(function (d) {
    const el = d3.select(this);
    el.selectAll("*").remove();
    const rt = d.relation_type;
    const line = el.append("line").attr("class", "graph-edge-line");
    if (rt === "소속") {
      line.attr("stroke", "rgba(255,255,255,0.08)")
        .attr("stroke-width", 0.5)
        .attr("stroke-opacity", 1)
        .attr("stroke-dasharray", null);
    } else {
      const p = _graphRelationEdgePaint(rt);
      line.attr("stroke", p.stroke)
        .attr("stroke-width", Math.max(0.45, p.width * 0.55))
        .attr("stroke-opacity", p.opacity * 0.4)
        .attr("stroke-dasharray", p.dash || null);
    }
    if ((rt === "shared_topic" || rt === "shared_entity" || rt === "shared_concept") && d.edge_label) {
      el.append("text")
        .attr("class", "graph-edge-tag-label")
        .attr("font-size", 8)
        .attr("fill", _edgeTagLabelFill(rt))
        .attr("text-anchor", "middle")
        .style("pointer-events", "none")
        .style("display", _graphEdgeTagVisible(d) ? null : "none")
        .attr("opacity", 0)
        .text(d.edge_label);
    }
  });

  linkWrap
    .filter((d) => d.relation_type === "shared_topic")
    .style("cursor", "crosshair")
    .on("mouseenter", (ev, d) => _showSharedTopicEdgeTooltip(ev, d))
    .on("mouseleave", () => { _hideSharedTopicHoverTooltip(); _hideTooltip(); });

  const nodeSel = nodeG.selectAll("g").data(simNodes, (d) => d.id).join("g").attr("class", "gn")
    .call(d3.drag()
      .filter(function (event, d) {
        const nt = _nodeTypeOf(d);
        return nt !== "brand";
      })
      .on("start", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0.25).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (ev, d) => {
        d.fx = ev.x;
        d.fy = ev.y;
      })
      .on("end", (ev, d) => {
        if (!ev.active) sim.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      }));

  _appendNodeShape(nodeSel);

  const baseNodeCount = simNodes.length;
  const baseSimEdgeListSnapshot = simEdgeList.slice();

  _fullClusterCtx = {
    sim,
    baseNodeCount,
    baseSimEdgeList: baseSimEdgeListSnapshot,
    fdNodes: nodesGraphSvg,
    fdEdges: edges,
    cx0,
    cy0,
    nodeG,
    linkG,
    labelG,
    svg,
    g,
    allNodesForSharedTopic: nodesGraphSvg,
  };

  function _fcHoverSelection() {
    const c = _fullClusterCtx;
    if (!c) return [null, null, null];
    return [
      c.nodeG.selectAll("g.gn"),
      c.linkG.selectAll("g.graph-edge"),
      c.labelG.selectAll("text.gl-text-node"),
    ];
  }

  nodeSel.on("click", _graphNodeClick);
  nodeSel.on("mouseover", (ev, d) => {
    if (_nodeTypeOf(d) === "material") {
      const matR = 6;
      d3.select(ev.currentTarget).select("circle.graph-mat-node")
        .attr("r", matR * 1.12)
        .attr("fill", "rgba(200,200,210,0.9)");
    }
    const [ns, lw, ls] = _fcHoverSelection();
    if (ns) _hoverNode(d, ns, lw, ls, true);
    _showGraphHoverTitleTooltip(ev, d);
  });
  nodeSel.on("mouseout", (ev, d) => {
    if (_nodeTypeOf(d) === "material") {
      const matR = 6;
      d3.select(ev.currentTarget).select("circle.graph-mat-node")
        .attr("r", matR)
        .attr("fill", "rgba(200,200,210,0.9)");
    }
    const [ns, lw, ls] = _fcHoverSelection();
    if (ns) _hoverNode(d, ns, lw, ls, false);
    _hideTooltip();
  });

  let _simTickN = 0;
  sim.on("tick", () => {
    _simTickN++;
    const settling = sim.alpha() > 0.05;
    if (settling && _simTickN % 3 !== 0) return;
    const c = _fullClusterCtx;
    if (!c || c.sim !== sim) return;
    c.linkG.selectAll("g.graph-edge").each(function (d) {
      const sx = d.source.x;
      const sy = d.source.y;
      const tx = d.target.x;
      const ty = d.target.y;
      d3.select(this).select("line.graph-edge-line")
        .attr("x1", sx).attr("y1", sy).attr("x2", tx).attr("y2", ty);
      const mid = d3.select(this).select("text.graph-edge-tag-label");
      if (!mid.empty()) {
        const S = _graphHoveredNodeId != null ? _graphHoveredNodeId : _graphSelectedNodeId;
        const sId = typeof d.source === "object" ? d.source.id : d.source;
        const isSourceFocused = (sId === S);
        const t = 0.7;
        const px = isSourceFocused ? sx + (tx - sx) * t : tx + (sx - tx) * t;
        const py = isSourceFocused ? sy + (ty - sy) * t : ty + (sy - ty) * t;
        let angle = Math.atan2(ty - sy, tx - sx) * (180 / Math.PI);
        if (angle > 90) angle -= 180;
        if (angle < -90) angle += 180;
        mid.attr("x", px).attr("y", py)
          .attr("transform", `rotate(${angle},${px},${py})`)
          .attr("dy", "-0.4em")
          .style("display", _graphEdgeTagVisible(d) ? null : "none");
      }
    });
    c.nodeG.selectAll("g.gn").attr("transform", (d) => `translate(${d.x},${d.y})`);
    c.labelG.selectAll("text.gl-text-node").attr("x", (d) => d.x).attr("y", (d) => d.y);
    if (!_graphHoveredNodeId) {
      _graphApplyNeighborBadgeEdges();
      _graphApplySelectionToggleEdgeDim();
    }
  });

  svg.on("click", () => {
    _clearGraphNeighborBadgeState();
    _graphSelectedNodeId = null;
    _graphProgressiveMaterialId = null;
    _fullClusterSyncProgressive(null);
    const [ns, lw, ls] = _fcHoverSelection();
    if (ns) _hoverNode(null, ns, lw, ls, false);
  });

  if (gf.search) setTimeout(_highlightSearch, 300);
  _syncGraphNeighborViz();
  _updateGraphLabelVisibility();
}

function _updateGraphLabelVisibility() {
  if (!_graphG) return;
  if (_graphSimpleMode && !_graphMiniConstellationMode) return;
  if (gf.search && gf.search.length >= 2) {
    _highlightSearch();
    return;
  }
  if (_graphMiniConstellationMode) {
    _graphG.selectAll(".gl-text-mini-material").each(function (d) {
      const el = d3.select(this);
      const vis = _graphMaterialLabelVisible(d.id);
      if (!vis) {
        el.style("display", "none");
      } else {
        el.style("display", null);
        el.style("opacity", 1);
      }
    });
    _graphG.selectAll(".graph-brand-label-innode").each(function () {
      d3.select(this).style("display", null).style("opacity", 1);
    });
    return;
  }
  const shownEdgeLabels = new Set();
  _graphG.selectAll("text.graph-edge-tag-label").each(function () {
    const el = d3.select(this);
    const lnk = d3.select(this.parentNode).datum();
    const shouldShow = lnk && _graphEdgeTagVisible(lnk);
    const labelText = lnk ? (lnk.edge_label || "") : "";
    if (!shouldShow) {
      el.style("display", "none");
      return;
    }
    if (!shownEdgeLabels.has(labelText)) {
      shownEdgeLabels.add(labelText);
      el.style("display", null).style("opacity", 1);
    } else {
      el.style("display", null).style("opacity", 0);
    }
  });
  _graphG.selectAll(".gl-text.gl-text-node").each(function (d) {
    const el = d3.select(this);
    const vis = _graphMaterialTextVisible(d.id);
    if (!vis) {
      el.style("display", "none");
    } else {
      el.style("display", null);
      el.style("opacity", 1);
    }
  });

  _graphG.selectAll(".graph-brand-label-innode").each(function () {
    d3.select(this).style("display", null).style("opacity", 1);
  });
  if (_fullClusterCtx && !_graphSimpleMode && !_graphMiniConstellationMode) {
    _graphSyncMainNodeSelectionOutline();
  }
}

function _hoverNode(d, nodeSel, linkWrap, labelSel, active) {
  _graphHoveredNodeId = (active && d) ? d.id : null;
  if (!active || !d) {
    nodeSel.selectAll(".gn-shape").attr("opacity", 1);
    nodeSel.selectAll(".graph-brand-label,.graph-mat-card-text,.graph-brand-label-innode").attr("opacity", 1);
    linkWrap.selectAll("text.graph-edge-tag-label").attr("opacity", 1);
    _graphApplyNeighborBadgeEdges();
    _graphApplySelectionToggleEdgeDim();
    _updateGraphLabelVisibility();
    return;
  }
  const neighbors = new Set([d.id]);
  linkWrap.each(function () {
    const lnk = d3.select(this).datum();
    const sid = typeof lnk.source === "object" ? lnk.source.id : lnk.source;
    const tid = typeof lnk.target === "object" ? lnk.target.id : lnk.target;
    if (sid === d.id) neighbors.add(tid);
    if (tid === d.id) neighbors.add(sid);
  });
  nodeSel.selectAll(".gn-shape").attr("opacity", (n) => (neighbors.has(n.id) ? 1 : 0.15));
  nodeSel.selectAll(".graph-brand-label,.graph-mat-card-text").attr("opacity", (n) => (neighbors.has(n.id) ? 1 : 0.12));
  nodeSel.selectAll(".graph-brand-label-innode").attr("opacity", 1);
  const hoverNodeId = d.id;
  const ntHover = _nodeTypeOf(d);
  if (_graphSelectedNodeId != null && hoverNodeId !== _graphSelectedNodeId) {
    /* 소속(브랜드) 호버: 다른 노드가 선택돼 있어도 클릭한 때와 동일한 엣지 강조 */
    if (ntHover === "brand" && _fullClusterCtx && _fullClusterCtx.linkG) {
      _graphSyncFullClusterEdgesBaselineCore(d.id);
    }
    _updateGraphLabelVisibility();
    return;
  }
  /* 노드 미선택: 호버 중이면 클릭 선택과 동일한 엣지·태그·테두리 강조 */
  if (_graphSelectedNodeId === null) {
    if (_fullClusterCtx && _fullClusterCtx.linkG) {
      _graphSyncFullClusterEdgesBaselineCore(d.id);
    }
    _updateGraphLabelVisibility();
    return;
  }
  /* 소속 선택·호버: 자료 호버 시의 수동 링크 페인트 대신 클릭과 동일한 베이스라인 */
  if (ntHover === "brand" && _fullClusterCtx && _fullClusterCtx.linkG) {
    _graphSyncFullClusterEdgesBaselineCore(d.id);
    _updateGraphLabelVisibility();
    return;
  }
  linkWrap.each(function (lnk) {
    const gg = d3.select(this);
    const sid = typeof lnk.source === "object" ? lnk.source.id : lnk.source;
    const tid = typeof lnk.target === "object" ? lnk.target.id : lnk.target;
    const hit = sid === d.id || tid === d.id;
    const line = gg.select(".graph-edge-line");
    if (line.empty()) return;
    const rt = lnk.relation_type;
    if (hit) {
      gg.style("display", null);
      const wBoost = 1.2;
      const p = _graphRelationEdgePaint(rt);
      line.attr("stroke", p.stroke)
        .attr("stroke-opacity", 0.7)
        .attr("stroke-width", Math.max(0.8, p.width * wBoost))
        .attr("stroke-dasharray", p.dash || null);
    } else {
      gg.style("display", null);
      line.attr("stroke", "rgba(255,255,255,0.08)")
        .attr("stroke-width", 0.5)
        .attr("stroke-opacity", 1)
        .attr("stroke-dasharray", null);
    }
    gg.select("text.graph-edge-tag-label").attr("opacity", hit ? 1 : 0.05);
  });
  _updateGraphLabelVisibility();
}

function _graphHoverTooltipTitle(d) {
  const nt = _nodeTypeOf(d);
  if (nt === "material") return (d.title || "").trim() || "자료";
  if (nt === "brand") {
    return (d.brand_label || d.title || "").replace(/\s*\(\d+건\)\s*$/, "").trim() || "출처";
  }
  if (nt === "entity" || nt === "concept") return (d.title || "").trim() || "";
  return "";
}

function _showGraphHoverTitleTooltip(ev, d) {
  const tip = document.getElementById("graphTooltip");
  if (!tip) return;
  if (_graphTooltipHideTimer) {
    clearTimeout(_graphTooltipHideTimer);
    _graphTooltipHideTimer = null;
  }
  const title = _graphHoverTooltipTitle(d);
  tip.classList.add("graph-tooltip-minimal");
  tip.innerHTML = `<div class="gtt-mini-title">${escapeHtml(title)}</div>`;
  tip.style.display = "block";
  const rect = tip.parentElement.getBoundingClientRect();
  const mx = ev.clientX - rect.left + 12;
  const my = ev.clientY - rect.top - 10;
  tip.style.left = `${Math.min(mx, rect.width - 220)}px`;
  tip.style.top = `${Math.max(my, 0)}px`;
  _graphTooltipHideTimer = setTimeout(() => {
    _graphTooltipHideTimer = null;
    _hideTooltip();
  }, 3000);
}

function _hideTooltip() {
  if (_graphTooltipHideTimer) {
    clearTimeout(_graphTooltipHideTimer);
    _graphTooltipHideTimer = null;
  }
  const tip = document.getElementById("graphTooltip");
  if (tip) {
    tip.style.display = "none";
    tip.classList.remove("graph-tooltip-minimal");
  }
}

function _showSharedTopicEdgeTooltip(ev, d) {
  if (_graphTooltipHideTimer) {
    clearTimeout(_graphTooltipHideTimer);
    _graphTooltipHideTimer = null;
  }
  const tip = document.getElementById("graphSharedTopicTooltip") || document.getElementById("graphTooltip");
  if (!tip) return;
  const topic = (d.edge_label && String(d.edge_label).trim())
    || (d.shared_tags && d.shared_tags.length && String(d.shared_tags[0]).trim())
    || "";
  if (tip.id === "graphSharedTopicTooltip") {
    tip.textContent = topic ? `공유 주제: ${topic}` : "관련 자료";
    tip.style.display = "block";
    const wrap = document.getElementById("graphCanvasWrap");
    if (wrap) {
      const rect = wrap.getBoundingClientRect();
      tip.style.left = `${ev.clientX - rect.left + 10}px`;
      tip.style.top = `${ev.clientY - rect.top - 20}px`;
    }
    return;
  }
  const tags = (d.shared_tags || []).slice(0, 16).map((t) => `<span class="gtt-tag">${escapeHtml(String(t))}</span>`).join("");
  const lbl = d.edge_label ? `<div class="gtt-meta">${escapeHtml(String(d.edge_label))}</div>` : "";
  const tagBlock = tags ? `<div class="gtt-tags">${tags}</div>` : '<div class="gtt-meta">태그 없음</div>';
  tip.classList.remove("graph-tooltip-minimal");
  tip.innerHTML = `<div class="gtt-title">공유 주제</div>${lbl}${tagBlock}`;
  tip.style.display = "block";
  const rect = tip.parentElement.getBoundingClientRect();
  const mx = ev.clientX - rect.left + 12;
  const my = ev.clientY - rect.top - 10;
  tip.style.left = `${Math.min(mx, rect.width - 280)}px`;
  tip.style.top = `${Math.max(my, 0)}px`;
}

function _hideSharedTopicHoverTooltip() {
  const tip = document.getElementById("graphSharedTopicTooltip");
  if (tip) tip.style.display = "none";
}

function _hoverMiniConstellation(d, nodeSel, linkWrap, labelMat, active) {
  _graphHoveredNodeId = (active && d) ? d.id : null;
  if (!active || !d) {
    nodeSel.each(function () {
      const nn = d3.select(this).datum();
      const gop = (_nodeTypeOf(nn) === "material" && nn._isMiniOrphan) ? 0.5 : 1;
      d3.select(this).attr("opacity", gop).selectAll(".gn-shape").attr("opacity", 1);
    });
    linkWrap.each(function (lnk) {
      const isBel = lnk.relation_type === "소속";
      d3.select(this).select("path.graph-mini-link").attr("stroke-opacity", isBel ? 0.12 : 0.2);
    });
    if (_graphNeighborBadgeAnchorId) _graphApplyNeighborBadgeEdgesMini();
    _updateGraphLabelVisibility();
    return;
  }
  const neighbors = new Set([d.id]);
  linkWrap.each(function () {
    const lnk = d3.select(this).datum();
    const sid = typeof lnk.source === "object" ? lnk.source.id : lnk.source;
    const tid = typeof lnk.target === "object" ? lnk.target.id : lnk.target;
    if (sid === d.id) neighbors.add(tid);
    if (tid === d.id) neighbors.add(sid);
  });
  nodeSel.each(function () {
    const nn = d3.select(this).datum();
    const gop = (_nodeTypeOf(nn) === "material" && nn._isMiniOrphan) ? 0.5 : 1;
    const shapeOp = neighbors.has(nn.id) ? 1 : 0.15;
    d3.select(this).attr("opacity", gop).selectAll(".gn-shape").attr("opacity", shapeOp);
  });
  nodeSel.selectAll(".graph-brand-label-innode").attr("opacity", 1);
  linkWrap.each(function () {
    const lnk = d3.select(this).datum();
    const sid = typeof lnk.source === "object" ? lnk.source.id : lnk.source;
    const tid = typeof lnk.target === "object" ? lnk.target.id : lnk.target;
    const hit = sid === d.id || tid === d.id;
    d3.select(this).select("path.graph-mini-link")
      .attr("stroke-opacity", hit ? 0.8 : 0.05);
  });
  _updateGraphLabelVisibility();
}

function _resetGraphSearchVisuals() {
  if (!_graphG) return;
  _graphG.selectAll("g.gn").each(function (d) {
    const g = d3.select(this);
    if (_graphMiniConstellationMode && _nodeTypeOf(d) === "material" && d._isMiniOrphan) g.attr("opacity", 0.5);
    else g.attr("opacity", 1);
    g.classed("graph-node-search-match", false);
  });
  _graphG.selectAll(".gn .gn-shape").each(function () {
    const shape = d3.select(this);
    const d = d3.select(this.parentNode).datum();
    const nt = _nodeTypeOf(d);
    if (nt === "material") {
      shape.attr("stroke", "rgba(255,255,255,0.12)")
        .attr("stroke-width", 0.5)
        .attr("fill", "rgba(200,200,210,0.9)")
        .attr("filter", null)
        .attr("opacity", 1);
    } else if (nt === "brand") {
      shape.attr("stroke", "rgba(255,255,255,0.2)")
        .attr("stroke-width", 1)
        .attr("fill", "rgba(200,200,210,0.9)")
        .attr("filter", null)
        .attr("opacity", 1);
    } else {
      shape.attr("opacity", 1);
    }
  });
  _updateGraphLabelVisibility();
}

function _highlightSearch() {
  if (!_graphG) return;
  const inp = document.getElementById("graphSearchInput");
  const raw = (inp && inp.value) ? inp.value : "";
  gf.search = raw.trim().toLowerCase();
  const q = gf.search;
  if (!q || q.length < 2) {
    _resetGraphSearchVisuals();
    return;
  }
  const fd = _lastGraphFiltered || _getFilteredData();
  const { nodes, edges } = fd;
  const matchFn = (d) => {
    const nt = _nodeTypeOf(d);
    if (d.title && String(d.title).toLowerCase().includes(q)) return true;
    if ((d.tags || []).some((t) => String(t).toLowerCase().includes(q))) return true;
    if (nt === "brand") {
      const bl = String(d.brand_label || "").toLowerCase();
      const plat = String(d.platform || d.category_large || "").toLowerCase();
      if (bl.includes(q) || plat.includes(q)) return true;
    }
    return false;
  };
  const matched = new Set();
  nodes.forEach((n) => {
    if (matchFn(n)) matched.add(n.id);
  });
  const neighbor = new Set();
  edges.forEach((e) => {
    const s = matched.has(e.source_id);
    const t = matched.has(e.target_id);
    if (s && !t) neighbor.add(e.target_id);
    if (t && !s) neighbor.add(e.source_id);
  });
  _graphG.selectAll("g.gn").each(function (d) {
    const g = d3.select(this);
    const id = d.id;
    let op = 0.15;
    if (matched.has(id)) op = 1;
    else if (neighbor.has(id)) op = 0.5;
    g.attr("opacity", op);
    g.classed("graph-node-search-match", matched.has(id));
  });
  const el = _graphG.selectAll(".gl-text");
  el.style("opacity", function (d) {
    if (!d) return 1;
    if (matched.has(d.id)) return 1;
    if (neighbor.has(d.id)) return 0.5;
    return 0.15;
  });
  // 자료 제목은 검색 중에도 숨김 (인라인 style opacity 덮어씀)
  el.filter(".gl-text-material").style("opacity", 0);
}

function _graphZoomStep(factor) {
  if (!_graphSvgSel || !_graphZoomBehavior) return;
  _graphSvgSel.transition().duration(300).call(_graphZoomBehavior.scaleBy, factor);
}

function _graphZoomFit() {
  if (!_graphSvgSel || !_graphZoomBehavior || !_graphG) return;
  const bounds = _graphG.node().getBBox();
  if (!bounds.width || !bounds.height) return;
  const svgEl = _graphSvgSel.node();
  const fullWidth = svgEl.clientWidth || 900;
  const fullHeight = svgEl.clientHeight || 600;
  const scale = Math.min(fullWidth / (bounds.width + 80), fullHeight / (bounds.height + 80), 2) * 0.9;
  const tx = fullWidth / 2 - scale * (bounds.x + bounds.width / 2);
  const ty = fullHeight / 2 - scale * (bounds.y + bounds.height / 2);
  _graphSvgSel.transition().duration(500).call(
    _graphZoomBehavior.transform,
    d3.zoomIdentity.translate(tx, ty).scale(scale)
  );
}


/* === 버전 이력 === */

async function showVersionHistory(materialId) {
  try {
    const res = await api(`/api/library/material/${materialId}/versions`);
    const versions = res.data;
    const modal = document.getElementById("versionModal");
    const timeline = document.getElementById("versionTimeline");

    if (versions.length === 0) {
      timeline.innerHTML = '<p class="placeholder-text">버전 이력이 없습니다. (아직 수정된 적이 없는 자료입니다)</p>';
    } else {
      timeline.innerHTML = versions.map(v => `
        <div class="version-item">
          <div class="version-marker"></div>
          <div class="version-body">
            <div class="version-header">
              <span class="version-number">v${v.version_number}</span>
              <span class="version-date">${v.created_at ? new Date(v.created_at).toLocaleString("ko-KR") : ""}</span>
            </div>
            <div class="version-title">${v.title || "(제목 없음)"}</div>
            ${v.change_reason ? `<div class="version-reason">💬 ${v.change_reason}</div>` : ""}
            ${v.changed_fields && v.changed_fields.length ? `<div class="version-fields">변경: ${v.changed_fields.join(", ")}</div>` : ""}
            ${v.summary ? `<div class="version-summary">${v.summary}</div>` : ""}
            <button class="btn btn-small" onclick="revertToVersion(${materialId}, ${v.id}, ${v.version_number})">이 버전으로 되돌리기</button>
          </div>
        </div>
      `).join("");
    }

    modal.style.display = "flex";
  } catch (err) {
    showToast(`버전 이력 로드 실패: ${err.message}`, "error");
  }
}

function closeVersionModal() {
  document.getElementById("versionModal").style.display = "none";
}

async function revertToVersion(materialId, versionId, versionNum) {
  if (!confirm(`v${versionNum} 버전으로 되돌리시겠습니까?`)) return;
  try {
    await api(`/api/library/material/${materialId}/revert`, {
      method: "POST",
      body: { version_id: versionId },
    });
    showToast(`v${versionNum} 버전으로 되돌렸습니다.`, "success");
    closeVersionModal();
    closeMaterialModal();
    loadLibrary();
  } catch (err) {
    showToast(`되돌리기 실패: ${err.message}`, "error");
  }
}

(function bindGraphFullscreenBack() {
  const btn = document.getElementById("btnGraphFullscreenBack");
  if (btn) btn.addEventListener("click", () => switchLibraryView("list"));
})();

(function mountGraphLegendInStatsPanel() {
  const sidebar = document.querySelector(".graph-stats-panel");
  const wrap = document.getElementById("graphLegendWrap");
  if (!sidebar || !wrap) return;
  if (wrap.parentElement !== sidebar) sidebar.appendChild(wrap);
})();

(function bindGraphLegendToggle() {
  const wrap = document.getElementById("graphLegendWrap");
  const btn = document.getElementById("btnGraphLegendToggle");
  const panel = document.getElementById("graphLegendPanel");
  if (!wrap || !btn || !panel) return;
  btn.addEventListener("click", () => {
    const open = wrap.classList.toggle("is-open");
    btn.textContent = open ? "범례 ▲" : "범례 ▼";
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    panel.setAttribute("aria-hidden", open ? "false" : "true");
  });
})();
