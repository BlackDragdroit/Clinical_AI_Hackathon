"""All settings come from the environment (.env locally, docker-compose in the stack). Owner: SWE 1."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    base_url: str = _env("BASE_URL", "http://localhost:8000")            # public portal URL that goes into links
    db_path: str = _env("DB_PATH", str(ROOT / "var" / "befundbruecke.sqlite"))
    var_dir: str = _env("VAR_DIR", str(ROOT / "var"))
    secret_key: str = _env("SECRET_KEY", "dev-only-change-me")            # signs session cookies + mock eID assertions

    clinic_name: str = _env("CLINIC_NAME", "Klinikum Beispielstadt")
    doctor_mxid: str = _env("DOCTOR_MXID", "@lena.hofer:klinikum.example")
    doctor_name: str = _env("DOCTOR_NAME", "Dr. Lena Hofer")
    # Matrix IDs allowed to send commands (the clinic directory; here only Dr. Hofer)
    authorized_senders: tuple[str, ...] = field(default_factory=lambda: tuple(
        s.strip() for s in _env("AUTHORIZED_SENDERS", _env("DOCTOR_MXID", "@lena.hofer:klinikum.example")).split(",") if s.strip()))

    hapi_url: str = _env("HAPI_URL", "http://localhost:8090/fhir")        # what the app talks to
    hapi_public_url: str = _env("HAPI_PUBLIC_URL", "http://localhost:8090/fhir")   # what links in Matrix point to

    smtp_host: str = _env("SMTP_HOST", "localhost")
    smtp_port: int = int(_env("SMTP_PORT", "1025"))
    mail_from: str = _env("MAIL_FROM", "no-reply@klinikum.example")
    mailpit_api: str = _env("MAILPIT_API", "http://localhost:8025/api/v1")

    matrix_enabled: bool = _env("MATRIX_ENABLED", "0") == "1"             # 0 = notifications go to the console
    matrix_homeserver: str = _env("MATRIX_HOMESERVER", "http://localhost:8008")
    matrix_bot_user: str = _env("MATRIX_BOT_USER", "@befundbruecke:klinikum.example")
    matrix_bot_password: str = _env("MATRIX_BOT_PASSWORD", "")
    matrix_room_id: str = _env("MATRIX_ROOM_ID", "")
    chat_images: bool = _env("CHAT_IMAGES", "0") == "1"   # drawn icons/bridges inline; needs unauthenticated media

    llm_provider: str = _env("LLM_PROVIDER", "openai_compatible")         # vLLM/Ollama behind an OpenAI-style API
    llm_base_url: str = _env("LLM_BASE_URL", "http://localhost:8001/v1")  # SSH tunnel to the GPU instance
    llm_model: str = _env("LLM_MODEL", "ministral-8b")
    llm_api_key: str = _env("LLM_API_KEY", "")                            # empty = no Authorization header
    llm_timeout: float = float(_env("LLM_TIMEOUT", "120"))

    email_channel: str = _env("EMAIL_CHANNEL", "mailpit")                 # mailpit | ftapi
    link_ttl_hours: int = int(_env("LINK_TTL_HOURS", "72"))
    max_identity_attempts: int = int(_env("MAX_IDENTITY_ATTEMPTS", "5"))
    known_domains: tuple[str, ...] = field(default_factory=lambda: tuple(
        d.strip() for d in _env("KNOWN_DOMAINS", "labor-kanal.example,reha-waldblick.example").split(",") if d.strip()))


settings = Settings()
