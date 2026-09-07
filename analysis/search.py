"""Intelligent search query generation for marketplace collectors."""

from __future__ import annotations

import re
from typing import Set

from categories.base import CategoryKnowledge


class SearchGenerator:
    """Generates optimized search combinations for collectors.

    The Intelligent Search Generation Algorithm follows these stages:

    1.  **Tokenization**: The seed query is split into alphanumeric tokens.
    2.  **Token Expansion**: Each token is expanded into a set of variants:
        -   **Plurals & Singulars**: Using basic English morphology rules.
        -   **Abbreviations**: Mapping common terms to their shortened forms (e.g., "receiver" -> "rcvr").
        -   **Brand Aliases**: Common misspellings or alternative names for brands.
        -   **Foreign Spellings**: Regional variations (e.g., "color" -> "colour").
        -   **Category-specific Misspellings**: Leveraging the category knowledge plugin.
    3.  **Candidate Generation**:
        -   The original query is preserved as the first candidate.
        -   New candidates are formed by replacing one token at a time with its variants. This avoids a full combinatorial explosion while still covering significant ground.
    4.  **Expansion & Modifiers**:
        -   **Category Expansion**: If a category is provided, top brands, keywords, and model prefixes from that category are appended to the seed query.
        -   **Repair Modifiers**: Append keywords like "repair", "broken", or category-specific repair opportunities.
        -   **Bundle Modifiers**: Append keywords like "bundle" or "lot".
        -   **Seller Motivation**: Append keywords like "must go" or "moving".
    5.  **Collector Optimization**:
        -   All candidates are normalized (lowercased, whitespace stripped).
        -   Deduplication ensures only unique queries are returned.
        -   The list is capped by `max_queries` (default 24), prioritizing the original query and single-token variants.
    """

    ABBREVIATIONS = {
        "receiver": ["rcvr"],
        "amplifier": ["amp"],
        "microphone": ["mic"],
        "speaker": ["spkr"],
        "headphones": ["hpns"],
        "computer": ["pc"],
        "monitor": ["mon"],
        "router": ["rtr"],
        "server": ["srv"],
        "camera": ["cam"],
        "guitar": ["gtr"],
        "repair": ["fix"],
        "television": ["tv"],
        "laptop": ["nb"],
    }

    BRAND_ALIASES = {
        "marantz": ["maranz"],
        "sennheiser": ["senheiser"],
        "technics": ["technics"],
        "yamaha": ["yamaha"],
        "klipsch": ["klipsch"],
        "pioneer": ["pioner"],
        "sony": ["sonie"],
        "panasonic": ["panasound"],
    }

    FOREIGN_SPELLINGS = {
        "color": ["colour"],
        "favorite": ["favourite"],
        "model": ["modello"],
        "meter": ["metre"],
        "analog": ["analogue"],
    }

    REPAIR_KEYWORDS = ["repair", "broken", "untested", "parts", "needs work", "as is"]
    BUNDLE_KEYWORDS = [
        "bundle",
        "lot",
        "collection",
        "with accessories",
        "complete set",
    ]
    SELLER_MOTIVATION = [
        "must sell",
        "must go",
        "urgent",
        "moving",
        "estate",
        "garage",
        "cleaning out",
    ]

    def _load_global_keywords(self) -> None:
        """Attempt to load keywords from data/keywords.json if available."""
        try:
            import json
            import os

            # Use absolute path relative to project root if possible, or assume it's in data/
            # For simplicity, we'll try 'data/keywords.json' first
            json_path = "data/keywords.json"
            if os.path.exists(json_path):
                with open(json_path, "r") as f:
                    data = json.load(f)
                    if "repair" in data:
                        self.REPAIR_KEYWORDS = list(
                            dict.fromkeys(data["repair"] + self.REPAIR_KEYWORDS)
                        )
                    if "high_value" in data:
                        self.SELLER_MOTIVATION = list(
                            dict.fromkeys(
                                self.SELLER_MOTIVATION
                                + ["must sell"]
                                + data["high_value"]
                            )
                        )
        except (ImportError, IOError, json.JSONDecodeError):
            pass

    def __init__(self, category: CategoryKnowledge | None = None):
        self.category = category
        self._load_global_keywords()

    def generate(self, query: str, max_queries: int = 24) -> list[str]:
        """Generate a list of optimized search queries."""
        if not query or not query.strip():
            return []

        base_query = query.strip()
        tokens = re.findall(r"[A-Za-z0-9]+", base_query)
        if not tokens:
            return [base_query]

        # 1. Expand each token into its variants
        token_variants = []
        for token in tokens:
            variants = self._expand_token(token)
            token_variants.append(variants)

        # 2. Build initial combinations
        # Start with the base query and then swap one token at a time
        candidate_queries = [base_query.lower()]
        seen_candidates = {base_query.lower()}

        for i, variants in enumerate(token_variants):
            for variant in variants:
                low_variant = variant.lower()
                if low_variant != tokens[i].lower():
                    new_query = self._replace_token(tokens, i, variant).lower()
                    if new_query not in seen_candidates:
                        candidate_queries.append(new_query)
                        seen_candidates.add(new_query)

        # 3. Apply Modifiers and Category Expansions
        category_expansions = []
        if self.category:
            for brand in self.category.brands[:2]:
                if brand.lower() not in base_query.lower():
                    category_expansions.append(f"{base_query} {brand}".lower())

            for keyword in self.category.keywords[:2]:
                if keyword.lower() not in base_query.lower():
                    category_expansions.append(f"{base_query} {keyword}".lower())

            for prefix in self.category.common_model_prefixes[:2]:
                category_expansions.append(f"{base_query} {prefix}".lower())

        modifiers = (
            self.SELLER_MOTIVATION[:6]
            + self.REPAIR_KEYWORDS[:6]
            + self.BUNDLE_KEYWORDS[:3]
        )
        if self.category:
            modifiers = list(
                dict.fromkeys(modifiers + list(self.category.repair_opportunities[:5]))
            )

        modified_queries = []
        seen_modified = set()

        # Mix modifiers with original query first
        for mod in modifiers:
            q = f"{base_query} {mod}".lower()
            if q not in seen_modified and q not in seen_candidates:
                modified_queries.append(q)
                seen_modified.add(q)

        # Then mix modifiers with other candidates if we have room
        for q_cand in candidate_queries[1:]:
            if (
                len(modified_queries)
                + len(candidate_queries)
                + len(category_expansions)
                >= max_queries * 2
            ):
                break
            for mod in modifiers:
                q = f"{q_cand} {mod}".lower()
                if q not in seen_modified and q not in seen_candidates:
                    modified_queries.append(q)
                    seen_modified.add(q)

        # 4. Combine and Rank
        # Priority: Original > Candidates (Variants) > Category Expansions > Modified Queries
        ordered_results = []
        seen_final = set()

        all_to_process = (
            [base_query.lower()]
            + candidate_queries
            + category_expansions
            + modified_queries
        )

        for q in all_to_process:
            normalized = " ".join(q.split())
            if normalized and normalized not in seen_final:
                seen_final.add(normalized)
                ordered_results.append(normalized)
            if len(ordered_results) >= max_queries:
                break

        return ordered_results

    def _expand_token(self, token: str) -> Set[str]:
        """Expand a single token into variants."""
        variants = {token}
        lower_token = token.lower()

        # Plurals/Singulars
        variants.add(self._pluralize(lower_token))
        variants.add(self._singularize(lower_token))

        # Abbreviations
        if lower_token in self.ABBREVIATIONS:
            variants.update(self.ABBREVIATIONS[lower_token])

        # Brand Aliases
        if lower_token in self.BRAND_ALIASES:
            variants.update(self.BRAND_ALIASES[lower_token])

        # Foreign Spellings
        if lower_token in self.FOREIGN_SPELLINGS:
            variants.update(self.FOREIGN_SPELLINGS[lower_token])

        # Category-specific misspellings
        if self.category:
            for misspelling in self.category.common_misspellings:
                if misspelling.lower() == lower_token:
                    variants.add(misspelling)

        return variants

    def _replace_token(self, tokens: list[str], index: int, replacement: str) -> str:
        """Replace a token at a specific index and return the new query string."""
        new_tokens = list(tokens)
        new_tokens[index] = replacement
        return " ".join(new_tokens)

    def _pluralize(self, token: str) -> str:
        if len(token) < 3:
            return token
        if token.endswith("y") and not token.endswith(("ay", "ey", "iy", "oy", "uy")):
            return token[:-1] + "ies"
        if token.endswith(("s", "sh", "ch", "x", "z")):
            if token.endswith("s") and len(token) > 3 and token[-2] not in "aeiou":
                # already likely plural or special case, but for bus -> buses we want it
                pass
            return token + "es"
        return token + "s"

    def _singularize(self, token: str) -> str:
        if len(token) < 3:
            return token
        if token.endswith("ies"):
            return token[:-3] + "y"
        if token.endswith("es") and token.endswith(
            ("ses", "xes", "zes", "ches", "shes")
        ):
            return token[:-2]
        if token.endswith("s") and not token.endswith("ss"):
            return token[:-1]
        return token
