"""
AI-powered relevance scorer using Google Gemini.

When enabled (matcher: ai in config.yaml), each message that passes the
keyword pre-filter is sent to Gemini along with the area's description.
Gemini returns a JSON relevance assessment that drives the final match decision.

Rate limiting: The free Gemini Flash tier allows 15 RPM / 1 500 RPD.
A semaphore caps concurrent requests; exponential backoff handles quota errors.
"""

import asyncio
import json
import os
from typing import Optional

from google import genai
from google.genai import errors

from telefeed.display import print_warning


# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a strict relevance filter for a personalized Telegram feed reader. "
    "Your only job is to decide if a Telegram message matches a user's stated interest area. "
    "Be selective — only mark as a match when the message is clearly and directly relevant. "
    "Always reply with valid JSON only. No prose, no markdown, no code fences."
)

_USER_TMPL = """\
Interest area: "{area_name}"
User's goal / description:
{description}

Telegram message to evaluate:
\"\"\"
{text}
\"\"\"

Reply ONLY with this exact JSON (no other text):
{{"match": true_or_false, "score": 0_to_100, "reason": "one concise sentence"}}

Guidelines:
- score 0-100 reflects how relevant the message is to the goal
- match is true only when score >= {threshold}
- reason must be a single sentence (≤ 20 words)
- If the message is unrelated, off-topic, or just noise, match: false
"""


# ──────────────────────────────────────────────────────────────────────────────
# AIScorer
# ──────────────────────────────────────────────────────────────────────────────

class AIScorer:
    """
    Async Gemini-based relevance scorer.

    Usage::

        scorer = AIScorer.from_env()          # reads GEMINI_API_KEY
        match, score, reason = await scorer.score(area_name, description, text, threshold)
    """

    # Limit concurrent Gemini calls to avoid hitting RPM quota
    _SEMAPHORE = asyncio.Semaphore(5)
    _MAX_RETRIES = 3
    _RETRY_BASE = 2.0   # seconds — doubles on each retry

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        # In-process cache: (area_name, text_prefix) → (match, score, reason)
        # Avoids re-scoring the same post if it appears in multiple batches
        self._cache: dict[tuple[str, str], tuple[bool, int, str]] = {}
        self.calls_made: int = 0
        self.calls_cached: int = 0

    @classmethod
    def from_env(cls, key: str = "") -> "AIScorer":
        """Build scorer from Gemini API key string or GEMINI_API_KEY environment variable."""
        api_key = key or os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError(
                "Gemini API key is not configured.\n"
                "Add 'api_key' under 'gemini:' in your config.yaml "
                "or set GEMINI_API_KEY in environment.\n"
                "Get a free key at https://aistudio.google.com/apikey"
            )
        return cls(api_key=api_key)

    async def score(
        self,
        area_name: str,
        description: str,
        text: str,
        threshold: int = 65,
    ) -> tuple[bool, int, str]:
        """
        Score *text* against an area's *description* using Gemini.

        Returns:
            (match: bool, score: int 0-100, reason: str)

        On any API error the function returns (False, 0, "<error description>")
        rather than raising, so a single bad response never breaks the run.
        """
        cache_key = (area_name, text[:300])
        if cache_key in self._cache:
            self.calls_cached += 1
            return self._cache[cache_key]

        prompt = _USER_TMPL.format(
            area_name=area_name,
            description=description.strip() or "(no description provided)",
            text=text[:2000],   # truncate extremely long messages
            threshold=threshold,
        )

        result = await self._call_with_retry(prompt)
        self._cache[cache_key] = result
        self.calls_made += 1
        return result

    async def _call_with_retry(self, prompt: str) -> tuple[bool, int, str]:
        """Call Gemini with exponential backoff on quota/server errors."""
        async with self._SEMAPHORE:
            for attempt in range(self._MAX_RETRIES):
                try:
                    response = await self._client.aio.models.generate_content(
                        model=self._model_name,
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            system_instruction=_SYSTEM,
                            temperature=0.1,
                            response_mime_type="application/json",
                        )
                    )
                    return _parse_response(response.text)
                except errors.APIError as exc:
                    if exc.code in (429, 503):
                        wait = self._RETRY_BASE ** (attempt + 1)
                        print_warning(
                            f"Gemini rate limited — waiting {wait:.0f}s (attempt {attempt + 1}/{self._MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        return (False, 0, f"[AI error: {exc.message}]")
                except Exception as exc:
                    return (False, 0, f"[AI error: {type(exc).__name__}: {exc}]")

        return (False, 0, "[AI error: max retries exceeded]")

    def stats(self) -> str:
        total = self.calls_made + self.calls_cached
        return (
            f"AI calls: {self.calls_made} to Gemini, "
            f"{self.calls_cached} from cache "
            f"({total} total)"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_response(raw: str) -> tuple[bool, int, str]:
    """
    Parse Gemini's JSON response.  Handles edge cases gracefully:
    - Strips accidental code fences
    - Falls back to False on malformed JSON
    """
    text = raw.strip()
    # Strip markdown code fences Gemini sometimes adds despite the instruction
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        match = bool(data.get("match", False))
        score = max(0, min(100, int(data.get("score", 0))))
        reason = str(data.get("reason", "")).strip()
        return (match, score, reason)
    except (json.JSONDecodeError, ValueError, KeyError):
        return (False, 0, f"[Could not parse AI response: {raw[:80]}]")


# ──────────────────────────────────────────────────────────────────────────────
# Matching helper used by cli.py
# ──────────────────────────────────────────────────────────────────────────────

async def ai_check_all_areas(
    areas: list,
    text: str,
    scorer: AIScorer,
    threshold: int,
) -> list:
    """
    AI-mode replacement for filters.check_all_areas().

    Pipeline per area:
      1. Negative keyword gate — hard discard (no AI call)
      2. Positive keyword pre-filter — if area has keywords, at least one must hit
         (saves AI quota; areas with no keywords bypass this step)
      3. Gemini scores the message vs. the area's description
      4. Return MatchResult only if score >= threshold

    Returns a list of MatchResult objects (same type as keyword mode).
    """
    from telefeed.filters import check_area, MatchResult

    results: list[MatchResult] = []

    for area in areas:
        # ── Step 1: negative keyword gate (free) ──────────────────────────────
        kw_result = check_area(area, text)
        if kw_result.blocked_by is not None:
            continue  # hard discard — don't even call AI

        # ── Step 2: positive keyword pre-filter ───────────────────────────────
        # If the area has keywords, require at least one hit before calling AI.
        # Areas with no keywords skip straight to AI (user opted for full scan).
        if area.keywords and not kw_result.is_match:
            continue

        # ── Step 3: Gemini scoring ─────────────────────────────────────────────
        match, score, reason = await scorer.score(
            area_name=area.name,
            description=area.description,
            text=text,
            threshold=threshold,
        )

        if match:
            # Overwrite the keyword score with the AI score (0.0–1.0 range)
            kw_result.score = score / 100.0
            kw_result.ai_reason = reason
            results.append(kw_result)

    return results
