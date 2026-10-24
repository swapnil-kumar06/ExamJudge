"""Thin OpenAI-compatible client configured for Google Gemini. Temperature is fixed at 0.0."""
from __future__ import annotations
import json
import re
import time

OFFLINE = "Offline baseline (no API key)"

GEMINI = "Google Gemini"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# The deployed dashboard intentionally offers no arbitrary/custom endpoint. This
# prevents an app visitor from redirecting a server-held API key to another host.
PROVIDERS = {
    OFFLINE: {"base_url": "", "model": "keyword-rubric-baseline", "env": ""},
    GEMINI: {"base_url": GEMINI_BASE_URL, "model": "gemini-2.5-flash", "env": "GEMINI_API_KEY"},
}


class LLMError(Exception):
    pass


def extract_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("Model did not return JSON")
    try:
        return json.loads(t[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"Invalid JSON from model: {e}")


def chat_json(cfg, messages) -> dict:
    """Call the configured Gemini-compatible endpoint and return parsed JSON.

    API secrets stay on the server. Error messages are intentionally sanitized so
    provider request details and credentials are never reflected in the UI.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError("The openai compatibility client is not installed. Install requirements.txt.") from e
    if not cfg.api_key:
        raise LLMError("Gemini API key is not configured on the server. Add GEMINI_API_KEY in Streamlit Secrets.")
    if cfg.provider == GEMINI and cfg.base_url.rstrip("/") != GEMINI_BASE_URL.rstrip("/"):
        raise LLMError("Gemini endpoint configuration is invalid. Restore the official Gemini-compatible endpoint.")

    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url or None,
                    timeout=45, max_retries=0)
    use_json_mode = True
    last = LLMError("Gemini request failed.")
    for attempt in range(max(0, min(int(cfg.max_retries), 2)) + 1):
        try:
            kwargs = dict(model=cfg.model, messages=messages, temperature=0.0)
            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            return extract_json(content)
        except LLMError as e:
            last = e
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status in (401, 403):
                raise LLMError("Gemini authentication failed. Check GEMINI_API_KEY in Streamlit Secrets.") from None
            if status == 429:
                raise LLMError("Gemini rate limit or quota reached. Wait, reduce requests, or check your provider quota.") from None
            if use_json_mode and ("response_format" in str(e).lower() or "json mode" in str(e).lower()):
                use_json_mode = False
                continue
            if status == 400:
                last = LLMError("Gemini rejected the request. Check GEMINI_MODEL and the prompt size.")
            elif status and status >= 500:
                last = LLMError("Gemini is temporarily unavailable. Try again later.")
            elif isinstance(status, int):
                last = LLMError(f"Gemini request failed (HTTP {status}). Check model configuration and quota.")
            else:
                last = LLMError("Could not reach Gemini. Check connectivity and your model configuration.")
        if attempt < max(0, min(int(cfg.max_retries), 2)):
            time.sleep(1.0 * (attempt + 1))
    raise last
