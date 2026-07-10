import aiohttp
from app.llm.provider import BaseLLMClient


class ClaudeClient(BaseLLMClient):
    API_URL = "https://api.anthropic.com/v1/messages"

    async def chat(self, system_prompt: str, user_message: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message},
            ],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.API_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"Claude API 오류 ({resp.status}): {error}")
                data = await resp.json()
                return data["content"][0]["text"]

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
