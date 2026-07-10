import aiohttp
from app.llm.provider import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    API_URL = "https://api.openai.com/v1/chat/completions"

    async def chat(self, system_prompt: str, user_message: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.API_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"OpenAI API 오류 ({resp.status}): {error}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.openai.com/v1/models",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
