"""LM Studio 클라이언트 (OpenAI-compatible API)"""
import aiohttp
from app.llm.provider import BaseLLMClient


class LMStudioClient(BaseLLMClient):
    """LM Studio의 /v1/chat/completions 엔드포인트를 사용하는 클라이언트."""

    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = ""

    async def chat(self, system_prompt: str, user_message: str) -> str:
        url = f"{self.endpoint}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
            "stream": False,
        }

        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"LM Studio 오류 ({resp.status}): {error}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def chat_stream(self, system_prompt: str, user_message: str):
        """LM Studio 스트리밍 응답 (OpenAI SSE 포맷). 토큰 단위로 yield."""
        url = f"{self.endpoint}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
            "stream": True,
        }

        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"LM Studio 오류 ({resp.status}): {error}")
                import json

                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        continue

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.endpoint}/v1/models",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
