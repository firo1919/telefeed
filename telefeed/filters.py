"""
Keyword & BM25 Relevance Filtering Engine.

Each "Area" has:
  - keywords          : list of strings; any match is a candidate
  - negative_keywords : list of strings; any match disqualifies the message
  - description       : plain-text intent description (scored via Okapi BM25)

Scoring:
  A hybrid score is computed combining exact keyword match ratio and
  Okapi BM25 relevance scoring based on the Area description.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from rank_bm25 import BM25Okapi, BM25Plus

# Standard English stop words to ignore when parsing Area descriptions
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "with", "would", "you", "your", "yours",
    "yourself", "yourselves", "looking", "want", "need", "find", "search", "track", "get"
}


def extract_description_tokens(description: str) -> list[str]:
    """Extract clean non-stopword tokens from an area description."""
    if not description:
        return []
    tokens = re.findall(r'\b[a-zA-Z0-9_-]{2,}\b', description.lower())
    return [t for t in tokens if t not in STOP_WORDS]


@dataclass
class Area:
    name: str
    description: str
    keywords: list[str]
    negative_keywords: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    # Pre-compiled patterns and tokens built on initialization
    _kw_patterns: list[re.Pattern] = field(default_factory=list, repr=False)
    _neg_patterns: list[re.Pattern] = field(default_factory=list, repr=False)
    _desc_tokens: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._kw_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in self.keywords
        ]
        self._neg_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE) for kw in self.negative_keywords
        ]
        self._desc_tokens = extract_description_tokens(self.description)


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


def compute_bm25_score(
    area: Area,
    text: str,
) -> tuple[float, list[str]]:
    """
    Calculate Okapi BM25 relevance score for a message against an Area's description & keywords
    using the rank-bm25 package.

    Returns:
        (score: float 0.0-1.0, matched_desc_tokens: list[str])
    """
    doc_tokens = re.findall(r'\b[a-zA-Z0-9_-]+\b', text.lower())
    if not doc_tokens:
        return 0.0, []

    # Query terms = keywords (weighted 2x) + description tokens
    query_terms: list[str] = []
    for kw in area.keywords:
        kw_clean = kw.lower().strip()
        query_terms.extend([kw_clean, kw_clean])

    query_terms.extend(area._desc_tokens)

    if not query_terms:
        return 0.0, []

    # Initialize BM25 model with document tokens as corpus
    bm25 = BM25Plus([doc_tokens])
    scores = bm25.get_scores(query_terms)
    raw_score = float(scores[0])

    doc_set = set(doc_tokens)
    matched_desc_tokens = [
        dt for dt in area._desc_tokens
        if dt in doc_set or any(dt in d or d in dt for d in doc_set)
    ]

    max_bm25 = BM25Plus([query_terms])
    max_score = float(max_bm25.get_scores(query_terms)[0])

    norm_score = round(min(1.0, raw_score / max_score), 3) if max_score > 0 else 0.0
    return norm_score, matched_desc_tokens


def check_area(area: Area, text: str) -> MatchResult:
    """
    Run keyword, description BM25, and negative-keyword checks against *text* for a single *area*.

    Returns a MatchResult. Call .is_match to know if it passed.
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

    # --- Positive keyword hits ---
    hits: list[str] = []
    for kw, pat in zip(area.keywords, area._kw_patterns):
        if pat.search(normalized):
            hits.append(kw)

    # --- BM25 Description & Keyword Scoring ---
    bm25_score, desc_hits = compute_bm25_score(area, text)

    if area.keywords:
        kw_score = len(hits) / len(area.keywords)
        if hits:
            score = kw_score
            matched = hits
        elif desc_hits and bm25_score > 0.0:
            score = round(0.5 * bm25_score, 3)
            matched = [f"desc:{dh}" for dh in desc_hits]
        else:
            score = 0.0
            matched = []
    else:
        score = bm25_score
        matched = [f"desc:{dh}" for dh in desc_hits]

    return MatchResult(area=area, score=score, matched_keywords=matched)


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
