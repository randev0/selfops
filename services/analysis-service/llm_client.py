import json
import os
import structlog
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

log = structlog.get_logger()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
async def _call_openrouter(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://github.com/selfops",
                "X-Title": "SelfOps",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-3-haiku",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1024,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def call_llm(prompt: str) -> dict:
    if not OPENROUTER_API_KEY:
        log.warning("OPENROUTER_API_KEY not set, returning stub analysis")
        return {
            "summary": "Analysis skipped — OpenRouter API key not configured.",
            "probable_cause": "Unknown — manual investigation required.",
            "evidence_points": ["API key missing"],
            "recommended_action_id": None,
            "confidence": 0.0,
            "escalate": True,
        }

    try:
        raw_text = await _call_openrouter(prompt)
        log.info("LLM response received", length=len(raw_text))
    except Exception as exc:
        log.error("LLM call failed after retries", error=str(exc))
        return {"error": "llm_call_failed", "raw": str(exc)}

    # Try to parse JSON from the response
    try:
        # Strip any accidental markdown code fences
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Failed to parse LLM JSON response", raw=raw_text[:200])
        return {"error": "parse_failed", "raw": raw_text}
