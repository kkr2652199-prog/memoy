import json
import time
import urllib.request


def _fetch_all_active_material_ids() -> list[int]:
    """API 응답 형식에 맞춰 활성 자료 ID 전부 수집 (페이지 순회)."""
    ids: list[int] = []
    page = 1
    while True:
        url = (
            f"http://127.0.0.1:8123/api/library/materials"
            f"?status=active&size=100&page={page}"
        )
        raw = urllib.request.urlopen(url).read()
        res = json.loads(raw)
        data = res.get("data") or {}
        items = data.get("items") or []
        for m in items:
            if m.get("status") == "active":
                ids.append(m["id"])
        total_pages = int(data.get("total_pages") or 1)
        if page >= total_pages:
            break
        page += 1
    return ids


ids = _fetch_all_active_material_ids()

print(f"총 {len(ids)}건 재추출 시작")
success = 0
fail = 0
start = time.time()

for i, mid in enumerate(ids, 1):
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:8123/api/knowledge/reprocess/{mid}",
            method="POST",
        )
        r = json.loads(urllib.request.urlopen(req, timeout=120).read())
        if r.get("success"):
            success += 1
            print(f"[{i}/{len(ids)}] ID {mid} 성공")
        else:
            fail += 1
            print(f"[{i}/{len(ids)}] ID {mid} 실패: {r}")
    except Exception as e:
        fail += 1
        print(f"[{i}/{len(ids)}] ID {mid} 에러: {e}")

    # LLM API 과부하 방지 — 1건당 2초 대기
    time.sleep(2)

elapsed = time.time() - start
print(f"\n완료: 성공 {success}, 실패 {fail}, 소요 {elapsed:.0f}초")
