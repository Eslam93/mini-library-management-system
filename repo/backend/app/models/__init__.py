"""ORM models, one module per table. Importing this package registers every table on
Base.metadata, which Alembic compares against the database.
"""

from app.models.activity_event import ActivityEvent, ActivityVia
from app.models.book import Book
from app.models.copilot import (
    CopilotConversation,
    CopilotFace,
    CopilotMessage,
    CopilotProposal,
    CopilotRole,
    ProposalAction,
    ProposalStatus,
)
from app.models.copy import COPY_CODE_SEQUENCE, Copy
from app.models.loan import Loan
from app.models.member import Member
from app.models.user import User, UserRole
from app.models.user_session import UserSession

__all__ = [
    "COPY_CODE_SEQUENCE",
    "ActivityEvent",
    "ActivityVia",
    "Book",
    "CopilotConversation",
    "CopilotFace",
    "CopilotMessage",
    "CopilotProposal",
    "CopilotRole",
    "Copy",
    "Loan",
    "Member",
    "ProposalAction",
    "ProposalStatus",
    "User",
    "UserRole",
    "UserSession",
]
