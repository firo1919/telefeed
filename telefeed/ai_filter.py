"""
AI-powered relevance scorer with multi-provider support.

Supported providers:
  - gemini     : Google Gemini (native google-genai SDK)
  - openai     : OpenAI GPT models (openai SDK)
  - anthropic  : Anthropic Claude (anthropic SDK)
  - ollama     : Local Ollama models (OpenAI-compatible endpoint)
  - openrouter : OpenRouter (OpenAI-compatible endpoint, 100+ models)

All scorers share the same BaseScorer interface and the same
3-stage filtering pipeline used by ai_check_all_areas().

Rate limiting: a semaphore caps concurrent requests to avoid hitting
provider RPM limits. Exponential backoff handles transient 429/503 errors.
"""

from __future__ import annotations

import abc
import asyncio
import json
import os
from typing import Optional

from telefeed.display import print_warning


# ──────────────────────────────────────────────────────────────────────────────
# Shared prompt templates (provider-agnostic)
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
# Response parsing (shared across providers)
# ──────────────────────────────────────────────────────────────────────────────

def _parse_response(raw: str) -> tuple[bool, int, str]:
    """
    Parse JSON response from any AI provider.

    Handles:
    - Markdown code fences (```json ... ```)
    - Malformed JSON (returns safe fallback)
    """
    text = raw.strip()
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
# Base scorer (ABC)
# ──────────────────────────────────────────────────────────────────────────────

class BaseScorer(abc.ABC):
    """
    Abstract base class for all AI scorer backends.

    Subclasses must implement _call_with_retry().
    Caching, semaphore control, and the public score() method live here.
    """

    _MAX_RETRIES = 3
    _RETRY_BASE = 2.0

    def __init__(self, model: str, concurrency: int = 5) -> None:
        self._model_name = model
        self._semaphore = asyncio.Semaphore(concurrency)
        self._cache: dict[tuple[str, str], tuple[bool, int, str]] = {}
        self.calls_made: int = 0
        self.calls_cached: int = 0

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__.replace("Scorer", "").lower()

    async def score(
        self,
        area_name: str,
        description: str,
        text: str,
        threshold: int = 65,
    ) -> tuple[bool, int, str]:
        """
        Score *text* against an area's *description*.

        Returns:
            (match: bool, score: int 0-100, reason: str)

        On any API error returns (False, 0, "<error>") without raising,
        so a single bad response never breaks the whole run.
        """
        cache_key = (area_name, text[:300])
        if cache_key in self._cache:
            self.calls_cached += 1
            return self._cache[cache_key]

        prompt = _USER_TMPL.format(
            area_name=area_name,
            description=description.strip() or "(no description provided)",
            text=text[:2000],
            threshold=threshold,
        )

        result = await self._call_with_retry(prompt)
        self._cache[cache_key] = result
        self.calls_made += 1
        return result

    @abc.abstractmethod
    async def _call_with_retry(self, prompt: str) -> tuple[bool, int, str]:
        """Call the LLM API with exponential backoff on transient errors."""
        ...

    def stats(self) -> str:
        total = self.calls_made + self.calls_cached
        return (
            f"AI calls: {self.calls_made} to {self.provider_name} ({self._model_name}), "
            f"{self.calls_cached} from cache "
            f"({total} total)"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Gemini backend (native google-genai SDK)
# ──────────────────────────────────────────────────────────────────────────────

class GeminiScorer(BaseScorer):
    """Relevance scorer backed by Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        super().__init__(model=model)
        try:
            from google import genai
            self._client = genai.Client(api_key=api_key)
            self._genai = genai
        except ImportError:
            raise ImportError(
                "google-genai is not installed.\n"
                "Run: pip install google-genai"
            )

    async def _call_with_retry(self, prompt: str) -> tuple[bool, int, str]:
        try:
            from google.genai import errors
        except ImportError:
            return (False, 0, "[AI error: google-genai not installed]")

        async with self._semaphore:
            for attempt in range(self._MAX_RETRIES):
                try:
                    response = await self._client.aio.models.generate_content(
                        model=self._model_name,
                        contents=prompt,
                        config=self._genai.types.GenerateContentConfig(
                            system_instruction=_SYSTEM,
                            temperature=0.1,
                            response_mime_type="application/json",
                        ),
                    )
                    return _parse_response(response.text)
                except errors.APIError as exc:
                    if exc.code in (429, 503):
                        wait = self._RETRY_BASE ** (attempt + 1)
                        print_warning(
                            f"Gemini rate limited — waiting {wait:.0f}s "
                            f"(attempt {attempt + 1}/{self._MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        return (False, 0, f"[AI error: {exc.message}]")
                except Exception as exc:
                    return (False, 0, f"[AI error: {type(exc).__name__}: {exc}]")

        return (False, 0, "[AI error: max retries exceeded]")


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI-compatible backend (OpenAI, Ollama, OpenRouter, Together AI, etc.)
# ──────────────────────────────────────────────────────────────────────────────

class OpenAICompatibleScorer(BaseScorer):
    """
    Relevance scorer backed by any OpenAI-compatible API.

    Works with:
      - OpenAI (api_key, default base_url)
      - Ollama (no key, base_url="http://localhost:11434/v1")
      - OpenRouter (api_key, base_url="https://openrouter.ai/api/v1")
      - Any other OpenAI-compatible provider
    """

    def __init__(
        self,
        model: str,
        api_key: str = "ollama",
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(model=model)
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=api_key or "ollama",
                base_url=base_url or None,
            )
        except ImportError:
            raise ImportError(
                "openai package is not installed.\n"
                "Run: pip install 'telefeed[openai]'"
            )

    async def _call_with_retry(self, prompt: str) -> tuple[bool, int, str]:
        async with self._semaphore:
            for attempt in range(self._MAX_RETRIES):
                try:
                    from openai import RateLimitError, APIStatusError
                    response = await self._client.chat.completions.create(
                        model=self._model_name,
                        messages=[
                            {"role": "system", "content": _SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.1,
                        response_format={"type": "json_object"},
                    )
                    raw = response.choices[0].message.content or ""
                    return _parse_response(raw)
                except Exception as exc:
                    # Check for rate limit by class name to avoid hard import dependency
                    exc_name = type(exc).__name__
                    if exc_name in ("RateLimitError",):
                        wait = self._RETRY_BASE ** (attempt + 1)
                        print_warning(
                            f"OpenAI-compatible rate limited — waiting {wait:.0f}s "
                            f"(attempt {attempt + 1}/{self._MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        return (False, 0, f"[AI error: {exc_name}: {exc}]")

        return (False, 0, "[AI error: max retries exceeded]")


# ──────────────────────────────────────────────────────────────────────────────
# Anthropic Claude backend
# ──────────────────────────────────────────────────────────────────────────────

class AnthropicScorer(BaseScorer):
    """Relevance scorer backed by Anthropic Claude."""

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022") -> None:
        super().__init__(model=model)
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            self._anthropic = anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is not installed.\n"
                "Run: pip install 'telefeed[anthropic]'"
            )

    async def _call_with_retry(self, prompt: str) -> tuple[bool, int, str]:
        async with self._semaphore:
            for attempt in range(self._MAX_RETRIES):
                try:
                    response = await self._client.messages.create(
                        model=self._model_name,
                        max_tokens=256,
                        system=_SYSTEM,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                    )
                    raw = response.content[0].text if response.content else ""
                    return _parse_response(raw)
                except Exception as exc:
                    exc_name = type(exc).__name__
                    if exc_name in ("RateLimitError", "OverloadedError"):
                        wait = self._RETRY_BASE ** (attempt + 1)
                        print_warning(
                            f"Anthropic rate limited — waiting {wait:.0f}s "
                            f"(attempt {attempt + 1}/{self._MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        return (False, 0, f"[AI error: {exc_name}: {exc}]")

        return (False, 0, "[AI error: max retries exceeded]")


# ──────────────────────────────────────────────────────────────────────────────
# Factory — build the right scorer from config
# ──────────────────────────────────────────────────────────────────────────────

def build_scorer(provider: str, model: str, api_key: str, base_url: str = "") -> BaseScorer:
    """
    Factory that returns the correct BaseScorer subclass for a given provider.

    Args:
        provider : One of 'gemini', 'openai', 'anthropic', 'ollama', 'openrouter'
        model    : Model name (e.g. 'gemini-2.5-flash', 'gpt-4o-mini', 'llama3.2')
        api_key  : Provider API key (not required for Ollama)
        base_url : Optional endpoint override

    Raises:
        ValueError: If provider is unknown or API key is missing when required.
    """
    PROVIDERS_REQUIRING_KEY = {"gemini", "openai", "anthropic", "openrouter"}

    if provider in PROVIDERS_REQUIRING_KEY:
        if not api_key or api_key in ("YOUR_API_KEY", "your_gemini_api_key_here"):
            raise ValueError(
                f"API key is required for provider '{provider}'.\n"
                f"Add 'api_key' under 'ai:' in your config.yaml.\n"
                + {
                    "gemini": "Get a free Gemini key at https://aistudio.google.com/apikey",
                    "openai": "Get an OpenAI key at https://platform.openai.com/api-keys",
                    "anthropic": "Get an Anthropic key at https://console.anthropic.com/",
                    "openrouter": "Get an OpenRouter key at https://openrouter.ai/keys",
                }.get(provider, "")
            )

    if provider == "gemini":
        return GeminiScorer(api_key=api_key, model=model)

    elif provider in ("openai", "ollama", "openrouter"):
        effective_base_url = base_url or {
            "openrouter": "https://openrouter.ai/api/v1",
        }.get(provider)
        return OpenAICompatibleScorer(
            model=model,
            api_key=api_key or "ollama",
            base_url=effective_base_url,
        )

    elif provider == "anthropic":
        return AnthropicScorer(api_key=api_key, model=model)

    else:
        raise ValueError(
            f"Unknown AI provider: '{provider}'.\n"
            "Supported providers: gemini, openai, anthropic, ollama, openrouter"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Backward-compat alias (used in tests)
# ──────────────────────────────────────────────────────────────────────────────

class AIScorer(GeminiScorer):
    """Backward-compatible alias for GeminiScorer. Use build_scorer() for new code."""

    @classmethod
    def from_env(cls, key: str = "") -> "AIScorer":
        api_key = key or os.getenv("GEMINI_API_KEY", "")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError(
                "Gemini API key is not configured.\n"
                "Add 'api_key' under 'ai:' in your config.yaml "
                "or set GEMINI_API_KEY in environment.\n"
                "Get a free key at https://aistudio.google.com/apikey"
            )
        return cls(api_key=api_key)


# ──────────────────────────────────────────────────────────────────────────────
# Filtering helper used by cli.py
# ──────────────────────────────────────────────────────────────────────────────

async def ai_check_all_areas(
    areas: list,
    text: str,
    scorer: BaseScorer,
    threshold: int,
) -> list:
    """
    AI-mode replacement for filters.check_all_areas().

    Pipeline per area:
      1. Negative keyword gate — hard discard (no AI call)
      2. Positive keyword pre-filter — if area has keywords, at least one must hit
         (saves AI quota; areas with no keywords bypass this step)
      3. AI scores the message vs. the area's description
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
        if area.keywords and not kw_result.is_match:
            continue

        # ── Step 3: AI scoring ────────────────────────────────────────────────
        match, score, reason = await scorer.score(
            area_name=area.name,
            description=area.description,
            text=text,
            threshold=threshold,
        )

        if match:
            kw_result.score = score / 100.0
            kw_result.ai_reason = reason
            results.append(kw_result)

    return results
