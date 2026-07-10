import aiohttp
from app.llm.provider import BaseLLMClient


class LocalClient(BaseLLMClient):
    def __init__(self, endpoint: str, model: str):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = ""

    async def chat(self, system_prompt: str, user_message: str) -> str:
        url = f"{self.endpoint}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }

        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"로컬 LLM 오류 ({resp.status}): {error}")
                data = await resp.json()
                return data["message"]["content"]

    async def chat_stream(self, system_prompt: str, user_message: str):
        """Ollama 스트리밍 응답. 토큰 단위로 yield한다."""
        url = f"{self.endpoint}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": True,
        }

        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"로컬 LLM 오류 ({resp.status}): {error}")
                import json

                async for line in resp.content:
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if chunk.get("done", False):
                                return
                        except json.JSONDecodeError:
                            continue

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.endpoint}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
