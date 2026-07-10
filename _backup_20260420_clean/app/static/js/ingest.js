/* === 섭취 탭 === */

const btnAnalyze = document.getElementById("btnAnalyze");
const btnIngest = document.getElementById("btnIngest");
const ingestContent = document.getElementById("ingestContent");
const previewContent = document.getElementById("previewContent");
const fileDropZone = document.getElementById("fileDropZone");
const fileInput = document.getElementById("fileInput");
const fileList = document.getElementById("fileList");
const fileItems = document.getElementById("fileItems");
const fileCount = document.getElementById("fileCount");
const urlBadge = document.getElementById("urlBadge");
const urlBadgeIcon = document.getElementById("urlBadgeIcon");
const urlBadgeText = document.getElementById("urlBadgeText");
const urlBadgeType = document.getElementById("urlBadgeType");
const ingestProgress = document.getElementById("ingestProgress");
const progressLabel = document.getElementById("progressLabel");
const progressPct = document.getElementById("progressPct");
const progressFill = document.getElementById("progressFill");
const progressDetail = document.getElementById("progressDetail");

let currentAnalysis = null;
let selectedFiles = [];
let pendingSimilarData = null;
let currentBatchMode = "individual";
let currentMaterialType = "information";
/** 유사 자료 확인 후 "그래도 새로 추가" 시에만 true로 한 번 전달 */
let ingestForceNext = false;
let detectedBulkUrls = null;

function isIngestTabActive() {
  const tab = document.getElementById("tab-ingest");
  return tab && tab.classList.contains("active");
}

const GOOGLE_DOC_REGEX = /docs\.google\.com\/(document|spreadsheets|presentation)\/d\/[a-zA-Z0-9_-]+/;
const YOUTUBE_REGEX = /(?:youtube\.com\/watch\?.*v=|youtu\.be\/)[a-zA-Z0-9_-]{11}/;
const GENERAL_URL_REGEX = /^https?:\/\/.+/;
const GOOGLE_TYPE_LABELS = { document: "Google Docs", spreadsheets: "Google Sheets", presentation: "Google Slides" };

/* === 자료 종류 선택 === */
function selectMaterialType(type) {
  currentMaterialType = type;
  const btnInfo = document.getElementById("mtBtnInfo");
  const btnUser = document.getElementById("mtBtnUser");
  const userCatInput = document.getElementById("userCategoryInput");

  btnInfo.classList.toggle("active", type === "information");
  btnUser.classList.toggle("active", type === "user");
  userCatInput.style.display = type === "user" ? "block" : "none";

  if (type === "user") {
    loadUserCategories();
  }
}

/** material_type=user 자료만 집계한 대분류 → [중분류…] */
let userCategoryTree = null;

function escapeAttr(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function allMediumsUnion(tree) {
  const set = new Set();
  if (!tree) return [];
  for (const arr of Object.values(tree)) {
    (arr || []).forEach((m) => set.add(m));
  }
  return [...set].sort((a, b) => a.localeCompare(b, "ko"));
}

function fillLargeSelectAndDatalist(categories) {
  const sel = document.getElementById("userCatLargeSelect");
  const largeList = document.getElementById("userCatLargeList");
  userCategoryTree = {};
  (categories || []).forEach((c) => {
    userCategoryTree[c.name] = (c.subcategories || []).map((s) => s.name);
  });
  const names = (categories || []).map((c) => c.name);
  if (sel) {
    sel.innerHTML =
      `<option value="">저장된 대분류 선택…</option>` +
      names.map((n) => `<option value="${escapeAttr(n)}">${escapeAttr(n)}</option>`).join("");
  }
  if (largeList) {
    largeList.innerHTML = names.map((n) => `<option value="${escapeAttr(n)}">`).join("");
  }
}

/** 선택한 대분류에 맞는 중분류만 datalist/셀렉트에 채움. 없으면 전체 중분류 합집합 */
function fillMediumForLarge(largeName) {
  const mediumList = document.getElementById("userCatMediumList");
  const medSel = document.getElementById("userCatMediumSelect");
  let mediums = [];
  const key = (largeName || "").trim();
  if (key && userCategoryTree && userCategoryTree[key]) {
    mediums = [...userCategoryTree[key]].sort((a, b) => a.localeCompare(b, "ko"));
  } else {
    mediums = allMediumsUnion(userCategoryTree);
  }
  if (medSel) {
    medSel.innerHTML =
      `<option value="">저장된 중분류 선택…</option>` +
      mediums.map((m) => `<option value="${escapeAttr(m)}">${escapeAttr(m)}</option>`).join("");
  }
  if (mediumList) {
    mediumList.innerHTML = mediums.map((m) => `<option value="${escapeAttr(m)}">`).join("");
  }
}

async function loadUserCategories() {
  try {
    const res = await api("/api/library/categories?material_type=user");
    const categories = res.data?.categories || [];
    fillLargeSelectAndDatalist(categories);
    const curL = document.getElementById("userCatLarge")?.value?.trim();
    fillMediumForLarge(curL || "");
    syncUserCatSelectFromInputs();
  } catch (e) {
    console.warn("loadUserCategories", e);
  }
}

function syncUserCatSelectFromInputs() {
  const lIn = document.getElementById("userCatLarge");
  const mIn = document.getElementById("userCatMedium");
  const lSel = document.getElementById("userCatLargeSelect");
  const mSel = document.getElementById("userCatMediumSelect");
  const lv = (lIn?.value || "").trim();
  const mv = (mIn?.value || "").trim();
  if (lSel) {
    const hasL = [...lSel.options].some((o) => o.value === lv);
    lSel.value = hasL ? lv : "";
  }
  if (mSel) {
    const hasM = [...mSel.options].some((o) => o.value === mv);
    mSel.value = hasM ? mv : "";
  }
}

function initUserCategoryControls() {
  const lSel = document.getElementById("userCatLargeSelect");
  const mSel = document.getElementById("userCatMediumSelect");
  const lIn = document.getElementById("userCatLarge");
  const mIn = document.getElementById("userCatMedium");
  if (!lSel || !mSel || !lIn || !mIn) return;

  lSel.addEventListener("change", () => {
    const v = lSel.value;
    lIn.value = v;
    fillMediumForLarge(v);
    mIn.value = "";
    mSel.value = "";
  });

  mSel.addEventListener("change", () => {
    mIn.value = mSel.value;
  });

  lIn.addEventListener("input", () => {
    const v = lIn.value.trim();
    fillMediumForLarge(v);
    const hasL = [...lSel.options].some((o) => o.value === v);
    lSel.value = hasL ? v : "";
  });

  mIn.addEventListener("input", () => {
    const v = mIn.value.trim();
    const hasM = [...mSel.options].some((o) => o.value === v);
    mSel.value = hasM ? v : "";
  });
}

initUserCategoryControls();

/* === URL 자동 감지 === */

function _extractUrls(text) {
  const lines = text.split(/[\n\r]+/).map(l => l.trim()).filter(Boolean);
  const urls = [];
  for (const line of lines) {
    if (GOOGLE_DOC_REGEX.test(line) || YOUTUBE_REGEX.test(line) || GENERAL_URL_REGEX.test(line)) {
      urls.push(line);
    }
  }
  return urls;
}

ingestContent.addEventListener("input", () => {
  const text = ingestContent.value.trim();
  detectedBulkUrls = null;

  const urls = _extractUrls(text);
  if (urls.length > 1) {
    const ytCount = urls.filter(u => YOUTUBE_REGEX.test(u)).length;
    const googleCount = urls.filter(u => GOOGLE_DOC_REGEX.test(u)).length;
    const webCount = urls.length - ytCount - googleCount;
    const parts = [];
    if (ytCount) parts.push(`YouTube ${ytCount}`);
    if (googleCount) parts.push(`Google ${googleCount}`);
    if (webCount) parts.push(`Web ${webCount}`);

    urlBadgeIcon.textContent = "🚀";
    urlBadgeText.textContent = `${urls.length}개 URL 감지 (벌크 섭취)`;
    urlBadgeType.textContent = parts.join(" / ");
    urlBadge.className = "url-badge url-badge-bulk";
    urlBadge.style.display = "flex";
    detectedBulkUrls = urls;
    return;
  }

  const googleMatch = text.match(GOOGLE_DOC_REGEX);
  if (googleMatch) {
    urlBadgeIcon.textContent = "📄";
    urlBadgeText.textContent = "구글 문서가 감지되었습니다";
    urlBadgeType.textContent = GOOGLE_TYPE_LABELS[googleMatch[1]] || googleMatch[1];
    urlBadge.className = "url-badge url-badge-google";
    urlBadge.style.display = "flex";
    return;
  }

  if (YOUTUBE_REGEX.test(text)) {
    urlBadgeIcon.textContent = "▶️";
    urlBadgeText.textContent = "유튜브 영상이 감지되었습니다";
    urlBadgeType.textContent = "YouTube";
    urlBadge.className = "url-badge url-badge-youtube";
    urlBadge.style.display = "flex";
    return;
  }

  if (GENERAL_URL_REGEX.test(text) && !text.includes("\n")) {
    urlBadgeIcon.textContent = "🌐";
    urlBadgeText.textContent = "웹페이지가 감지되었습니다";
    urlBadgeType.textContent = "";
    urlBadge.className = "url-badge url-badge-web";
    urlBadge.style.display = "flex";
    return;
  }

  urlBadge.style.display = "none";
});

/* === 드래그 앤 드롭 === */
fileDropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  fileDropZone.classList.add("drag-over");
});

fileDropZone.addEventListener("dragleave", () => {
  fileDropZone.classList.remove("drag-over");
});

fileDropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  fileDropZone.classList.remove("drag-over");
  addFiles(Array.from(e.dataTransfer.files));
});

fileInput.addEventListener("change", () => {
  addFiles(Array.from(fileInput.files));
  fileInput.value = "";
});

function addFiles(files) {
  for (const file of files) {
    const exists = selectedFiles.some((f) => f.name === file.name && f.size === file.size);
    if (!exists) selectedFiles.push(file);
  }
  renderFileList();
}

function removeFile(index) {
  selectedFiles.splice(index, 1);
  renderFileList();
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

const EXT_ICONS = {
  txt: "📝", md: "📝", pdf: "📕", xlsx: "📊", xls: "📊", csv: "📊",
  docx: "📄", jpg: "🖼️", jpeg: "🖼️", png: "🖼️", html: "🌐", htm: "🌐",
};

function getFileIcon(filename) {
  const ext = filename.split(".").pop().toLowerCase();
  return EXT_ICONS[ext] || "📎";
}

function renderFileList() {
  fileCount.textContent = selectedFiles.length;
  if (selectedFiles.length === 0) {
    fileList.style.display = "none";
    return;
  }
  fileList.style.display = "block";
  fileItems.innerHTML = selectedFiles
    .map(
      (f, i) => `
    <div class="file-item">
      <span class="file-icon">${getFileIcon(f.name)}</span>
      <div class="file-info">
        <span class="file-name">${f.name}</span>
        <span class="file-size">${formatFileSize(f.size)}</span>
      </div>
      <button class="file-remove" onclick="removeFile(${i})" title="제거">&times;</button>
    </div>`
    )
    .join("");
}

/* === 미리보기 === */
btnAnalyze.addEventListener("click", async () => {
  if (!isIngestTabActive()) return;
  const content = ingestContent.value.trim();
  if (!content && selectedFiles.length === 0) {
    showToast("미리보기하려면 텍스트를 입력하거나 파일을 첨부해 주세요.", "info");
    return;
  }
  btnAnalyze.disabled = true;
  btnAnalyze.innerHTML = '<span class="spinner"></span> 분석 중...';

  try {
    if (content) {
      const res = await api("/api/ingest/analyze", {
        method: "POST",
        body: { content },
      });
      currentAnalysis = res.data;
      renderPreview(currentAnalysis);

      if (currentAnalysis._url_type === "google") {
        showToast(`구글 문서 내용을 가져왔습니다 (${currentAnalysis._google_type})`, "success");
      } else if (currentAnalysis._url_type === "youtube") {
        showToast(`유튜브 자막을 가져왔습니다: ${currentAnalysis._youtube_title}`, "success");
      } else if (currentAnalysis._url_type === "webpage") {
        showToast(`웹페이지 내용을 가져왔습니다: ${currentAnalysis._page_title}`, "success");
      } else {
        showToast("분석 완료!", "success");
      }
    }
    if (selectedFiles.length > 0 && !content) {
      const excelFile = selectedFiles.find(f => /\.xlsx?$/i.test(f.name));
      if (excelFile) {
        try {
          const formData = new FormData();
          formData.append("file", excelFile);
          const fRes = await fetch(resolveApiUrl("/api/ingest/analyze-file"), { method: "POST", body: formData });
          const fData = await fRes.json();
          if (fRes.ok && fData.data) {
            currentAnalysis = fData.data;
            renderPreview(currentAnalysis);
            showToast(`엑셀 파일 분석 완료 (시트 ${fData.data._sheets_info?.length || 1}개)`, "success");
          }
        } catch { /* 무시 */ }
      } else {
        showToast(`${selectedFiles.length}개 파일은 섭취 시 자동 분석됩니다.`, "info");
      }
    } else if (selectedFiles.length > 0) {
      showToast(`${selectedFiles.length}개 파일은 섭취 시 자동 분석됩니다.`, "info");
    }
  } catch (err) {
    if (err.message.includes("비공개")) {
      showToast("이 문서는 비공개입니다. 공유 설정을 확인하세요.", "error");
    } else {
      showToast(`분석 실패: ${err.message}`, "error");
    }
  } finally {
    btnAnalyze.disabled = false;
    btnAnalyze.textContent = "🔍 미리보기";
  }
});

/* === 전체 섭취하기 === */
btnIngest.addEventListener("click", async () => {
  if (!isIngestTabActive()) return;
  const content = ingestContent.value.trim();
  const hasText = content.length > 0;
  const hasFiles = selectedFiles.length > 0;

  if (!hasText && !hasFiles) {
    showToast("섭취하려면 텍스트를 입력하거나 파일을 첨부해 주세요.", "info");
    return;
  }

  await executeIngest(content, hasText, hasFiles);
});

async function executeIngest(content, hasText, hasFiles, opts = {}) {
  const force = opts.force === true || ingestForceNext;
  ingestForceNext = false;
  btnIngest.disabled = true;
  btnAnalyze.disabled = true;

  const totalSteps = (hasText ? 1 : 0) + selectedFiles.length;
  let completed = 0;
  const results = [];
  const errors = [];

  showProgress(true);
  updateProgress(0, totalSteps, "준비 중...");

  try {
    if (hasText && detectedBulkUrls && detectedBulkUrls.length > 1) {
      const bulkTotal = detectedBulkUrls.length;
      updateProgress(0, bulkTotal, `벌크 섭취 시작: ${bulkTotal}개 URL...`);
      try {
        const userCatLarge = document.getElementById("userCatLarge")?.value || "";
        const userCatMedium = document.getElementById("userCatMedium")?.value || "";
        const res = await api("/api/ingest/bulk-urls", {
          method: "POST",
          body: {
            urls: detectedBulkUrls,
            material_type: currentMaterialType,
            user_category_large: userCatLarge,
            user_category_medium: userCatMedium,
            force,
          },
        });
        if (res.batch && res.data) {
          const bd = res.data;
          if (bd.results) {
            for (const r of bd.results) {
              results.push(r.data);
            }
          }
          if (bd.errors) {
            for (const e of bd.errors) {
              errors.push({ name: e.url, error: e.error });
            }
          }
          updateProgress(bd.completed, bulkTotal, `벌크 완료: ${bd.completed}건 성공, ${bd.failed}건 실패`);
        }
      } catch (err) {
        errors.push({ name: "벌크 URL", error: err.message });
      }
      completed = totalSteps;
      detectedBulkUrls = null;
    } else if (hasText) {
      updateProgress(completed, totalSteps, "텍스트/URL 섭취 중...");
      try {
        const userCatLarge = document.getElementById("userCatLarge")?.value || "";
        const userCatMedium = document.getElementById("userCatMedium")?.value || "";
        const userCatSmall = document.getElementById("userCatSmall")?.value?.trim() || "";
        const selectedSheets = getSelectedSheets();
        const body = {
          content,
          batch_mode: currentBatchMode,
          material_type: currentMaterialType,
          user_category_large: userCatLarge,
          user_category_medium: userCatMedium,
          user_category_small: userCatSmall,
          force,
        };
        if (selectedSheets) body.selected_sheets = selectedSheets;
        const res = await api("/api/ingest/auto", {
          method: "POST",
          body,
        });
        if (res.success === false && res.duplicate_type === "url" && res.is_duplicate) {
          const msg = res.message || "이미 동일한 URL의 자료가 있습니다.";
          const ok = window.confirm(`${msg}\n\n그래도 새로 저장하시겠습니까?`);
          if (ok) {
            await executeIngest(content, hasText, hasFiles, { force: true });
          }
          return;
        }
        if (res.similar_found && res.data) {
          if (res.data.analysis) {
            currentAnalysis = res.data.analysis;
          }
          pendingSimilarData = {
            content,
            hasText,
            hasFiles,
            similar: res.data.similar_materials || [],
          };
          showSimilarModal(pendingSimilarData.similar);
          return;
        }
        if (res.batch && Array.isArray(res.data)) {
          results.push(...res.data);
        } else {
          results.push(res.data);
        }
      } catch (err) {
        errors.push({ name: "텍스트 입력", error: err.message });
      }
      completed++;
      updateProgress(completed, totalSteps, "텍스트/URL 처리 완료");
    }

    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      updateProgress(completed, totalSteps, `파일 처리 중: ${file.name}`);

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("is_personal", "false");
        formData.append("batch_mode", currentBatchMode);
        formData.append("material_type", currentMaterialType);
        const ucL = document.getElementById("userCatLarge")?.value || "";
        const ucM = document.getElementById("userCatMedium")?.value || "";
        if (ucL) formData.append("user_category_large", ucL);
        if (ucM) formData.append("user_category_medium", ucM);
        formData.append("force", force ? "true" : "false");

        const res = await fetch(resolveApiUrl("/api/ingest/file"), { method: "POST", body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "업로드 실패");
        if (data.similar_found && data.data) {
          pendingSimilarData = {
            content,
            hasText,
            hasFiles,
            similar: data.data.similar_materials || [],
          };
          showSimilarModal(pendingSimilarData.similar);
          return;
        }
        if (data.batch && Array.isArray(data.data)) {
          results.push(...data.data);
        } else {
          results.push(data.data);
        }
      } catch (err) {
        errors.push({ name: file.name, error: err.message });
      }
      completed++;
      updateProgress(completed, totalSteps, `${file.name} 처리 완료`);
    }

    if (results.length > 0) {
      showToast(`${results.length}건 섭취 완료!${errors.length > 0 ? ` (${errors.length}건 실패)` : ""}`, "success");
      showIngestResults(results);
    } else {
      showToast("모든 섭취가 실패했습니다.", "error");
    }

    if (errors.length > 0) {
      progressDetail.textContent = errors.map((e) => `${e.name}: ${e.error}`).join("\n");
    }

    const hadSuccess = results.length > 0;
    const wasUser = currentMaterialType === "user";
    resetIngestForm();
    if (wasUser && hadSuccess) {
      loadUserCategories();
    }
    loadRecentIngested();
    loadNotificationCount();
    if (hadSuccess && typeof window.refreshLibraryAfterIngest === "function") {
      window.refreshLibraryAfterIngest().catch(() => {});
    }
  } finally {
    btnIngest.disabled = false;
    btnAnalyze.disabled = false;
    btnIngest.textContent = "📥 전체 섭취하기";
    setTimeout(() => showProgress(false), 3000);
  }
}

function resetIngestForm() {
  ingestContent.value = "";
  urlBadge.style.display = "none";
  selectedFiles = [];
  renderFileList();
  currentAnalysis = null;
  previewContent.innerHTML = '<p class="placeholder-text">자료를 입력하고 \'미리보기\'를 클릭하면 분석 결과가 여기에 표시됩니다.</p>';
  selectMaterialType("information");
  const ucl = document.getElementById("userCatLarge");
  const ucm = document.getElementById("userCatMedium");
  const ucs = document.getElementById("userCatSmall");
  const ucls = document.getElementById("userCatLargeSelect");
  const ucms = document.getElementById("userCatMediumSelect");
  if (ucl) ucl.value = "";
  if (ucm) ucm.value = "";
  if (ucs) ucs.value = "";
  if (ucls) ucls.value = "";
  if (ucms) ucms.value = "";
}

/* === 유사 자료 모달 === */
function showSimilarModal(similarList) {
  const modal = document.getElementById("similarModal");
  const listEl = document.getElementById("similarList");
  const btnUpdate = document.getElementById("btnUpdateExisting");

  listEl.innerHTML = similarList.map((s, i) => `
    <div class="similar-item ${i === 0 ? 'selected' : ''}" onclick="selectSimilarItem(this, ${s.id})">
      <div class="similar-title">${s.title}</div>
      <div class="similar-meta">${s.category} | 유사도: ${s.similarity_score}%</div>
      <div class="similar-summary">${s.summary ? s.summary.slice(0, 100) + "..." : ""}</div>
    </div>
  `).join("");

  if (similarList.length > 0) {
    btnUpdate.style.display = "";
    btnUpdate.dataset.materialId = similarList[0].id;
  }

  modal.style.display = "flex";
}

function closeSimilarModal() {
  document.getElementById("similarModal").style.display = "none";
  pendingSimilarData = null;
}

function selectSimilarItem(el, id) {
  document.querySelectorAll(".similar-item").forEach(e => e.classList.remove("selected"));
  el.classList.add("selected");
  document.getElementById("btnUpdateExisting").dataset.materialId = id;
}

async function handleSimilarChoice(choice) {
  if (!pendingSimilarData) return;
  const { content, hasText, hasFiles } = pendingSimilarData;

  closeSimilarModal();

  if (choice === "new") {
    await executeIngest(content, hasText, hasFiles, { force: true });
  } else if (choice === "update") {
    const materialId = document.getElementById("btnUpdateExisting").dataset.materialId;
    try {
      const res = await api("/api/ingest/update-existing", {
        method: "POST",
        body: {
          material_id: parseInt(materialId),
          content: content,
          summary: currentAnalysis?.summary || "",
          title: currentAnalysis?.title || "",
          change_reason: "새 자료 반영으로 업데이트",
        },
      });
      showToast(`기존 자료가 업데이트되었습니다 (v${res.data.version})`, "success");
      resetIngestForm();
      loadRecentIngested();
      if (typeof window.refreshLibraryAfterIngest === "function") {
        window.refreshLibraryAfterIngest().catch(() => {});
      }
    } catch (err) {
      showToast(`업데이트 실패: ${err.message}`, "error");
    }
  }
}

/* === 진행률 === */
function showProgress(show) {
  ingestProgress.style.display = show ? "block" : "none";
}

function updateProgress(current, total, label) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  progressLabel.textContent = label;
  progressPct.textContent = `${pct}%`;
  progressFill.style.width = `${pct}%`;
  progressDetail.textContent = `${current} / ${total}`;
}

/* === 미리보기 렌더링 === */
function renderPreview(analysis) {
  const tags = (analysis.tags || []).map((t) => `<span class="tag">${t}</span>`).join("");
  const points = (analysis.key_points || []).map((p) => `<li>${p}</li>`).join("");

  let sourceBadge = "";
  if (analysis._url_type === "google") {
    sourceBadge = `<div class="preview-field"><label>소스</label><div class="value"><span class="tag" style="background:var(--success);color:#fff;border-color:var(--success);">📄 ${analysis._google_type}</span></div></div>`;
  } else if (analysis._url_type === "youtube") {
    sourceBadge = `<div class="preview-field"><label>소스</label><div class="value"><span class="tag" style="background:#ff0000;color:#fff;border-color:#ff0000;">▶️ YouTube: ${analysis._youtube_title || ""}</span></div></div>`;
  } else if (analysis._url_type === "webpage") {
    sourceBadge = `<div class="preview-field"><label>소스</label><div class="value"><span class="tag" style="background:#0f3460;color:#fff;border-color:#0f3460;">🌐 ${analysis._page_source || ""}: ${analysis._page_title || ""}</span></div></div>`;
  }

  let sheetsSection = "";
  if (analysis._sheets_info && analysis._sheets_info.length >= 1) {
    const sheetRows = analysis._sheets_info.map((s, i) =>
      `<tr>
        <td><input type="checkbox" class="sheet-check" data-sheet="${s.name}" checked></td>
        <td>${i + 1}</td>
        <td>${s.name}</td>
        <td>${s.row_count}행</td>
      </tr>`
    ).join("");
    sheetsSection = `
      <div class="preview-field">
        <label>📊 시트 목록 (${analysis._sheets_info.length}개)</label>
        <div style="margin:6px 0 4px;">
          <label style="cursor:pointer;font-size:0.82rem;display:flex;align-items:center;gap:4px;">
            <input type="checkbox" id="sheetCheckAll" checked onchange="toggleAllSheets(this.checked)">
            전체 선택/해제
          </label>
        </div>
        <table class="sheets-table" style="width:100%;font-size:0.85rem;border-collapse:collapse;">
          <thead><tr style="border-bottom:1px solid var(--border);"><th style="padding:4px;width:30px;"></th><th style="text-align:left;padding:4px;">#</th><th style="text-align:left;padding:4px;">시트명</th><th style="text-align:left;padding:4px;">행 수</th></tr></thead>
          <tbody>${sheetRows}</tbody>
        </table>
      </div>
      <div class="preview-field">
        <label>섭취 방식</label>
        <div style="display:flex;gap:16px;margin-top:6px;">
          <label style="cursor:pointer;display:flex;align-items:center;gap:4px;font-size:0.9rem;">
            <input type="radio" name="batchMode" value="individual" checked onchange="currentBatchMode=this.value">
            각 시트를 개별 자료로 섭취
          </label>
          <label style="cursor:pointer;display:flex;align-items:center;gap:4px;font-size:0.9rem;">
            <input type="radio" name="batchMode" value="single" onchange="currentBatchMode=this.value">
            전체 시트를 하나의 자료로 섭취
          </label>
        </div>
      </div>
    `;
    currentBatchMode = "individual";
  }

  const fetchedPreview = analysis._fetched_content
    ? `<div class="preview-field"><label>가져온 내용 (미리보기)</label><div class="value" style="font-size:0.85rem;max-height:100px;overflow-y:auto;white-space:pre-wrap;">${analysis._fetched_content}...</div></div>`
    : "";

  previewContent.innerHTML = `
    ${sourceBadge}
    ${sheetsSection}
    ${fetchedPreview}
    <div class="preview-field">
      <label>제목</label>
      <div class="value">${analysis.title || "-"}</div>
    </div>
    <div class="preview-field">
      <label>출처</label>
      <div class="value">${analysis.source || "-"}</div>
    </div>
    <div class="preview-field">
      <label>날짜</label>
      <div class="value">${analysis.original_date || "-"}</div>
    </div>
    <div class="preview-field">
      <label>분류</label>
      <div class="value">${analysis.category_large} > ${analysis.category_medium}${analysis.category_small ? " > " + analysis.category_small : ""}</div>
    </div>
    <div class="preview-field">
      <label>요약</label>
      <div class="value">${analysis.summary || "-"}</div>
    </div>
    <div class="preview-field">
      <label>주요 포인트</label>
      <ul style="padding-left:18px;color:var(--text-secondary);font-size:0.9rem;">${points || "<li>-</li>"}</ul>
    </div>
    <div class="preview-field">
      <label>태그</label>
      <div class="preview-tags">${tags || "-"}</div>
    </div>
    <div class="preview-field">
      <label>중요도</label>
      <div class="value">${"★".repeat(analysis.importance || 3)}${"☆".repeat(5 - (analysis.importance || 3))}</div>
    </div>
  `;
}

/* === 시트 선택 === */
function toggleAllSheets(checked) {
  document.querySelectorAll(".sheet-check").forEach(cb => { cb.checked = checked; });
}

function getSelectedSheets() {
  const checks = document.querySelectorAll(".sheet-check");
  if (checks.length === 0) return null;
  const selected = [];
  checks.forEach(cb => { if (cb.checked) selected.push(cb.dataset.sheet); });
  return selected.length === checks.length ? null : selected;
}

/* === 최근 섭취 === */
async function loadRecentIngested() {
  try {
    const res = await api("/api/library/search?per_page=5");
    const items = res.data.items;
    const container = document.getElementById("recentList");

    if (items.length === 0) {
      container.innerHTML = '<p class="placeholder-text">아직 섭취한 자료가 없습니다.</p>';
      return;
    }

    container.innerHTML = items
      .map(
        (item) => `
      <div class="card" onclick="document.querySelector('[data-tab=library]').click()">
        <div class="card-title">${item.title}</div>
        <div class="card-meta">
          <span>📂 ${item.category_large} > ${item.category_medium}</span>
          <span>📅 ${item.original_date || "-"}</span>
          <span>📰 ${item.source}</span>
        </div>
        <div class="card-summary">${item.summary || ""}</div>
        <div class="card-tags">${(item.tags || []).map((t) => `<span class="tag">${t}</span>`).join("")}</div>
      </div>
    `
      )
      .join("");
  } catch {
    /* 무시 */
  }
}

async function showIngestResults(results) {
  const container = document.getElementById("previewContent");
  if (!container) return;

  const cards = [];
  for (const r of results) {
    if (!r || !r.id) continue;
    let keInfo = { entities: 0, concepts: 0 };
    try {
      const [entR, conR] = await Promise.all([
        api(`/api/knowledge/material/${r.id}/entities`),
        api(`/api/knowledge/material/${r.id}/concepts`),
      ]);
      keInfo.entities = (entR.data || []).length;
      keInfo.concepts = (conR.data || []).length;
    } catch { /* silent */ }

    const title = r.title || "제목 없음";
    const summary = (r.summary || "").slice(0, 200);
    const cat = [r.category_large, r.category_medium].filter(Boolean).join(" > ");
    const tags = (r.tags || []).slice(0, 5);
    const source = r.source || "";
    const date = r.original_date || "";

    cards.push(`
      <div class="ingest-result-card">
        <div class="ir-header">
          <span class="ir-status">&#10003; 섭취 완료</span>
          <button class="btn btn-small btn-primary ir-view-btn" onclick="document.querySelector('[data-tab=library]').click(); setTimeout(()=>showMaterialDetail(${r.id}),500)">도서관에서 보기</button>
        </div>
        <h4 class="ir-title">${title}</h4>
        <div class="ir-meta">
          ${cat ? `<span>&#128194; ${cat}</span>` : ""}
          ${source ? `<span>&#128240; ${source}</span>` : ""}
          ${date ? `<span>&#128197; ${date}</span>` : ""}
        </div>
        <p class="ir-summary">${summary}${summary.length >= 200 ? "..." : ""}</p>
        <div class="ir-stats">
          ${keInfo.entities > 0 ? `<span class="ir-stat">&#128100; 핵심 태그 ${keInfo.entities}개</span>` : ""}
          ${keInfo.concepts > 0 ? `<span class="ir-stat">&#128161; 주제 ${keInfo.concepts}개</span>` : ""}
          ${tags.length > 0 ? tags.map(t => `<span class="tag">${t}</span>`).join("") : ""}
        </div>
      </div>
    `);
  }

  if (cards.length > 0) {
    container.innerHTML = `
      <div class="ingest-results-wrap">
        <h3 class="ir-results-title">&#128230; 섭취 결과 (${cards.length}건)</h3>
        ${cards.join("")}
      </div>`;
  }
}
