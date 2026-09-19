"""Substring search patterns. PostgreSQL trigram indexes serve ILIKE '%term%' on the indexed
columns, so a partial word such as "herb" finds "Herbert".
"""

from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.orm import QueryableAttribute

_ESCAPE = "\\"


def search_term(q: str | None) -> str | None:
    """The trimmed search text, or None when there is nothing to search for."""
    term = (q or "").strip()
    return term or None


def contains(column: QueryableAttribute[Any], term: str) -> ColumnElement[bool]:
    """Case-insensitive match of term anywhere in the column. % and _ in the term match only
    themselves.
    """
    escaped = term.replace(_ESCAPE, _ESCAPE * 2).replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape=_ESCAPE)
