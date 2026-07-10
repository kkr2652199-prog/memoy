import aiohttp
from app.llm.provider import BaseLLMClient


class GeminiClient(BaseLLMClient):
    API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    async def chat(self, system_prompt: str, user_message: str) -> str:
        url = f"{self.API_BASE}/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": user_message}]},
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 8192,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"Gemini API 오류 ({resp.status}): {error}")
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            url = f"{self.API_BASE}?key={self.api_key}"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
