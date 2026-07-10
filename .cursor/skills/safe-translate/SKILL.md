---
name: safe-translate
description: 자료의 원본 content를 보존하면서 한국어 번역을 수행한다. "번역해줘", "translate", "한국어로 바꿔줘" 라고 하면 사용. wiki_body를 절대 덮어쓰지 않는다.
---

# 안전한 번역 작업

## 핵심 규칙
- content 원본은 절대 수정하지 않는다
- translated_content 필드에만 저장한다
- wiki_body는 절대 번역 내용으로 덮어쓰지 않는다
- 6000자 제한 없이 4000자 청크로 분할 번역한다

## 번역 전 확인
1. 대상 material의 content 길이 확인
2. 이미 translated_content가 있는지 확인
3. wiki_body의 현재 길이 기록 (번역 후 변경되면 안 됨)

## 번역 후 검증
SELECT id, LENGTH(content) as orig, LENGTH(translated_content) as trans, LENGTH(wiki_body) as wiki FROM materials WHERE id = 대상ID;

확인 항목:
- translated_content가 저장되었는지
- wiki_body 길이가 번역 전과 동일한지
- content가 변경되지 않았는지
