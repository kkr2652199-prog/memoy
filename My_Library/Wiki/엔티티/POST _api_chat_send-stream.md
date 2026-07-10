---
type: entity
name: "POST /api/chat/send-stream"
category: "고유명사"
first_mentioned: "2026-04-21"
related_materials: [234]
---

# POST /api/chat/send-stream

## 개요

POST /api/chat/send-stream은(는) AI 답변을 토큰 단위로 실시간 스트리밍하여 사용자에게 제공하는 API 엔드포인트이다.

핵심 특징:
- 실시간 스트리밍 UX: SSE(Server-Sent Events)를 활용하여 AI 답변을 토큰 단위로 실시간 전송하고 표시한다.
- 'fast' 경로 최적화: `quick_intent` 키워드 기반 처리, 경량 `LOCAL_STREAM_*` 프롬프트, 약 1000자 내외의 컨텍스트 및 `max_items 3` 등의 설정을 통해 응답 지연을 최소화한다.
- 동적 UI 표시 및 유지: UI가 로컬 또는 LM Studio 환경일 때만 「지능」 행을 표시하며, `localStorage(chat_stream_intelligence)`를 통해 마지막 선택을 유지한다.
- 작업 형식 오버라이드 지원: 'fast' 경로에서 `task_type_override`가 유효할 경우 `quick_intent["task_type"]`에 해당 값이 반영되도록 지원한다.

관련: [[chat_stream]], [[quick_intent]], [[/api/chat/save-to-wiki]]

출처: [자료 ID:234]

## 관련 자료

- [[로컬_AI_업데이트_이전·이후_분석_보고_1]]

## 관련 핵심 태그·주제

**핵심 태그**

- [[Ollama]] (1회 언급)
- [[LM Studio]] (1회 언급)
- [[POST /api/chat/send]] (1회 언급)
- [[stream_intelligence]] (1회 언급)
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
