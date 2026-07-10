# My_Library 앱 구조 요약

## 기본 정보
- **경로**: d:\MONEY lol\My_Library
- **서버**: FastAPI, localhost:8123
- **LLM**: LM Studio (Gemma e4b/e2b), localhost:1234
- **임베딩**: BGE-M3 (CPU, 1024차원)
- **DB**: data/library.db (SQLite)

## 핵심 모듈
| 모듈 | 경로 | 역할 |
|------|------|------|
| 섭취 | app/core/ingest.py | URL에서 자료 수집·분석 |
| 위키생성 | app/core/librarian.py | AI가 위키 자동 생성 |
| 검색 | app/core/search.py | 하이브리드 검색 (FTS5+벡터) |
| 교차참조 | app/core/cross_references.py | 자료 간 연결 관리 |
| 모순감지 | app/core/knowledge_engine.py | 자료 간 모순 발견 |
| 스케줄러 | app/core/scheduler.py | 자동 작업 실행 |
| 메모리 | app/core/memory_manager.py | 선호도, 유사대화, 결정화 |
| 채팅 | app/api/routes_chat.py | 채팅 API (일반+스트리밍) |
| 그래프 | app/core/graph_builder.py | 지식 그래프 시각화 |
| 임베딩 | app/llm/embedding_client.py | LM Studio BGE-M3 |

## DB 테이블
- materials (203개): 도서관 자료 원본
- entities (321개): 추출된 엔티티
- concepts (435개): 추출된 개념
- contradictions (126개): 감지된 모순
- cross_references (7,026개): 자료 간 연결
- chat_history (356건+): 대화 기록
- user_preferences (17건): 사용자 선호도
- material_embeddings (203개): 벡터 임베딩

## 팀 역할
- **로하**: 앱 내부 AI 사서 (챗봇, 위키 생성, 자료 분석)
- **잼마**: Cursor 내부 AI (코딩 보조, 문서 작성, 프로젝트 관리)
- **형(사용자)**: 총괄, 방향 결정, 자료 큐레이션

## 위키 구조 (Wiki/)
- 개념/ (454개): AI가 추출한 개념 위키
- 엔티티/ (327개): AI가 추출한 엔티티 위키
- 종합/ (13개): 종합 분석·세션 요약
- index.md: 전체 목차
- log.md: 작업 기록

## 최근 업데이트 (2026-04-22)
- LM Studio 스트리밍 구현
- 임베딩 BGE-M3로 교체 (CPU)
- 교차참조 품질 개선 (의미연결+엔티티연결)
- Agent Memory 강화 (선호도+유사대화+결정화)
- 위키 깃허브 동기화
