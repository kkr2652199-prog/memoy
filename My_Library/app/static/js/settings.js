/* === 설정 탭 === */

const btnSaveSettings = document.getElementById("btnSaveSettings");
const btnHealthCheck = document.getElementById("btnHealthCheck");

async function loadSettings() {
  try {
    const res = await api("/api/settings/config");
    const config = res.data;
    const llm = config.llm || {};

    document.getElementById("settingProvider").value = llm.default_provider || "openai";
    document.getElementById("settingLocalEndpoint").value = llm.local_endpoint || "http://localhost:11434";
    const lmEl = document.getElementById("settingLmstudioEndpoint");
    if (lmEl) {
      lmEl.value = llm.lmstudio_endpoint || "http://localhost:1234";
    }

    loadNotifications();
    loadSchedulerStatus();
  } catch (err) {
    showToast(`설정 로드 실패: ${err.message}`, "error");
  }
}

btnSaveSettings.addEventListener("click", async () => {
  const updates = [
    { key_path: "llm.default_provider", value: document.getElementById("settingProvider").value },
    { key_path: "llm.local_endpoint", value: document.getElementById("settingLocalEndpoint").value },
    {
      key_path: "llm.lmstudio_endpoint",
      value:
        (document.getElementById("settingLmstudioEndpoint")?.value || "").trim() ||
        "http://localhost:1234",
    },
  ];

  const openaiKey = document.getElementById("settingOpenaiKey").value;
  if (openaiKey) updates.push({ key_path: "llm.openai_api_key", value: openaiKey });

  const claudeKey = document.getElementById("settingClaudeKey").value;
  if (claudeKey) updates.push({ key_path: "llm.claude_api_key", value: claudeKey });

  const geminiKey = document.getElementById("settingGeminiKey").value;
  if (geminiKey) updates.push({ key_path: "llm.gemini_api_key", value: geminiKey });

  try {
    for (const update of updates) {
      await api("/api/settings/config", { method: "PUT", body: update });
    }
    showToast("설정 저장 완료!", "success");

    document.getElementById("settingOpenaiKey").value = "";
    document.getElementById("settingClaudeKey").value = "";
    document.getElementById("settingGeminiKey").value = "";
  } catch (err) {
    showToast(`저장 실패: ${err.message}`, "error");
  }
});

btnHealthCheck.addEventListener("click", async () => {
  btnHealthCheck.disabled = true;
  btnHealthCheck.innerHTML = '<span class="spinner"></span> 점검 중...';

  try {
    const res = await api("/api/settings/health-check", { method: "POST" });
    const data = res.data;
    const container = document.getElementById("healthResult");

    const orphanList = (data.orphan_pages || [])
      .map((o) => `<li>${o.title} (ID: ${o.id})</li>`)
      .join("");
    const unusedList = (data.unused_materials || [])
      .map((u) => `<li>${u.title} (ID: ${u.id})</li>`)
      .join("");

    const missingRefs = (data.missing_cross_references || [])
      .map((r) => `<li>"${r.material_a.title}" ↔ "${r.material_b.title}" (공유 태그: ${r.shared_tags.join(", ") || "같은 분류"})</li>`)
      .join("");
    const gaps = (data.knowledge_gaps || [])
      .map((g) => `<li><strong>[${g.type}]</strong> ${g.suggestion}</li>`)
      .join("");

    container.innerHTML = `
      <div class="settings-section" style="margin-top:12px;padding:16px;">
        <p><strong>총 이슈:</strong> ${data.total_issues}건</p>
        <div style="margin-top:10px;">
          <strong>🔗 고아 페이지 (교차 참조 없음): ${data.orphan_pages.length}건</strong>
          ${orphanList ? `<ul style="padding-left:20px;margin-top:6px;color:var(--text-secondary);font-size:0.88rem;">${orphanList}</ul>` : ""}
        </div>
        <div style="margin-top:10px;">
          <strong>📦 미사용 자료 (30일 이상): ${data.unused_materials.length}건</strong>
          ${unusedList ? `<ul style="padding-left:20px;margin-top:6px;color:var(--text-secondary);font-size:0.88rem;">${unusedList}</ul>` : ""}
        </div>
        ${missingRefs ? `<div style="margin-top:10px;">
          <strong>🔍 누락된 교차 참조 제안: ${(data.missing_cross_references || []).length}건</strong>
          <ul style="padding-left:20px;margin-top:6px;color:var(--text-secondary);font-size:0.88rem;">${missingRefs}</ul>
        </div>` : ""}
        ${gaps ? `<div style="margin-top:10px;">
          <strong>💡 지식 갭 & 추천:</strong>
          <ul style="padding-left:20px;margin-top:6px;color:var(--text-secondary);font-size:0.88rem;">${gaps}</ul>
        </div>` : ""}
      </div>`;

    showToast("건강 상태 점검 완료!", "success");
    loadNotificationCount();
  } catch (err) {
    showToast(`점검 실패: ${err.message}`, "error");
  } finally {
    btnHealthCheck.disabled = false;
    btnHealthCheck.textContent = "건강 상태 확인";
  }
});

const notificationActionHtml = `
<div class="notification-actions" style="display:flex; gap:8px; margin-bottom:12px;">
  <button type="button" data-notify-action="read-all"
    style="padding:6px 12px; background:var(--accent); color:#fff; border:none; border-radius:6px; cursor:pointer; font-size:0.82rem;">
    전체 읽음
  </button>
  <button type="button" data-notify-action="delete-read"
    style="padding:6px 12px; background:#555; color:#fff; border:none; border-radius:6px; cursor:pointer; font-size:0.82rem;">
    읽은 알림 삭제
  </button>
  <button type="button" data-notify-action="delete-all"
    style="padding:6px 12px; background:#d32f2f; color:#fff; border:none; border-radius:6px; cursor:pointer; font-size:0.82rem;">
    전체 삭제
  </button>
</div>
`;

function wireNotificationBulkActions(container) {
  const bar = container.querySelector(".notification-actions");
  if (!bar) return;
  const bind = (action, fn) => {
    bar.querySelector(`[data-notify-action="${action}"]`)?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      void fn();
    });
  };
  bind("read-all", markAllNotificationsRead);
  bind("delete-read", deleteReadNotifications);
  bind("delete-all", deleteAllNotifications);
}

async function loadNotifications() {
  try {
    const res = await api("/api/settings/notifications");
    const notifications = res.data;
    const container = document.getElementById("notificationList");

    if (notifications.length === 0) {
      container.innerHTML =
        notificationActionHtml + '<p class="placeholder-text">알림이 없습니다.</p>';
      wireNotificationBulkActions(container);
      return;
    }

    const listHtml = notifications
      .map(
        (n) => `
      <div class="notification-item ${n.is_read ? "" : "unread"}" onclick="markNotificationRead(${n.id}, this)">
        <div>
          <span class="notification-type">[${n.type}]</span>
          ${n.message}
        </div>
        <span style="font-size:0.75rem;color:var(--text-muted);">${new Date(n.created_at).toLocaleDateString("ko-KR")}</span>
      </div>`
      )
      .join("");
    container.innerHTML = notificationActionHtml + listHtml;
    wireNotificationBulkActions(container);
  } catch {
    /* 무시 */
  }
}

async function markNotificationRead(id, el) {
  try {
    await api(`/api/settings/notifications/${id}/read`, { method: "PUT" });
    el.classList.remove("unread");
    loadNotificationCount();
  } catch {
    /* 무시 */
  }
}

async function markAllNotificationsRead() {
  if (!confirm("모든 알림을 읽음 처리할까요?")) return;
  try {
    const data = await api("/api/settings/notifications/read-all", { method: "PUT" });
    alert(`${data.updated ?? 0}개 알림 읽음 처리됨`);
    loadNotifications();
    loadNotificationCount();
  } catch (e) {
    showToast(e.message || "요청 실패", "error");
  }
}

async function deleteReadNotifications() {
  if (!confirm("읽은 알림을 모두 삭제할까요?")) return;
  try {
    const data = await api("/api/settings/notifications/read", { method: "DELETE" });
    alert(`${data.deleted ?? 0}개 삭제됨`);
    loadNotifications();
    loadNotificationCount();
  } catch (e) {
    showToast(e.message || "요청 실패", "error");
  }
}

async function deleteAllNotifications() {
  if (!confirm("⚠️ 모든 알림을 삭제합니다. 계속할까요?")) return;
  try {
    const data = await api("/api/settings/notifications/all", { method: "DELETE" });
    alert(`${data.deleted ?? 0}개 삭제됨`);
    loadNotifications();
    loadNotificationCount();
  } catch (e) {
    showToast(e.message || "요청 실패", "error");
  }
}

/* === LLM 연결 테스트 === */
const _keyInputMap = {
  openai: "settingOpenaiKey",
  claude: "settingClaudeKey",
  gemini: "settingGeminiKey",
  local: "settingLocalEndpoint",
  lmstudio: "settingLmstudioEndpoint",
};

document.querySelectorAll(".btn-test-llm").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const provider = btn.dataset.provider;
    const inputId = _keyInputMap[provider];
    const inputVal = inputId ? (document.getElementById(inputId)?.value || "") : "";

    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = "테스트 중...";
    btn.style.color = "";
    btn.style.borderColor = "";

    try {
      const body = { provider };
      if (inputVal) body.api_key = inputVal;
      const res = await api("/api/settings/test-llm", {
        method: "POST",
        body,
      });
      const d = res.data;
      if (d.connected) {
        btn.textContent = "✅ 연결 성공";
        btn.style.color = "#27ae60";
        btn.style.borderColor = "#27ae60";
      } else {
        btn.textContent = "❌ 연결 실패";
        btn.style.color = "#e74c3c";
        btn.style.borderColor = "#e74c3c";
        showToast(d.message, "error");
      }
    } catch (err) {
      btn.textContent = "❌ 오류";
      btn.style.color = "#e74c3c";
      btn.style.borderColor = "#e74c3c";
      showToast(`테스트 실패: ${err.message}`, "error");
    }

    setTimeout(() => {
      btn.textContent = originalText;
      btn.disabled = false;
      btn.style.color = "";
      btn.style.borderColor = "";
    }, 3000);
  });
});

/* === 스케줄러 토글 === */
const schedulerToggle = document.getElementById("schedulerToggle");
const schedulerInterval = document.getElementById("schedulerInterval");

async function loadSchedulerStatus() {
  try {
    const res = await api("/api/settings/scheduler");
    const d = res.data;
    if (schedulerToggle) schedulerToggle.checked = d.enabled;
    if (schedulerInterval) schedulerInterval.value = String(d.interval_hours);
    if (schedulerInterval) schedulerInterval.disabled = !d.enabled;
  } catch {
    /* 무시 */
  }
}

async function updateScheduler() {
  const enabled = schedulerToggle.checked;
  const interval = parseInt(schedulerInterval.value, 10) || 24;
  if (schedulerInterval) schedulerInterval.disabled = !enabled;

  try {
    await api("/api/settings/scheduler", {
      method: "POST",
      body: { enabled, interval_hours: interval },
    });
    showToast(enabled ? `자동 점검 활성화 (${interval}시간 주기)` : "자동 점검 비활성화", "success");
  } catch (err) {
    showToast(`스케줄러 설정 실패: ${err.message}`, "error");
  }
}

if (schedulerToggle) schedulerToggle.addEventListener("change", updateScheduler);
if (schedulerInterval) schedulerInterval.addEventListener("change", updateScheduler);
