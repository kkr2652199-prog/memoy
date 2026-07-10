# Karpathy·AI 한계·앱 제작 동기 — 영상 8편 공부 노트

> **목적**: 우리가 지금 만들고 있는 앱(**나의 지식 도서관 / My_Library**)의 **동기**와 **AI의 한계**를 Karpathy 계열 논의와 연결해 정리한다.  
> **이번 갱신**: YouTube **oEmbed**로 각 링크의 **제목·채널**을 확인했고, **같은 폴더(My_Library) 안**의 위키·원본 Raw와 대조해 **무엇이 무엇인지** 한눈에 보이게 다시 적었다.

---

## 0. 이 문서가 답하는 질문

| 질문 | 어디를 보면 되는가 |
|------|-------------------|
| 8개 링크가 각각 **무슨 영상**인가? | 아래 [§2 출처 목록](#2-출처-목록-번호-순-메타--라이브러리-연결) 표 |
| **우리 앱 폴더**에 이미 정리된 글이 있는가? | 표의 **라이브러리 연결** 열 (없으면 “미수집”) |
| 같은 말이 여러 영상에 나오면? | [§4 중복 주제 인덱스](#4-중복-주제-인덱스) |

---

## 1. 이 문서에서 쓰는 기호

| 기호 | 의미 |
|------|------|
| **출처 N** | [§2](#2-출처-목록-번호-순-메타--라이브러리-연결)의 N번 행(영상) |
| **중복 G-R** | 공통 주제 그룹 **G**의 **R**번째 반복 서술. 첫 상세는 한 곳에만 두고 나머지는 `→ 출처 K`로 연결 |
| **→ 출처 K** | 동일·유사 내용의 **첫 요약**이 출처 K에 있음 |

---

## 2. 출처 목록 (번호 순, 메타 + 라이브러리 연결)

메타(제목·채널)는 **YouTube oEmbed**로 조회한 값이다.  
라이브러리 연결은 **프로젝트 내 실제 경로**이며, 없으면 해당 영상은 아직 **섭취·위키화되지 않은** 것이다.

| 번호 | 제목 (YouTube) | 채널 | URL | 라이브러리 연결 |
|:----:|----------------|------|-----|----------------|
| 1 | 세계가 주목한 Karpathy LLM Wiki, 진짜 돌아가는 도구를 만들었습니다 \| MindVault | 코딩 못하는 문과 개발자 | [링크](https://youtu.be/LxMhb8HIL7A?si=v3mnYz8nR_Y1K30i) | 위키 [[Wiki/유튜브/코딩 못하는 문과 개발자/세계가 주목한 Karpathy LLM Wiki, 진짜 돌아가는 도구를 만들었습니다 _ MindVault_2026-04.md]] · 원본 `Raw_Materials/2026-04-12_세계가 주목한 Karpathy LLM Wiki, 진짜 돌아가는 도구를 만들었습니다 _ MindVault_2.md` |
| 2 | LLM Wiki 입문 가이드 | 편집자P | [링크](https://youtu.be/S6w4g2OQlVQ?si=LVd-1mW8tUYiwCgV) | 위키 [[Wiki/유튜브/편집자P/LLM Wiki 입문 가이드_2026-04.md]] · 원본 `Raw_Materials/2026-04-12_LLM Wiki 입문 가이드.md` |
| 3 | 안쓰면 손해! 클로드코드가 내 노하우를 나무위키처럼 정리해줍니다 (feat. 안드레 카파시) | 시민개발자 구씨 | [링크](https://youtu.be/wXc7-vFSd5U?si=K0kxzEzcVhmoLVwH) | **미수집** (동일 제목의 `Wiki/`·`Raw_Materials/` 파일 없음) |
| 4 | 안드레 카파시가 제안한 LLM 위키의 개념을 이해 | AI ON | [링크](https://youtu.be/JvL4w520o0o?si=xzXATe7WpVIoFSUe) | 위키 [[Wiki/유튜브/AI ON/안드레 카파시가 제안한 LLM 위키의 개념을 이해_2026-04.md]] · 원본 `Raw_Materials/2026-04-12_안드레 카파시가 제안한 LLM 위키의 개념을 이해_2.md` |
| 5 | 프리 출근 전 이력서 살피기, 진행 중인 작업(kiki) 간단 소개, LLM Wiki 엔진으로 엮은 MD 그래프 | mango_fr | [링크](https://youtu.be/yjnqqYkb6sc?si=qlH7m2Hs63U8Y6s9) | 위키 [[Wiki/유튜브/mango_fr/프리 출근 전 이력서 살피기, 진행 중인 작업(kiki) 간단 소개, LLM Wiki 엔진으로 엮은 MD 그래프_2026-04.md]] · 원본 `Raw_Materials/2026-04-12_프리 출근 전 이력서 살피기, 진행 중인 작업(kiki) 간단 소개, LLM Wiki 엔진으로 엮은 MD 그래프_2.md` |
| 6 | Fix Karpathy’s LLM Wiki with a Knowledge Graph \| Claude Code + Obsidian + InfraNodus | Nodus Labs | [링크](https://youtu.be/yYSTsKo8moU?si=e3ePvi4Lyfk65ZZf) | 위키 [[Wiki/유튜브/Nodus Labs/Fix Karpathy’s LLM Wiki with a Knowledge Graph _ Claude Code + Obsidian + InfraNodus_2026-04.md]] · 원본 `Raw_Materials/2026-04-12_Fix Karpathy’s LLM Wiki with a Knowledge Graph _ Claude Code + Obsidian + InfraNodus_2.md` |
| 7 | How To Do PHD-Level Research with AI (Karpathy's LLM Wiki) | Tommy Chryst | [링크](https://youtu.be/FR9USL0yj3I?si=ZQ2_5KtdBIE2zf0i) | 위키 [[Wiki/유튜브/Tommy Chryst/How To Do PHD-Level Research with AI (Karpathy's LLM Wiki)_2026-04.md]] · 원본 `Raw_Materials/2026-04-12_How To Do PHD-Level Research with AI (Karpathy's LLM Wiki)_2.md` |
| 8 | Build Your Second Brain With Claude Code, Karpathy’s Method | AI for Work | [링크](https://youtu.be/lnsExa1UbnM?si=c7Di8fnLcGixRRWs) | 위키 [[Wiki/유튜브/AI for Work/Build Your Second Brain With Claude Code, Karpathy’s Method_2026-04.md]] · 원본 `Raw_Materials/2026-04-12_Build Your Second Brain With Claude Code, Karpathy’s Method_6.md` |

**색인**: `Wiki/index.md`에 본 문서 및 위 유튜브 위키 다수가 링크되어 있다.

---

## 3. 공통 주제 축 (라이브러리 요약과 맞춘 뼈대)

아래는 **위키에 이미 요약된 내용**을 축으로 묶은 것이다. 세부 인용은 각 위키 페이지를 본다.

1. **Karpathy식 LLM Wiki / 두 번째 뇌** — 원시 자료 → 분류·연결·위키화, 사용자 도메인이 중심 (출처 2, 4, 7, 8 등, 내용 겹침 → [중복1](#중복1-llm-wiki--두-번째-뇌-개념))  
2. **실제 도구·구현** — MindVault(검색·그래프·위키 레이어, 토큰 절감 등) (출처 1)  
3. **LLM만으로 부족한 점 → 지식 그래프** — InfraNodus, 공백·클러스터 시각화 (출처 6)  
4. **Claude Code + Obsidian 스택** — 원시 입력, 위키 페이지 생성, Web Clipper 등 (출처 6, 8)  
5. **연구 깊이·질문** — 다량 자료 입력·복잡 질문·Obsidian 시각화 (출처 7)  
6. **개인 맥락·실험** — LLM 엔진·MD 그래프·작업 추적·지오드 등 (출처 5)  
7. **(미수집)** 클로드코드로 노하우 정리·카파시 언급 (출처 3 — vault에 글 없음)

**우리 앱(My_Library)과의 연결**: 자료 **인제스트**, **엔티티·개념·위키**, **그래프 뷰**는 위 표의 “도구화” 논의와 같은 방향이다. 다만 이 문서의 위키 요약은 **유튜브 가공본**이므로, 제품 코드와 1:1 대응은 `app/` 문서가 아니라 **기획 메모**로 취급한다.

---

## 4. 중복 주제 인덱스

### 중복1 — LLM Wiki / 두 번째 뇌 개념

| 항목 | 내용 |
|------|------|
| 주제 한 줄 | Karpathy가 제안한 **개인 지식을 LLM으로 위키화**하는 흐름, **옵시디언** 결합, **사용자 전문성**이 핵심 |
| 최초 상세 요약 위치 | 출처 **4** 위키 [[Wiki/유튜브/AI ON/안드레 카파시가 제안한 LLM 위키의 개념을 이해_2026-04.md]] |
| 중복1-1 | 출처 **2** — 입문 가이드 관점 (`LLM Wiki 입문 가이드_2026-04.md`) → **→ 출처 4** |
| 중복1-2 | 출처 **7** — 연구·다량 자료·Obsidian (`How To Do PHD-Level Research...`) → **→ 출처 4** |
| 중복1-3 | 출처 **8** — Claude Code + Obsidian 세팅 (`Build Your Second Brain...`) → **→ 출처 4** |

### 중복2 — Claude Code / Obsidian / 코딩 에이전트 스택

| 항목 | 내용 |
|------|------|
| 주제 한 줄 | **Claude Code**로 원시 자료 분석·위키 생성, **Obsidian**에서 링크·태그 관리 |
| 최초 상세 요약 위치 | 출처 **8** 위키 [[Wiki/유튜브/AI for Work/Build Your Second Brain With Claude Code, Karpathy’s Method_2026-04.md]] |
| 중복2-1 | 출처 **6** — 동일 스택 + InfraNodus (`Fix Karpathy’s LLM Wiki...`) → **→ 출처 8** (도구 스택 겹침; 6은 **지식 그래프 보완**이 추가 주제) |

### 중복3 — 지식 그래프로 LLM Wiki 보완 (한계·통찰)

| 항목 | 내용 |
|------|------|
| 주제 한 줄 | LLM Wiki만으로는 **자기 인식·누적 한계** 등 이슈 → **지식 그래프**로 공백·클러스터 파악 |
| 최초 상세 요약 위치 | 출처 **6** 위키 [[Wiki/유튜브/Nodus Labs/Fix Karpathy’s LLM Wiki with a Knowledge Graph _ Claude Code + Obsidian + InfraNodus_2026-04.md]] |
| (다른 출처 동일 주제) | 출처 1(MindVault)도 **그래프 레이어** 언급 — 구현 사례는 다름 → 상세는 출처 1 위키 |

### 중복4 — 구현 사례·제품 소개 (MindVault)

| 항목 | 내용 |
|------|------|
| 주제 한 줄 | **MindVault** 오픈소스: 검색·그래프·위키, BM25, 자동 갱신, 토큰 절감 등 **제품 설명** |
| 최초 상세 요약 위치 | 출처 **1** 위키 (MindVault) |
| (타 출처와 혼동 주의) | “LLM Wiki” **개념** 설명은 중복1; **MindVault**는 별도 제품 |

---

## 5. 영상별 노트 (라이브러리 기준 재기록)

### 출처 1 — MindVault

- **채널·제목**: 코딩 못하는 문과 개발자 · 세계가 주목한 Karpathy LLM Wiki, 진짜 돌아가는 도구를 만들었습니다 \| MindVault  
- **URL**: https://youtu.be/LxMhb8HIL7A?si=v3mnYz8nR_Y1K30i  
- **핵심 개념 (위키 요약)**: MindVault = Karpathy LLM Wiki 패턴 기반 오픈소스; **검색·그래프·위키** 3레이어; BM25 검색; 프로젝트 자료 자동 분석·위키화; 토큰 절감·자동 업데이트 등 **제품 소개** 중심.  
- **AI 한계·보완**: 개념 일반론은 `중복1`·`중복3` 참고.  
- **도구·앱 연결**: “실제로 도는 도구” 사례 연구용. 우리 앱과는 **그래프·위키** 방향 유사.  
- **라이브러리**: 위 §2 표 참조.

---

### 출처 2 — LLM Wiki 입문 가이드

- **채널·제목**: 편집자P · LLM Wiki 입문 가이드  
- **URL**: https://youtu.be/S6w4g2OQlVQ?si=LVd-1mW8tUYiwCgV  
- **핵심 개념**: 파편 지식 관리, 옵시디언 결합, 에이전트·**인제스트/커리/린트** 등 운영 명령, 지속 검수 필요.  
- **중복**: `중복1-1` → 출처 4.

---

### 출처 3 — 클로드코드 × 나무위키 (시민개발자 구씨)

- **채널·제목**: 시민개발자 구씨 · 안쓰면 손해! 클로드코드가 내 노하우를 나무위키처럼 정리해줍니다 (feat. 안드레 카파시)  
- **URL**: https://youtu.be/wXc7-vFSd5U?si=K0kxzEzcVhmoLVwH  
- **라이브러리**: **미수집** — 섭취 후 `Raw_Materials/`·`Wiki/유튜브/...`에 넣으면 이 표와 맞출 수 있음.  
- **핵심 개념**: (vault 없음) 제목상 **Claude Code**로 개인 노하우 구조화·Karpathy 레퍼런스.

---

### 출처 4 — LLM 위키 개념 이해 (AI ON)

- **채널·제목**: AI ON · 안드레 카파시가 제안한 LLM 위키의 개념을 이해  
- **URL**: https://youtu.be/JvL4w520o0o?si=xzXATe7WpVIoFSUe  
- **핵심 개념**: 로우 폴더·**수집/질문/정리**·AI 정원사 은유; 주인공은 사용자 전문성.  
- **중복**: `중복1` 최초 상세.

---

### 출처 5 — mango_fr (이력서·kiki·MD 그래프)

- **채널·제목**: mango_fr · 프리 출근 전 이력서 살피기, 진행 중인 작업(kiki) 간단 소개, LLM Wiki 엔진으로 엮은 MD 그래프  
- **URL**: https://youtu.be/yjnqqYkb6sc?si=qlH7m2Hs63U8Y6s9  
- **핵심 개념**: LLM 엔진·지식 그래프·작업 추적·블로그 연결·지오드·툴 오프로딩·자동/수동 개발 논의 등 **개인 실험·브이로그 성격**.  
- **중복**: LLM Wiki **이름**은 중복1과 겹치나, **내용 초점**은 출처 1·4와 다름.

---

### 출처 6 — Nodus Labs (지식 그래프로 LLM Wiki 고치기)

- **채널·제목**: Nodus Labs · Fix Karpathy’s LLM Wiki with a Knowledge Graph \| Claude Code + Obsidian + InfraNodus  
- **URL**: https://youtu.be/yYSTsKo8moU?si=e3ePvi4Lyfk65ZZf  
- **핵심 개념**: LLM Wiki **한계**(자기 인식 등)·**InfraNodus**로 그래프 시각화·공백 발견; IDE·옵시디언.  
- **중복**: `중복2-1`, `중복3` 최초.

---

### 출처 7 — Tommy Chryst (PHD급 리서치)

- **채널·제목**: Tommy Chryst · How To Do PHD-Level Research with AI (Karpathy's LLM Wiki)  
- **URL**: https://youtu.be/FR9USL0yj3I?si=ZQ2_5KtdBIE2zf0i  
- **핵심 개념**: 개인 지식 베이스·다량 자료·복잡 질문·Obsidian·Karpathy `llm-wiki.md` 레퍼런스.  
- **중복**: `중복1-2` → 출처 4.

---

### 출처 8 — AI for Work (Claude Code 세컨드 브레인)

- **채널·제목**: AI for Work · Build Your Second Brain With Claude Code, Karpathy’s Method  
- **URL**: https://youtu.be/lnsExa1UbnM?si=c7Di8fnLcGixRRWs  
- **핵심 개념**: Obsidian + Claude Code로 PKS; 원시 입력→분석·위키 페이지; 태그·관계; 전사·썸네일 등.  
- **중복**: `중복1-3`, `중복2` 최초(스택).

---

## 6. 메타

- **의도**: Karpathy 계열 **LLM Wiki** 논의와 **상위권 개발자들의 각색**(도구·연구·제품)을 한 파일에서 **번호·중복·라이브러리 경로**로 열람 가능하게 함.  
- **갱신 이력**: 제목·채널은 YouTube oEmbed 기준; 본문 요약은 **기존 위키 페이지**에 의존. 출처 3은 vault **미수집**.

---

## 7. 외부 링크 (원본)

1. [YouTube — 출처 1](https://youtu.be/LxMhb8HIL7A?si=v3mnYz8nR_Y1K30i)  
2. [YouTube — 출처 2](https://youtu.be/S6w4g2OQlVQ?si=LVd-1mW8tUYiwCgV)  
3. [YouTube — 출처 3](https://youtu.be/wXc7-vFSd5U?si=K0kxzEzcVhmoLVwH)  
4. [YouTube — 출처 4](https://youtu.be/JvL4w520o0o?si=xzXATe7WpVIoFSUe)  
5. [YouTube — 출처 5](https://youtu.be/yjnqqYkb6sc?si=qlH7m2Hs63U8Y6s9)  
6. [YouTube — 출처 6](https://youtu.be/yYSTsKo8moU?si=e3ePvi4Lyfk65ZZf)  
7. [YouTube — 출처 7](https://youtu.be/FR9USL0yj3I?si=ZQ2_5KtdBIE2zf0i)  
8. [YouTube — 출처 8](https://youtu.be/lnsExa1UbnM?si=c7Di8fnLcGixRRWs)  

---

*파일 경로: `My_Library/Wiki/종합/Karpathy_관련_영상_8편_개념_정리.md`*
