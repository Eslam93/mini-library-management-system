"""The analyst in the staff Copilot, with a scripted fake model: a question about how the library
is used streams a table, a follow-up changes one filter, refusals go back to the model, and
members never get the analyst's tools. Nothing here reaches the network.
"""

from datetime import UTC, date, datetime

import pytest
from copilot_stream import chat, data_of, names, tool_results
from sqlalchemy import update

from app.copilot.engine import FALLBACK_INTRO
from app.copilot.fake import call, calls, reply
from app.models import Member
from app.services.activity import format_day
from app.services.metrics import CATALOGUE

pytestmark = pytest.mark.integration

BY_CATEGORY = {"metric": "loans", "group_by": "category", "period": {"preset": "this_quarter"}}


def today() -> date:
    return datetime.now(UTC).date()


def this_quarter() -> tuple[str, str, str]:
    """This quarter as the results write it: its label, first day and today."""
    now = today()
    quarter = (now.month - 1) // 3 + 1
    start = date(now.year, 3 * quarter - 2, 1)
    return f"Q{quarter} {now.year} so far", format_day(start), format_day(now)


@pytest.fixture
async def lending(make_book, make_member, borrow, empty_db) -> None:
    """Three loans made today: two of a Technology book and one of a Fiction book. Maya joined
    today; Omar joined in 2024.
    """
    code = await make_book(
        title="Clean Code", author="Robert C. Martin", category="Technology", copies=2
    )
    emma = await make_book(title="Emma", author="Jane Austen", category="Fiction")
    maya, omar = await make_member("Maya Hassan"), await make_member("Omar Farouk")
    await borrow(code["copies"][0]["id"], maya["id"])
    await borrow(code["copies"][1]["id"], omar["id"])
    await borrow(emma["copies"][0]["id"], maya["id"])
    await empty_db.execute(
        update(Member).where(Member.full_name == "Omar Farouk").values(joined_on=date(2024, 5, 1))
    )
    await empty_db.commit()


async def test_a_question_about_use_streams_a_table_and_a_short_reading(lending, copilot):
    answer = "Technology leads so far this quarter with 2 loans, 66.7% of the total."
    http, model = await copilot(call("query_metrics", **BY_CATEGORY), reply(answer), role="staff")

    events = await chat(http, "Which categories were borrowed most this quarter?")

    label, start, end = this_quarter()
    assert names(events) == ["conversation", "status", "result", "message", "done"]
    assert data_of(events, "status") == [{"text": "Counting the figures"}]
    assert data_of(events, "message") == [{"text": answer}]
    assert tool_results(model, 1)[0] == {
        "metric": "loans",
        "label": "Loans",
        "measured": "period",
        "period": {"from": start, "to": end, "label": label, "partial": True},
        "comparison": None,
        "group_by": "category",
        "sort": "value_desc",
        "rows": [
            {"key": "Technology", "label": "Technology", "value": 2, "share_pct": 66.7},
            {"key": "Fiction", "label": "Fiction", "value": 1, "share_pct": 33.3},
        ],
        "rows_total": 2,
        "total": {"value": 3},
    }
    [result] = data_of(events, "result")
    assert result["tool"] == "query_metrics"
    assert result["display"] == {
        "kind": "table",
        "title": "Loans by category",
        "subtitle": f"{label} ({start} to {end})",
        "columns": [
            {"key": "label", "label": "Category", "format": "text"},
            {"key": "value", "label": "Loans", "format": "count"},
            {"key": "share_pct", "label": "Share", "format": "percent"},
        ],
        "rows": [
            {"label": "Technology", "value": 2, "share_pct": 66.7},
            {"label": "Fiction", "value": 1, "share_pct": 33.3},
        ],
        "total": {"label": "Total", "value": 3, "share_pct": None},
        "chart": {"type": "bar", "x": "label", "series": [{"key": "value", "label": "Loans"}]},
    }


async def test_a_follow_up_repeats_the_query_with_one_filter_added(lending, copilot):
    year = today().year
    joined = {"member_joined_year": {"from": year, "to": year}}
    http, model = await copilot(
        call("query_metrics", **BY_CATEGORY),
        reply("Technology leads with 2 loans."),
        call("query_metrics", **BY_CATEGORY, filters=joined),
        reply("Among members who joined this year, Fiction and Technology have 1 loan each."),
        role="staff",
    )

    first = await chat(http, "Which categories were borrowed most this quarter?")
    conversation_id = data_of(first, "conversation")[0]["conversation_id"]
    second = await chat(http, "Only among members who joined this year?", conversation_id)

    # The follow-up's model call has the first query in the conversation, to repeat it.
    earlier_calls = [
        message["tool_calls"][0]["function"]
        for message in model.requests[2].messages
        if message.get("tool_calls")
    ]
    assert [call["name"] for call in earlier_calls] == ["query_metrics"]
    rows = tool_results(model, 3)[-1]["rows"]
    assert [(row["label"], row["value"], row["share_pct"]) for row in rows] == [
        ("Fiction", 1, 50.0),
        ("Technology", 1, 50.0),
    ]
    [table] = [data["display"] for data in data_of(second, "result")]
    assert table["subtitle"].endswith(f" · members who joined in {year}")
    assert table["total"]["value"] == 2
    assert data_of(second, "message") == [
        {"text": "Among members who joined this year, Fiction and Technology have 1 loan each."}
    ]


async def test_a_comparison_answers_with_the_servers_shares_and_changes(lending, copilot):
    http, model = await copilot(
        call("query_metrics", **BY_CATEGORY, compare_to="previous_period"),
        reply("Technology is 66.7% of loans so far, against nothing in the previous period."),
        role="staff",
    )

    events = await chat(http, "How does that compare with last quarter?")

    data = tool_results(model, 1)[0]
    assert data["comparison"]["kind"] == "previous_period"
    assert data["rows"][0] == {
        "key": "Technology",
        "label": "Technology",
        "value": 2,
        "share_pct": 66.7,
        "previous_value": 0,
        "previous_share_pct": None,
        "change": 2,
        "change_pct": None,
    }
    assert data["total"] == {"value": 3, "previous_value": 0, "change": 3, "change_pct": None}
    [result] = data_of(events, "result")
    assert [column["key"] for column in result["display"]["columns"]] == [
        "label",
        "value",
        "share_pct",
        "previous_value",
        "previous_share_pct",
        "change",
        "change_pct",
    ]
    assert [series["label"] for series in result["display"]["chart"]["series"]] == [
        "Loans",
        "Previous period",
    ]


async def test_a_single_figure_is_a_one_row_table_measured_now(lending, copilot):
    http, model = await copilot(
        call("query_metrics", metric="active_loans"),
        reply("There are 3 active loans."),
        role="staff",
    )

    events = await chat(http, "How many active loans are there?")

    data = tool_results(model, 1)[0]
    assert (data["measured"], data["period"], data["rows"], data["total"]) == (
        "now",
        None,
        [],
        {"value": 3},
    )
    [result] = data_of(events, "result")
    assert result["display"] == {
        "kind": "table",
        "title": "Active loans",
        "subtitle": "Now",
        "columns": [{"key": "value", "label": "Active loans", "format": "count"}],
        "rows": [{"value": 3}],
        "total": None,
        "chart": None,
    }
    assert data_of(events, "message") == [{"text": "There are 3 active loans."}]


async def test_an_invented_figure_falls_back_to_the_results_in_sentences(lending, copilot):
    http, model = await copilot(
        call("query_metrics", **BY_CATEGORY),
        reply("Technology rose by 47 points."),
        reply("Technology rose by 47 points, as I said."),
        role="staff",
    )

    events = await chat(http, "Which categories were borrowed most this quarter?")

    label, start, end = this_quarter()
    [message] = data_of(events, "message")
    assert message["text"] == (
        f"{FALLBACK_INTRO}\n\n"
        f"Loans by category, {label} ({start} to {end}):\n"
        "- Technology: 2 (66.7% of the total)\n"
        "- Fiction: 1 (33.3% of the total)\n"
        "Total: 3."
    )
    assert model.requests[2].tool_choice == "none"


async def test_refusals_go_back_to_the_model_with_what_is_accepted(lending, copilot):
    http, model = await copilot(
        calls(
            call("query_metrics", metric="active_loans", period={"preset": "this_year"}),
            call("query_metrics", metric="loans", sql="SELECT * FROM loans"),
            call("query_metrics", metric="loans", filters={"categories": ["Sci-fi"]}),
            call("query_metrics", metric="new_members", group_by="category"),
        ),
        reply("I can count loans by category instead."),
        role="staff",
    )

    events = await chat(http, "Active loans this year, please")

    measured_now, unknown_field, unknown_category, grouping = tool_results(model, 1)
    assert measured_now == {
        "error": "measured_now",
        "message": "active_loans is measured now, so it takes no period and no comparison. "
        "Leave period and compare_to out.",
    }
    assert unknown_field["error"] == "invalid_arguments"
    assert unknown_field["problems"] == [
        {"field": "sql", "problem": "Extra inputs are not permitted"}
    ]
    assert unknown_category == {
        "error": "unknown_category",
        "message": "No category is named Sci-fi. The categories are: Fiction, Technology.",
    }
    assert grouping == {
        "error": "grouping_not_accepted",
        "message": "new_members cannot be grouped by category. It accepts group_by: none, "
        "month, year.",
    }
    assert data_of(events, "result") == []


async def test_describe_metrics_gives_the_catalogue_without_a_card(copilot):
    http, model = await copilot(
        call("describe_metrics"), reply("I can count loans, returns and more."), role="staff"
    )

    events = await chat(http, "What can you tell me about the library?")

    catalogue = tool_results(model, 1)[0]
    assert catalogue["today"] == format_day(today())
    assert [metric["name"] for metric in catalogue["metrics"]] == list(CATALOGUE)
    assert catalogue["metrics"][2] == {
        "name": "active_loans",
        "meaning": "Loans not returned yet, now.",
        "measured": "now",
        "value": "count",
        "group_by": ["none", "category", "book", "author", "member_joined_year"],
        "filters": ["categories", "author", "book_id", "member_joined_year"],
        "share_of_total": True,
    }
    assert catalogue["periods"]["default"] == "last_12_months"
    assert set(catalogue["compare_to"]) == {"none", "previous_period", "same_period_last_year"}
    assert data_of(events, "status") == [{"text": "Looking at the figures available"}]
    assert data_of(events, "result") == []


async def test_members_never_get_the_analyst_tools(lending, copilot):
    http, model = await copilot(
        call("query_metrics", metric="active_loans"),
        call("describe_metrics"),
        reply("I cannot answer that."),
    )

    events = await chat(http, "How many active loans are there?")

    assert "query_metrics" not in model.requests[0].tool_names
    assert "describe_metrics" not in model.requests[0].tool_names
    assert tool_results(model, 1)[0]["error"] == "unknown_tool"
    assert tool_results(model, 2)[1]["error"] == "unknown_tool"
    assert data_of(events, "result") == []
