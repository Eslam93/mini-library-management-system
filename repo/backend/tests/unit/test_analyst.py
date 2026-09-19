"""The analyst's tools without a database: the result the model reads, the table and chart the
panel shows, the plain reply, and the staff face that carries them.
"""

import json
import re
from datetime import date

import pytest

from app.copilot.analyst import QUERY_METRICS, result_data, table_display
from app.copilot.faces import MEMBER_FACE, STAFF_FACE
from app.copilot.fake import FakeModelClient
from app.services.metrics import CATALOGUE, Comparison, MetricResult, Period, Row, Total

QUARTER = Period(date(2026, 7, 1), date(2026, 9, 19), "Q3 2026 so far", True, 3)
EARLIER = Comparison(
    "previous_period", date(2026, 4, 1), date(2026, 6, 19), "1 Apr 2026 to 19 Jun 2026"
)


def result(metric="loans", *, group_by="category", sort="value_desc", rows=(), **fields):
    values = {
        "metric": CATALOGUE[metric],
        "period": QUARTER if CATALOGUE[metric].measured == "period" else None,
        "comparison": None,
        "group_by": group_by,
        "sort": sort,
        "rows": list(rows),
        "rows_total": len(rows),
        "total": Total(sum(row.value for row in rows)),
        "scope": [],
        **fields,
    }
    return MetricResult(**values)


def months(count: int) -> list[Row]:
    return [Row(f"2026-{n:02d}", f"M{n}", n) for n in range(1, count + 1)]


def categories(count: int) -> list[Row]:
    return [Row(f"C{n}", f"C{n}", n, share_pct=1.0) for n in range(count)]


def test_the_model_reads_every_figure_with_dates_written_out():
    compared = result(
        rows=[
            Row("Technology", "Technology", 4, 40.0, 2, 50.0, 2, 100.0),
            Row("Fiction", "Fiction", 0, 0.0, 2, 50.0, -2, -100.0),
        ],
        comparison=EARLIER,
        total=Total(10, 4, 6, 150.0),
    )

    assert result_data(compared) == {
        "metric": "loans",
        "label": "Loans",
        "measured": "period",
        "period": {
            "from": "1 Jul 2026",
            "to": "19 Sep 2026",
            "label": "Q3 2026 so far",
            "partial": True,
        },
        "comparison": {
            "kind": "previous_period",
            "from": "1 Apr 2026",
            "to": "19 Jun 2026",
            "label": "1 Apr 2026 to 19 Jun 2026",
        },
        "group_by": "category",
        "sort": "value_desc",
        "rows": [
            {
                "key": "Technology",
                "label": "Technology",
                "value": 4,
                "share_pct": 40.0,
                "previous_value": 2,
                "previous_share_pct": 50.0,
                "change": 2,
                "change_pct": 100.0,
            },
            {
                "key": "Fiction",
                "label": "Fiction",
                "value": 0,
                "share_pct": 0.0,
                "previous_value": 2,
                "previous_share_pct": 50.0,
                "change": -2,
                "change_pct": -100.0,
            },
        ],
        "rows_total": 2,
        "total": {"value": 10, "previous_value": 4, "change": 6, "change_pct": 150.0},
    }


def test_rates_have_no_shares_and_no_relative_change_and_books_keep_their_id_apart():
    rate = result(
        "late_return_rate",
        group_by="book",
        rows=[Row("5f0e7a12-0000-4000-8000-000000000042", "Dune by Frank Herbert", 25.0)],
        comparison=EARLIER,
        total=Total(25.0, 12.5, 12.5, None),
    )

    data = result_data(rate)

    assert data["rows"] == [
        {
            "book_id": "5f0e7a12-0000-4000-8000-000000000042",
            "label": "Dune by Frank Herbert",
            "value": 25.0,
            "previous_value": None,
            "change": None,
        }
    ]
    assert data["total"] == {"value": 25.0, "previous_value": 12.5, "change": 12.5}


def test_a_table_has_the_figures_raw_with_formats_a_total_row_and_a_bar_chart():
    display = table_display(
        result(
            rows=[Row("Technology", "Technology", 4, 40.0, 2, 50.0, 2, 100.0)],
            comparison=EARLIER,
            total=Total(10, 4, 6, 150.0),
            scope=["members who joined in 2026"],
        )
    ).model_dump()

    assert display["kind"] == "table"
    assert display["title"] == "Loans by category"
    assert display["subtitle"] == (
        "Q3 2026 so far (1 Jul 2026 to 19 Sep 2026) · compared with 1 Apr 2026 to 19 Jun 2026 · "
        "members who joined in 2026"
    )
    assert [(c["key"], c["label"], c["format"]) for c in display["columns"]] == [
        ("label", "Category", "text"),
        ("value", "Loans", "count"),
        ("share_pct", "Share", "percent"),
        ("previous_value", "Previous period", "count"),
        ("previous_share_pct", "Share before", "percent"),
        ("change", "Change", "count"),
        ("change_pct", "Change %", "change_percent"),
    ]
    assert display["rows"] == [
        {
            "label": "Technology",
            "value": 4,
            "share_pct": 40.0,
            "previous_value": 2,
            "previous_share_pct": 50.0,
            "change": 2,
            "change_pct": 100.0,
        }
    ]
    assert display["total"] == {
        "label": "Total",
        "value": 10,
        "share_pct": None,
        "previous_value": 4,
        "previous_share_pct": None,
        "change": 6,
        "change_pct": 150.0,
    }
    # One row is too few for a bar chart.
    assert display["chart"] is None


def test_a_rate_changes_in_points_and_a_single_figure_is_a_one_row_table():
    display = table_display(
        result(
            "late_return_rate", group_by="none", comparison=EARLIER, total=Total(33.3, 50.0, -16.7)
        )
    ).model_dump()

    assert [(c["key"], c["format"]) for c in display["columns"]] == [
        ("value", "percent"),
        ("previous_value", "percent"),
        ("change", "points"),
    ]
    assert display["rows"] == [{"value": 33.3, "previous_value": 50.0, "change": -16.7}]
    assert (display["title"], display["total"], display["chart"]) == (
        "Late return rate",
        None,
        None,
    )


def test_a_figure_measured_now_says_now():
    display = table_display(result("active_loans", group_by="none", total=Total(119)))

    assert (display.subtitle, display.rows) == ("Now", [{"value": 119}])


@pytest.mark.parametrize(
    ("grouping", "sort", "rows", "chart"),
    [
        ("month", "key", months(12), "line"),
        ("year", "key", months(3), "line"),
        ("month", "key", months(2), None),
        # Months ordered by their values are no longer a time line.
        ("month", "value_desc", months(5), "bar"),
        ("weekday", "key", categories(7), "bar"),
        ("category", "value_desc", categories(2), "bar"),
        ("category", "value_desc", categories(12), "bar"),
        ("category", "value_desc", categories(13), None),
        ("category", "value_desc", categories(1), None),
        ("none", "value_desc", [], None),
    ],
)
def test_the_server_chooses_the_chart(grouping, sort, rows, chart):
    display = table_display(result(group_by=grouping, sort=sort, rows=rows))

    assert (display.chart.type if display.chart else None) == chart


def test_a_chart_with_a_comparison_has_both_series_and_a_list_of_books_has_none():
    compared = table_display(result(rows=categories(3), comparison=EARLIER))
    books = table_display(result("titles_not_borrowed", group_by="book", rows=categories(3)))

    assert compared.chart is not None
    assert compared.chart.model_dump() == {
        "type": "bar",
        "x": "label",
        "series": [
            {"key": "value", "label": "Loans"},
            {"key": "previous_value", "label": "Previous period"},
        ],
    }
    assert books.chart is None


def test_the_plain_reply_puts_the_figures_in_sentences():
    compared = result(
        rows=[Row("Technology", "Technology", 1234, 40.0, 2, 50.0, 1232, 61600.0)],
        comparison=EARLIER,
        total=Total(3085, 4, 3081, None),
    )
    kpi = result("average_loan_days", group_by="none", total=Total(12.3))

    assert QUERY_METRICS.render(result_data(compared)) == (
        "Loans by category, Q3 2026 so far (1 Jul 2026 to 19 Sep 2026), compared with 1 Apr 2026 "
        "to 19 Jun 2026:\n"
        "- Technology: 1,234 (40.0% of the total), against 2 (50.0%), a change of +1,232 "
        "(+61600.0%)\n"
        "Total: 3,085, against 4, a change of +3,081."
    )
    assert QUERY_METRICS.render(result_data(kpi)) == (
        "Average loan length, Q3 2026 so far (1 Jul 2026 to 19 Sep 2026): 12.3 days."
    )


# The staff face


def test_staff_get_the_analyst_tools_and_members_do_not():
    assert [tool.name for tool in STAFF_FACE.tools][-2:] == ["describe_metrics", "query_metrics"]
    assert MEMBER_FACE.tool("query_metrics") is None
    assert MEMBER_FACE.tool("describe_metrics") is None
    assert "Which categories were borrowed most this quarter?" in STAFF_FACE.examples
    assert len(STAFF_FACE.examples) == 4


def test_the_staff_prompt_carries_the_analyst_rules_without_digits():
    prompt = STAFF_FACE.prompt

    assert not re.search(r"\d", prompt)
    for rule in (
        "describe_metrics first when unsure",
        "repeat the previous query with only the changed part",
        'say "so far" when the period is partial',
        "Quote shares, changes and totals exactly as the results give them",
        "say so plainly and name the nearest thing you can answer",
    ):
        assert rule in prompt


def test_the_query_tool_schema_is_written_out_without_references():
    [definition] = [d for d in STAFF_FACE.definitions() if d["function"]["name"] == "query_metrics"]
    parameters = definition["function"]["parameters"]

    assert "$ref" not in str(parameters)
    assert "$defs" not in parameters
    filters = parameters["properties"]["filters"]
    assert filters["additionalProperties"] is False
    assert set(filters["properties"]) == {"categories", "author", "book_id", "member_joined_year"}
    period = parameters["properties"]["period"]["anyOf"][0]
    assert set(period["properties"]) == {"preset", "from", "to"}


@pytest.mark.parametrize(
    ("message", "arguments"),
    [
        (
            "Which categories were borrowed most this quarter?",
            {"metric": "loans", "group_by": "category", "period": {"preset": "this_quarter"}},
        ),
        ("Loans per month, please", {"metric": "loans", "group_by": "month"}),
    ],
)
async def test_the_offline_fake_counts_loans_for_staff(message, arguments):
    [call] = (await ask_offline(STAFF_FACE, message)).tool_calls

    assert (call.name, json.loads(call.arguments)) == ("query_metrics", arguments)


async def test_the_offline_fake_never_counts_for_members():
    [call] = (await ask_offline(MEMBER_FACE, "Which categories are read most?")).tool_calls

    assert call.name == "list_categories"


async def ask_offline(face, message: str):
    return await FakeModelClient().complete(
        [{"role": "user", "content": message}],
        tools=face.definitions(),
        tool_choice="auto",
        timeout=1,
    )
