# -*- coding: utf-8 -*-
"""Splice new graph detail panel functions into library.js."""
from pathlib import Path
import re

lib_path = Path(r"d:\MONEY\My_Library\app\static\js\library.js")
lib = lib_path.read_text(encoding="utf-8")

m_start = lib.index("async function openGraphDetailPanelMaterial")
m_brand = lib.index("async function openGraphDetailPanelBrand", m_start)
m_end = lib.index("function _renderGraphStatsBarFiltered", m_brand)

mat_chunk = lib[m_start:m_brand]
brand_chunk = lib[m_brand:m_end]

LOADING = re.search(r'gdp-meta\\">([^<]+)</p>', mat_chunk).group(1)
KIND_M = re.search(
    r'const kindLabel = w\.kind === "entity" \? "([^"]+)" : "([^"]+)";',
    mat_chunk,
)
KIND_ENTITY, KIND_CONCEPT = KIND_M.group(1), KIND_M.group(2)
WIKI_PAGE_NONE = re.search(
    r": \"<p class=\\\"gdp-meta\\\">([^<]+)</p>\";",
    brand_chunk,
).group(1)

WIKI_NONE = "\uc5f0\uacb0\ub41c \uc704\ud0a4 \uc2a4\ub2c8\ud3ab\uc774 \uc5c6\uc2b5\ub2c8\ub2e4."
PROSE_PREFIX = (
    "\uc774 \ucd9c\ucc98\u00b7\ubd84\ub958\uc5d0 \uc18c\uc18d\ub41c \uc790\ub8cc\ub294 \ucd1d "
)
PROSE_SUFFIX = "\uac74\uc785\ub2c8\ub2e4."

material_fn = f"""async function openGraphDetailPanelMaterial(id) {{
  setGraphDetailOpen(true);
  const body = document.getElementById("graphDetailBody");
  if (body) {{
    body.innerHTML = "<h2 class=\\"gdp-panel-title\\">자료</h2>"
      + "<p class=\\"gdp-meta\\">{LOADING}</p>";
  }}
  try {{
    const res = await api(`/api/library/material/${{id}}/graph-panel`);
    const payload = res.data;
    const material = payload.material;
    const wikiSnippets = payload.wiki_snippets || [];
    const neighbors = _neighborMaterialTitles(id);
    const titleText = (material.title || "").trim() || "자료";
    const datePart = (material.ingested_date || "").trim()
      ? escapeHtml(String(material.ingested_date).trim())
      : "";
    const dateLine = datePart
      ? `${{datePart}} · 중요도 ${{material.importance ?? "—"}}`
      : `중요도 ${{material.importance ?? "—"}}`;
    let html = "";
    html += `<h2 class="gdp-panel-title">${{escapeHtml(titleText)}}</h2>`;
    html += `<div class="gdp-panel-date">${{dateLine}}</div>`;
    html += "<hr class=\\"gdp-rule\\">";
    html += "<div class=\\"gdp-subhead\\">요약</div>";
    if (material.summary) {{
      html += `<div class="gdp-prose">${{escapeHtml(String(material.summary))}}</div>`;
    }} else {{
      html += "<div class=\\"gdp-prose gdp-prose--empty\\">요약이 없습니다.</div>";
    }}
    if (material.tags && material.tags.length) {{
      html += `<div class="gdp-tags">${{material.tags.slice(0, 24).map((t) =>
        `<span class="gdp-tag">${{escapeHtml(String(t))}}</span>`).join("")}}</div>`;
    }}
    html += "<hr class=\\"gdp-rule\\">";
    html += "<div class=\\"gdp-subhead\\">위키 내용</div>";
    const wikiChunks = [];
    wikiSnippets.forEach((w) => {{
      const kindLabel = w.kind === "entity" ? "{KIND_ENTITY}" : "{KIND_CONCEPT}";
      const content = cleanWikiPanelContent(w.snippet || "");
      if (!content) return;
      const head = `${{kindLabel}}: ${{(w.name || "").trim()}}`;
      wikiChunks.push(`${{head}}\\n${{content.trim()}}`);
    }});
    const wikiMerged = wikiChunks.join("\\n\\n");
    if (wikiMerged) {{
      html += `<div class="gdp-prose">${{escapeHtml(wikiMerged)}}</div>`;
    }} else {{
      html += "<p class=\\"gdp-meta\\">{WIKI_NONE}</p>";
    }}
    html += "<hr class=\\"gdp-rule\\">";
    html += "<div class=\\"gdp-subhead\\">연결된 자료</div>";
    if (!neighbors.length) {{
      html += "<p class=\\"gdp-meta\\">연결된 자료가 없습니다.</p>";
    }} else {{
      html += "<ul class=\\"gdp-linked-list\\">";
      neighbors.forEach((n) => {{
        const dotCol = getBrandColor(n.group);
        html += `<li class="gdp-linked-item" data-mid="${{n.id}}" role="button" tabindex="0">`
          + `<span class="gdp-linked-dot" style="background:${{dotCol}}"></span>`
          + `<span class="gdp-linked-title">${{escapeHtml(n.title)}}</span>`
          + "</li>";
      }});
      html += "</ul>";
    }}
    body.innerHTML = html;
    body.querySelectorAll(".gdp-linked-item[data-mid]").forEach((row) => {{
      const go = () => {{
        const mid = Number.parseInt(row.dataset.mid, 10);
        if (mid) openGraphDetailPanelMaterial(mid);
      }};
      row.addEventListener("click", go);
      row.addEventListener("keydown", (ev) => {{
        if (ev.key === "Enter" || ev.key === " ") {{
          ev.preventDefault();
          go();
        }}
      }});
    }});
  }} catch (e) {{
    if (body) {{
      body.innerHTML = "<h2 class=\\"gdp-panel-title\\">자료</h2>"
        + `<p class="gdp-meta">로드 실패: ${{escapeHtml(e.message || String(e))}}</p>`;
    }}
  }}
}}

"""

brand_fn = (
    """async function openGraphDetailPanelBrand(d) {
  setGraphDetailOpen(true);
  const label = (d.brand_label || d.group || "").trim() || "미분류";
  const body = document.getElementById("graphDetailBody");
  const plat = (d.platform != null && String(d.platform).trim()) ? String(d.platform).trim() : "—";
  const catLarge = (d.category_large != null && String(d.category_large).trim())
    ? String(d.category_large).trim()
    : "—";
  if (body) {
    body.innerHTML = `<h2 class="gdp-panel-title">${escapeHtml(label)}</h2>`
      + "<p class=\\"gdp-meta\\">"""
    + LOADING
    + """</p>";
  }
  const fd = _lastGraphFiltered || _getFilteredData();
  const materials = (fd.nodes || []).filter((n) =>
    _nodeTypeOf(n) === "material" &&
    (n.group || n.brand_label || "미분류").trim() === label
  );
  let synthSnippet = "";
  try {
    const listRes = await api("/api/knowledge/synthesis");
    const pages = listRes.data || [];
    const match = pages.find((p) =>
      (p.title || "").includes(label) || (p.filename || "").includes(label.replace(/[\\\\/]/g, "_"))
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
  html += "<hr class=\\"gdp-rule\\">";
  html += "<div class=\\"gdp-subhead\\">요약</div>";
  html += `<div class="gdp-prose">"""
    + PROSE_PREFIX
    + "${materials.length}"
    + PROSE_SUFFIX
    + """</div>`;
  html += "<hr class=\\"gdp-rule\\">";
  html += "<div class=\\"gdp-subhead\\">위키 내용</div>";
  if (synthSnippet) {
    html += `<div class="gdp-prose">${escapeHtml(synthSnippet)}</div>`;
  } else {
    html += "<p class=\\"gdp-meta\\">"""
    + WIKI_PAGE_NONE
    + """</p>";
  }
  html += "<hr class=\\"gdp-rule\\">";
  html += "<div class=\\"gdp-subhead\\">연결된 자료</div>";
  if (!materials.length) {
    html += "<p class=\\"gdp-meta\\">연결된 자료가 없습니다.</p>";
  } else {
    html += "<ul class=\\"gdp-linked-list\\">";
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

"""
)

new_block = material_fn + brand_fn
if not new_block.endswith("\n"):
    new_block += "\n"

lines = lib.splitlines(keepends=True)


def idx_prefix(prefix):
    return next(i for i, ln in enumerate(lines) if ln.startswith(prefix))

m0 = idx_prefix("async function openGraphDetailPanelMaterial")
m2 = idx_prefix("function _renderGraphStatsBarFiltered")
out = "".join(lines[:m0] + [new_block] + lines[m2:])
lib_path.write_text(out, encoding="utf-8")
print("library.js: graph panel functions replaced OK")
