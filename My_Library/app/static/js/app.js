/* === 공통 API 호출 === */
/** FastAPI 기본 포트(uvicorn). HTML을 다른 포트(미리보기 등)에서 열면 이쪽으로 API 요청을 보냄 */
const API_DEFAULT_PORT = "8123";

function resolveApiUrl(path) {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const p = path.startsWith("/") ? path : `/${path}`;
  const loc = typeof window !== "undefined" ? window.location : null;
  if (!loc) {
    return p;
  }
  if (loc.protocol === "file:") {
    return `http://127.0.0.1:${API_DEFAULT_PORT}${p}`;
  }
  const localHost =
    loc.hostname === "localhost" || loc.hostname === "127.0.0.1";
  const port = loc.port || "";
  if (localHost && port && port !== API_DEFAULT_PORT) {
    return `http://${loc.hostname}:${API_DEFAULT_PORT}${p}`;
  }
  return p;
}

async function api(url, options = {}) {
  const defaults = {
    headers: { "Content-Type": "application/json" },
  };
  const config = { ...defaults, ...options };
  if (options.body && typeof options.body === "object") {
    config.body = JSON.stringify(options.body);
  }
  const fullUrl = resolveApiUrl(url);
  let response;
  try {
    response = await fetch(fullUrl, config);
  } catch (e) {
    const isNetwork =
      e && (e.name === "TypeError" || String(e.message || "").includes("fetch"));
    throw new Error(
      isNetwork
        ? "서버에 연결할 수 없습니다. 터미널에서 앱을 실행했는지, 주소가 http://127.0.0.1:8000 인지 확인하세요."
        : String(e.message || e)
    );
  }

  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(
        response.ok
          ? "서버 응답을 JSON으로 읽을 수 없습니다."
          : `서버 오류 (${response.status}). 로그인 페이지나 HTML이 반환된 경우 API 주소·프록시를 확인하세요.`
      );
    }
  }

  if (!response.ok) {
    const detail = data.detail;
    let msg;
    if (Array.isArray(detail)) {
      msg = detail
        .map((d) => (d && (d.msg || d.message)) || JSON.stringify(d))
        .join(" ");
    } else if (typeof detail === "string") {
      msg = detail;
    } else if (detail != null && typeof detail === "object") {
      msg = JSON.stringify(detail);
    } else {
      msg = response.statusText || `HTTP ${response.status}`;
    }
    throw new Error(msg || "요청 실패");
  }
  return data;
}

/* === 토스트 알림 === */
function showToast(message, type = "info") {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

/* === 탭 전환 === */
const tabBtns = document.querySelectorAll(".tab-btn");
const tabContents = document.querySelectorAll(".tab-content");

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetTab = btn.dataset.tab;
    tabBtns.forEach((b) => b.classList.remove("active"));
    tabContents.forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${targetTab}`).classList.add("active");

    if (targetTab !== "library") {
      document.body.classList.remove("library-graph-fullscreen");
    }

    if (targetTab === "library") loadLibrary();
    if (targetTab === "project") loadProjects();
    if (targetTab === "chat") {
      loadChatHistory();
      if (typeof window.refreshChatProviderStatus === "function") {
        window.refreshChatProviderStatus();
      }
    }
    if (targetTab === "settings") loadSettings();
    if (targetTab === "lotto" && typeof loadDashboard === "function") loadDashboard();
  });
});

/** index.html 사이드바 `switchTab('library')` 등 onclick 호환 */
function switchTab(targetTab) {
  const btn = document.querySelector(`.tab-btn[data-tab="${targetTab}"]`);
  if (btn) btn.click();
}
window.switchTab = switchTab;

/* === 알림 로드 === */
async function loadNotificationCount() {
  try {
    const res = await api("/api/settings/notifications/count");
    const count = Number(res.data.unread_count) || 0;
    const badge = document.getElementById("notificationBadge");
    badge.textContent = count > 99 ? "99+" : String(count);
    badge.classList.toggle("show", count > 0);
  } catch {
    /* 무시 */
  }
}

document.getElementById("notificationBtn").addEventListener("click", () => {
  document.querySelector('[data-tab="settings"]').click();
});

/* === 초기 로드 === */
document.addEventListener("DOMContentLoaded", () => {
  loadNotificationCount();
  loadRecentIngested();
});
