/* === 작업실 탭 === */

const btnNewProject = document.getElementById("btnNewProject");

btnNewProject.addEventListener("click", () => {
  const name = prompt("새 프로젝트 이름을 입력하세요:");
  if (!name) return;
  const desc = prompt("프로젝트 설명 (선택):") || "";
  createProject(name, desc);
});

async function createProject(name, description) {
  try {
    const res = await api("/api/projects/", {
      method: "POST",
      body: { name, description },
    });
    showToast(`프로젝트 "${name}" 생성 완료!`, "success");
    loadProjects();
  } catch (err) {
    showToast(`생성 실패: ${err.message}`, "error");
  }
}

async function loadProjects() {
  try {
    const res = await api("/api/projects/");
    const projects = res.data;
    const container = document.getElementById("projectList");
    const detail = document.getElementById("projectDetail");
    detail.style.display = "none";

    if (projects.length === 0) {
      container.innerHTML = '<p class="placeholder-text">프로젝트가 없습니다. "새 프로젝트" 버튼을 클릭해보세요.</p>';
      return;
    }

    container.innerHTML = projects
      .map((p) => {
        const statusClass =
          p.status === "진행중" ? "ongoing" : p.status === "완료" ? "done" : "paused";
        return `
        <div class="project-card" onclick="showProjectDetail(${p.id})">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div class="project-name">${p.name}</div>
            <span class="status-badge ${statusClass}">${p.status}</span>
          </div>
          <div class="project-meta">
            ${p.description ? `<span>${p.description}</span> · ` : ""}
            <span>자료 ${p.material_count}개</span>
          </div>
        </div>`;
      })
      .join("");
  } catch (err) {
    showToast(`프로젝트 로드 실패: ${err.message}`, "error");
  }
}

async function showProjectDetail(projectId) {
  try {
    const res = await api(`/api/projects/${projectId}`);
    const p = res.data;
    const detail = document.getElementById("projectDetail");

    const materials = (p.materials || [])
      .map(
        (m) => `
      <div class="card" style="padding:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <strong>${m.title}</strong>
            <div style="font-size:0.8rem;color:var(--text-muted);">${m.category}${m.note ? " · " + m.note : ""}</div>
          </div>
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:0.78rem;"
            onclick="removeFromProject(${p.id}, ${m.id})">제거</button>
        </div>
      </div>`
      )
      .join("");

    const statusClass =
      p.status === "진행중" ? "ongoing" : p.status === "완료" ? "done" : "paused";

    detail.style.display = "block";
    detail.innerHTML = `
      <div class="settings-section" style="margin-top:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3>${p.name} <span class="status-badge ${statusClass}">${p.status}</span></h3>
          <div style="display:flex;gap:8px;">
            <button class="btn btn-secondary" onclick="addMaterialToProject(${p.id})">+ 자료 추가</button>
            <button class="btn btn-secondary" onclick="changeProjectStatus(${p.id})">상태 변경</button>
            <button class="btn btn-secondary" onclick="deleteProject(${p.id})">🗑️ 삭제</button>
          </div>
        </div>
        ${p.description ? `<p style="color:var(--text-secondary);margin-bottom:16px;">${p.description}</p>` : ""}
        <h4 style="margin-bottom:10px;">연결된 자료 (${p.material_count})</h4>
        <div class="card-list">${materials || '<p class="placeholder-text">연결된 자료가 없습니다.</p>'}</div>
      </div>`;
  } catch (err) {
    showToast(`프로젝트 상세 로드 실패: ${err.message}`, "error");
  }
}

let _addMatProjectId = null;

async function addMaterialToProject(projectId) {
  _addMatProjectId = projectId;
  const modal = document.getElementById("addMaterialModal");
  const listEl = document.getElementById("addMatList");
  const searchInput = document.getElementById("addMatSearchInput");
  searchInput.value = "";
  listEl.innerHTML = '<p class="placeholder-text">로딩 중...</p>';
  modal.style.display = "flex";
  await _loadAddMaterialList("");
}

async function _loadAddMaterialList(query) {
  const listEl = document.getElementById("addMatList");
  try {
    const params = new URLSearchParams({ page: "1", size: "50", status: "active" });
    if (query) params.set("q", query);
    const res = await api(`/api/library/materials?${params}`);
    const items = (res.data && res.data.items) || [];
    if (items.length === 0) {
      listEl.innerHTML = '<p class="placeholder-text">검색 결과가 없습니다.</p>';
      return;
    }
    listEl.innerHTML = items.map((m) => `
      <label class="add-mat-item" style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--border);cursor:pointer;">
        <input type="checkbox" value="${m.id}" class="add-mat-cb">
        <div style="flex:1;min-width:0;">
          <div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${m.title}</div>
          <div style="font-size:0.78rem;color:var(--text-muted);">${m.category_large} > ${m.category_medium} · ID: ${m.id}</div>
        </div>
      </label>
    `).join("");
  } catch (err) {
    listEl.innerHTML = `<p class="placeholder-text">로드 실패: ${err.message}</p>`;
  }
}

function closeAddMaterialModal() {
  document.getElementById("addMaterialModal").style.display = "none";
  _addMatProjectId = null;
}

document.getElementById("btnAddMatSearch").addEventListener("click", () => {
  _loadAddMaterialList(document.getElementById("addMatSearchInput").value.trim());
});
document.getElementById("addMatSearchInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") _loadAddMaterialList(e.target.value.trim());
});

document.getElementById("btnAddMatConfirm").addEventListener("click", async () => {
  if (!_addMatProjectId) return;
  const checked = document.querySelectorAll("#addMatList .add-mat-cb:checked");
  if (checked.length === 0) {
    showToast("자료를 선택하세요.", "info");
    return;
  }
  let successCount = 0;
  for (const cb of checked) {
    try {
      await api(`/api/projects/${_addMatProjectId}/materials`, {
        method: "POST",
        body: { material_id: parseInt(cb.value) },
      });
      successCount++;
    } catch (err) {
      showToast(`ID ${cb.value} 추가 실패: ${err.message}`, "error");
    }
  }
  if (successCount > 0) {
    showToast(`${successCount}개 자료 추가 완료!`, "success");
    showProjectDetail(_addMatProjectId);
  }
  closeAddMaterialModal();
});

async function removeFromProject(projectId, materialId) {
  try {
    await api(`/api/projects/${projectId}/materials/${materialId}`, {
      method: "DELETE",
    });
    showToast("자료 제거 완료", "success");
    showProjectDetail(projectId);
  } catch (err) {
    showToast(`제거 실패: ${err.message}`, "error");
  }
}

async function changeProjectStatus(projectId) {
  const status = prompt("새 상태를 입력하세요 (진행중 / 완료 / 보류):");
  if (!status) return;

  try {
    await api(`/api/projects/${projectId}`, {
      method: "PUT",
      body: { status },
    });
    showToast("상태 변경 완료!", "success");
    showProjectDetail(projectId);
  } catch (err) {
    showToast(`변경 실패: ${err.message}`, "error");
  }
}

async function deleteProject(projectId) {
  if (!confirm("정말 삭제하시겠습니까?")) return;

  try {
    await api(`/api/projects/${projectId}`, { method: "DELETE" });
    showToast("프로젝트 삭제 완료", "success");
    loadProjects();
  } catch (err) {
    showToast(`삭제 실패: ${err.message}`, "error");
  }
}
