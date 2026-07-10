/**
 * 역전 로또 (V11) 프론트엔드
 * 1군 lotto.js 통째 복제 + URL/ID/함수명 치환
 *
 * 원칙:
 * - 1군 lotto.js 0줄 수정 (SHA256 검증)
 * - 모든 API: /api/lotto3/v12/*
 * - 모든 DOM: #tab-lotto-army3, #lotto3-* 접두사
 * - 7뇌 한글명: 1군 동일 6뇌 + V11 뱀 합성두뇌 (v12_snake)
 * - brain_tag: v12_* (DB 분리)
 */

(function () {
  'use strict';

/* ═══════════════════════════════════════════
   로또 대시보드 JavaScript
   ═══════════════════════════════════════════ */

/* ── 로또 독립 유틸: app.js 의존 최소화 ── */
const _lottoResolveApiUrl = (typeof resolveApiUrl === 'function')
    ? resolveApiUrl
    : function(path) { return path; };

const BRAIN_DISPLAY_NAMES = {
  v12_stat: '🕰️ 시간여행자',
  v12_run: '🎯 사냥꾼',
  v12_offset: '🎼 리듬분석가',
  v12_combo: '🎓 지식박사',
  v12_lstm: '🔮 예언자',
  v12_fusion: '📋 작전본부장',
  v12_hyena: '🦊 하이에나',
  v12_snake: '🐍 뱀 합성두뇌',
  miss_analysis: '🔬 미당첨분석',
  snake: '🐍 뱀'
};

const BRAIN_DESCRIPTIONS = {
  v12_stat: '과거 학습 AI',
  v12_run: '연속 출현 추적',
  v12_offset: '간격·자기상관 분석',
  v12_combo: 'AI 자문위원',
  v12_lstm: '시계열 딥러닝 AI',
  v12_fusion: '두뇌 합의 AI',
  v12_hyena: '메타 최적화 AI',
  v12_snake: '1군과 차별화 합성뇌',
  miss_analysis: '사각지대 학습 AI',
  snake: '잔여 조합 AI'
};

function getBrainDisplayName(tag) {
  return BRAIN_DISPLAY_NAMES[tag] || tag;
}

function getBrainDescription(tag) {
  return BRAIN_DESCRIPTIONS[tag] || '';
}

// ── 탭 전환 ──
function switchLotto3Tab(tabName) {
  document.querySelectorAll('.lotto-tab-content').forEach((el) => { el.style.display = 'none'; });
  document.querySelectorAll('.lotto-sub-tab').forEach((el) => { el.classList.remove('active'); });
  const target = document.getElementById('lotto3-tab-' + tabName);
  if (target) target.style.display = 'block';
  const btn = document.querySelector(`[data-lotto3-tab="${tabName}"]`);
  if (btn) btn.classList.add('active');

  if (tabName === 'predictions') {
    initLottoDrawSearch();
  }
  if (tabName === 'stats') loadLotto3Stats();
  if (tabName === 'draws') loadLotto3Draws();
}

// ── 회차 검색 + 저장 예측(7두뇌 탭) ──
let _lottoDrawList = [];
let _lottoDrawDates = {};
let _lottoPredRowsCache = null;
let _currentBrainTab = 'v12_hyena';

const BRAIN_LIST = [
  { tag: 'v12_stat', name: '통계', icon: '📊', color: '#3b82f6' },
  { tag: 'v12_run', name: '사냥꾼', icon: '🎯', color: '#dc2626' },
  { tag: 'v12_offset', name: '리듬분석가', icon: '🎼', color: '#7c3aed' },
  { tag: 'v12_combo', name: 'LLM', icon: '🤖', color: '#f59e0b' },
  { tag: 'v12_lstm', name: 'LSTM', icon: '🧠', color: '#ef4444' },
  { tag: 'v12_fusion', name: '퓨전', icon: '⚡', color: '#8b5cf6' },
  { tag: 'v12_hyena', name: '하이에나', icon: '🦁', color: '#eab308' },
  { tag: 'v12_snake', name: '뱀', icon: '🐍', color: '#059669' },
];

function lottoFormatDow(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    const dows = ['일', '월', '화', '수', '목', '금', '토'];
    return dows[d.getDay()] || '';
  } catch (e) {
    return '';
  }
}

async function loadLottoDrawList() {
  try {
    const r = await fetch(resolveApiUrl('/api/lotto3/v12/predictions?limit=20000'));
    const data = await r.json();
    const rows = data && data.predictions ? data.predictions : [];
    _lottoPredRowsCache = rows;
    const set = new Set(rows.map((p) => p.target_draw_no).filter((n) => n != null));
    _lottoDrawList = Array.from(set).map((n) => parseInt(n, 10)).filter((n) => n > 0).sort((a, b) => b - a);

    const dr = await fetch(resolveApiUrl('/api/lotto3/v12/draws?limit=2000'));
    const dj = await dr.json();
    const draws = (dj && dj.draws) ? dj.draws : [];
    draws.forEach((d) => {
      if (d && d.draw_no) {
        _lottoDrawDates[parseInt(d.draw_no, 10)] = d.draw_date;
      }
    });

    refreshLotto3DrawSelectDom();
    return true;
  } catch (e) {
    console.error('회차 목록 로드 실패:', e);
    return false;
  }
}

/** `_lottoDrawList` 기준으로 드롭다운 옵션만 다시 채움 */
function refreshLotto3DrawSelectDom() {
  const sel = document.getElementById('lotto3DrawSelect');
  if (!sel || !_lottoDrawList.length) {
    return;
  }
  sel.innerHTML = _lottoDrawList.map((no) => {
    const date = _lottoDrawDates[no] || '?';
    const dow = lottoFormatDow(date);
    return `<option value="${no}">${no}회 (${date} ${dow})</option>`;
  }).join('');
}

/** 예측 직후 `_lottoDrawList`가 아직 비동기 갱신 전일 때 ◀▶가 깨지지 않도록 회차를 목록에 반영 */
function ensureDrawInNavList(drawNo) {
  const n = parseInt(drawNo, 10);
  if (!Number.isFinite(n) || n < 1) {
    return;
  }
  if (_lottoDrawList.indexOf(n) >= 0) {
    return;
  }
  _lottoDrawList.push(n);
  _lottoDrawList.sort((a, b) => b - a);
  refreshLotto3DrawSelectDom();
}

/**
 * 내림차순 `_lottoDrawList`에서 현재 회차의 네비 앵커 인덱스.
 * 목록에 없으면 삽입 위치(또는 미래 회차면 -1).
 */
function _lotto3ActiveDrawIndex(baseDraw) {
  const base = parseInt(baseDraw, 10);
  if (!_lottoDrawList.length || !Number.isFinite(base)) {
    return 0;
  }
  const arr = _lottoDrawList;
  const hit = arr.indexOf(base);
  if (hit >= 0) {
    return hit;
  }
  if (base > arr[0]) {
    return -1;
  }
  const last = arr[arr.length - 1];
  if (base < last) {
    return arr.length - 1;
  }
  let i = 0;
  while (i < arr.length && arr[i] > base) {
    i += 1;
  }
  return i;
}

function initLottoDrawSearch() {
  const sel = document.getElementById('lotto3DrawSelect');
  if (!sel) return;
  if (_lottoDrawList.length > 0) return;
  loadLottoDrawList().then(() => {
    if (!_lottoDrawList.length) return;
    const latest = _lottoDrawList[0];
    const input = document.getElementById('lotto3PredictDrawNo');
    if (input && !input.value) {
      input.value = latest;
      sel.value = String(latest);
      lottoLoadSavedPrediction(latest);
    }
  });
}

function lotto3SelectDraw(drawNo) {
  const no = parseInt(drawNo, 10);
  if (!no) return;
  const input = document.getElementById('lotto3PredictDrawNo');
  if (input) input.value = String(no);
  lottoLoadSavedPrediction(no);
}

function lotto3NavDraw(delta) {
  if (!_lottoDrawList.length) {
    loadLottoDrawList()
      .then(() => {
        if (_lottoDrawList.length) {
          lotto3NavDraw(delta);
        }
      })
      .catch(() => {});
    return;
  }
  const input = document.getElementById('lotto3PredictDrawNo');
  const sel = document.getElementById('lotto3DrawSelect');
  const cur = input ? parseInt(input.value, 10) : NaN;
  const base = Number.isFinite(cur) ? cur : _lottoDrawList[0];
  const navIdx = _lotto3ActiveDrawIndex(base);
  const step = delta > 0 ? -1 : 1; // 최신순: 오른쪽(▶)은 과거로
  let nextIdx;
  if (navIdx < 0) {
    if (step > 0) {
      nextIdx = 0;
    } else {
      return;
    }
  } else {
    nextIdx = Math.max(0, Math.min(_lottoDrawList.length - 1, navIdx + step));
  }
  const nextNo = _lottoDrawList[nextIdx];
  if (input) input.value = String(nextNo);
  if (sel) sel.value = String(nextNo);
  lottoLoadSavedPrediction(nextNo);
}

async function lottoLoadSavedPrediction(drawNo) {
  const container = document.getElementById('lotto3PredictionResults');
  if (!container) return;
  container.innerHTML = '<p style="color: #888;">로딩 중...</p>';
  try {
    if (!_lottoPredRowsCache) {
      await loadLottoDrawList();
    }
    const rows = (_lottoPredRowsCache || []).filter((p) => parseInt(p.target_draw_no, 10) === parseInt(drawNo, 10));
    if (!rows.length) {
      container.innerHTML = `<p style="color: #888;">${drawNo}회차 저장된 예측 없음. \"두뇌 예측\" 버튼으로 실행하세요.</p>`;
      return;
    }
    renderPredictionsByBrain(parseInt(drawNo, 10), rows);
  } catch (e) {
    container.innerHTML = `<p style="color: #f88;">로드 실패: ${e.message}</p>`;
  }
}

/** 인라인 onclick은 전역만 참조 가능 — 1군 `lottoSwitchBrainTab`과 충돌하지 않도록 별도 이름 */
function lotto3SwitchBrainTab(brainTag) {
  _currentBrainTab = String(brainTag || '').toLowerCase();
  const drawNo = parseInt(document.getElementById('lotto3PredictDrawNo').value, 10);
  if (drawNo) {
    lottoLoadSavedPrediction(drawNo);
  }
}

function lottoMiniBallBg(num) {
  const n = parseInt(num, 10);
  if (!n) return '#555';
  if (n <= 10) return '#fbc400';
  if (n <= 20) return '#69c8f2';
  if (n <= 30) return '#ff7272';
  if (n <= 40) return '#aaa';
  return '#b0d840';
}

function renderMiniBall(num, isHit, extraClass) {
  const n = parseInt(num, 10);
  const bg = lottoMiniBallBg(n);
  const hitClass = isHit ? 'is-hit' : '';
  const ex = extraClass ? String(extraClass) : '';
  return `<span class="lotto-mini-ball ${hitClass} ${ex}" style="background:${bg};">${n}</span>`;
}

function renderBrainSetCard(row, idx) {
  const nums = [row.num1, row.num2, row.num3, row.num4, row.num5, row.num6].map((n) => parseInt(n, 10));
  const matched = Number(row.matched_count);
  const bonus = Number(row.bonus_matched);

  let rank = '';
  let rankClass = 'rank-none';
  if (matched === 6) { rank = '🏆 1등!'; rankClass = 'rank-1'; }
  else if (matched === 5 && bonus === 1) { rank = '🥈 2등'; rankClass = 'rank-2'; }
  else if (matched === 5) { rank = '🥉 3등'; rankClass = 'rank-3'; }
  else if (matched === 4) { rank = '4등'; rankClass = 'rank-4'; }
  else if (matched === 3) { rank = '5등'; rankClass = 'rank-5'; }
  else if (matched >= 0) { rank = '미당첨'; rankClass = 'rank-none'; }
  else { rank = '추첨 전'; rankClass = 'rank-pending'; }

  const actuals = [row.actual_1, row.actual_2, row.actual_3, row.actual_4, row.actual_5, row.actual_6].filter((x) => x != null);
  const actualSet = new Set(actuals.map((n) => parseInt(n, 10)));

  const ballsHtml = nums.map((n) => renderMiniBall(n, actualSet.has(n))).join('');

  let conf = '-';
  if (row.confidence != null && row.confidence !== '') {
    const v = Number(row.confidence);
    if (Number.isFinite(v)) {
      // DB가 0~1 또는 이미 % (예: 97.9) 둘 다 대응
      conf = (v <= 1 ? (v * 100) : v).toFixed(1) + '%';
    }
  }

  const dzFlag =
    row.dz_filter_passed === false
      ? '<span class="dz-flag" title="Dead Zone: 저분산·중권·소수 패턴 보정">DZ</span>'
      : '';

  return `
    <div class="lotto-set-card ${rankClass}">
      <div class="lotto-set-header">
        <span class="lotto-set-idx">#${idx}</span>
        <span class="lotto-set-rank">${rank}</span>
        ${dzFlag}
        <span class="lotto-set-conf">신뢰도 ${conf}</span>
      </div>
      <div class="lotto-set-balls">${ballsHtml}</div>
    </div>
  `;
}

function renderPredictionsByBrain(drawNo, rows) {
  const container = document.getElementById('lotto3PredictionResults');
  if (!container) return;
  const date = _lottoDrawDates[drawNo] || '?';
  const dow = lottoFormatDow(date);
  const first = rows[0] || {};
  const hasActual = first.actual_1 != null;

  let actualHtml = '';
  if (hasActual) {
    const balls = [first.actual_1, first.actual_2, first.actual_3, first.actual_4, first.actual_5, first.actual_6];
    actualHtml = `
      <div class="lotto-actual-row">
        <span class="lotto-actual-label">실제 당첨번호:</span>
        <span class="lotto-actual-balls">
          ${balls.map((n) => renderMiniBall(n, false, 'is-actual')).join('')}
        </span>
        <span class="lotto-actual-bonus">+ 보너스 ${renderMiniBall(first.actual_bonus, false, 'is-actual is-bonus')}</span>
      </div>
    `;
  } else {
    actualHtml = '<div class="lotto-actual-row lotto-no-actual">아직 추첨 전입니다</div>';
  }

  const byBrain = {};
  rows.forEach((r) => {
    const tag = String(r.brain_tag || 'legacy').toLowerCase();
    if (!byBrain[tag]) byBrain[tag] = [];
    byBrain[tag].push(r);
  });

  if (!_currentBrainTab || _currentBrainTab === 'legacy') {
    _currentBrainTab = 'v12_hyena';
  }
  if (!byBrain[_currentBrainTab]) {
    const firstTag = Object.keys(byBrain)[0];
    _currentBrainTab = firstTag || 'v12_hyena';
  }

  const tabsHtml = BRAIN_LIST.map((b) => {
    const cnt = (byBrain[b.tag] || []).length;
    const active = b.tag === _currentBrainTab ? 'active' : '';
    const disabled = cnt === 0 ? 'disabled' : '';
    return `
      <button class="lotto-brain-tab ${active} ${disabled}"
              data-brain="${b.tag}"
              style="--brain-color: ${b.color};"
              onclick="lotto3SwitchBrainTab('${b.tag}')"
              ${disabled ? 'disabled' : ''}>
        <span class="lotto-brain-icon">${b.icon}</span>
        <span class="lotto-brain-name">${getBrainDisplayName(b.tag)}</span>
        <span class="lotto-brain-cnt">${cnt}</span>
      </button>
    `;
  }).join('');

  const selectedRows = byBrain[_currentBrainTab] || [];
  const cardsHtml = selectedRows.length
    ? selectedRows.map((r, i) => renderBrainSetCard(r, i + 1)).join('')
    : '<p style="color:#888; padding: 16px;">이 두뇌는 이 회차에 예측 데이터가 없습니다.</p>';

  container.innerHTML = `
    <div class="lotto-result-header">
      <h3>${drawNo}회 (${date} ${dow})</h3>
      ${actualHtml}
    </div>
    <div class="lotto-brain-tabs">${tabsHtml}</div>
    <div class="lotto-brain-cards" id="lottoBrainCards">${cardsHtml}</div>
  `;
}

/** ISO(YYYY-MM-DD) → 2026년4월25일 (엔진 `draw_date_for_draw_no`와 동일) */
function formatLottoDateKr(isoDate) {
  if (!isoDate || typeof isoDate !== 'string') {
    return '';
  }
  const p = isoDate.split('T')[0].split('-');
  if (p.length !== 3) {
    return isoDate;
  }
  const y = parseInt(p[0], 10);
  const m = parseInt(p[1], 10);
  const d = parseInt(p[2], 10);
  if (Number.isNaN(y) || Number.isNaN(m) || Number.isNaN(d)) {
    return isoDate;
  }
  return `${y}년${m}월${d}일`;
}

function lottoSetActionStatusText(el, text, color) {
  if (!el) {
    return;
  }
  el.className = 'lotto-action-status';
  el.textContent = text;
  el.style.color = color || '';
}

function lottoSetActionStatusNoNew(el, isoDate) {
  if (!el) {
    return;
  }
  const line2 = formatLottoDateKr(isoDate) || '다음 추첨일(추정)을 알 수 없습니다';
  el.className = 'lotto-action-status lotto-action-status--no-new';
  el.removeAttribute('style');
  el.innerHTML = '<div class="lotto-action-status__title">신규 회차 없음</div>'
    + '<div class="lotto-action-status__date">' + line2 + '</div>';
}

// ── 데이터 수집 (역전 전용 UI — API만 1군과 동일 `/api/lotto/*`, lotto_draws 공유) ──
async function lotto3FetchAll() {
  const status = document.getElementById('lotto3CollectStatus');
  const btn = document.getElementById('btnLotto3FetchAll');
  if (!status || !btn) return;
  btn.disabled = true;
  lottoSetActionStatusText(status, '힌트 불러오는 중…', '#f0c040');
  try {
    try {
      const hintRes = await fetch(resolveApiUrl('/api/lotto/collection-hint'));
      const hint = await hintRes.json();
      if (hint && hint.max_draw_no > 0) {
        lottoSetActionStatusText(
          status,
          '이미 로또 데이터가 있습니다(최대 ' + hint.max_draw_no + '회). "전체 데이터 수집"은 잠금 처리되었습니다. 필요 시 관리자에게 문의하세요.',
          '#f0c040',
        );
        alert('이미 과거 로또 데이터가 있어서 "전체 데이터 수집"은 잠금 처리되었습니다.');
        btn.disabled = false;
        return;
      }
      lottoSetActionStatusText(status, 'DB가 비어 있습니다. 전체 수집 요청 중…', '#f0c040');
    } catch (_hintErr) {
      lottoSetActionStatusText(status, '전체 수집 요청 중… (힌트 생략)', '#f0c040');
    }
    const res = await fetch(resolveApiUrl('/api/lotto/fetch-all'), { method: 'POST' });
    const data = await res.json();
    lottoSetActionStatusText(
      status,
      (data && data.message) ? data.message : '수집 시작됨. 완료 요약을 불러옵니다…',
      '#4ade80',
    );

    var attempts = 0;
    var poll = setInterval(async function() {
      attempts += 1;
      try {
        const lr = await fetch(resolveApiUrl('/api/lotto/last-fetch-all'));
        const j = await lr.json();
        var r = j && j.result;
        if (r && r.user_message) {
          if (r.status === 'running') {
            if (attempts >= 200) {
              clearInterval(poll);
              lottoSetActionStatusText(status, '응답이 지연되고 있습니다. 잠시 후 역전 탭 당첨 이력을 확인하세요.', '#f0c040');
              btn.disabled = false;
              loadLotto3Draws();
            }
            return;
          }
          clearInterval(poll);
          lottoSetActionStatusText(
            status,
            r.user_message,
            (r.ok === false) ? '#f87171' : (r.tail_unavailable > 0 && (r.fetched || 0) === 0) ? '#f0c040' : '#4ade80',
          );
          loadLotto3Draws();
          loadLotto3BrainStatus();
          loadLotto3Dashboard();
          btn.disabled = false;
          return;
        }
        if (attempts >= 200) {
          clearInterval(poll);
          lottoSetActionStatusText(status, '완료 요약을 가져오지 못했습니다. 역전 탭 당첨 이력을 확인하세요.', '#f0c040');
          loadLotto3Draws();
          loadLotto3BrainStatus();
          loadLotto3Dashboard();
          btn.disabled = false;
        }
      } catch (err) {
        clearInterval(poll);
        lottoSetActionStatusText(status, '상태 조회 실패: ' + err.message, '#f87171');
        btn.disabled = false;
      }
    }, 500);
  } catch (e) {
    lottoSetActionStatusText(status, '수집 실패: ' + e.message, '#f87171');
    btn.disabled = false;
  }
}

async function lotto3FetchLatest() {
  const status = document.getElementById('lotto3CollectStatus');
  if (!status) return;
  try {
    const res = await fetch(resolveApiUrl('/api/lotto/fetch-latest'), { method: 'POST' });
    const data = await res.json();
    if (data.draw) {
      lottoSetActionStatusText(status, `${data.draw.draw_no}회차 수집 완료!`, '#4ade80');
      loadLotto3Draws();
      loadLotto3Dashboard();
    } else {
      const iso = data && data.next_draw_date;
      if (iso) {
        lottoSetActionStatusNoNew(status, iso);
      } else {
        try {
          const hRes = await fetch(resolveApiUrl('/api/lotto/collection-hint'));
          const hint = await hRes.json();
          if (hint && hint.next_draw_date) {
            lottoSetActionStatusNoNew(status, hint.next_draw_date);
          } else {
            lottoSetActionStatusText(status, '신규 회차 없음', 'var(--text-secondary)');
          }
        } catch (_hintEx) {
          lottoSetActionStatusText(status, '신규 회차 없음', 'var(--text-secondary)');
        }
      }
    }
  } catch (e) {
    lottoSetActionStatusText(status, '수집 실패: ' + e.message, '#f87171');
  }
}


// ── 두뇌 예측 ──
async function lotto3Predict() {
  const input = document.getElementById('lotto3PredictDrawNo');
  const drawNo = parseInt(input.value, 10);
  if (!drawNo || drawNo < 1) {
    alert('회차 번호를 입력하세요.');
    return;
  }
  const status = document.getElementById('lotto3ActionStatus');
  lottoSetActionStatusText(status, '두뇌 풀가동 중... (약 30초~1분)', '#f0c040');

  try {
    const res = await fetch(resolveApiUrl(`/api/lotto3/v12/predict/${drawNo}`), { method: 'POST' });
    const data = await res.json();

    if (data.error) {
      lottoSetActionStatusText(status, data.error, '#f87171');
      return;
    }
    if (data.status === 'error') {
      lottoSetActionStatusText(status, data.reason || '예측 오류', '#f87171');
      return;
    }

    lottoSetActionStatusText(status, `${drawNo}회차 예측 완료!`, '#4ade80');
    // 업그레이드 UI(회차 드롭다운)가 있으면 7두뇌 탭 렌더만 사용(깜빡임 방지)
    const sel = document.getElementById('lotto3DrawSelect');
    if (!sel) {
      renderPredictions(data);
    }
    try {
      // 업그레이드 UI에서는 캐시를 기다리지 말고, 응답(data)로 즉시 렌더한다.
      if (sel) {
        const rawPreds = Array.isArray(data.all_predictions) ? data.all_predictions : [];
        const actuals = Array.isArray(data.actual_numbers) ? data.actual_numbers : null;
        const bonus = (data.actual_bonus != null) ? data.actual_bonus : null;

        let rows;
        if (rawPreds.length > 0) {
          rows = rawPreds.map((p) => {
            const nums = p.nums || [];
            const base = {
              target_draw_no: drawNo,
              method: p.method,
              brain_tag: p.brain_tag,
              confidence: p.confidence,
              reasoning: p.reasoning,
              matched_count: p.matched_count,
              bonus_matched: p.bonus_matched,
              num1: nums[0],
              num2: nums[1],
              num3: nums[2],
              num4: nums[3],
              num5: nums[4],
              num6: nums[5],
            };
            if (p.dz_var != null) base.dz_var = p.dz_var;
            if (p.dz_prime_cnt != null) base.dz_prime_cnt = p.dz_prime_cnt;
            if (p.dz_z3_cnt != null) base.dz_z3_cnt = p.dz_z3_cnt;
            if (p.dz_delta_conf != null) base.dz_delta_conf = p.dz_delta_conf;
            if (p.dz_filter_passed != null) base.dz_filter_passed = p.dz_filter_passed;
            if (actuals && actuals.length === 6) {
              base.actual_1 = actuals[0];
              base.actual_2 = actuals[1];
              base.actual_3 = actuals[2];
              base.actual_4 = actuals[3];
              base.actual_5 = actuals[4];
              base.actual_6 = actuals[5];
              base.actual_bonus = bonus;
            }
            return base;
          });
        } else {
          // ok 응답은 all_predictions 포함. cached·구버전만 목록 API로 채움
          await loadLottoDrawList();
          rows = (_lottoPredRowsCache || []).filter((p) => parseInt(p.target_draw_no, 10) === drawNo);
        }

        if (!rows.length) {
          lottoSetActionStatusText(
            status,
            `${drawNo}회차: 서버에는 반영됐으나 예측 세트를 화면에 불러오지 못했습니다. 새로고침 후 당첨 이력·예측 목록을 확인하세요.`,
            '#f87171',
          );
          return;
        }

        // 캐시에도 해당 회차를 즉시 반영(다음 렌더/탭 전환 일관성)
        _lottoPredRowsCache = (_lottoPredRowsCache || []).filter((p) => parseInt(p.target_draw_no, 10) !== drawNo);
        _lottoPredRowsCache = rows.concat(_lottoPredRowsCache);

        ensureDrawInNavList(drawNo);
        if (sel) sel.value = String(drawNo);

        renderPredictionsByBrain(drawNo, rows);

        if (rawPreds.length > 0) {
          loadLottoDrawList().then(() => {
            if (sel) sel.value = String(drawNo);
          }).catch(() => {});
        }
      } else {
        // 기존 UI는 원래 흐름 유지
        await loadLottoDrawList();
        await lottoLoadSavedPrediction(drawNo);
      }
    } catch (e2) {
      // 무시 (기존 렌더는 이미 완료)
    }
    loadLotto3BrainStatus();
  } catch (e) {
    lottoSetActionStatusText(status, '예측 실패: ' + e.message, '#f87171');
  }
}

/** 예측 세트 1개 카드 (Top5 / 최다 적중 공용) */
function renderLottoPredCard(pred, rankLabel, data, options) {
  const opts = options || {};
  const nums = pred.nums || [pred.num1, pred.num2, pred.num3, pred.num4, pred.num5, pred.num6];
  const matched = pred.matched_count >= 0 ? pred.matched_count : null;
  const tag = String(pred.brain_tag || '').toLowerCase();
  const dn = tag ? getBrainDisplayName(tag) : '';
  const dd = tag ? getBrainDescription(tag) : '';
  const method = pred.method || '알수없음';
  const brainText = dn ? (dn + (dd ? ' (' + dd + ')' : '')) : method;
  const confidence = pred.confidence || 0;
  const matchColor = matched === null ? '#666' :
    matched >= 5 ? '#ffd700' :
      matched >= 4 ? '#ff6b6b' :
        matched >= 3 ? '#4ade80' : '#666';
  const leftBar = opts.emphasize ? '#2ed573' : matchColor;
  let h = '';
  h += '<div style="background: #1e1e3a; border-left: 4px solid ' + leftBar + '; border-radius: 8px; padding: 14px; margin-bottom: 10px;">';
  h += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
  h += '<span style="color: #8b9cf7; font-weight: bold;">' + rankLabel + ' ' + brainText + '</span>';
  h += '<span style="color: #aaa; font-size: 12px;">신뢰도: ' + confidence + '%</span>';
  h += '</div>';
  h += '<div style="margin-bottom: 6px;">';
  nums.forEach((n) => {
    const isM = data.actual_numbers && data.actual_numbers.indexOf(n) >= 0;
    h += renderBall(n, isM, isM ? { role: 'hit' } : undefined);
  });
  h += '</div>';
  if (matched !== null && matched >= 0) {
    let rankText = '';
    if (matched === 6) { rankText = '🏆 1등!!! (6개 전체 적중)'; } else if (matched === 5 && pred.bonus_matched) { rankText = '🥈 2등! (5개 + 보너스)'; } else if (matched === 5) { rankText = '🥉 3등! (5개 적중)'; } else if (matched === 4) { rankText = '🎯 4등 (4개 적중)'; } else if (matched === 3) { rankText = '✅ 5등 (3개 적중)'; } else { rankText = matched + '개 적중 (등수 외)'; }
    h += '<div style="font-size: 13px; color: ' + matchColor + '; font-weight: bold;">' + rankText + '</div>';
  }
  if (pred.reasoning) {
    h += '<div style="font-size: 12px; color: #888; margin-top: 4px;">' + pred.reasoning + '</div>';
  }
  h += '</div>';
  return h;
}

function renderPredictions(data) {
  const container = document.getElementById('lotto3PredictionResults');
  let html = `<h3 style="color: #e0e0ff;">${data.target_draw_no}회차 예측 결과</h3>`;

  if (data.status && data.status.includes('기존')) {
    html += `<p style="color: #f0c040; font-size: 13px;">ℹ️ ${data.status}</p>`;
  }

  if (data.actual_numbers) {
    const sorted = [...data.actual_numbers].sort((a, b) => a - b);
    html += `<div style="background: #2d1b69; padding: 12px; border-radius: 8px; margin-bottom: 16px;">`;
    html += `<span style="color: #ffd700; font-weight: bold;">실제 당첨번호: </span>`;
    sorted.forEach((n) => {
      html += renderBall(n, true, { role: 'winning' });
    });
    if (data.actual_bonus != null && data.actual_bonus !== undefined) {
      html += `<span style="color: #888; margin: 0 6px;">+</span>`;
      html += '<span style="color: #ffd700; font-size: 12px; margin-right: 4px;">보너스</span>';
      html += renderBall(data.actual_bonus, true, { role: 'winning' });
    }
    html += `</div>`;
  }

  const totalN = data.total_sets || (data.predictions && data.predictions.length) || 0;
  // 당첨이 있을 때: Top5는 '신뢰도' 기준이라, 적중 개수가 가장 많은 세트(예: 5등)가 6~15위에 있으면 여기 안 나옴(명예의 전당과 달리 보이는 이유)
  if (data.actual_numbers && data.all_predictions && data.all_predictions.length) {
    const aps = data.all_predictions;
    const counts = aps.map((p) => (p.matched_count != null && p.matched_count >= 0 ? p.matched_count : 0));
    const maxM = Math.max(0, ...counts);
    if (maxM > 0) {
      const bestPreds = aps.filter((p) => p.matched_count != null && p.matched_count === maxM);
      if (bestPreds.length) {
        html += `<p style="color: #a8e6cf; font-size: 13px; margin: 0 0 8px 0;">🎯 이 회차 <b>최다 적중</b> (총 15세트 기준) — <span style="color: #9a9ab0; font-weight: normal;">적중 ${maxM}개(동률이면 여러 줄). <b>신뢰도 1~5위 밖</b>일 수 있음</span></p>`;
        bestPreds.forEach((pred, i) => {
          const rlab = bestPreds.length > 1 ? '최다' + (i + 1) : '최다';
          html += renderLottoPredCard(pred, rlab, data, { emphasize: true });
        });
        html += '<hr style="border: 0; border-top: 1px solid #333; margin: 12px 0;" />';
      }
    }
  }
  html += `<p style="color: #aaa; font-size: 13px;">🏅 <b>신뢰도</b> 상위 5세트 (총 ${totalN}세트 중) — 3개 이상 맞힌 세트는 <b>최다 적중</b> 블록에 있을 수 있고, 여기(#1~#5)엔 없을 수 있음</p>`;

  const top5 = data.top5 || (data.predictions && data.predictions.slice(0, 5)) || [];
  top5.forEach((pred, i) => {
    html += renderLottoPredCard(pred, '#' + (i + 1), data, {});
  });

  container.innerHTML = html;
}

/**
 * @param {number} num
 * @param {boolean} highlighted
 * @param {{ role?: 'hit' | 'winning' }} [opt] — hit: 예측↔당첨 일치(최강), winning: 당첨 요약 행
 */
function renderBall(num, highlighted, opt) {
  const role = (opt && opt.role) || null;
  const colors = {
    1: '#fbc400', 11: '#69c8f2', 21: '#ff7272',
    31: '#aaa', 41: '#b0d840',
  };
  let bg = '#555';
  const keys = Object.keys(colors).map((k) => parseInt(k, 10)).sort((a, b) => b - a);
  for (const start of keys) {
    if (num >= start) {
      bg = colors[start];
      break;
    }
  }
  const base =
    'display: inline-flex; align-items: center; justify-content: center; ' +
    'border-radius: 50%; color: #000; font-weight: bold; margin: 3px; ' +
    'vertical-align: middle; box-sizing: border-box;';

  // 예측 번호가 실제 당첨과 겹칠 때(가독성 최우선)
  if (role === 'hit' && highlighted) {
    var redHit = opt && opt.red_hit_border;
    var hitBorder = redHit
      ? 'border: 3px solid #e53935; box-shadow: 0 0 0 1px rgba(229,57,53,0.5), 0 0 12px rgba(229,57,53,0.45); '
      : 'border: 3px solid #fff; ' +
        'box-shadow: 0 0 0 2px #f5c400, 0 0 0 5px rgba(46,213,115,0.55), 0 0 22px 4px rgba(255,220,100,0.9); ';
    return (
      '<span style="' + base + ' ' +
      'width: 42px; height: 42px; font-size: 16px; background: ' + bg + '; ' +
      hitBorder +
      'transform: scale(1.1); z-index: 1; position: relative;' +
      '" title="당첨번호와 일치">' +
      num +
      '</span>'
    );
  }

  // «실제 당첨번호» 요약 행(전체 6+보너스) — 눈에 띄게, 적중 강조보다는 덜
  if (role === 'winning' || (highlighted && !role)) {
    return (
      '<span style="' + base + ' ' +
      'width: 38px; height: 38px; font-size: 15px; background: ' + bg + '; ' +
      'border: 2px solid rgba(255, 215, 0, 0.95); ' +
      'box-shadow: 0 0 14px rgba(255, 200, 80, 0.55), inset 0 0 8px rgba(255,255,255,0.15);' +
      '">' +
      num +
      '</span>'
    );
  }

  return (
    '<span style="' + base + ' ' +
    'width: 36px; height: 36px; font-size: 14px; background: ' + bg + '; ' +
    'border: 2px solid transparent;">' +
    num +
    '</span>'
  );
}

// ── 두뇌 상태 ──
async function loadLotto3BrainStatus() {
  try {
    var res = await fetch(resolveApiUrl('/api/lotto3/v12/brain/status'));
    var data = await res.json();

    document.getElementById('lotto3BrainGrade').textContent = data.grade_emoji || '🧠';
    document.getElementById('lotto3BrainGradeText').textContent = '두뇌 등급: ' + (data.grade || '일반');

    // 기본 통계
    var statsHtml = '총 예측: ' + (data.total_predictions || 0) + '건 | 최고 기록: ';
    if (data.best_record) {
      var mc = data.best_record.matched_count;
      var bm = data.best_record.bonus_matched;
      var bestRank = '';
      if (mc === 6) bestRank = '🏆 1등';
      else if (mc === 5 && bm) bestRank = '🥈 2등';
      else if (mc === 5) bestRank = '🥉 3등';
      else if (mc === 4) bestRank = '🎯 4등';
      else if (mc === 3) bestRank = '✅ 5등';
      else bestRank = mc + '개 적중';
      statsHtml += bestRank + ' (' + data.best_record.target_draw_no + '회차, ' + data.best_record.method + ')';
    } else {
      statsHtml += '없음';
    }
    document.getElementById('lotto3BrainStats').innerHTML = statsHtml;

    // 3종 두뇌별 성적 비교 카드
    var profileDiv = document.getElementById('lotto3BrainProfiles');
    if (profileDiv && data.brain_profiles && data.brain_profiles.length > 0) {
      var pHtml = '';
      data.brain_profiles.forEach(function(bp) {
        var icon = '🧠';
        if (bp.method === '통계두뇌') icon = '📊';
        else if (bp.method === 'LLM두뇌') icon = '🤖';
        else if (bp.method === '하이브리드두뇌') icon = '⚡';
        else if (bp.brain_tag === 'v12_snake' || bp.method === 'v12_snake') icon = '🐍';

        var barWidth = Math.min(Math.round((bp.avg_match || 0) / 3 * 100), 100);
        var barColor = bp.best_match >= 3 ? '#4ade80' : bp.best_match >= 2 ? '#f0c040' : '#666';
        var profileLabel = (bp.brain_tag === 'v12_snake')
          ? '뱀 합성두뇌'
          : (bp.method || '');

        pHtml += '<div style="background: #1e1e3a; border-radius: 8px; padding: 12px; flex: 1; min-width: 200px;">';
        pHtml += '<div style="font-size: 18px; margin-bottom: 6px;">' + icon + ' <span style="color: #e0e0ff; font-weight: bold;">' + profileLabel + '</span></div>';
        pHtml += '<div style="color: #aaa; font-size: 13px;">예측: ' + (bp.total_predictions || 0) + '건</div>';
        pHtml += '<div style="color: #aaa; font-size: 13px;">평균 적중: ' + (bp.avg_match || 0).toFixed(2) + '개</div>';
        pHtml += '<div style="color: #aaa; font-size: 13px;">최고 적중: ' + (bp.best_match || 0) + '개</div>';
        pHtml += '<div style="background: #333; border-radius: 4px; height: 8px; margin-top: 6px;">';
        pHtml += '<div style="background: ' + barColor + '; width: ' + barWidth + '%; height: 100%; border-radius: 4px;"></div>';
        pHtml += '</div>';
        pHtml += '</div>';
      });
      profileDiv.innerHTML = pHtml;
    }

  } catch (e) {
    console.warn('두뇌 상태 로드 실패:', e);
  }
}

// ── 명예의 전당 ──
// === 명예의전당 전역 변수 ===
var _fameAllData = [];
var _fameCurrentRank = 'all';
var _fameShowCount = {};  // 두뇌별 표시 건수

/** 인라인 onclick 대신 위임 — 1군 전역 `fameFilterRank`와 충돌·캐시 이슈 방지 */
function ensureLotto3FameClickDelegation() {
  if (window._lotto3FameDelegationBound) {
    return;
  }
  var root = document.getElementById('lotto3HallOfFame');
  if (!root) {
    return;
  }
  window._lotto3FameDelegationBound = true;
  root.addEventListener('click', function (ev) {
    var filterBtn = ev.target && ev.target.closest && ev.target.closest('[data-lotto3-fame-rank]');
    if (filterBtn && root.contains(filterBtn)) {
      var rank = filterBtn.getAttribute('data-lotto3-fame-rank');
      if (rank != null) {
        fameFilterRank(rank);
      }
      ev.preventDefault();
      return;
    }
    var moreBtn = ev.target && ev.target.closest && ev.target.closest('[data-lotto3-fame-brain]');
    if (moreBtn && root.contains(moreBtn)) {
      var brain = moreBtn.getAttribute('data-lotto3-fame-brain');
      if (brain) {
        fameShowMore(brain);
      }
      ev.preventDefault();
    }
  });
}

async function loadLotto3HallOfFame() {
  try {
    ensureLotto3FameClickDelegation();
    const res = await fetch(resolveApiUrl('/api/lotto3/v12/brain/hall-of-fame?limit=25000'));
    const data = await res.json();
    _fameAllData = data.hall_of_fame || [];
    _fameCurrentRank = '1';
    _fameShowCount = {};
    renderHallOfFame();
  } catch (e) {
    console.warn('명예의 전당 로드 실패:', e);
  }
}

function getFameRank(mc, bm) {
  // JSON/SQLite에서 숫자가 문자열로 올 수 있음 — 엄격 비교(===)만 쓰면 5등 집계가 0으로 떨어짐
  var m = Number(mc);
  var b = Number(bm);
  if (m === 6) return '1';
  if (m === 5 && b === 1) return '2';
  if (m === 5) return '3';
  if (m === 4) return '4';
  if (m === 3) return '5';
  return '0';
}

function getFameRankText(rank) {
  var map = { '1': '🏆 1등!!!', '2': '🥈 2등!', '3': '🥉 3등!', '4': '🎯 4등', '5': '✅ 5등' };
  return map[rank] || '';
}

function getFameRankColor(rank) {
  var map = { '1': '#ffd700', '2': '#c0c0c0', '3': '#ff6b6b', '4': '#ff6b6b', '5': '#4ade80' };
  return map[rank] || '#888';
}

function renderHallOfFame() {
  var container = document.getElementById('lotto3HallOfFame');
  if (!_fameAllData.length) {
    container.innerHTML = '<p class="fame-empty">🏆 3개 이상 적중한 예측이 없습니다. (V11 백테스트·예측 데이터 확인)</p>';
    return;
  }

  // 필터링
  var filtered = _fameAllData;
  if (_fameCurrentRank !== 'all') {
    filtered = _fameAllData.filter(function(r) {
      return getFameRank(r.matched_count, r.bonus_matched) === _fameCurrentRank;
    });
  }

  // 등수별 건수 계산 (필터바 표시용)
  var rankCounts = { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 };
  _fameAllData.forEach(function(r) {
    var rk = getFameRank(r.matched_count, r.bonus_matched);
    if (rankCounts[rk] !== undefined) rankCounts[rk]++;
  });
  var totalCount = _fameAllData.length;

  // 필터 바
  var html = '<div class="fame-filter-bar">';
  var ranks = [
    { key: 'all', label: '전체 (' + totalCount + ')' },
    { key: '1', label: '1등 (' + rankCounts['1'] + ')' },
    { key: '2', label: '2등 (' + rankCounts['2'] + ')' },
    { key: '3', label: '3등 (' + rankCounts['3'] + ')' },
    { key: '4', label: '4등 (' + rankCounts['4'] + ')' },
    { key: '5', label: '5등 (' + rankCounts['5'] + ')' }
  ];
  ranks.forEach(function(rk) {
    var active = _fameCurrentRank === rk.key ? ' active' : '';
    html += '<button type="button" class="fame-filter-btn' + active + '" data-lotto3-fame-rank="' + rk.key + '">' + rk.label + '</button>';
  });
  html += '</div>';

  // 6컬럼 그리드
  var brains = ['v12_stat', 'v12_run', 'v12_offset', 'v12_combo', 'v12_lstm', 'v12_fusion', 'v12_hyena', 'v12_snake'];
  html += '<div class="fame-grid">';

  brains.forEach(function(brain) {
    var brainData = filtered.filter(function(r) {
      return (r.brain_tag || '').toLowerCase() === brain;
    });
    // 최신순 정렬
    brainData.sort(function(a, b) { return (b.target_draw_no || 0) - (a.target_draw_no || 0); });

    var showKey = brain + '_' + _fameCurrentRank;
    if (!_fameShowCount[showKey]) _fameShowCount[showKey] = 20;
    var limit = _fameShowCount[showKey];
    var showing = brainData.slice(0, limit);

    html += '<div class="fame-column">';
    // 헤더
    html += '<div class="fame-col-header">';
    html += '<div class="brain-name">' + getBrainDisplayName(brain) + '</div>';
    html += '<div class="brain-desc">' + getBrainDescription(brain) + '</div>';
    html += '<div class="fame-count">' + brainData.length + '건</div>';
    html += '</div>';

    if (showing.length === 0) {
      html += '<div class="fame-empty">(없음)</div>';
    }

    showing.forEach(function(record) {
      var rank = getFameRank(record.matched_count, record.bonus_matched);
      var rankClass = 'fame-card rank-' + rank;
      var rankColor = getFameRankColor(rank);

      var predNums = [record.num1, record.num2, record.num3, record.num4, record.num5, record.num6];
      var actNums = [record.actual_1, record.actual_2, record.actual_3, record.actual_4, record.actual_5, record.actual_6].filter(function(n) { return n != null; });
      var actBonus = record.actual_bonus || null;
      var actSet = {};
      actNums.forEach(function(n) {
        actSet[n] = true;
        actSet[String(n)] = true;
      });
      var drawDate = record.draw_date ? ' (' + record.draw_date + ')' : '';

      html += '<div class="' + rankClass + '">';
      // 헤더
      html += '<div class="card-header">';
      html += '<span class="draw-info">' + record.target_draw_no + '회' + drawDate + '</span>';
      html += '<span class="rank-badge" style="color:' + rankColor + '">' + getFameRankText(rank) + '</span>';
      html += '</div>';
      // 예측 번호
      html += '<div class="nums-row"><span class="label">예측: </span>';
      predNums.forEach(function(n) {
        var isMatch = actSet[n] === true || actSet[String(n)] === true;
        html += renderBall(n, isMatch, isMatch ? { role: 'hit' } : undefined);
      });
      html += '</div>';
      // 당첨 번호
      if (actNums.length > 0) {
        html += '<div class="nums-row"><span class="label">당첨: </span>';
        actNums.forEach(function(n) {
          html += renderBall(n, true, { role: 'winning' });
        });
        if (actBonus) {
          html += '<span style="color:#aaa;margin:0 2px">+</span>';
          html += renderBall(actBonus, true, { role: 'winning' });
        }
        html += '</div>';
      }
      // 푸터 (DB가 0~1 또는 이미 % 인 경우 모두 표시)
      html += '<div class="card-footer">';
      var confFoot = '-';
      if (record.confidence != null && record.confidence !== '') {
        var cf = Number(record.confidence);
        if (isFinite(cf)) {
          confFoot = (cf <= 1 ? cf * 100 : cf).toFixed(1) + '%';
        }
      }
      html += '<span>신뢰도 ' + confFoot + '</span>';
      html += '</div>';
      html += '</div>';
    });

    // 더보기 버튼
    if (brainData.length > limit) {
      var remaining = brainData.length - limit;
      html += '<button type="button" class="fame-more-btn" data-lotto3-fame-brain="' + brain + '">+ 더보기 (' + remaining + '건 남음)</button>';
    }

    html += '</div>';
  });

  html += '</div>';
  container.innerHTML = html;
}

function fameFilterRank(rank) {
  _fameCurrentRank = rank;
  _fameShowCount = {};
  renderHallOfFame();
}

function fameShowMore(brain) {
  var showKey = brain + '_' + _fameCurrentRank;
  _fameShowCount[showKey] = (_fameShowCount[showKey] || 20) + 20;
  renderHallOfFame();
}

// ── 통계 분석 ──
async function loadLotto3Stats() {
  try {
    const res = await fetch(resolveApiUrl('/api/lotto3/v12/stats/comprehensive'));
    const data = await res.json();

    if (data.error) {
      document.getElementById('lotto3FreqChart').innerHTML = `<p style="color: #f87171;">${data.error}</p>`;
      return;
    }

    renderFreqChart(data.frequency);
    renderOddEvenChart(data.odd_even);
    renderRangeChart(data.range_distribution);
    renderSumChart(data.sum_range);
    renderPairChart(data.pair_frequency);
  } catch (e) {
    console.warn('통계 로드 실패:', e);
  }
}

function renderFreqChart(freq) {
  const container = document.getElementById('lotto3FreqChart');
  if (!freq) { container.innerHTML = '데이터 없음'; return; }

  const values = Object.values(freq).map((v) => v.count || 0);
  const maxCount = values.length > 0 ? Math.max.apply(null, values) : 1;

  let html = '<div style="display: flex; flex-wrap: wrap; gap: 4px;">';
  for (let n = 1; n <= 45; n += 1) {
    const info = freq[n] || freq[String(n)] || { count: 0 };
    const count = info.count || 0;
    const intensity = Math.round((count / Math.max(maxCount, 1)) * 255);
    const bg = `rgb(${intensity}, ${Math.round(intensity * 0.6)}, ${255 - intensity})`;
    html += `<div style="width: 48px; text-align: center; padding: 4px; border-radius: 6px; background: ${bg}; color: #fff; font-size: 11px;"
                  title="${n}번: ${count}회 출현">
              <div style="font-weight: bold;">${n}</div>
              <div>${count}</div>
            </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

function renderOddEvenChart(data) {
  const container = document.getElementById('lotto3OddEvenChart');
  if (!data) { container.innerHTML = '데이터 없음'; return; }

  let html = '';
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = entries.length > 0 ? entries[0][1] : 1;
  entries.forEach(([pattern, count]) => {
    const width = Math.round((count / max) * 100);
    html += `<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <span style="min-width: 70px; color: #aaa; font-size: 13px;">${pattern}</span>
              <div style="flex: 1; background: #333; border-radius: 4px; height: 20px;">
                <div style="width: ${width}%; background: #8b9cf7; border-radius: 4px; height: 100%;"></div>
              </div>
              <span style="color: #ccc; font-size: 12px; min-width: 40px;">${count}회</span>
            </div>`;
  });
  container.innerHTML = html;
}

function renderRangeChart(data) {
  const container = document.getElementById('lotto3RangeChart');
  if (!data) { container.innerHTML = '데이터 없음'; return; }

  let html = '';
  const vals = Object.values(data);
  const max = vals.length > 0 ? Math.max.apply(null, vals) : 1;
  Object.entries(data).forEach(([range, count]) => {
    const width = Math.round((count / max) * 100);
    html += `<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <span style="min-width: 50px; color: #aaa; font-size: 13px;">${range}</span>
              <div style="flex: 1; background: #333; border-radius: 4px; height: 20px;">
                <div style="width: ${width}%; background: #4ade80; border-radius: 4px; height: 100%;"></div>
              </div>
              <span style="color: #ccc; font-size: 12px; min-width: 50px;">${count}회</span>
            </div>`;
  });
  container.innerHTML = html;
}

function renderSumChart(data) {
  const container = document.getElementById('lotto3SumChart');
  if (!data) { container.innerHTML = '데이터 없음'; return; }

  const html = `<p style="color: #ccc; font-size: 14px;">
    평균 합계: <b style="color: #ffd700;">${data.average}</b> |
    최소: ${data.min} | 최대: ${data.max}
  </p>`;
  container.innerHTML = html;
}

function renderPairChart(pairs) {
  const container = document.getElementById('lotto3PairChart');
  if (!pairs || pairs.length === 0) { container.innerHTML = '데이터 없음'; return; }

  let html = '<div style="display: flex; flex-wrap: wrap; gap: 6px;">';
  pairs.slice(0, 30).forEach((p) => {
    html += `<span style="background: #2a2a4e; padding: 4px 10px; border-radius: 12px; color: #ccc; font-size: 12px;">
              ${p.pair[0]}-${p.pair[1]} (${p.count}회)
            </span>`;
  });
  html += '</div>';
  container.innerHTML = html;
}

// ── 당첨 이력 ──
async function loadLotto3Draws() {
  try {
    const res = await fetch(resolveApiUrl('/api/lotto3/v12/draws?limit=50'));
    const data = await res.json();
    const container = document.getElementById('lotto3DrawsList');

    if (!data.draws || data.draws.length === 0) {
      container.innerHTML = '<p style="color: #888;">데이터가 없습니다. "전체 데이터 수집"을 먼저 실행하세요.</p>';
      return;
    }

    let html = `<p style="color: #aaa; margin-bottom: 12px;">총 ${data.total}회차 저장됨 (최근 50개 표시)</p>`;
    html += '<div style="max-height: 500px; overflow-y: auto;">';

    data.draws.forEach((d) => {
      html += `<div style="display: flex; align-items: center; gap: 12px; padding: 8px; border-bottom: 1px solid #333;">`;
      html += `<span style="color: #8b9cf7; font-weight: bold; min-width: 70px;">${d.draw_no}회</span>`;
      html += `<span style="color: #888; min-width: 90px; font-size: 12px;">${d.draw_date}</span>`;
      [d.num1, d.num2, d.num3, d.num4, d.num5, d.num6].forEach((n) => {
        html += renderBall(n, false);
      });
      html += `<span style="color: #888; font-size: 11px;">+</span>`;
      html += renderBall(d.bonus, false);
      if (d.first_prize) {
        html += `<span style="color: #aaa; font-size: 11px; margin-left: 8px;">1등: ${(d.first_prize / 100000000).toFixed(1)}억</span>`;
      }
      html += `</div>`;
    });

    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    console.warn('당첨 이력 로드 실패:', e);
  }
}

// ── 초기화 ──
document.addEventListener('DOMContentLoaded', () => {
  const reverseTab = document.querySelector('[data-tab="lotto-army3"]');
  if (reverseTab) {
    reverseTab.addEventListener('click', () => {
      setTimeout(() => {
        loadLotto3BrainStatus();
        loadLotto3HallOfFame();
        initLottoDrawSearch();
      }, 300);
    });
  }
});

// ============================================
// === 사이드바 + 대시보드 (1단계) ===
// ============================================

// === 사이드바 페이지 전환 ===
function switchLotto3Page(pageName) {
  document.querySelectorAll('.lotto-page').forEach((p) => p.classList.remove('active'));
  document.querySelectorAll('.lotto-sidebar-item').forEach((b) => b.classList.remove('active'));

  const page = document.getElementById('lotto3-page-' + pageName);
  if (page) page.classList.add('active');

  document.querySelectorAll('.lotto-sidebar-item').forEach((b) => {
    if (b.getAttribute('onclick') === "switchLotto3Page('" + pageName + "')") {
      b.classList.add('active');
    }
  });

  // 페이지별 데이터 로드
  if (pageName === 'dashboard') loadLotto3Dashboard();
  if (pageName === 'predict') initLottoDrawSearch();
  if (pageName === 'fame') loadLotto3HallOfFame();
  if (pageName === 'stats') loadLotto3Stats();
  if (pageName === 'draws') loadLotto3Draws();
  if (pageName === 'brains') loadLotto3BrainStatus();
}

/** 역전 대시보드 랭킹 패널 ID: index.html `lotto3Rank1List` / `lotto3Rank1Count` */
function _lotto3RankPanelId(rankKey, which /* 'List' | 'Count' */) {
  const mid = String(rankKey || '').replace(/^rank/i, 'Rank'); // rank1 -> Rank1
  return 'lotto3' + mid + which;
}

// === 등수 드롭다운 토글 ===
function toggleLotto3RankDropdown(rankId) {
  const list = document.getElementById(_lotto3RankPanelId(rankId, 'List'));
  if (list) {
    list.style.display = list.style.display === 'none' ? 'block' : 'none';
  }
}

// === 대시보드 데이터 로드 ===
async function loadLotto3Dashboard() {
  try {
    const res = await fetch('/api/lotto3/v12/dashboard-summary');
    const data = await res.json();
    renderCountdown(data.next_draw_no, data.next_draw_date, data.next_draw_weekday);
    renderRankings(data.rankings);
    renderPowerMeter(data.brain_power);
    renderProgress(data.learning_range, data.total_predictions);
    renderScores(data.scores);
  } catch (e) {
    console.error('Dashboard load failed:', e);
  }
}

// === 카운트다운 타이머 ===
let _lottoCountdownInterval = null;

function renderCountdown(drawNo, dateStr, weekday) {
  const nextEl = document.getElementById('lotto3NextDraw');
  if (nextEl) {
    nextEl.textContent = '🔔 다음 추첨: ' + drawNo + '회 (' + dateStr + ' ' + weekday + ')';
  }

  if (_lottoCountdownInterval) clearInterval(_lottoCountdownInterval);
  const target = new Date(dateStr + 'T20:45:00+09:00');

  function updateTimer() {
    const el = document.getElementById('lotto3CountdownTimer');
    if (!el) return;
    const now = new Date();
    const diff = target - now;
    if (diff <= 0) {
      el.textContent = '🎉 추첨 완료!';
      clearInterval(_lottoCountdownInterval);
      return;
    }
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    el.textContent =
      '⏰ 추첨까지 D-' + d + ' ' +
      String(h).padStart(2, '0') + ':' +
      String(m).padStart(2, '0') + ':' +
      String(s).padStart(2, '0');
  }

  updateTimer();
  _lottoCountdownInterval = setInterval(updateTimer, 1000);
}

// === 등수별 랭킹 ===
function renderRankings(rankings) {
  if (!rankings) return;
  window._lotto3DashboardRankings = rankings;
  if (!window._lotto3RankState) {
    window._lotto3RankState = { rank1: { limit: 20 }, rank2: { limit: 20 }, rank3: { limit: 20 } };
  }
  ['rank1', 'rank2', 'rank3'].forEach((key) => {
    const list = rankings[key] || [];
    const countEl = document.getElementById(_lotto3RankPanelId(key, 'Count'));
    const listEl = document.getElementById(_lotto3RankPanelId(key, 'List'));
    const totalKey = key + '_total';
    const totalAll = rankings[totalKey];
    const displayCount =
      typeof totalAll === 'number' && !Number.isNaN(totalAll) ? totalAll : list.length;
    if (countEl) countEl.textContent = String(displayCount);
    if (listEl) {
      if (list.length === 0) {
        listEl.innerHTML = '<div style="padding:8px;color:#666">아직 없음</div>';
      } else {
        const state = window._lotto3RankState[key] || { limit: 20 };
        const limit = Math.max(20, Number(state.limit || 20));
        const shown = list.slice(0, limit);
        let html = '';
        html += shown.map((item) => {
          const raw = item || {};
          const drawNo = raw.draw_no != null ? raw.draw_no : raw.target_draw_no;
          const t = String(raw.brain ?? raw.brain_tag ?? '').toLowerCase();
          const brain = getBrainDisplayName(t);
          let nums = raw.numbers;
          if (!Array.isArray(nums) && raw.num1 != null) {
            nums = [raw.num1, raw.num2, raw.num3, raw.num4, raw.num5, raw.num6].map((x) =>
              parseInt(x, 10),
            );
          }
          const numStr = Array.isArray(nums) ? nums.join(', ') : '';
          return '<div style="padding:4px 0;border-bottom:1px solid #0f3460">' +
            '<strong>' + drawNo + '회</strong> ' + brain + ' — ' +
            numStr +
          '</div>';
        }).join('');
        if (displayCount > list.length) {
          html +=
            '<div style="padding:8px 6px;color:#888;font-size:12px;border-top:1px solid #0f3460">' +
            '목록은 최근 ' +
            list.length +
            '건만 표시 (전체 ' +
            displayCount +
            '건)</div>';
        }
        if (list.length > limit) {
          html += '<div style="padding:10px 0;display:flex;justify-content:center">';
          html += '<button class="btn btn-primary" style="padding:8px 12px;font-size:12px" onclick="lotto3RankShowMore(\'' + key + '\')">더보기 (+20)</button>';
          html += '</div>';
        } else {
          html += '<div style="padding:8px 0;color:#666;text-align:center;font-size:12px">끝</div>';
        }
        listEl.innerHTML = html;
      }
    }
  });
}

function lottoRankShowMore(key) {
  if (!window._lotto3RankState) window._lotto3RankState = {};
  const state = window._lotto3RankState[key] || { limit: 20 };
  state.limit = Number(state.limit || 20) + 20;
  window._lotto3RankState[key] = state;
  if (window._lotto3DashboardRankings) {
    renderRankings(window._lotto3DashboardRankings);
    const el = document.getElementById(_lotto3RankPanelId(key, 'List'));
    if (el) el.style.display = 'block';
  }
}

function lottoRankShowAll(key) {
  if (!window._lotto3RankState) window._lotto3RankState = {};
  const state = window._lotto3RankState[key] || { limit: 20 };
  state.limit = 1000000;
  window._lotto3RankState[key] = state;
  if (window._lotto3DashboardRankings) {
    renderRankings(window._lotto3DashboardRankings);
    const el = document.getElementById(_lotto3RankPanelId(key, 'List'));
    if (el) el.style.display = 'block';
  }
}

// === 두뇌 파워 미터 ===
function renderPowerMeter(brainPower) {
  const el = document.getElementById('lotto3PowerMeterContent');
  if (!el || !brainPower) return;
  const maxScore = Math.max(...brainPower.map((b) => b.rank1 * 100 + b.rank2 * 50 + b.rank3 * 10), 1);
  el.innerHTML = brainPower.map((b) => {
    const t = String(b.brain || '').toLowerCase();
    const brain = getBrainDisplayName(t);
    const desc = getBrainDescription(t);
    const score = b.rank1 * 100 + b.rank2 * 50 + b.rank3 * 10;
    const pct = Math.round(score / maxScore * 100);
    const medal = pct >= 80 ? '🥇' : pct >= 50 ? '🥈' : pct >= 30 ? '🥉' : '  ';
    return '<div style="margin-bottom:12px">' +
      '<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
        '<span style="color:#fff">' + medal + ' ' + brain + (desc ? ' <span style="color:#9a9ab0;font-size:12px">(' + desc + ')</span>' : '') + '</span>' +
        '<span style="color:#ffd700">' + b.label + '</span>' +
      '</div>' +
      '<div style="color:#a0a0b0;font-size:13px;margin-bottom:4px">' +
        '1등 ' + b.rank1 + '회 · 2등 ' + b.rank2 + '회 · 3등 ' + b.rank3 + '회' +
      '</div>' +
      '<div style="background:#0a0a1a;border-radius:4px;height:8px;overflow:hidden">' +
        '<div style="background:linear-gradient(90deg,#e94560,#ffd700);width:' + pct + '%;height:100%;border-radius:4px"></div>' +
      '</div>' +
    '</div>';
  }).join('');
}

// === AI 학습 현황 ===
function renderProgress(range, totalPreds) {
  const el = document.getElementById('lotto3ProgressContent');
  if (!el || !range) return;
  const learned = (range.end - range.start + 1);
  const total = range.total_draws;
  const pct = Math.round(learned / Math.max(total, 1) * 100);
  el.innerHTML =
    '<div style="display:flex;justify-content:space-between;color:#fff;margin-bottom:8px">' +
      '<span>학습 범위: ' + range.start + ' ~ ' + range.end + '회차</span>' +
      '<span>' + pct + '% (' + learned + '/' + total + ')</span>' +
    '</div>' +
    '<div style="background:#0a0a1a;border-radius:4px;height:12px;overflow:hidden;margin-bottom:8px">' +
      '<div style="background:linear-gradient(90deg,#00b894,#0984e3);width:' + pct + '%;height:100%;border-radius:4px"></div>' +
    '</div>' +
    '<div style="color:#a0a0b0;font-size:13px">총 예측 세트: ' + Number(totalPreds || 0).toLocaleString() + '건</div>';
}

// === 등수별 적중 점수 ===
function renderScores(scores) {
  const el = document.getElementById('lotto3ScoresContent');
  if (!el || !scores) return;
  const rows = [
    { label: '🥇 1등', pct: scores.rank1_pct, cnt: scores.rank1_cnt, color: '#ffd700' },
    { label: '🥈 2등', pct: scores.rank2_pct, cnt: scores.rank2_cnt, color: '#c0c0c0' },
    { label: '🥉 3등', pct: scores.rank3_pct, cnt: scores.rank3_cnt, color: '#cd7f32' },
    { label: '4등', pct: scores.rank4_pct, cnt: scores.rank4_cnt, color: '#74b9ff' },
    { label: '5등', pct: scores.rank5_pct, cnt: scores.rank5_cnt, color: '#a0a0b0' },
  ];
  el.innerHTML = rows.map((r) =>
    '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #0f3460">' +
      '<span style="color:' + r.color + '">' + r.label + '</span>' +
      '<span style="color:#fff">' + Number(r.pct || 0).toFixed(3) + '% (' + Number(r.cnt || 0) + '건)</span>' +
    '</div>'
  ).join('') +
  '<div style="display:flex;justify-content:space-between;padding:8px 0;margin-top:4px">' +
    '<span style="color:#e94560;font-weight:bold">🎯 총 당첨 점수</span>' +
    '<span style="color:#e94560;font-weight:bold">' + Number(scores.total_hit_pct || 0).toFixed(2) + '%</span>' +
  '</div>';
}

// === 로또 탭 진입 시 대시보드 자동 로드 ===
(function() {
  const lottoTab = document.getElementById('tab-lotto-army3');
  if (!lottoTab || typeof MutationObserver === 'undefined') return;
  const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(m) {
      if (m.target && m.target.id === 'tab-lotto-army3' && m.target.classList.contains('active')) {
        loadLotto3Dashboard();
      }
    });
  });
  observer.observe(lottoTab, { attributes: true, attributeFilter: ['class'] });
})();

function lottoGetActiveStatusEl() {
  const reverse = document.getElementById('tab-lotto-army3');
  if (!reverse) return document.getElementById('lotto3ActionStatus');
  const activePage = reverse.querySelector('.lotto-page.active');
  if (!activePage) return document.getElementById('lotto3ActionStatus');
  if (activePage.id === 'lotto3-page-collect') {
    return document.getElementById('lotto3CollectStatus') || document.getElementById('lotto3ActionStatus');
  }
  return document.getElementById('lotto3ActionStatus');
}

  // 전역 노출 (index.html onclick 호환)
  window.switchLotto3Page = switchLotto3Page;
  window.switchLotto3Tab = switchLotto3Tab;
  window.lotto3Predict = lotto3Predict;
  window.lotto3NavDraw = lotto3NavDraw;
  window.lotto3SelectDraw = lotto3SelectDraw;
  window.lotto3FetchAll = lotto3FetchAll;
  window.lotto3FetchLatest = lotto3FetchLatest;
  window.toggleLotto3RankDropdown = toggleLotto3RankDropdown;
  // 동적 HTML 인라인 onclick — IIFE 밖 전역에 반드시 등록 (1군 전역 함수와 이름 분리)
  window.lotto3SwitchBrainTab = lotto3SwitchBrainTab;
  window.lotto3FameFilterRank = fameFilterRank;
  window.lotto3FameShowMore = fameShowMore;
  window.lotto3RankShowMore = lottoRankShowMore;
})();
