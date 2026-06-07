"""
branch_filter.py
Flexible branch matching with alias support.
Filters college tables to keep only user-requested branches.
"""

import re
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Alias / abbreviation map
# ──────────────────────────────────────────────────────────────────────────────

BRANCH_ALIASES: dict[str, list[str]] = {
    # Computer
    "CSE": ["Computer Science Engineering", "Computer Science And Engineering",
             "Computer Science & Engineering"],
    "CS": ["Computer Science Engineering", "Computer Science And Engineering"],
    "IT": ["Information Technology", "Information Science Engineering",
            "Information Science And Engineering"],
    "IS": ["Information Science Engineering", "Information Science And Engineering"],
    # Electronics
    "ECE": ["Electronics And Communication Engineering",
             "Electronics And Communication Engg",
             "Electronics & Communication Engineering"],
    "EC": ["Electronics And Communication Engineering"],
    "EEE": ["Electrical And Electronics Engineering",
             "Electrical & Electronics Engineering"],
    "EE": ["Electrical Engineering"],
    "EIE": ["Electronics And Instrumentation Engineering",
             "Electronics And Instrumentation Engg"],
    "ETE": ["Electronics And Telecommunication Engineering",
             "Electronics And Telecommunication Engg"],
    # Mechanical
    "ME": ["Mechanical Engineering"],
    "MECH": ["Mechanical Engineering"],
    "AUTO": ["Automobile Engineering"],
    "AE": ["Automobile Engineering", "Aeronautical Engineering"],
    "IE": ["Industrial Engineering & Management", "Industrial Engineering And Management"],
    # Civil
    "CE": ["Civil Engineering"],
    "CIVIL": ["Civil Engineering"],
    # Chemical
    "CHE": ["Chemical Engineering"],
    "CHEM": ["Chemical Engineering"],
    # Textile / Silk
    "TE": ["Textile Technology", "Textiles Technology"],
    "TEXTILE": ["Textile Technology", "Textiles Technology"],
    "SILK": ["Silk Technology"],
    # Others
    "BT": ["Biotechnology"],
    "BIO": ["Biotechnology"],
    "ENV": ["Environmental Engineering"],
    "MINING": ["Mining Engineering"],
    "ARCH": ["Architecture"],
    "AERO": ["Aeronautical Engineering"],
    "PE": ["Polymer Engineering", "Polymer Science And Technology"],
    "AI": ["Artificial Intelligence", "Artificial Intelligence And Data Science",
            "Artificial Intelligence And Machine Learning"],
    "ML": ["Machine Learning", "Artificial Intelligence And Machine Learning"],
    "DS": ["Data Science", "Artificial Intelligence And Data Science"],
    "AIDS": ["Artificial Intelligence And Data Science"],
    "AIML": ["Artificial Intelligence And Machine Learning"],
    "CSD": ["Computer Science Design"],
    "CSM": ["Computer Science Machine Learning"],
    "CSBS": ["Computer Science Business Systems"],
    "CYBER": ["Cyber Security"],
    "IOT": ["Internet Of Things"],
    "ROBOTICS": ["Robotics And Automation"],
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def filter_colleges(
    colleges: list[dict],
    branch_inputs: list[str],
    similarity_threshold: float = 0.75,
) -> list[dict]:
    """
    Given a list of college dicts (each with 'table' DataFrame),
    return a filtered list containing only matching branch rows.

    Colleges with zero matching branches are excluded entirely.
    """
    if not branch_inputs:
        return []

    # Build the canonical search terms (expand aliases)
    search_terms = _build_search_terms(branch_inputs)
    logger.info(f"Search terms: {search_terms}")

    results = []
    for college in colleges:
        df = college.get("table")
        if df is None or df.empty:
            continue

        # Identify the course-name column
        course_col = _detect_course_column(df)
        if course_col is None:
            logger.warning(f"No course column found for {college['college_name']}")
            continue

        # Filter rows
        matched_mask = df[course_col].apply(
            lambda branch: _branch_matches(branch, search_terms, similarity_threshold)
        )
        filtered_df = df[matched_mask].reset_index(drop=True)

        if not filtered_df.empty:
            results.append({
                **college,
                "table": filtered_df,
            })

    logger.info(f"Colleges with matches: {len(results)}/{len(colleges)}")
    return results


def expand_aliases(user_input: str) -> list[str]:
    """
    Given a user shorthand like 'ME', return all possible full names.
    """
    upper = user_input.strip().upper()
    if upper in BRANCH_ALIASES:
        return BRANCH_ALIASES[upper]
    return [user_input.strip()]


# ──────────────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────────────

def _build_search_terms(inputs: list[str]) -> list[str]:
    """
    Expand each user input through alias map and return a flat
    deduplicated list of terms to match against.
    """
    terms = []
    for inp in inputs:
        inp = inp.strip()
        if not inp:
            continue
        upper = inp.upper()
        if upper in BRANCH_ALIASES:
            terms.extend(BRANCH_ALIASES[upper])
            terms.append(inp)  # also keep original in case it's exact
        else:
            terms.append(inp)
    # Deduplicate preserving order
    seen = set()
    result = []
    for t in terms:
        key = t.upper()
        if key not in seen:
            seen.add(key)
            result.append(t)
    return result


def _detect_course_column(df) -> str | None:
    """Return the name of the first column (course name column)."""
    for col in df.columns:
        if "course" in col.lower() or col == "Course Name":
            return col
    # Fallback: first column
    return df.columns[0] if len(df.columns) > 0 else None


def _branch_matches(
    branch_name: str,
    search_terms: list[str],
    threshold: float,
) -> bool:
    """
    Returns True if branch_name matches any of the search_terms.
    Uses substring match first, then fuzzy similarity as fallback.
    """
    branch_upper = branch_name.strip().upper()

    if not branch_upper or branch_upper in ("--", "COURSE NAME", ""):
        return False

    for term in search_terms:
        term_upper = term.strip().upper()
        if not term_upper:
            continue

        # 1. Exact match
        if branch_upper == term_upper:
            return True

        # 2. Substring match (user typed partial name)
        if term_upper in branch_upper or branch_upper in term_upper:
            return True

        # 3. Word-level overlap (e.g. "Mechanical" matches "Mechanical Engineering")
        branch_words = set(re.split(r"\W+", branch_upper))
        term_words = set(re.split(r"\W+", term_upper))
        if term_words and term_words.issubset(branch_words):
            return True

        # 4. Fuzzy similarity
        ratio = SequenceMatcher(None, branch_upper, term_upper).ratio()
        if ratio >= threshold:
            return True

    return False
