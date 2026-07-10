import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"

RAW_MATERIALS_DIR = BASE_DIR / "Raw_Materials"
WIKI_DIR = BASE_DIR / "Wiki"
INDEX_MD = BASE_DIR / "index.md"
LOG_MD = BASE_DIR / "log.md"

DEFAULT_CONFIG = {
    "llm": {
        "default_provider": "openai",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "claude_api_key": "",
        "claude_model": "claude-sonnet-4-20250514",
        "gemini_api_key": "",
        "gemini_model": "gemini-2.0-flash",
        "local_endpoint": "http://localhost:11434",
        "local_model": "llama3",
        "lmstudio_endpoint": "http://localhost:1234",
        "lmstudio_model": "gemma4:e2b",
        "lmstudio_model_ids": [],
    },
    "library": {
        "auto_classify": True,
        "auto_cross_reference": True,
        "importance_default": 3,
        "language": "ko",
    },
    "scheduler": {
        "enabled": False,
        "interval_hours": 24,
    },
    "ui": {
        "theme": "dark",
        "items_per_page": 20,
    },
    "classification": {
        "topics": [
            "경제", "정치", "사회", "기술", "투자", "부동산",
            "영상제작", "마케팅", "자기계발", "과학", "문화예술",
            "AI", "프로그래밍", "디자인", "교육", "기타",
        ],
    },
}


def _migrate_scheduler_keys(cfg: dict) -> dict:
    """scheduler.health_check_* → scheduler.enabled / interval_hours 통일."""
    sched = cfg.get("scheduler")
    if not isinstance(sched, dict):
        return cfg
    if "interval_hours" not in sched and "health_check_interval_hours" in sched:
        try:
            sched["interval_hours"] = int(sched["health_check_interval_hours"])
        except (TypeError, ValueError):
            sched["interval_hours"] = 24
    # deep_merge로 기본 enabled=False가 들어와 예전 health_check_enabled=True가 덮어쓰이지 못한 경우
    if sched.get("health_check_enabled") is True and sched.get("enabled") is False:
        sched["enabled"] = True
    return cfg


def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        merged = _deep_merge(DEFAULT_CONFIG, user_cfg)
        merged = _migrate_scheduler_keys(merged)
        return merged
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_value(key_path: str, default=None):
    cfg = load_config()
    keys = key_path.split(".")
    current = cfg
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


def set_value(key_path: str, value):
    cfg = load_config()
    keys = key_path.split(".")
    current = cfg
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    current[keys[-1]] = value
    save_config(cfg)


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
