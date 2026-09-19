"""Request and response shapes for sign-in."""

from uuid import UUID

from pydantic import BaseModel

from app.models import UserRole


class UserOut(BaseModel):
    id: UUID
    display_name: str
    email: str | None
    role: UserRole
    # The member record a member signs in as. Null for staff.
    member_id: UUID | None
    is_demo: bool


class AuthConfigOut(BaseModel):
    """Which ways to sign in the sign-in page offers."""

    demo_login: bool
    google: bool


class DemoSignIn(BaseModel):
    role: UserRole
