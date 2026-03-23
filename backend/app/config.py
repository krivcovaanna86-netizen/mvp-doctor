"""Application configuration."""

import os
import yaml
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
EXPORTS_DIR = BASE_DIR / "exports"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "backend" / "templates"

UPLOADS_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(exist_ok=True)

# --- OpenAI / LLM config ---
def _load_openai_config():
    """Load OpenAI config from yaml or env vars."""
    config_path = Path.home() / ".genspark_llm.yaml"
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "")

    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
            if cfg and "openai" in cfg:
                api_key = api_key or cfg["openai"].get("api_key", "")
                base_url = base_url or cfg["openai"].get("base_url", "")

    return api_key, base_url

OPENAI_API_KEY, OPENAI_BASE_URL = _load_openai_config()
LLM_MODEL = "gpt-5"

# --- Audio settings ---
MAX_AUDIO_SIZE_MB = 50
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/wav", "audio/mp3",
    "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/flac",
    "video/webm",  # browser sometimes sends this for audio/webm
}

# --- App settings ---
APP_TITLE = "МедЗапись — AI-ассистент врача"
APP_VERSION = "1.0.0-mvp"
