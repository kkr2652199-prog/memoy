---
type: entity
name: "stream_intelligence"
category: "고유명사"
first_mentioned: "2026-04-21"
related_materials: [234]
---

# stream_intelligence

## 개요

stream_intelligence는 실시간 스트리밍 사용자 경험(UX)을 위해 설계된, 저지연 AI 답변 생성 및 관리 시스템이다.

핵심 특징:
- 실시간 스트리밍 답변: SSE(Server-Sent Events) 기반의 토큰 단위 스트리밍을 통해 답변을 실시간으로 사용자에게 제공한다 (send-stream 및 chat_stream 활용).
- 저지연 최적화: 키워드 기반 quick_intent, 경량 프롬프트(LOCAL_STREAM_*), 약 1000자 내외의 컨텍스트, max_items 3개 제한 등을 통해 응답 지연을 최소화하는 'fast' 경로를 사용한다.
- UI 연동 및 설정 유지: 로컬 또는 LM Studio 환경의 UI에서 '지능' 행으로 표시되며, localStorage(chat_stream_intelligence)를 사용하여 사용자의 마지막 선택을 유지한다.
- 작업 형식 오버라이드: 'fast' 경로에서 task_type_override가 유효할 경우, quick_intent의 "task_type"에 해당 값을 반영하여 작업 형식을 동적으로 제어한다.
- 독립적인 저장 경로: 채팅 스트리밍 여부와 관계없이, /api/chat/save-to-wiki 및 그 내부의 ingest, run_evolution_engine을 통한 위키 저장 경로는 stream_intelligence의 동작과 별개로 관리된다.

관련: [[quick_intent]], [[SSE]], [[localStorage]], [[LM Studio]]

출처: [자료 ID:234]

## 관련 자료

- [[로컬_AI_업데이트_이전·이후_분석_보고_1]]

## 관련 핵심 태그·주제

**핵심 태그**

- [[POST /api/chat/send-stream]] (1회 언급)
- [[Ollama]] (1회 언급)
- [[LM Studio]] (1회 언급)
- [[POST /api/chat/send]] (1회 언급)
- [[SSE]] (1회 언급)

**주제**

- [[로컬 AI]] (1회 언급)
- [[스트리밍 UX]] (1회 언급)
- [[지능 3단계]] (1회 언급)
- [[프롬프트·컨텍스트 조합]] (1회 언급)
- [[임베딩]] (1회 언급)
- [[사서 답변 파이프라인]] (1회 언급)

## 관련 사건/정보

- [2026-04-21 (추정)] 로컬 AI 업데이트 이전·이후 분석 보고 1. 스트리밍 UX 토큰 단위 SSE로 답변이 실시간으로 보임 (send-stream + chat_st ([[로컬_AI_업데이트_이전·이후_분석_보고_1]])
- [2026-04-21] 로컬 AI 업데이트 이전·이후 분석 보고 1. 스트리밍 UX 토큰 단위 SSE로 답변이 실시간으로 보임 (send-stream + chat_st ([[로컬_AI_업데이트_이전·이후_분석_보고_1]])

## 변화 이력

| 날짜 | 내용 | 출처 |
|------|------|------|
| 2026-04-21 | 로컬 AI 업데이트 이전·이후 분석 보고 1. 스트리밍 UX 토큰 단위 SSE로 답변이 실시간으로 보임 (s | 로컬_AI_업데이트_이전·이후_분석_보고_1 |
| 2026-04-21 (추정) | 로컬 AI 업데이트 이전·이후 분석 보고 1. 스트리밍 UX 토큰 단위 SSE로 답변이 실시간으로 보임 (s | 로컬_AI_업데이트_이전·이후_분석_보고_1 |
