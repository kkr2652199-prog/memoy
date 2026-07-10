import urllib.request
import json

data = json.dumps({
    "content": "[제목] 테스트 기사\n[출처] 테스트 뉴스\n[날짜] 2026-04-08\n\n한국은행이 금리를 인하했다. 경기 둔화 우려 때문이다."
}).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/ingest/auto",
    data=data,
    headers={"Content-Type": "application/json"},
)
r = urllib.request.urlopen(req)
print(r.read().decode("utf-8"))
