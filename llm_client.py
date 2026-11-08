"""Application transport for DeepSeek/OpenAI. Importing never calls an API."""
import os
import time

import httpx

from config import BASE_DIR  # loads the local environment before settings

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
if LLM_PROVIDER not in {"deepseek", "openai"}:
    raise ValueError("LLM_PROVIDER must be deepseek or openai")
LLM_MODEL = (os.getenv("DEEPSEEK_MODEL", "deepseek-flash") if LLM_PROVIDER == "deepseek"
             else os.getenv("OPENAI_MODEL", "")).strip()


def call_llm(messages, max_tokens=900, *, transport=None):
    """Bounded transient retries; never retry authentication or empty/truncated output."""
    key = os.getenv("DEEPSEEK_API_KEY" if LLM_PROVIDER == "deepseek" else "OPENAI_API_KEY", "")
    if not key or not LLM_MODEL:
        raise RuntimeError(f"Configure {LLM_PROVIDER.upper()}_API_KEY and {LLM_PROVIDER.upper()}_MODEL")
    payload = {"model": LLM_MODEL, "messages": messages, "stream": False}
    if LLM_PROVIDER == "deepseek":
        base = "https://api.deepseek.com"
        payload.update(max_tokens=max_tokens, temperature=0, thinking={"type": "disabled"})
    else:
        base = "https://api.openai.com/v1"
        payload.update(max_completion_tokens=max_tokens)
        effort = os.getenv("OPENAI_REASONING_EFFORT", "").strip()
        if effort:
            payload["reasoning_effort"] = effort
    with httpx.Client(base_url=base, headers={"Authorization": "Bearer " + key},
                      timeout=120, follow_redirects=False, transport=transport) as client:
        for attempt in range(3):
            try:
                response = client.post("/chat/completions", json=payload)
            except httpx.TransportError:
                if attempt == 2:
                    raise RuntimeError("LLM transport failed after 3 attempts") from None
                time.sleep(2 ** attempt)
                continue
            if response.status_code != 200:
                if (response.status_code == 429 or response.status_code >= 500) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"{LLM_PROVIDER} API HTTP {response.status_code}")
            choice = response.json()["choices"][0]
            content = choice["message"].get("content")
            if choice.get("finish_reason") != "stop" or not isinstance(content, str) or not content.strip():
                raise RuntimeError("LLM output is empty, truncated or incomplete")
            return content.strip()
