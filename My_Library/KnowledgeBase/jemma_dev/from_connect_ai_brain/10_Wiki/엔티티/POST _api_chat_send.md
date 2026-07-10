---
type: entity
name: "POST /api/chat/send"
category: "고유명사"
first_mentioned: "2026-04-21"
related_materials: [234]
---

# POST /api/chat/send

## 개요

POST /api/chat/send은(는) 로컬 AI 업데이트 이후 스트리밍 UX를 통해 실시간 답변을 제공하며, 지연 감소를 위한 Fast 경로 등 다양한 처리 방식을 지원하는 채팅 메시지 전송 API이다.

핵심 특징:
- 실시간 스트리밍 답변: 토큰 단위 SSE(Server-Sent Events)를 통해 send-stream 및 chat_stream 방식으로 답변을 실시간으로 제공하여 사용자 경험을 개선합니다.
- 지연 감소를 위한 Fast 경로: quick_intent 기반의 키워드 처리, 경량 LOCAL_STREAM_* 프롬프트, 약 1000자의 제한된 컨텍스트, max_items 3 등의 최적화를 통해 응답 지연을 최소화합니다.
- UI 지능 표시 조건부 제어: UI가 로컬 또는 LM Studio 환경일 때만 "지능" 행을 표시하며, localStorage(chat_stream_intelligence)를 통해 사용자의 마지막 선택을 유지합니다.
- 작업 형식 오버라이드 지원: Fast 경로에서 task_type_override가 유효할 경우 quick_intent["task_type"]에 해당 작업 형식을 반영하여 특정 의도를 처리합니다.

관련: [[send-stream]], [[chat_stream]], [[quick_intent]], [[POST /api/chat/save-to-wiki]]

출처: [자료 ID:234]

## 관련 자료

- [[로컬_AI_업데이트_이전·이후_분석_보고_1]]

## 관련 핵심 태그·주제

**핵심 태그**

- [[POST /api/chat/send-stream]] (1회 언급)
- [[Ollama]] (1회 언급)
- [[LM Studio]] (1회 언급)
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
