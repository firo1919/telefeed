"""
Keyword-based filtering engine.

Each "Area" has:
  - keywords          : list of strings; any match is a candidate
  - negative_keywords : list of strings; any match disqualifies the message
  - description       : plain-text intent description (used for scoring)

Scoring:
  A simple relevance score is computed as the number of keyword hits
  divided by the total keyword count.  This gives a [0.0, 1.0] score
  that can later be replaced by a proper embedding/LLM call.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Area:
    name: str
    description: str
    keywords: list[str]
    negative_keywords: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    # Pre-compiled patterns built on first use
    _kw_patterns: list[re.Pattern] = field(default_factory=list, repr=False)
    _neg_patterns: list[re.Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._kw_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in self.keywords
        ]
        self._neg_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in self.negative_keywords
        ]


@dataclass
class MatchResult:
    area: Area
    score: float                        # 0.0 – 1.0
    matched_keywords: list[str]
    blocked_by: Optional[str] = None    # set if a negative_keyword hit
    ai_reason: Optional[str] = None     # set by AI mode; None in keyword mode

    @property
    def is_match(self) -> bool:
        return self.blocked_by is None and self.score > 0.0


def _normalize(text: str) -> str:
    """Collapse whitespace and strip for consistent matching."""
    return " ".join(text.split())


def check_area(area: Area, text: str) -> MatchResult:
    """
    Run keyword and negative-keyword checks against *text* for a single *area*.

    Returns a MatchResult.  Call .is_match to know if it passed.
    """
    normalized = _normalize(text)

    # --- Negative keyword gate (fast path) ---
    for pat in area._neg_patterns:
        m = pat.search(normalized)
        if m:
            return MatchResult(
                area=area,
                score=0.0,
                matched_keywords=[],
                blocked_by=m.group(0),
            )

    # --- Keyword hits ---
    hits: list[str] = []
    for kw, pat in zip(area.keywords, area._kw_patterns):
        if pat.search(normalized):
            hits.append(kw)

    score = len(hits) / len(area.keywords) if area.keywords else 0.0

    return MatchResult(area=area, score=score, matched_keywords=hits)


def check_all_areas(areas: list[Area], text: str) -> list[MatchResult]:
    """
    Run every area against *text*.  Returns only the MatchResults that pass.
    """
    results: list[MatchResult] = []
    for area in areas:
        result = check_area(area, text)
        if result.is_match:
            results.append(result)
    return results


def highlight_keywords(text: str, keywords: list[str], style: str = "bold yellow") -> str:
    """
    Return the text with matched keywords wrapped in Rich markup tags.
    Used by display.py for terminal highlighting.
    """
    # Work through matches in reverse order of position so offsets don't shift
    combined = re.compile(
        "|".join(re.escape(kw) for kw in keywords), re.IGNORECASE
    )
    # Replace each match with Rich markup
    result = combined.sub(lambda m: f"[{style}]{m.group(0)}[/{style}]", text)
    return result


def load_areas_from_config(config: dict) -> list[Area]:
    """
    Parse the top-level 'areas' list from the loaded YAML config dict
    and return a list of Area objects.
    """
    areas: list[Area] = []
    for raw in config.get("areas", []):
        areas.append(
            Area(
                name=raw["name"],
                description=raw.get("description", ""),
                keywords=[kw.lower() for kw in raw.get("keywords", [])],
                negative_keywords=[kw.lower() for kw in raw.get("negative_keywords", [])],
                sources=raw.get("sources", []),
            )
        )
    return areas


def load_matcher_config(config: dict) -> tuple[str, int]:
    """
    Read top-level matcher settings from the config dict.

    Returns:
        (matcher, ai_threshold)

        matcher      : 'keywords' or 'ai'
        ai_threshold : int 0-100 (minimum AI score to count as a match)
    """
    matcher = str(config.get("matcher", "keywords")).lower().strip()
    if matcher not in ("keywords", "ai"):
        matcher = "keywords"
    threshold = int(config.get("ai_threshold", 65))
    threshold = max(0, min(100, threshold))
    return matcher, threshold
