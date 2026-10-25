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
    """Call Gemini and return validated JSON with clearer error handling."""
    try:
        from openai import (
            OpenAI,
            APIConnectionError,
            APITimeoutError,
            APIStatusError,
            RateLimitError,
            AuthenticationError,
            NotFoundError,
            BadRequestError,
        )
    except ImportError:
        raise LLMError(
            "The OpenAI-compatible client is missing. Install requirements.txt."
        ) from None

    if not cfg.api_key:
        raise LLMError("Gemini API key is not configured on the server.")

    if (
        cfg.provider == GEMINI
        and cfg.base_url.rstrip("/") != GEMINI_BASE_URL.rstrip("/")
    ):
        raise LLMError("Invalid Gemini endpoint configuration.")

    client = OpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url or None,
        timeout=120,
        max_retries=0,
    )

    retries = max(0, min(int(cfg.max_retries), 2))
    use_json_mode = True
    attempt = 0

    while attempt <= retries:
        try:
            kwargs = {
                "model": cfg.model,
                "messages": messages,
                "temperature": 0.0,
            }

            if use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""

            return extract_json(content)

        except AuthenticationError:
            raise LLMError(
                "Gemini authentication failed. Check the server API key."
            ) from None

        except RateLimitError:
            raise LLMError(
                "Gemini rate limit or quota exceeded (HTTP 429). "
                "Check AI Studio usage and retry after the quota resets."
            ) from None

        except NotFoundError:
            raise LLMError(
                f"Gemini returned HTTP 404. Check whether model "
                f"'{cfg.model}' is available for this API endpoint and key."
            ) from None

        except BadRequestError as exc:
            # Retry without JSON mode only when the provider explicitly
            # rejects the JSON response-format parameter.
            message = str(exc).lower()

            if use_json_mode and (
                "response_format" in message
                or "json mode" in message
                or "response mime type" in message
            ):
                use_json_mode = False
                continue

            raise LLMError(
                "Gemini rejected the request (HTTP 400). "
                "Check the model, input size, and request format."
            ) from None

        except APITimeoutError:
            error_message = "Gemini request timed out."

        except APIConnectionError:
            error_message = (
                "Could not connect to Gemini. Check network connectivity "
                "and the configured API endpoint."
            )

        except APIStatusError as exc:
            status = exc.status_code

            if status == 403:
                error_message = (
                    "Gemini returned HTTP 403. Check API access, "
                    "permissions, and project restrictions."
                )
            elif status == 503:
                error_message = (
                    "Gemini is temporarily unavailable (HTTP 503)."
                )
            else:
                error_message = f"Gemini request failed with HTTP {status}."

        except LLMError:
            raise

        except Exception as exc:
            # Keep credentials and raw provider responses out of the UI.
            raise LLMError(
                f"Unexpected grading error ({type(exc).__name__}). "
                "Check server logs for details."
            ) from None

        if attempt < retries:
            time.sleep(1.5 * (2 ** attempt))
            attempt += 1
        else:
            raise LLMError(error_message) from None


