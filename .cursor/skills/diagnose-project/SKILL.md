---
name: diagnose-project
description: My_Library 프로젝트의 DB, 서버, 파일 상태를 진단한다. "진단해줘", "프로젝트 상태", "DB 확인", "서버 확인", "diagnose", "health check" 라고 하면 사용.
---

# 프로젝트 진단

## 절차

### 1단계: 앱 임포트 확인
python -c "from app.main import app; print('app OK')"

### 2단계: DB 상태 확인
sqlite3 data/library.db "SELECT COUNT(*) as materials FROM materials;"
sqlite3 data/library.db "SELECT COUNT(*) as embeddings FROM embeddings;"
sqlite3 data/library.db "SELECT sql FROM sqlite_master WHERE name='materials';"

### 3단계: 서버 확인 (실행 중일 때만)
curl -s http://localhost:8123/api/library/stats

### 4단계: 최근 변경 파일
최근 수정된 Python/JS/CSS 파일 5개를 찾아 보고하라.

### 5단계: 결과 표로 정리
항목과 결과를 표로 출력하라.
