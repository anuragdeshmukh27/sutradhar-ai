"""Single LLM entry point: provider interface, live/record/replay, retry + model fallback."""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv(Path(__file__).resolve().parents[2] / ".env", encoding="utf-8-sig")

T = TypeVar("T", bound=BaseModel)
CASSETTE_DIR = Path(__file__).resolve().parents[1] / "cassettes"
RETRYABLE = {429, 503}
MAX_ATTEMPTS = 4  # per model
BASE_DELAY = 1.0  # seconds; doubles each attempt
COOLDOWN = 60.0  # after a model exhausts its retries, skip it for this long (when a fallback exists)
_skip_until: dict[str, float] = {}


class LLMError(Exception):
    """Friendly, UI-safe error."""


class GeminiProvider:
    def __init__(self):
        from google import genai

        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def generate(self, model: str, system: str, prompt: str, schema: Type[BaseModel]) -> str:
        from google.genai import types

        resp = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(system + "\n\n" if system else "")
                + "Reply with JSON only, matching this JSON Schema:\n"
                + json.dumps(schema.model_json_schema()),
                response_mime_type="application/json",
            ),
        )
        return resp.text

    @staticmethod
    def status_code(exc: Exception) -> int | None:
        return getattr(exc, "code", None) or getattr(exc, "status_code", None)


def _provider():
    name = os.getenv("LLM_PROVIDER", "gemini")
    if name == "gemini":
        return GeminiProvider()
    raise LLMError(f"Unsupported LLM_PROVIDER '{name}'")


def _generate_with_fallback(provider, system: str, prompt: str, schema: Type[BaseModel]) -> str:
    primary = os.environ["LLM_MODEL"]
    fallback = os.getenv("LLM_FALLBACK_MODEL")
    models = [primary] + ([fallback] if fallback and fallback != primary else [])
    last: Exception | None = None
    live = [m for m in models if _skip_until.get(m, 0) <= time.monotonic()]
    for model in live or models:
        for attempt in range(MAX_ATTEMPTS):
            try:
                return provider.generate(model, system, prompt, schema)
            except Exception as exc:  # noqa: BLE001
                if provider.status_code(exc) not in RETRYABLE:
                    raise LLMError(f"LLM call failed: {exc}") from exc
                last = exc
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(BASE_DELAY * 2**attempt)
        _skip_until[model] = time.monotonic() + COOLDOWN
        print(f"[llm] {model} unavailable after {MAX_ATTEMPTS} attempts; trying next model")
    raise LLMError("The AI service is busy right now. Please try again in a minute.") from last


def _key(system: str, prompt: str, schema: Type[BaseModel]) -> str:
    return hashlib.sha256(f"{schema.__name__}\n{system}\n{prompt}".encode()).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def call(prompt: str, schema: Type[T], system: str = "", scenario: str = "default") -> T:
    """Return a validated `schema` instance. Mode comes from LLM_MODE (live|record|replay)."""
    mode = os.getenv("LLM_MODE", "live")
    key = _key(system, prompt, schema)
    cassette = CASSETTE_DIR / f"{scenario}.json"

    if mode == "replay":
        data = _load(cassette)
        if key not in data:
            raise LLMError(f"No recorded response for this prompt in cassette '{scenario}'.")
        return schema.model_validate_json(data[key])

    provider = _provider()
    p = prompt
    for attempt in range(2):  # one automatic retry on validation failure
        raw = _generate_with_fallback(provider, system, p, schema)
        try:
            result = schema.model_validate_json(raw)
            break
        except ValidationError as exc:
            if attempt == 1:
                raise LLMError("The AI returned an invalid response. Please retry.") from exc
            p = f"{prompt}\n\nYour previous reply failed validation:\n{exc}\nReturn valid JSON only."

    if mode == "record":
        CASSETTE_DIR.mkdir(exist_ok=True)
        data = _load(cassette)
        data[key] = result.model_dump_json()
        cassette.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
