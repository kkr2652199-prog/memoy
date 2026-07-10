/* === 챗봇 탭 === */

const CHAT_SESSION_STORAGE_KEY = "myLibraryChatSessionId";

function getOrCreateChatSessionId() {
  try {
    let id = sessionStorage.getItem(CHAT_SESSION_STORAGE_KEY);
    if (!id) {
      id =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `sess-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
      sessionStorage.setItem(CHAT_SESSION_STORAGE_KEY, id);
    }
    return id;
  } catch {
    return `sess-${Date.now()}`;
  }
}

const chatInput = document.getElementById("chatInput");
const chatMessages = document.getElementById("chatMessages");
const btnSendChat = document.getElementById("btnSendChat");
const btnClearChat = document.getElementById("btnClearChat");
const chatProviderSelect = document.getElementById("chatProviderSelect");
const chatProviderStatusDot = document.getElementById("chatProviderStatusDot");
const chatMaterialScope = document.getElementById("chatMaterialScope");
const chatCategoryLarge = document.getElementById("chatCategoryLarge");
const chatCategoryMedium = document.getElementById("chatCategoryMedium");
const chatTaskTypeOverride = document.getElementById("chatTaskTypeOverride");

/** @type {Array<{name:string,count:number,subcategories:Array<{name:string,count:number}>}>} */
let chatCategoryTree = [];

/** 세션당 한 번: 빈 분류 트리 안내 (자료 없음 vs 오류 구분) */
const CHAT_EMPTY_CATEGORY_HINT_KEY = "myLibraryChatEmptyCategoryHintShown";

function getChatMaterialTypeQuery() {
  const v = (chatMaterialScope?.value || "").trim();
  if (v === "information" || v === "user") return v;
  return "";
}

/** API categories 배열에서 중분류 이름 기준 유니온 (material_type별 트리용). */
function collectUniqueSubcategories(categories) {
  const byName = new Map();
  for (const cat of categories || []) {
    for (const sub of cat.subcategories || []) {
      const n = (sub.name || "").trim();
      if (!n) continue;
      const prev = byName.get(n);
      const add = sub.count || 0;
      byName.set(n, {
        name: n,
        count: (prev ? prev.count : 0) + add,
      });
    }
  }
  return Array.from(byName.values()).sort((a, b) =>
    a.name.localeCompare(b.name, "ko")
  );
}

async function fetchChatCategoryTreeForType(materialType) {
  const q = `?material_type=${encodeURIComponent(materialType)}`;
  const res = await api(`/api/library/categories${q}`);
  const raw = res.data;
  if (Array.isArray(raw)) return raw;
  if (raw && Array.isArray(raw.categories)) return raw.categories;
  return [];
}

function appendChatMediumOptionPreamble() {
  if (!chatCategoryMedium) return;
  const oInfo = document.createElement("option");
  oInfo.value = "__info_all__";
  oInfo.textContent = "📰 정보 중분류 전체보기";
  chatCategoryMedium.appendChild(oInfo);
  const oUser = document.createElement("option");
  oUser.value = "__user_all__";
  oUser.textContent = "👤 사용자 중분류 전체보기";
  chatCategoryMedium.appendChild(oUser);
  const sep = document.createElement("option");
  sep.disabled = true;
  sep.value = "";
  sep.textContent = "── 구분 ──";
  chatCategoryMedium.appendChild(sep);
}

async function loadChatCategoryTree() {
  if (!chatCategoryLarge || !chatCategoryMedium) return;
  const mt = getChatMaterialTypeQuery();
  const q = mt ? `?material_type=${encodeURIComponent(mt)}` : "";
  let loadFailed = false;
  try {
    const res = await api(`/api/library/categories${q}`);
    const raw = res.data;
    if (Array.isArray(raw)) {
      chatCategoryTree = raw;
    } else if (raw && Array.isArray(raw.categories)) {
      chatCategoryTree = raw.categories;
    } else {
      chatCategoryTree = [];
    }
  } catch {
    loadFailed = true;
    chatCategoryTree = [];
    showToast("분류 목록을 불러오지 못했습니다. 네트워크를 확인해 주세요.", "error");
  }
  if (!loadFailed && chatCategoryTree.length === 0) {
    try {
      if (!sessionStorage.getItem(CHAT_EMPTY_CATEGORY_HINT_KEY)) {
        showToast(
          "이 범위에 등록된 분류가 없습니다. 자료가 없거나 아직 분류되지 않았을 수 있습니다.",
          "info"
        );
        sessionStorage.setItem(CHAT_EMPTY_CATEGORY_HINT_KEY, "1");
      }
    } catch {
      /* sessionStorage 불가 시에도 셀렉트는 동작 */
    }
  }
  fillChatCategoryLargeOptions();
  await fillChatCategoryMediumOptions();
}

function fillChatCategoryLargeOptions() {
  if (!chatCategoryLarge) return;
  const prev = chatCategoryLarge.value;
  chatCategoryLarge.innerHTML = '<option value="">전체 / 미지정</option>';
  const oInfo = document.createElement("option");
  oInfo.value = "__info_all__";
  oInfo.textContent = "📰 정보 전체보기";
  chatCategoryLarge.appendChild(oInfo);
  const oUser = document.createElement("option");
  oUser.value = "__user_all__";
  oUser.textContent = "👤 사용자 전체보기";
  chatCategoryLarge.appendChild(oUser);
  const sep = document.createElement("option");
  sep.disabled = true;
  sep.value = "";
  sep.textContent = "── 구분 ──";
  chatCategoryLarge.appendChild(sep);
  chatCategoryTree.forEach((cat) => {
    const o = document.createElement("option");
    o.value = cat.name;
    o.textContent = `${cat.name} (${cat.count})`;
    chatCategoryLarge.appendChild(o);
  });
  if (prev && [...chatCategoryLarge.options].some((opt) => opt.value === prev && !opt.disabled)) {
    chatCategoryLarge.value = prev;
  }
}

async function fillChatCategoryMediumOptions() {
  if (!chatCategoryMedium || !chatCategoryLarge) return;
  const prev = chatCategoryMedium.value;
  const largeName = chatCategoryLarge.value;
  chatCategoryMedium.innerHTML = '<option value="">전체 / 미지정</option>';
  appendChatMediumOptionPreamble();

  let subs = [];
  if (!largeName) {
    subs = [];
  } else if (largeName === "__info_all__") {
    try {
      const tree = await fetchChatCategoryTreeForType("information");
      subs = collectUniqueSubcategories(tree);
    } catch {
      subs = [];
    }
  } else if (largeName === "__user_all__") {
    try {
      const tree = await fetchChatCategoryTreeForType("user");
      subs = collectUniqueSubcategories(tree);
    } catch {
      subs = [];
    }
  } else {
    const node = chatCategoryTree.find((c) => c.name === largeName);
    subs = node?.subcategories || [];
  }

  subs.forEach((sub) => {
    const o = document.createElement("option");
    o.value = sub.name;
    o.textContent = `${sub.name} (${sub.count})`;
    chatCategoryMedium.appendChild(o);
  });
  if (
    prev &&
    [...chatCategoryMedium.options].some(
      (opt) => opt.value === prev && !opt.disabled
    )
  ) {
    chatCategoryMedium.value = prev;
  }
}

if (chatMaterialScope) {
  chatMaterialScope.addEventListener("change", () => {
    loadChatCategoryTree();
  });
}
if (chatCategoryLarge) {
  chatCategoryLarge.addEventListener("change", () => {
    void fillChatCategoryMediumOptions();
  });
}

async function refreshChatProviderStatus() {
  if (!chatProviderSelect || !chatProviderStatusDot) return;
  const sel = (chatProviderSelect.value || "").trim();
  const key = sel || "default";
  try {
    const res = await api("/api/chat/providers-status");
    const st = res.data || {};
    let ok = false;
    if (!sel) {
      ok = Object.values(st).some(Boolean);
    } else {
      ok = !!st[sel];
    }
    chatProviderStatusDot.classList.remove("ok", "bad", "neutral");
    chatProviderStatusDot.classList.add(ok ? "ok" : "bad");
    chatProviderStatusDot.title = ok ? "연결됨" : "미연결 (API 키·엔드포인트 확인)";
  } catch {
    chatProviderStatusDot.classList.remove("ok", "bad", "neutral");
    chatProviderStatusDot.classList.add("neutral");
    chatProviderStatusDot.title = "상태 확인 실패";
  }
}

if (chatProviderSelect) {
  chatProviderSelect.addEventListener("change", refreshChatProviderStatus);
}

btnSendChat.addEventListener("click", sendChat);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
});
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + "px";
});

btnClearChat.addEventListener("click", async () => {
  try {
    const sid = getOrCreateChatSessionId();
    const q = `?session_id=${encodeURIComponent(sid)}`;
    await api(`/api/chat/history${q}`, { method: "DELETE" });
    chatMessages.innerHTML = `
      <div class="chat-bubble assistant">
        <p>대화가 초기화되었습니다. 무엇이든 물어보세요!</p>
      </div>`;
    showToast("대화 기록 삭제 완료", "success");
  } catch (err) {
    showToast(`삭제 실패: ${err.message}`, "error");
  }
});

async function sendChat() {
  const message = chatInput.value.trim();
  if (!message) return;

  appendBubble(message, "user");
  chatInput.value = "";
  chatInput.style.height = "auto";
  chatInput.disabled = true;
  btnSendChat.disabled = true;

  const loadingEl = appendBubble('<span class="spinner"></span> 생각 중...', "assistant");

  try {
    const provider = chatProviderSelect ? (chatProviderSelect.value || "").trim() : "";
    const sessionId = getOrCreateChatSessionId();
    const category_large = chatCategoryLarge ? (chatCategoryLarge.value || "").trim() : "";
    const category_medium = chatCategoryMedium ? (chatCategoryMedium.value || "").trim() : "";
    const material_scope = chatMaterialScope ? (chatMaterialScope.value || "").trim() : "";
    const task_type_override = chatTaskTypeOverride
      ? (chatTaskTypeOverride.value || "").trim()
      : "";

    const res = await api("/api/chat/send", {
      method: "POST",
      body: {
        message,
        provider,
        session_id: sessionId,
        category_large,
        category_medium,
        material_scope,
        task_type_override,
      },
    });

    loadingEl.remove();

    const rawResponse = res.data.response;
    const usedProvider = res.data.provider || "";
    const sourceType = res.data.source_type || "";

    let metaHtml = '<div class="chat-meta">';
    if (usedProvider) {
      metaHtml += `<span class="chat-provider-badge">🤖 ${usedProvider}</span>`;
    }
    if (sourceType === "library") {
      metaHtml += '<span class="chat-source-badge library">📚 도서관 자료 기반</span>';
    } else if (sourceType === "general") {
      metaHtml += '<span class="chat-source-badge general">💭 일반 지식 (자료 없음)</span>';
    }
    metaHtml += "</div>";

    let responseHtml = metaHtml;
    responseHtml += typeof marked !== "undefined" && marked.parse
      ? marked.parse(rawResponse)
      : rawResponse;
    const refs = res.data.referenced_materials || [];
    if (refs.length > 0) {
      responseHtml += '<div style="margin-top:10px;font-size:0.8rem;color:var(--text-muted);">📚 참조 자료: ';
      responseHtml += refs.map((r) => `<span class="tag" style="cursor:pointer;" onclick="showMaterialDetail(${r.id})">${r.title}</span>`).join(" ");
      responseHtml += "</div>";
    }
    responseHtml += `<button class="btn-save-wiki" onclick="saveAnswerToWiki(this)" data-q="${encodeURIComponent(message)}" data-a="${encodeURIComponent(rawResponse)}">📥 위키에 저장</button>`;
    appendBubble(responseHtml, "assistant", true);
  } catch (err) {
    loadingEl.remove();
    appendBubble(`오류가 발생했습니다: ${err.message}`, "assistant");
  } finally {
    chatInput.disabled = false;
    btnSendChat.disabled = false;
    chatInput.focus();
  }
}

function appendBubble(content, role, isHtml = false) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  if (isHtml) {
    bubble.innerHTML = `<div class="chat-md-body">${content}</div>`;
  } else {
    bubble.innerHTML = `<p>${content}</p>`;
  }
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

async function saveAnswerToWiki(btn) {
  const q = decodeURIComponent(btn.dataset.q);
  const a = decodeURIComponent(btn.dataset.a);
  btn.disabled = true;
  btn.textContent = "저장 중...";
  try {
    await api("/api/chat/save-to-wiki", { method: "POST", body: { question: q, answer: a } });
    btn.textContent = "✅ 저장 완료";
    btn.classList.add("saved");
    showToast("답변이 위키에 저장되었습니다.", "success");
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "📥 위키에 저장";
    showToast("저장 실패: " + err.message, "error");
  }
}

async function loadChatHistory() {
  try {
    const sid = getOrCreateChatSessionId();
    const res = await api(
      `/api/chat/history?limit=50&session_id=${encodeURIComponent(sid)}`
    );
    const messages = res.data;

    if (messages.length === 0) return;

    chatMessages.innerHTML = "";
    messages.forEach((msg) => {
      if (msg.role === "assistant" && typeof marked !== "undefined" && marked.parse) {
        appendBubble(marked.parse(msg.message), msg.role, true);
      } else {
        appendBubble(msg.message, msg.role);
      }
    });
  } catch {
    /* 무시 */
  }
}

document.addEventListener("DOMContentLoaded", () => {
  refreshChatProviderStatus();
  loadChatCategoryTree();
});

window.refreshChatProviderStatus = refreshChatProviderStatus;
