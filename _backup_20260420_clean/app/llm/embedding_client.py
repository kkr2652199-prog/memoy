"""Ollama 임베딩 클라이언트 (nomic-embed-text-v2-moe)"""
import httpx
import numpy as np
import logging
from typing import Optional

log = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text-v2-moe"


def get_embedding_sync(text: str, model: str = EMBED_MODEL) -> Optional[list[float]]:
    """텍스트 → 768차원 벡터 (동기)"""
    if not text or not text.strip():
        return None
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": model, "input": text[:8000]}
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"][0]
    except Exception as e:
        log.error(f"임베딩 실패: {e}")
        return None


async def get_embedding(text: str, model: str = EMBED_MODEL) -> Optional[list[float]]:
    """텍스트 → 768차원 벡터 (비동기)"""
    if not text or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": model, "input": text[:8000]}
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"][0]
    except Exception as e:
        log.error(f"임베딩 실패: {e}")
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """코사인 유사도 계산"""
    a_np, b_np = np.array(a), np.array(b)
    dot = np.dot(a_np, b_np)
    norm = np.linalg.norm(a_np) * np.linalg.norm(b_np)
    if norm < 1e-10:
        return 0.0
    return float(dot / norm)
