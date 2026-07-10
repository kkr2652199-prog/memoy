# 계획

## Obsidian 그래프 분석

### 렌더링 구조
- Pixi.js (WebGL) + 자체 물리엔진 (또는 D3 force 내장)
- 노드: 원, 크기 = 2 + sqrt(연결수)
- 색상: 3단계 (현재 노드 / 방문 노드 / 기본)
- 엣지: 직선 1px, lightgray, hover 시 gray
- hover: 이웃만 alpha 1, 나머지 0.2, 200ms tween 전환
- 라벨: 기본 숨김, 줌인하면 서서히 표시
- Force: charge -100, centerForce 0.3, linkDistance 30, collide = nodeRadius

### 참고 소스
- Quartz (오픈소스 Obsidian 클론): 
  https://github.com/jackyzha0/quartz/blob/v4/quartz/components/scripts/graph.inline.ts
- 추출본 위치: d:\MONEY\obsidian_core_unpacked (읽기 전용 참고)

---

## 그래프 Phase 5: Obsidian 스타일

### 적용 항목
1. 노드 크기: radius = 2 + Math.sqrt(linkCount) × 2
2. hover 전환: CSS transition 200ms (opacity)
3. charge: -100 (현재 -150에서 줄임)
4. linkDistance: 소속 50, shared_topic 150
5. 라벨: 기본 숨김, 줌인 시 표시 (줌 레벨 1.5 이상)
6. 엣지: 직선 유지, stroke-width 1, opacity 0.3

### 적용하지 않을 것
- Pixi.js 전환 (57노드라 SVG 충분)
- 색상 3단계 (브랜드별 색상 유지가 우리 앱에 더 적합)

---

## 그래프 Phase 6: 연결 구조 개편 (50개 이후)

### 현재 문제
- "소속" 엣지는 출처 정보일 뿐 지식 연관이 아님
- shared_topic은 키워드 수준, 깊이 부족
- 브랜드 중심 클러스터는 "누가 만들었나"를 보여줌
  "무엇에 대한 것인가"를 보여주지 않음

### Phase 6 목표: 주제 중심 그래프
1. 뷰 전환: "출처별 보기" ↔ "주제별 보기" 토글
2. 주제별 보기:
   - 중심 노드 = entity/concept (위키에서 추출)
   - 주변 노드 = 해당 주제를 다룬 자료들
   - 엣지 = "이 자료가 이 개념을 설명한다"
3. 클러스터 = 같은 상위 주제를 공유하는 개념들
4. 브랜드는 노드 색상으로만 표시 (시각적 힌트)

### 전제 조건
- 자료 50개 이상 축적
- entity/concept 위키 품질 검증 완료
- shared_topic 엣지 생성 알고리즘 개선
