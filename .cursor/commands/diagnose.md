# DB 및 서버 진단

프로젝트 현재 상태를 진단하라:

1. python -c "from app.main import app; print('app OK')" 실행
2. SQLite 쿼리 실행:
   - SELECT COUNT(*) FROM materials
   - SELECT COUNT(*) FROM embeddings (테이블 존재 시)
   - SELECT sql FROM sqlite_master WHERE name='materials'
3. 서버 실행 중이면: curl http://localhost:8123/api/library/stats
4. 최근 수정 파일 5개 확인
5. 결과를 표로 정리해서 보고
