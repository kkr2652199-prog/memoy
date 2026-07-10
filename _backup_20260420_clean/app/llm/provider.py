import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

FALLBACK_ORDER = ["openai", "claude", "gemini", "local"]
KEY_FIELDS = {
    "openai": "openai_api_key",
    "claude": "claude_api_key",
    "gemini": "gemini_api_key",
}


class BaseLLMClient(ABC):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def chat(self, system_prompt: str, user_message: str) -> str:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


def get_provider(provider_name: str, config: dict) -> BaseLLMClient:
    llm_cfg = config["llm"]

    if provider_name == "openai":
        from app.llm.openai_client import OpenAIClient
        return OpenAIClient(
            api_key=llm_cfg.get("openai_api_key", ""),
            model=llm_cfg.get("openai_model", "gpt-4o-mini"),
        )
    elif provider_name == "claude":
        from app.llm.claude_client import ClaudeClient
        return ClaudeClient(
            api_key=llm_cfg.get("claude_api_key", ""),
            model=llm_cfg.get("claude_model", "claude-sonnet-4-20250514"),
        )
    elif provider_name == "gemini":
        from app.llm.gemini_client import GeminiClient
        return GeminiClient(
            api_key=llm_cfg.get("gemini_api_key", ""),
            model=llm_cfg.get("gemini_model", "gemini-2.0-flash"),
        )
    elif provider_name == "local":
        from app.llm.local_client import LocalClient
        return LocalClient(
            endpoint=llm_cfg.get("local_endpoint", "http://localhost:11434"),
            model=llm_cfg.get("local_model", "llama3"),
        )
    else:
        raise ValueError(f"지원하지 않는 LLM 제공자: {provider_name}")


def find_available_provider(config: dict) -> str | None:
    """키가 설정된 제공자를 우선순위대로 찾는다. 기본 제공자를 가장 먼저 시도."""
    llm_cfg = config["llm"]
    default = llm_cfg.get("default_provider", "openai")

    if default in KEY_FIELDS:
        if llm_cfg.get(KEY_FIELDS[default], ""):
            return default

    for name in FALLBACK_ORDER:
        if name == default or name == "local":
            continue
        if name in KEY_FIELDS and llm_cfg.get(KEY_FIELDS[name], ""):
            if default != name:
                logger.info("기본 제공자 '%s' 사용 불가 → '%s'로 폴백", default, name)
            return name

    if default == "local":
        return default

    return None


def list_providers() -> list[dict]:
    return [
        {"id": "openai", "name": "OpenAI (GPT)", "requires_key": True},
        {"id": "claude", "name": "Anthropic (Claude)", "requires_key": True},
        {"id": "gemini", "name": "Google (Gemini)", "requires_key": True},
        {"id": "local", "name": "로컬 LLM (Ollama 등)", "requires_key": False},
    ]


def normalize_chat_provider_id(raw: str | None) -> str | None:
    """빈 문자열·기본 설정 → None. 유효한 제공자 id만 반환."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s in ("default", "auto"):
        return None
    allowed = {"openai", "claude", "gemini", "local"}
    return s if s in allowed else None


def build_chat_provider_candidates(config: dict, preferred: str | None) -> list[str]:
    """채팅 시도 순서: (선호 제공자) → find_available → FALLBACK_ORDER."""
    llm_cfg = config.get("llm", {})
    seen: set[str] = set()
    out: list[str] = []

    def add(name: str) -> None:
        if name in seen:
            return
        if name not in ("openai", "claude", "gemini", "local"):
            return
        if name == "local":
            seen.add(name)
            out.append(name)
            return
        k = KEY_FIELDS.get(name)
        if k and llm_cfg.get(k, ""):
            seen.add(name)
            out.append(name)

    pref = normalize_chat_provider_id(preferred)
    if pref:
        add(pref)
    avail = find_available_provider(config)
    if avail:
        add(avail)
    for name in FALLBACK_ORDER:
        add(name)
    return out
