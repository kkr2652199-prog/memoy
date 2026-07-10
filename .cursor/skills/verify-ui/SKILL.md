---
name: verify-ui
description: 프론트엔드 변경 후 캐시버스트, 서빙 확인, 하드코딩 색상 검사를 수행한다. "UI 검증", "프론트 확인", "캐시버스트 확인", "verify ui" 라고 하면 사용.
---

# UI 변경 검증

## 절차

### 1단계: 캐시버스트 확인
index.html에서 모든 script, link 태그의 ?v= 쿼리 파라미터를 추출하여 목록으로 보고하라.

### 2단계: 서버 서빙 확인 (실행 중일 때만)
curl -s http://localhost:8123/static/js/library.js 첫 5줄 확인
curl -s http://localhost:8123/static/css/style.css 첫 5줄 확인

### 3단계: 하드코딩 색상 검사
style.css에서 CSS 변수가 아닌 하드코딩 색상을 검색하라.
새로 추가된 하드코딩 색상이 있으면 경고하라.

### 4단계: 결과를 표로 정리해서 보고하라.
