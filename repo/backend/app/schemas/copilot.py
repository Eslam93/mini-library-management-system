"""Request and response shapes for the Copilot, and what its lookups show in the panel."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.models import CopilotFace, ProposalAction, ProposalStatus
from app.schemas.books import BookDetail, BookSummary
from app.schemas.loans import BookRef, CopyLookup, CopyRef, LoanOut
from app.schemas.members import MemberOut, MemberRef

MAX_MESSAGE_LENGTH = 2000

ChatText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH)
]


class CopilotConfigOut(BaseModel):
    available: bool
    face: CopilotFace
    # Why the assistant is unavailable, in words the panel can show. Null when available.
    reason: str | None
    # Prompts suited to the face, offered before the first message.
    examples: list[str]


class ChatRequest(BaseModel):
    # Leave out to start a new conversation.
    conversation_id: UUID | None = None
    message: ChatText


class ProposalError(BaseModel):
    code: str
    message: str


class ProposalOut(BaseModel):
    """A borrow or a return the Copilot prepared, as its card shows it. A pending proposal past
    expires_at reads as expired.
    """

    id: UUID
    action: ProposalAction
    status: ProposalStatus
    book: BookRef
    # "copy" would shadow BaseModel.copy, so the attribute has another name.
    copy_ref: CopyRef = Field(alias="copy")
    member: MemberRef
    # borrow: the due time the loan will get. return: the loan's due time.
    due_at: datetime
    # return: when the copy was borrowed. Null for a borrow.
    borrowed_at: datetime | None
    # return: whether the loan was overdue when proposed. Always false for a borrow.
    is_overdue: bool
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None
    # After a confirm: the new loan, or the returned loan.
    loan: LoanOut | None
    # Why the confirm failed. Null unless failed.
    error: ProposalError | None


# What a lookup shows, rendered with the product's own components.


class BooksDisplay(BaseModel):
    kind: Literal["books"] = "books"
    items: list[BookSummary]


class BookDisplay(BaseModel):
    kind: Literal["book"] = "book"
    book: BookDetail


class LoansDisplay(BaseModel):
    kind: Literal["loans"] = "loans"
    items: list[LoanOut]


class CategoriesDisplay(BaseModel):
    kind: Literal["categories"] = "categories"
    items: list[str]


class MembersDisplay(BaseModel):
    kind: Literal["members"] = "members"
    items: list[MemberOut]


class CopyDisplay(BaseModel):
    kind: Literal["copy"] = "copy"
    lookup: CopyLookup


class ProposalDisplay(BaseModel):
    kind: Literal["proposal"] = "proposal"
    proposal: ProposalOut


# How the panel writes a cell: text as it is; count with thousands separators; percent as
# "37.1%"; points as "+8.2 pts"; change_percent as "+12.5%"; days as "12.3 days". Null is a dash.
TableFormat = Literal["text", "count", "percent", "points", "change_percent", "days"]
# Raw values; the panel formats them by their column.
TableCell = str | int | float | None


class TableColumn(BaseModel):
    key: str
    label: str
    format: TableFormat


class ChartSeries(BaseModel):
    # The column that holds the series' values.
    key: str
    label: str


class ChartBand(BaseModel):
    """A range shaded under the lines, such as a forecast's likely range."""

    # The columns that hold the bottom and the top of the range in each row.
    low: str
    high: str
    label: str


class TableChart(BaseModel):
    # line: a time series. bar: a comparison between groups.
    type: Literal["bar", "line"]
    # The column that holds each point's label.
    x: str
    series: list[ChartSeries]
    # Line charts only. Left out of the JSON when there is none, so other charts keep their shape.
    band: ChartBand | None = Field(default=None, exclude_if=lambda band: band is None)


class TableDisplay(BaseModel):
    """An analyst answer: a table of figures, with a chart where it helps."""

    kind: Literal["table"] = "table"
    title: str
    # The period (or "Now"), the comparison and the filters.
    subtitle: str
    columns: list[TableColumn]
    # Each row maps a column key to its value.
    rows: list[dict[str, TableCell]]
    # The figures over the whole scope, in the same columns. Null for a single figure.
    total: dict[str, TableCell] | None
    chart: TableChart | None


Display = (
    BooksDisplay
    | BookDisplay
    | LoansDisplay
    | CategoriesDisplay
    | MembersDisplay
    | CopyDisplay
    | ProposalDisplay
    | TableDisplay
)
