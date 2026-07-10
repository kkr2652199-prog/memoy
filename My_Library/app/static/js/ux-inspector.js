/* AI UX Inspector: 개발자를 위한 클릭 피드백 도구 */

(function initUXInspector() {
  let isInspectMode = false;
  
  // 1. 스타일 동적 주입
  const style = document.createElement('style');
  style.textContent = `
    .ux-inspect-btn {
      position: fixed;
      top: 70px;
      right: 12px;
      z-index: 10000;
      background: #00bcd4;
      color: white;
      border: none;
      padding: 10px 16px;
      border-radius: 30px;
      cursor: pointer;
      font-weight: bold;
      box-shadow: 0 4px 15px rgba(0,0,0,0.3);
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .ux-inspect-btn.active {
      background: #ff5252;
      box-shadow: 0 0 20px rgba(255,82,82,0.5);
    }
    .ux-inspect-active * {
      cursor: crosshair !important;
    }
    .ux-inspect-hover {
      outline: 2px dashed #00bcd4 !important;
      outline-offset: 2px !important;
      background: rgba(0, 188, 212, 0.1) !important;
    }
    .ux-inspect-toast {
      position: fixed;
      top: 20px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 10001;
      background: #323232;
      color: white;
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 14px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.4);
      animation: fadeInOut 2.5s forwards;
    }
    @keyframes fadeInOut {
      0% { opacity: 0; transform: translate(-50%, -20px); }
      15% { opacity: 1; transform: translate(-50%, 0); }
      85% { opacity: 1; transform: translate(-50%, 0); }
      100% { opacity: 0; transform: translate(-50%, -20px); }
    }
  `;
  document.head.appendChild(style);

  // 2. 버튼 생성
  const btn = document.createElement('button');
  btn.className = 'ux-inspect-btn';
  btn.innerHTML = '<span>🔍</span> <span>Inspect Mode</span>';
  document.body.appendChild(btn);

  // 3. 토글 로직
  btn.onclick = () => {
    isInspectMode = !isInspectMode;
    btn.classList.toggle('active', isInspectMode);
    document.body.classList.toggle('ux-inspect-active', isInspectMode);
    btn.innerHTML = isInspectMode ? '<span>⏹️</span> <span>Stop Inspect</span>' : '<span>🔍</span> <span>Inspect Mode</span>';
    
    if (isInspectMode) {
      showToast("🔍 UX 점검 모드 활성: 수정할 부분을 클릭하세요.");
    }
  };

  // 4. 클릭 가로채기
  document.addEventListener('click', (e) => {
    if (!isInspectMode) return;
    if (e.target.closest('.ux-inspect-btn')) return;

    e.preventDefault();
    e.stopPropagation();

    const el = e.target;
    const details = {
      tag: el.tagName.toLowerCase(),
      id: el.id ? `#${el.id}` : '',
      classes: el.className ? (typeof el.className === 'string' ? el.className.split(' ').map(c => `.${c}`).join('') : '') : '',
      text: el.innerText ? el.innerText.slice(0, 20) : ''
    };

    const promptText = `[위치: ${details.tag}${details.id}${details.classes}] '${details.text}...' 이 부분 수정해줘: `;
    
    // 클립보드 복사
    navigator.clipboard.writeText(promptText).then(() => {
      showToast(`📝 정보 복사됨! 채팅창에 붙여넣으세요: ${details.tag}${details.id}`);
      
      // 반짝임 효과
      const originalOutline = el.style.outline;
      el.style.outline = '4px solid #ff5252';
      setTimeout(() => { el.style.outline = originalOutline; }, 500);
    });
  }, true);

  // 5. 마우스 오버 효과
  document.addEventListener('mouseover', (e) => {
    if (!isInspectMode) return;
    if (e.target.closest('.ux-inspect-btn')) return;
    e.target.classList.add('ux-inspect-hover');
  });
  document.addEventListener('mouseout', (e) => {
    if (!isInspectMode) return;
    e.target.classList.remove('ux-inspect-hover');
  });

  function showToast(msg) {
    const toast = document.createElement('div');
    toast.className = 'ux-inspect-toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2500);
  }
})();
