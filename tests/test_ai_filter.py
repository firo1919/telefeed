"""
Unit tests for telefeed.ai_filter module (Gemini AI scorer & pipeline).
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telefeed.ai_filter import AIScorer, _parse_response, ai_check_all_areas
from telefeed.filters import Area


def test_aiscorer_from_env_valid():
    scorer = AIScorer.from_env(key="valid_api_key")
    assert scorer._model_name == "gemini-2.5-flash"


def test_aiscorer_from_env_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        AIScorer.from_env(key="")

    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        AIScorer.from_env(key="your_gemini_api_key_here")


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


@pytest.mark.asyncio
async def test_score_caching():
    scorer = AIScorer(api_key="mock_key")
    
    # Mock model generate_content
    mock_resp = MagicMock()
    mock_resp.text = '{"match": true, "score": 90, "reason": "Matches interest"}'
    
    with patch.object(scorer._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        # First call
        m1, s1, r1 = await scorer.score("Area 1", "Desc", "Text content", 65)
        # Second call with identical content
        m2, s2, r2 = await scorer.score("Area 1", "Desc", "Text content", 65)

        assert m1 is True and m2 is True
        assert scorer.calls_made == 1
        assert scorer.calls_cached == 1
        assert "1 to Gemini, 1 from cache" in scorer.stats()


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

    areas = [area_with_keywords, area_no_keywords]
    scorer = AIScorer(api_key="mock_key")

    mock_resp = MagicMock()
    mock_resp.text = '{"match": true, "score": 88, "reason": "Matches AI description"}'

    with patch.object(scorer._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        # Case 1: Message blocked by negative keyword gate (no AI call made for Python area)
        res1 = await ai_check_all_areas([area_with_keywords], "Unpaid internship for python dev", scorer, threshold=65)
        assert len(res1) == 0

        # Case 2: Message fails positive keyword pre-filter for Python Area, but passes to AI for Area with no keywords
        res2 = await ai_check_all_areas(areas, "New paper on LLM agent architecture published.", scorer, threshold=65)
        assert len(res2) == 1
        assert res2[0].area.name == "AI Area"
        assert res2[0].score == 0.88
        assert res2[0].ai_reason == "Matches AI description"
