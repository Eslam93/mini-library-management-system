"""The number check: every number in a reply must come from a lookup result or the user's words.

Numbers are compared as digit runs: "4,120" is 4120, "07" is 7, and a date gives its year, month
and day. Line-leading list numbers ("1.", "2)") are numbering, not figures, and are left out.
Ids are left out of the allowed runs, so digits inside a book's id cannot vouch for a number.
Numbers written as words pass, by design.
"""

import re
from collections.abc import Iterable
from typing import Any

_LIST_MARKER = re.compile(r"^[ \t]*(?:[-*][ \t]+)?\d{1,2}[.)][ \t]", re.MULTILINE)
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_DIGIT_RUN = re.compile(r"\d+")


def digit_runs(text: str) -> set[str]:
    folded = _THOUSANDS_COMMA.sub("", text)
    return {run.lstrip("0") or "0" for run in _DIGIT_RUN.findall(folded)}


def _is_id_key(key: str) -> bool:
    return key == "id" or key.endswith("_id")


def data_digit_runs(value: Any) -> set[str]:
    """The digit runs in a lookup result's values, except ids."""
    if isinstance(value, dict):
        return set().union(
            *(data_digit_runs(item) for key, item in value.items() if not _is_id_key(str(key)))
        )
    if isinstance(value, list):
        return set().union(*(data_digit_runs(item) for item in value))
    if isinstance(value, bool) or value is None:
        return set()
    return digit_runs(str(value))


def allowed_runs(results: Iterable[Any], user_texts: Iterable[str]) -> set[str]:
    allowed: set[str] = set()
    for result in results:
        allowed |= data_digit_runs(result)
    for text in user_texts:
        allowed |= digit_runs(text)
    return allowed


def unsupported_numbers(reply: str, allowed: set[str]) -> list[str]:
    """The numbers in the reply that no lookup result or user message contains."""
    return sorted(digit_runs(_LIST_MARKER.sub("", reply)) - allowed, key=lambda run: int(run))
