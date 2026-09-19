"""The metric catalogue and the typed query: which metrics exist, what each one accepts, and the
query a caller sends. Every model rejects unknown fields, at every level.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.exceptions import ValidationFailedError

MetricName = Literal[
    "loans",
    "returns",
    "active_loans",
    "overdue_loans",
    "unique_borrowers",
    "new_members",
    "late_return_rate",
    "average_loan_days",
    "copies_on_loan_share",
    "titles_not_borrowed",
]
Grouping = Literal[
    "none", "category", "book", "author", "month", "year", "weekday", "member_joined_year"
]
FilterName = Literal["categories", "author", "book_id", "member_joined_year"]
PeriodPreset = Literal[
    "last_30_days",
    "last_90_days",
    "this_month",
    "this_quarter",
    "this_year",
    "last_month",
    "last_quarter",
    "last_year",
    "last_12_months",
    "all_time",
]
ComparisonKind = Literal["none", "previous_period", "same_period_last_year"]
SortOrder = Literal["value_desc", "value_asc", "key"]
# What a value is: a count, a percentage, or a number of days.
Unit = Literal["count", "percent", "days"]
Measured = Literal["period", "now"]

ALL_GROUPINGS: tuple[Grouping, ...] = get_args(Grouping)
NOW_GROUPINGS: tuple[Grouping, ...] = ("none", "category", "book", "author", "member_joined_year")
ALL_FILTERS: tuple[FilterName, ...] = get_args(FilterName)
# Time groupings list every bucket of the period, in time order unless asked otherwise.
TIME_GROUPINGS: tuple[Grouping, ...] = ("month", "year", "weekday")
DEFAULT_PRESET: PeriodPreset = "last_12_months"
DEFAULT_ROWS = 10
MAX_ROWS = 50
UNCATEGORISED = "Uncategorised"
_EARLIEST_YEAR = 1900
_LATEST_YEAR = 2100


@dataclass(frozen=True)
class Metric:
    name: MetricName
    label: str
    meaning: str
    unit: Unit
    measured: Measured
    groupings: tuple[Grouping, ...]
    filters: tuple[FilterName, ...]
    # Whether a row's share of the total means something: true for counts that add up.
    shares: bool


CATALOGUE: dict[MetricName, Metric] = {
    metric.name: metric
    for metric in (
        Metric(
            "loans", "Loans", "Loans started in the period.",
            "count", "period", ALL_GROUPINGS, ALL_FILTERS, shares=True,
        ),
        Metric(
            "returns", "Returns", "Loans returned in the period.",
            "count", "period", ALL_GROUPINGS, ALL_FILTERS, shares=True,
        ),
        Metric(
            "active_loans", "Active loans", "Loans not returned yet, now.",
            "count", "now", NOW_GROUPINGS, ALL_FILTERS, shares=True,
        ),
        Metric(
            "overdue_loans", "Overdue loans", "Active loans past their due date, now.",
            "count", "now", NOW_GROUPINGS, ALL_FILTERS, shares=True,
        ),
        Metric(
            "unique_borrowers", "Borrowers",
            "Members who started a loan in the period, each counted once per row and once in "
            "the total.",
            "count", "period", ALL_GROUPINGS, ALL_FILTERS, shares=False,
        ),
        Metric(
            "new_members", "New members", "Members who joined in the period.",
            "count", "period", ("none", "month", "year"), (), shares=True,
        ),
        Metric(
            "late_return_rate", "Late return rate",
            "Percentage of the period's returns that came back after the due date.",
            "percent", "period", ALL_GROUPINGS, ALL_FILTERS, shares=False,
        ),
        Metric(
            "average_loan_days", "Average loan length",
            "Average days from borrowing to return, over the period's returns.",
            "days", "period", ALL_GROUPINGS, ALL_FILTERS, shares=False,
        ),
        Metric(
            "copies_on_loan_share", "Copies on loan",
            "Percentage of the copies in circulation that are on loan now.",
            "percent", "now", ("none", "category"), ("categories", "author", "book_id"),
            shares=False,
        ),
        Metric(
            "titles_not_borrowed", "Titles not borrowed",
            "Books in the catalog with no loan started in the period. Grouped by book, it lists "
            "them.",
            "count", "period", ("none", "category", "author", "book"), ("categories", "author"),
            shares=True,
        ),
    )
}  # fmt: skip

GROUPINGS: dict[Grouping, str] = {
    "none": "One figure for the whole scope.",
    "category": f"The book's category; a book without one is {UNCATEGORISED}.",
    "book": "Each book, labelled with its title and author.",
    "author": "The book's author.",
    "month": "The calendar months of the period, with empty months as zero.",
    "year": "The calendar years of the period.",
    "weekday": "The days of the week, Monday first.",
    "member_joined_year": "The year the borrowing member joined the library.",
}

FILTERS: dict[FilterName, str] = {
    "categories": "Only these categories, named as list_categories gives them.",
    "author": "Only books by this author, the name exactly as results give it.",
    "book_id": "Only this book, by its id.",
    "member_joined_year": "Only members who joined in these years: from and to, the same year "
    "for one year.",
}

PRESETS: dict[PeriodPreset, str] = {
    "last_30_days": "Today and the days before it, thirty days in all.",
    "last_90_days": "Today and the days before it, ninety days in all.",
    "this_month": "From the first of this month to today; partial.",
    "this_quarter": "From the first day of this quarter to today; partial.",
    "this_year": "From the first of January to today; partial.",
    "last_month": "The whole previous calendar month.",
    "last_quarter": "The whole previous calendar quarter.",
    "last_year": "The whole previous calendar year.",
    "last_12_months": "The twelve whole calendar months before this month. The default.",
    "all_time": "From the first loan, or the first member for new_members, to today.",
}

COMPARISONS: dict[ComparisonKind, str] = {
    "none": "No comparison.",
    "previous_period": "The period just before: the previous calendar unit for calendar presets "
    "(cut at the same point when the current one is partial), otherwise the same number of days "
    "just before the start.",
    "same_period_last_year": "The same dates one year earlier.",
}


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class YearRange(_Spec):
    from_: int = Field(alias="from", ge=_EARLIEST_YEAR, le=_LATEST_YEAR, description="First year.")
    to: int = Field(
        ge=_EARLIEST_YEAR, le=_LATEST_YEAR, description="Last year; the same as from for one year."
    )

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if self.from_ > self.to:
            raise ValueError("from must not be after to.")
        return self


CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class MetricFilters(_Spec):
    categories: list[CategoryName] | None = Field(
        default=None, min_length=1, max_length=20, description=FILTERS["categories"]
    )
    author: str | None = Field(
        default=None, min_length=1, max_length=200, description=FILTERS["author"]
    )
    book_id: uuid.UUID | None = Field(default=None, description=FILTERS["book_id"])
    member_joined_year: YearRange | None = Field(
        default=None, description=FILTERS["member_joined_year"]
    )

    def used(self) -> list[str]:
        """The names of the filters that are set."""
        return list(self.model_dump(exclude_none=True))


class PeriodSpec(_Spec):
    preset: PeriodPreset | None = Field(default=None, description="A named period.")
    from_: date | None = Field(
        default=None, alias="from", description="First day, with to, instead of a preset."
    )
    to: date | None = Field(default=None, description="Last day, not after today.")

    @model_validator(mode="after")
    def _preset_or_dates(self) -> Self:
        dates = (self.from_, self.to)
        if self.preset is not None and dates != (None, None):
            raise ValueError("Give a preset, or from and to, not both.")
        if self.preset is None and None in dates:
            raise ValueError("Give a preset, or both from and to.")
        return self


class MetricQuery(_Spec):
    metric: MetricName = Field(description="What to measure; describe_metrics explains each.")
    group_by: Grouping = Field(default="none", description="How to split the figure into rows.")
    filters: MetricFilters = Field(
        default_factory=MetricFilters, description="Which loans, books or members count."
    )
    period: PeriodSpec | None = Field(
        default=None,
        description="For metrics measured over a period; leave it out for metrics measured "
        f"now. Left out, it is {DEFAULT_PRESET}.",
    )
    compare_to: ComparisonKind = Field(
        default="none", description="An earlier period to compare with."
    )
    sort: SortOrder | None = Field(
        default=None,
        description="value_desc, value_asc, or key (time buckets in time order, other rows "
        "alphabetically). Left out: key for month, year and weekday, otherwise value_desc.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_ROWS,
        description="How many rows to return. Left out: every bucket for month, year and "
        f"weekday, otherwise {DEFAULT_ROWS}.",
    )


ForecastMetricName = Literal["loans", "returns", "new_members"]
MAX_HORIZON_MONTHS = 6


class ForecastFilters(_Spec):
    categories: list[CategoryName] | None = Field(
        default=None, min_length=1, max_length=20, description=FILTERS["categories"]
    )
    author: str | None = Field(
        default=None, min_length=1, max_length=200, description=FILTERS["author"]
    )
    member_joined_year: YearRange | None = Field(
        default=None, description=FILTERS["member_joined_year"]
    )

    def used(self) -> list[str]:
        """The names of the filters that are set."""
        return list(self.model_dump(exclude_none=True))

    def as_metric_filters(self) -> MetricFilters:
        return MetricFilters.model_validate(self.model_dump(exclude_none=True, by_alias=True))


class ForecastQuery(_Spec):
    metric: ForecastMetricName = Field(description="What to forecast: a monthly count.")
    filters: ForecastFilters = Field(
        default_factory=ForecastFilters,
        description="For loans and returns only: which loans count.",
    )
    horizon_months: int = Field(
        default=3,
        ge=1,
        le=MAX_HORIZON_MONTHS,
        description="How many months to forecast, starting with this month.",
    )


def refusal(message: str, code: str) -> ValidationFailedError:
    return ValidationFailedError(message, code=code)


def check_query(metric: Metric, query: MetricQuery) -> None:
    """Refuses a grouping, filter, period or comparison the metric does not accept, with a
    message that lists what it accepts.
    """
    if query.group_by not in metric.groupings:
        raise refusal(
            f"{metric.name} cannot be grouped by {query.group_by}. It accepts group_by: "
            f"{', '.join(metric.groupings)}.",
            "grouping_not_accepted",
        )
    refused = [name for name in query.filters.used() if name not in metric.filters]
    if refused:
        accepted = (
            f"It accepts filters: {', '.join(metric.filters)}."
            if metric.filters
            else "It takes no filters."
        )
        raise refusal(
            f"{metric.name} cannot be filtered by {', '.join(refused)}. {accepted}",
            "filter_not_accepted",
        )
    if metric.measured == "now" and (query.period is not None or query.compare_to != "none"):
        raise refusal(
            f"{metric.name} is measured now, so it takes no period and no comparison. Leave "
            "period and compare_to out.",
            "measured_now",
        )
