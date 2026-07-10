"""HTTP HTML 응답 바이트 → str 복원 (한국 사이트·레거시 charset 대응)."""

import re

_CHARSET_HEADER_RE = re.compile(r"charset\s*=\s*['\"]?([\w._-]+)", re.I)


def decode_http_response_text(resp) -> str:
    """requests 응답 body(bytes)를 Content-Type·cp949·chardet 순으로 str로 복원."""
    raw: bytes = resp.content or b""
    if not raw:
        return ""
    # 1) Content-Type의 charset= 우선
    try:
        ct = (resp.headers.get("Content-Type") or "")
        m = _CHARSET_HEADER_RE.search(ct)
        if m:
            name = m.group(1).strip().strip("'\"").lower()
            candidates: list[str] = [name]
            if name in ("euc-kr", "ks_c_5601-1987", "ksc5601", "windows-949"):
                candidates.extend(["cp949", "euc-kr"])
            for enc in candidates:
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
    except Exception:
        pass
    # 2) UTF-8 (BOM 허용)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    # 3) chardet (requests)
    try:
        enc = getattr(resp, "apparent_encoding", None) or ""
        if enc and str(enc).lower() not in ("ascii", "binary"):
            return raw.decode(enc, errors="replace")
    except Exception:
        pass
    # 4) cp949
    try:
        return raw.decode("cp949", errors="replace")
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")


def text_likely_mojibake_korean(s: str | None) -> bool:
    """잘못 UTF-8 디코딩된 한국어(모지바케) 가능성. 재수집·보정 판별용 휴리스틱."""
    if not s or len(s) < 4:
        return False
    # 흔한 mojibake·Latin1 깨짐 토막
    bad_fragments = (
        "â€", "Â·", "Ã", "ë§¤", "ìˆ˜", "í†", "í™”", "ë‹ˆ", "ê²½",
    )
    if any(f in s for f in bad_fragments):
        return True
    hang = sum(1 for c in s if "\uac00" <= c <= "\ud7a3")
    if len(s) > 15 and hang < max(3, len(s) // 20):
        for c in s:
            o = ord(c)
            if o > 0x7F and o not in (0x00B7, 0x2022, 0x2026, 0x2013, 0x2014):
                return True
    return False
