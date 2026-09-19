"""The forecast tool without a database: what the model reads, the chart with the likely range
shaded, the trend table of a refusal, the plain reply, and the staff face that carries the tool.
"""

import json
import re
from datetime import date
from types import SimpleNamespace

from app.copilot.analyst import FORECAST_METRIC, forecast_data
from app.copilot.faces import MEMBER_FACE, STAFF_FACE
from app.copilot.fake import FakeModelClient
from app.services.metrics import (
    CATALOGUE,
    ForecastMonth,
    ForecastResult,
    MonthValue,
    Refusal,
    Trend,
)

LAST_MONTH = date(2026, 8, 1)


def history(count: int = 12) -> list[MonthValue]:
    """Sep 2025 to Aug 2026 for twelve months, valued 100, 101, ..."""
    months = [date(2025 + (8 + n) // 12, (8 + n) % 12 + 1, 1) for n in range(12)]
    return [MonthValue(month, 100 + n) for n, month in enumerate(months)][-count:]


def forecast(**fields) -> ForecastResult:
    values = {
        "metric": CATALOGUE["loans"],
        "months": 35,
        "first_month": date(2023, 10, 1),
        "last_month": LAST_MONTH,
        "history": history(),
        "trend_factor": 1.08,
        "typical_error_pct": 6.2,
        "forecast": [
            ForecastMonth(date(2026, 9, 1), 120, 108, 131),
            ForecastMonth(date(2026, 10, 1), 1300, 1150, 1420),
        ],
        "refusal": None,
        "trend": None,
        "scope": [],
        **fields,
    }
    return ForecastResult(**values)


TREND = Trend(
    start=date(2025, 9, 1),
    end=date(2026, 8, 31),
    value=96,
    previous_start=date(2024, 9, 1),
    previous_end=date(2025, 8, 31),
    previous_value=80,
    change=16,
    change_pct=20.0,
)


def refused(reason, have, need) -> ForecastResult:
    return forecast(
        typical_error_pct=None,
        trend_factor=None,
        forecast=[],
        refusal=Refusal(reason, have, need),
        trend=TREND,
        scope=["category: Poetry"],
    )


async def run_tool(result: ForecastResult, monkeypatch):
    async def fake_run(session, query, *, today):
        return result

    monkeypatch.setattr("app.services.metrics.run_forecast", fake_run)
    context = SimpleNamespace(session=None)
    return await FORECAST_METRIC.run(context, FORECAST_METRIC.params(metric="loans"))


def test_the_model_reads_the_method_the_basis_and_each_month_with_its_range():
    data = forecast_data(forecast())

    assert data["metric"] == "loans"
    assert data["label"] == "Loans"
    assert data["method"].startswith(
        "Each month is forecast as the same month a year earlier times the trend"
    )
    assert "tested on past months" in data["method"]
    assert data["basis"] == "35 months of history"
    assert data["typical_error_pct"] == 6.2
    assert data["history"][0] == {"month": "Sep 2025", "value": 100}
    assert data["history"][-1] == {"month": "Aug 2026", "value": 111}
    assert data["forecast"] == [
        {"month": "Sep 2026", "value": 120, "low": 108, "high": 131},
        {"month": "Oct 2026", "value": 1300, "low": 1150, "high": 1420},
    ]
    assert (data["refusal"], data["trend"]) == (None, None)


async def test_the_forecast_is_a_line_with_the_likely_range_shaded(monkeypatch):
    output = await run_tool(forecast(scope=["category: Fantasy"]), monkeypatch)
    display = output.display.model_dump(mode="json")

    assert display["title"] == "Loans forecast"
    assert display["subtitle"] == (
        "Sep 2026 to Oct 2026 · from 35 months of history, Oct 2023 to Aug 2026 · "
        "typical error 6.2% · category: Fantasy"
    )
    assert [(c["key"], c["label"], c["format"]) for c in display["columns"]] == [
        ("label", "Month", "text"),
        ("actual", "Loans", "count"),
        ("forecast", "Forecast", "count"),
        ("low", "Low", "count"),
        ("high", "High", "count"),
    ]
    rows = display["rows"]
    assert len(rows) == 14
    assert rows[0] == {
        "label": "Sep 2025",
        "actual": 100,
        "forecast": None,
        "low": None,
        "high": None,
    }
    assert rows[12] == {
        "label": "Sep 2026",
        "actual": None,
        "forecast": 120,
        "low": 108,
        "high": 131,
    }
    assert display["total"] is None
    assert display["chart"] == {
        "type": "line",
        "x": "label",
        "series": [{"key": "actual", "label": "Loans"}, {"key": "forecast", "label": "Forecast"}],
        "band": {"low": "low", "high": "high", "label": "Likely range"},
    }


async def test_a_refusal_says_what_it_has_and_needs_and_shows_the_trend_without_a_chart(
    monkeypatch,
):
    output = await run_tool(refused("too_sparse", 4.2, 10), monkeypatch)
    display = output.display.model_dump(mode="json")

    assert output.data["refusal"] == {
        "reason": "too_sparse",
        "have": "an average of 4.2 loans a month over the last 12 months",
        "need": "an average of at least 10 loans a month",
        "alternative": "the trend: the last 12 months against the 12 before",
    }
    assert output.data["trend"] == {
        "period": "Sep 2025 to Aug 2026",
        "value": 96,
        "previous_period": "Sep 2024 to Aug 2025",
        "previous_value": 80,
        "change": 16,
        "change_pct": 20.0,
    }
    assert output.data["forecast"] == []
    assert display["title"] == "Loans trend"
    assert display["subtitle"] == (
        "Sep 2025 to Aug 2026 compared with Sep 2024 to Aug 2025 · category: Poetry"
    )
    assert display["rows"] == [
        {"value": 96, "previous_value": 80, "change": 16, "change_pct": 20.0}
    ]
    assert [c["format"] for c in display["columns"]] == [
        "count",
        "count",
        "count",
        "change_percent",
    ]
    assert display["chart"] is None


def test_each_refusal_reason_is_put_in_words():
    short = forecast_data(refused("short_history", 20, 32))["refusal"]
    erratic = forecast_data(refused("too_erratic", 41.3, 35.0))["refusal"]
    unbounded = forecast_data(refused("too_erratic", None, 35.0))["refusal"]

    assert (short["have"], short["need"]) == (
        "20 full months of history",
        "32 full months: 24 to forecast from, and 8 more to test the method against",
    )
    assert (erratic["have"], erratic["need"]) == (
        "a typical error of 41.3% when the method was tested on past months",
        "a typical error of at most 35%",
    )
    assert unbounded["have"] == "past forecasts of no loans for months that had some"


def test_the_plain_reply_puts_the_forecast_or_the_refusal_in_sentences():
    assert FORECAST_METRIC.render(forecast_data(forecast())) == (
        "Loans forecast from 35 months of history, with a typical error of 6.2%:\n"
        "- Sep 2026: 120, likely 108 to 131\n"
        "- Oct 2026: 1,300, likely 1,150 to 1,420"
    )
    assert FORECAST_METRIC.render(forecast_data(refused("short_history", 20, 32))) == (
        "No forecast of loans: the records have 20 full months of history, and a forecast would "
        "need 32 full months: 24 to forecast from, and 8 more to test the method against. The "
        "trend instead: 96 in Sep 2025 to Aug 2026, against 80 in Sep 2024 to Aug 2025, a change "
        "of +16 (+20.0%)."
    )


def test_staff_get_the_forecast_tool_and_members_do_not():
    assert STAFF_FACE.tool("forecast_metric") is FORECAST_METRIC
    assert MEMBER_FACE.tool("forecast_metric") is None


def test_the_staff_prompt_carries_the_forecast_rules_without_digits():
    prompt = STAFF_FACE.prompt

    assert not re.search(r"\d", prompt)
    for rule in (
        "Forecasts come only from forecast_metric",
        "say in one sentence how the range was measured",
        "say what the records have and what a forecast would need, and give the trend instead",
    ):
        assert rule in prompt


def test_the_forecast_tool_takes_a_metric_filters_and_a_horizon_of_one_to_six_months():
    [definition] = [
        d for d in STAFF_FACE.definitions() if d["function"]["name"] == "forecast_metric"
    ]
    parameters = definition["function"]["parameters"]

    assert not re.search(r"\d", definition["function"]["description"])
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["metric"]["enum"] == ["loans", "returns", "new_members"]
    assert set(parameters["properties"]["filters"]["properties"]) == {
        "categories",
        "author",
        "member_joined_year",
    }
    horizon = parameters["properties"]["horizon_months"]
    assert (horizon["default"], horizon["minimum"], horizon["maximum"]) == (3, 1, 6)


async def test_the_offline_fake_forecasts_loans_for_staff_only():
    staff = await FakeModelClient().complete(
        [{"role": "user", "content": "Forecast borrowing for the next three months"}],
        tools=STAFF_FACE.definitions(),
        tool_choice="auto",
        timeout=1,
    )
    member = await FakeModelClient().complete(
        [{"role": "user", "content": "Forecast borrowing for the next three months"}],
        tools=MEMBER_FACE.definitions(),
        tool_choice="auto",
        timeout=1,
    )

    [call] = staff.tool_calls
    assert (call.name, json.loads(call.arguments)) == ("forecast_metric", {"metric": "loans"})
    assert member.tool_calls[0].name == "search_catalog"
