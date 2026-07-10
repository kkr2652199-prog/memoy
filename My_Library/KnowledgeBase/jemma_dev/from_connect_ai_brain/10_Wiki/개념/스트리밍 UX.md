---
type: concept
name: "스트리밍 UX"
related_materials: [234]
---

# 스트리밍 UX

## 설명

스트리밍 UX은(는) 토큰 단위의 실시간 응답을 통해 사용자에게 정보가 점진적으로 표시되도록 하여 상호작용의 지연을 최소화하는 사용자 경험 설계 방식이다.

유형/분류:
- 실시간 응답 메커니즘: SSE(Server-Sent Events)를 활용하여 토큰 단위로 답변을 스트리밍하고, `send-stream` 및 `chat_stream`과 같은 기술을 통해 실시간으로 사용자에게 표시한다.
- 지연 최적화 경로: `fast` 경로를 통해 키워드 기반의 [[quick_intent]], 경량 `LOCAL_STREAM_*` 프롬프트, 제한된 컨텍스트(약 1000자), `max_items` 설정 등을 활용하여 응답 지연을 최소화한다.
- 지능 표시 및 사용자 선택 유지: UI가 로컬 또는 [[LM Studio]] 환경일 때만 '지능' 관련 정보를 표시하며, [[localStorage]](`chat_stream_intelligence`)를 사용하여 사용자의 마지막 선택을 유지한다.
- 작업 형식 관리: `fast` 경로에서 `task_type_override`가 유효할 경우 [[quick_intent]]["task_type"]에 반영되어 특정 작업 형식에 대한 처리를 지원한다.

핵심 원리: 사용자에게 답변이 토큰 단위로 실시간으로 제공되어 대기 시간을 줄이고 상호작용의 연속성을 높이는 데 중점을 둔다. 이를 위해 최적화된 처리 경로와 특정 UI 동작을 통해 체감 지연을 최소화한다.

관련 도구: [[SSE]], [[quick_intent]], [[LM Studio]], [[localStorage]], [[/api/chat/save-to-wiki]]

출처: [자료 ID:234]

## 관련 핵심 태그·주제

**핵심 태그**

- [[POST /api/chat/send-stream]] (1회 언급)
- [[Ollama]] (1회 언급)
- [[LM Studio]] (1회 언급)
- [[POST /api/chat/send]] (1회 언급)
- [[stream_intelligence]] (1회 언급)
- [[SSE]] (1회 언급)

**주제**

- [[로컬 AI]] (1회 언급)
- [[지능 3단계]] (1회 언급)
- [[프롬프트·컨텍스트 조합]] (1회 언급)
- [[임베딩]] (1회 언급)
- [[사서 답변 파이프라인]] (1회 언급)

## 관련 자료

- [2026-04-21 (추정)] [[로컬_AI_업데이트_이전·이후_분석_보고_1]] — 로컬 AI 업데이트 이전·이후 분석 보고 1. 스트리밍 UX 토큰 단위 SSE로 답변이 실시간으로 보임 (send-stream + chat_st
- [2026-04-21] [[로컬_AI_업데이트_이전·이후_분석_보고_1]] — 로컬 AI 업데이트 이전·이후 분석 보고 1. 스트리밍 UX 토큰 단위 SSE로 답변이 실시간으로 보임 (send-stream + chat_st
