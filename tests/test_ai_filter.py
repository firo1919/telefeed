"""
Unit tests for telefeed.ai_filter module (multi-provider AI scorer & pipeline).
"""

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest

from telefeed.ai_filter import (
    AIScorer,
    AnthropicScorer,
    BaseScorer,
    GeminiScorer,
    OpenAICompatibleScorer,
    _parse_response,
    ai_check_all_areas,
    build_scorer,
)
from telefeed.filters import Area


# ──────────────────────────────────────────────────────────────────────────────
# Response parsing
# ──────────────────────────────────────────────────────────────────────────────

def test_parse_response_valid_json():
    raw = '{"match": true, "score": 85, "reason": "Highly relevant backend role"}'
    match, score, reason = _parse_response(raw)
    assert match is True
    assert score == 85
    assert reason == "Highly relevant backend role"


def test_parse_response_markdown_fences():
    raw = "```json\n{\n  \"match\": false,\n  \"score\": 30,\n  \"reason\": \"Not a software position\"\n}\n```"
    match, score, reason = _parse_response(raw)
    assert match is False
    assert score == 30
    assert reason == "Not a software position"


def test_parse_response_malformed():
    match, score, reason = _parse_response("Sorry, I cannot answer this.")
    assert match is False
    assert score == 0
    assert "[Could not parse AI response" in reason


def test_parse_response_score_clamping():
    match, score, reason = _parse_response('{"match": true, "score": 150, "reason": "test"}')
    assert score == 100

    match, score, reason = _parse_response('{"match": false, "score": -10, "reason": "test"}')
    assert score == 0


# ──────────────────────────────────────────────────────────────────────────────
# build_scorer factory
# ──────────────────────────────────────────────────────────────────────────────

def test_build_scorer_gemini():
    scorer = build_scorer("gemini", "gemini-2.5-flash", "valid_key")
    assert isinstance(scorer, GeminiScorer)
    assert scorer._model_name == "gemini-2.5-flash"


def test_build_scorer_openai():
    scorer = build_scorer("openai", "gpt-4o-mini", "sk-valid-key")
    assert isinstance(scorer, OpenAICompatibleScorer)


def test_build_scorer_openrouter():
    scorer = build_scorer("openrouter", "meta-llama/llama-3.1-8b-instruct", "or-valid-key")
    assert isinstance(scorer, OpenAICompatibleScorer)


def test_build_scorer_ollama():
    # Ollama doesn't need a key
    scorer = build_scorer("ollama", "llama3.2", "", "http://localhost:11434/v1")
    assert isinstance(scorer, OpenAICompatibleScorer)


def test_build_scorer_anthropic():
    scorer = build_scorer("anthropic", "claude-3-5-haiku-20241022", "sk-ant-valid")
    assert isinstance(scorer, AnthropicScorer)


def test_build_scorer_missing_key_raises():
    with pytest.raises(ValueError, match="API key is required"):
        build_scorer("gemini", "gemini-2.5-flash", "")

    with pytest.raises(ValueError, match="API key is required"):
        build_scorer("openai", "gpt-4o-mini", "YOUR_API_KEY")


def test_build_scorer_unknown_provider():
    with pytest.raises(ValueError, match="Unknown AI provider"):
        build_scorer("grok", "model", "key")


# ──────────────────────────────────────────────────────────────────────────────
# Backward-compat AIScorer alias
# ──────────────────────────────────────────────────────────────────────────────

def test_aiscorer_from_env_valid():
    scorer = AIScorer.from_env(key="valid_api_key")
    assert isinstance(scorer, GeminiScorer)


def test_aiscorer_from_env_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        AIScorer.from_env(key="")

    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        AIScorer.from_env(key="your_gemini_api_key_here")


# ──────────────────────────────────────────────────────────────────────────────
# Caching (provider-agnostic via BaseScorer)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_caching():
    scorer = GeminiScorer(api_key="mock_key")

    mock_resp = MagicMock()
    mock_resp.text = '{"match": true, "score": 90, "reason": "Matches interest"}'

    with patch.object(scorer._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        m1, s1, r1 = await scorer.score("Area 1", "Desc", "Text content", 65)
        m2, s2, r2 = await scorer.score("Area 1", "Desc", "Text content", 65)

        assert m1 is True and m2 is True
        assert scorer.calls_made == 1
        assert scorer.calls_cached == 1
        assert "1 to gemini" in scorer.stats()
        assert "1 from cache" in scorer.stats()


# ──────────────────────────────────────────────────────────────────────────────
# GeminiScorer
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_scorer_success():
    scorer = GeminiScorer(api_key="mock_key", model="gemini-2.5-flash")

    mock_resp = MagicMock()
    mock_resp.text = '{"match": true, "score": 88, "reason": "Relevant job posting"}'

    with patch.object(scorer._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        match, score, reason = await scorer.score("Jobs", "Backend jobs", "Python developer needed", 65)
        assert match is True
        assert score == 88
        assert reason == "Relevant job posting"


# ──────────────────────────────────────────────────────────────────────────────
# OpenAICompatibleScorer (covers openai, ollama, openrouter)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openai_scorer_success():
    scorer = OpenAICompatibleScorer(model="gpt-4o-mini", api_key="sk-mock")

    mock_choice = MagicMock()
    mock_choice.message.content = '{"match": true, "score": 78, "reason": "Strong technical match"}'
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    with patch.object(scorer._client.chat.completions, "create", new=AsyncMock(return_value=mock_completion)):
        match, score, reason = await scorer.score("Dev", "Backend dev", "Looking for a Go developer", 65)
        assert match is True
        assert score == 78


@pytest.mark.asyncio
async def test_ollama_scorer_no_key():
    # Ollama uses 'ollama' as placeholder key
    scorer = build_scorer("ollama", "llama3.2", "", "http://localhost:11434/v1")
    assert scorer._model_name == "llama3.2"
    assert isinstance(scorer, OpenAICompatibleScorer)


# ──────────────────────────────────────────────────────────────────────────────
# AnthropicScorer
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anthropic_scorer_success():
    scorer = AnthropicScorer(api_key="sk-ant-mock", model="claude-3-5-haiku-20241022")

    mock_content = MagicMock()
    mock_content.text = '{"match": false, "score": 20, "reason": "Unrelated to software jobs"}'
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    with patch.object(scorer._client.messages, "create", new=AsyncMock(return_value=mock_response)):
        match, score, reason = await scorer.score("Jobs", "Backend dev", "Summer sale 50% off", 65)
        assert match is False
        assert score == 20


# ──────────────────────────────────────────────────────────────────────────────
# ai_check_all_areas pipeline (provider-agnostic)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_check_all_areas_pipeline():
    area_with_keywords = Area(
        name="Python Area",
        description="Python backend engineering",
        keywords=["python"],
        negative_keywords=["internship"],
    )
    area_no_keywords = Area(
        name="AI Area",
        description="Generative AI and LLMs",
        keywords=[],
        negative_keywords=["crypto"],
    )

    scorer = GeminiScorer(api_key="mock_key")
    mock_resp = MagicMock()
    mock_resp.text = '{"match": true, "score": 88, "reason": "Matches AI description"}'

    with patch.object(scorer._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        # Case 1: negative keyword gate blocks Python Area only
        res1 = await ai_check_all_areas([area_with_keywords], "Unpaid internship for python dev", scorer, threshold=65)
        assert len(res1) == 0

        # Case 2: no keywords in AI Area → bypasses pre-filter → goes straight to AI
        res2 = await ai_check_all_areas(areas=[area_no_keywords], text="New paper on LLM agent architecture published.", scorer=scorer, threshold=65)
        assert len(res2) == 1
        assert res2[0].area.name == "AI Area"
        assert res2[0].score == 0.88
        assert res2[0].ai_reason == "Matches AI description"


# ──────────────────────────────────────────────────────────────────────────────
# stats() output
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_output():
    scorer = GeminiScorer(api_key="mock_key", model="gemini-2.5-flash")
    mock_resp = MagicMock()
    mock_resp.text = '{"match": true, "score": 80, "reason": "Relevant"}'

    with patch.object(scorer._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        await scorer.score("Area", "Desc", "Some text", 65)

    stats = scorer.stats()
    assert "1 to gemini" in stats
    assert "gemini-2.5-flash" in stats
    assert "0 from cache" in stats
