"""LM Studio 임베딩 클라이언트 (BGE-M3, 1024차원)"""
import httpx
import numpy as np
import logging
from typing import Optional
import time as _time

log = logging.getLogger(__name__)

_embed_fail_until = 0.0
_EMBED_COOLDOWN = 30

LMSTUDIO_BASE = "http://localhost:1234"
EMBED_MODEL = "text-embedding-bge-m3"
EMBED_DIM = 1024


def get_embedding_sync(text: str, model: str = EMBED_MODEL) -> Optional[list[float]]:
    """텍스트 → 1024차원 벡터 (동기)"""
    global _embed_fail_until
    if _time.time() < _embed_fail_until:
        return None
    if not text or not text.strip():
        return None
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=1.0)) as client:
            resp = client.post(
                f"{LMSTUDIO_BASE}/v1/embeddings",
                json={"model": model, "input": text[:8000]}
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as e:
        log.error(f"임베딩 실패: {e}")
        _embed_fail_until = _time.time() + _EMBED_COOLDOWN
        return None


async def get_embedding(text: str, model: str = EMBED_MODEL) -> Optional[list[float]]:
    """텍스트 → 1024차원 벡터 (비동기)"""
    global _embed_fail_until
    if _time.time() < _embed_fail_until:
        return None
    if not text or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as client:
            resp = await client.post(
                f"{LMSTUDIO_BASE}/v1/embeddings",
                json={"model": model, "input": text[:8000]}
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as e:
        log.error(f"임베딩 실패: {e}")
        _embed_fail_until = _time.time() + _EMBED_COOLDOWN
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """코사인 유사도 계산"""
    a_np, b_np = np.array(a), np.array(b)
    dot = np.dot(a_np, b_np)
    norm = np.linalg.norm(a_np) * np.linalg.norm(b_np)
    if norm < 1e-10:
        return 0.0
    return float(dot / norm)
