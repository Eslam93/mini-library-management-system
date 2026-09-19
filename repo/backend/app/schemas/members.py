"""Request and response shapes for members."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.schemas.fields import Email, FullName


class MemberCreate(BaseModel):
    full_name: FullName
    email: Email = None


class MemberRef(BaseModel):
    id: UUID
    full_name: str


class MemberOut(BaseModel):
    id: UUID
    full_name: str
    email: str | None
    joined_on: date
    active_loans: int


class MemberDetail(MemberOut):
    # Every loan the member has had, active and returned.
    loans_total: int
