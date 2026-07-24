"""
Unit tests for telefeed.filters module (Keyword & negative keyword matching engine).
"""

from telefeed.filters import (
    Area,
    MatchResult,
    check_all_areas,
    check_area,
    highlight_keywords,
    load_areas_from_config,
    load_matcher_config,
)


def test_area_initialization():
    area = Area(
        name="Test Area",
        description="Description",
        keywords=["Python", "RUST"],
        negative_keywords=["Internship"],
    )
    assert len(area._kw_patterns) == 2
    assert len(area._neg_patterns) == 1


def test_check_area_positive_match(sample_area: Area):
    text = "We are looking for a Senior Python and Golang developer for a remote role."
    result = check_area(sample_area, text)

    assert result.is_match is True
    assert result.blocked_by is None
    assert "python" in result.matched_keywords
    assert abs(result.score - 2 / 3) < 0.01  # 2 matched out of 3 total keywords


def test_check_area_negative_keyword_gate(sample_area: Area):
    text = "We have an unpaid internship for a Python developer."
    result = check_area(sample_area, text)

    assert result.is_match is False
    assert result.blocked_by is not None
    assert result.blocked_by.lower() in ("unpaid", "internship")
    assert result.score == 0.0


def test_check_area_no_match(sample_area: Area):
    text = "Sales manager needed for retail store."
    result = check_area(sample_area, text)

    assert result.is_match is False
    assert result.blocked_by is None
    assert result.score == 0.0
    assert result.matched_keywords == []


def test_check_all_areas():
    area1 = Area(name="Dev", description="", keywords=["python"])
    area2 = Area(name="Design", description="", keywords=["figma"])
    areas = [area1, area2]

    results = check_all_areas(areas, "Need a Python developer with Figma skills.")
    assert len(results) == 2
    assert {r.area.name for r in results} == {"Dev", "Design"}


def test_highlight_keywords():
    text = "Hiring Python and Rust engineers"
    highlighted = highlight_keywords(text, ["Python", "Rust"], style="bold yellow")
    assert "[bold yellow]Python[/bold yellow]" in highlighted
    assert "[bold yellow]Rust[/bold yellow]" in highlighted


def test_load_areas_from_config():
    config_dict = {
        "areas": [
            {
                "name": "Backend",
                "description": "Backend dev",
                "keywords": ["Python", "Go"],
                "negative_keywords": ["Unpaid"],
                "sources": ["@backendjobs"],
            }
        ]
    }
    areas = load_areas_from_config(config_dict)
    assert len(areas) == 1
    assert areas[0].name == "Backend"
    assert areas[0].keywords == ["python", "go"]
    assert areas[0].negative_keywords == ["unpaid"]
    assert areas[0].sources == ["@backendjobs"]


def test_load_matcher_config():
    # Test defaults
    m, t = load_matcher_config({})
    assert m == "keywords"
    assert t == 65

    # Test custom valid values
    m, t = load_matcher_config({"matcher": "AI", "ai_threshold": 80})
    assert m == "ai"
    assert t == 80

    # Test invalid matcher fallback & threshold clamping
    m, t = load_matcher_config({"matcher": "invalid_mode", "ai_threshold": 150})
    assert m == "keywords"
    assert t == 100

    m, t = load_matcher_config({"ai_threshold": -20})
    assert t == 0


def test_bm25_description_matching():
    # Area with no explicit keywords, only description
    area = Area(
        name="Machine Learning",
        description="Deep learning models, PyTorch training, and neural networks",
        keywords=[],
    )
    text = "We are training a new PyTorch model using deep learning techniques."
    result = check_area(area, text, threshold=50)

    assert result.is_match is True
    assert result.score > 0.0
    assert any("pytorch" in k for k in result.matched_keywords)


def test_extract_description_tokens():
    from telefeed.filters import extract_description_tokens
    tokens = extract_description_tokens("Looking for a Senior Python Developer with FastAPI experience.")
    assert "senior" in tokens
    assert "python" in tokens
    assert "developer" in tokens
    assert "fastapi" in tokens
    assert "experience" in tokens
    # Stop words like "looking", "for", "a", "with" should be removed
    assert "looking" not in tokens
    assert "for" not in tokens
    assert "with" not in tokens


def test_compute_bm25_score():
    from telefeed.filters import compute_bm25_score
    area = Area(
        name="Backend",
        description="Backend API microservices in Go and Rust",
        keywords=["microservices"],
    )
    matching_text = "Hiring developers for building high performance microservices in Rust."
    score, hits = compute_bm25_score(area, matching_text)
    assert score > 0.0
    assert "rust" in hits or "microservices" in area.keywords

    non_matching_text = "Local bakery selling fresh bread and cakes."
    score_zero, hits_zero = compute_bm25_score(area, non_matching_text)
    assert score_zero == 0.0
    assert hits_zero == []


def test_check_area_keyword_prefiltering_and_threshold():
    # If keywords are defined, at least one keyword MUST match
    area = Area(
        name="Python Web",
        description="Python web development jobs and projects",
        keywords=["django"],
    )
    # Text doesn't contain "django" -> keyword pre-filter fails
    text_no_keyword = "Hiring a developer for Python web development projects."
    result_no_kw = check_area(area, text_no_keyword, threshold=50)
    assert result_no_kw.is_match is False
    assert result_no_kw.score == 0.0

    # Text contains "django" -> keyword pre-filter passes
    text_with_keyword = "Hiring a developer for Django web development projects."
    result_kw = check_area(area, text_with_keyword, threshold=50)
    assert result_kw.is_match is True
    assert result_kw.score > 0.0


def test_check_area_low_bm25_score_rejected():
    area = Area(
        name="Computer Science",
        description="Software development, algorithms, system design, python backend engineering",
        keywords=["software engineer"],
    )
    # Text has almost no relevance (only matches generic word "national operations officer")
    irrelevant_text = "The Food and Agriculture Organization of the United Nations is inviting applications for National Operations Officer."
    result = check_area(area, irrelevant_text)

    assert result.is_match is False
    assert result.score == 0.0


