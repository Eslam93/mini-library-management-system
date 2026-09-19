"""Sign-in: sessions, the demo accounts, and completing a Google sign-in.

A session is an opaque random token kept in a cookie. The database stores only the token's
SHA-256 hash. A session ends at its absolute expiry, after the idle timeout without a request, or
when it is revoked by signing out. The application clock both writes the timestamps and checks
them, so one clock decides.
"""

import hashlib
import secrets
from collections.abc import Collection, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, User, UserRole, UserSession
from app.services import activity

# last_seen_at is written at most this often, so most requests only read their session.
TOUCH_INTERVAL = timedelta(minutes=1)
MAX_NEXT_PATH_LENGTH = 2000

# (display name, email) of the demo account for each role.
DEMO_ACCOUNTS: dict[UserRole, tuple[str, str]] = {
    "staff": ("Demo Staff", "staff@demo.local"),
    "member": ("Demo Member", "member@demo.local"),
}


class GoogleSignInRefused(Exception):
    """The Google account cannot sign in. The message is for the log, not for the browser."""


def now_utc() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


# Sessions


async def start_session(
    session: AsyncSession, user: User, *, lifetime: timedelta, now: datetime | None = None
) -> str:
    """Signs the user in: records the time and stores a new session, then commits. Returns the
    token for the cookie; only its hash is kept. The user's sessions past their absolute expiry
    are deleted on the way, so the table does not grow with every sign-in.
    """
    now = now or now_utc()
    token = secrets.token_urlsafe(32)
    await session.execute(
        delete(UserSession)
        .where(UserSession.user_id == user.id, UserSession.expires_at <= now)
        .execution_options(synchronize_session=False)
    )
    user.last_login_at = now
    session.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + lifetime,
        )
    )
    await session.commit()
    return token


async def user_for_token(
    session: AsyncSession, token: str, *, idle_timeout: timedelta, now: datetime | None = None
) -> User | None:
    """The signed-in user, or None when the session is unknown, revoked or expired."""
    now = now or now_utc()
    found = (
        await session.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_token(token), UserSession.revoked_at.is_(None))
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if found is None:
        return None
    user_session, user = found._tuple()
    idle = now - user_session.last_seen_at
    if now >= user_session.expires_at or idle >= idle_timeout:
        return None
    if idle >= TOUCH_INTERVAL:
        user_session.last_seen_at = now
        await session.commit()
    return user


async def revoke_session(session: AsyncSession, token: str, *, now: datetime | None = None) -> None:
    """Ends the session, if it is still active, and commits."""
    await session.execute(
        update(UserSession)
        .where(UserSession.token_hash == hash_token(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=now or now_utc())
        .execution_options(synchronize_session=False)
    )
    await session.commit()


def safe_next_path(raw: str | None) -> str:
    """Where to send the browser after sign-in: a path on this site, or "/".

    The value arrives in a link anyone can craft, so only a path starting with a single "/" is
    kept. "//host" and anything with a backslash would let a browser read it as another host.
    """
    if not raw or len(raw) > MAX_NEXT_PATH_LENGTH or not raw.startswith("/"):
        return "/"
    if raw.startswith("//") or "\\" in raw:
        return "/"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw):
        return "/"
    return raw


# Users


async def _user_by_email(session: AsyncSession, email: str) -> User | None:
    user: User | None = await session.scalar(
        select(User).where(func.lower(User.email) == email.lower())
    )
    return user


async def ensure_demo_user(
    session: AsyncSession, role: UserRole, *, member: Member | None = None
) -> User:
    """The demo account for the role, created and committed on first use.

    The member account signs in as `member` when one is given (the development seed passes one
    of its members, so the account has loans to show), otherwise as a member record of its own.
    """
    name, email = DEMO_ACCOUNTS[role]
    existing = await _user_by_email(session, email)
    if existing is not None:
        return existing

    try:
        user = User(email=email, display_name=name, role=role, is_demo=True)
        if role == "member":
            if member is None:
                member = Member(full_name=name, email=email)
                session.add(member)
                await session.flush()
                activity.record(
                    session,
                    via="system",
                    action="member.created",
                    entity_type="member",
                    entity_id=member.id,
                    summary=activity.member_created(name),
                    details={"email": email},
                )
            user.member_id = member.id
            user.display_name = member.full_name
        session.add(user)
        await session.commit()
    except IntegrityError:
        # A simultaneous first sign-in created the account; use that one.
        await session.rollback()
        existing = await _user_by_email(session, email)
        if existing is None:
            raise
        return existing
    return user


def _is_staff_email(email: str, staff_emails: Collection[str]) -> bool:
    return email.lower() in {address.lower() for address in staff_emails}


async def complete_google_login(
    session: AsyncSession, userinfo: Mapping[str, Any], *, staff_emails: Collection[str]
) -> User:
    """The user for a verified Google profile, created on first sign-in, and commits.

    The user is found by Google subject id, then by email address (linking the Google account).
    A new user is staff when the address is in staff_emails, otherwise a member: linked to the
    member record with that address when there is one, or to a new member record.
    """
    subject = userinfo.get("sub")
    email = userinfo.get("email")
    if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
        raise GoogleSignInRefused("the profile has no subject or email address")
    if userinfo.get("email_verified") is not True:
        raise GoogleSignInRefused("the email address is not verified")
    email = email.strip()

    user: User | None = await session.scalar(select(User).where(User.google_sub == subject))
    if user is None:
        user = await _user_by_email(session, email)
        if user is not None:
            if user.google_sub is not None:
                raise GoogleSignInRefused("the address belongs to a user of another Google account")
            user.google_sub = subject
    if user is None:
        name = userinfo.get("name")
        display_name = name.strip() if isinstance(name, str) and name.strip() else email
        if _is_staff_email(email, staff_emails):
            user = User(email=email, display_name=display_name, role="staff", google_sub=subject)
            session.add(user)
        else:
            user = await _new_member_user(session, email, display_name, subject)

    await session.commit()
    return user


async def _new_member_user(
    session: AsyncSession, email: str, display_name: str, subject: str
) -> User:
    member: Member | None = await session.scalar(
        select(Member).where(func.lower(Member.email) == email.lower())
    )
    is_new_member = member is None
    if member is None:
        member = Member(full_name=display_name, email=email)
        session.add(member)
        await session.flush()
    elif member.archived_at is not None:
        raise GoogleSignInRefused("the member record with this address is archived")
    elif await session.scalar(select(exists().where(User.member_id == member.id))):
        raise GoogleSignInRefused("the member record with this address has another user")

    user = User(
        email=email,
        display_name=member.full_name,
        role="member",
        member_id=member.id,
        google_sub=subject,
    )
    session.add(user)
    if is_new_member:
        await session.flush()
        activity.record(
            session,
            action="member.created",
            entity_type="member",
            entity_id=member.id,
            summary=activity.member_joined(member.full_name),
            details={"email": email},
            actor=user,
        )
    return user
