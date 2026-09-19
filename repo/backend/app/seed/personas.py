"""The reader personas the generated members are drawn from.

A persona is a habit, not a person: what its readers like, how often they borrow and in which
months, when in the day they come in, how long they keep a book and how punctual they are, how
likely they are to stop coming, and what share of new members it accounts for at the start and at
the end of the history (the share in between follows a straight line). Each member also gets a
personal activity level and punctuality around the persona's, so no two readers are the same.
"""

from collections.abc import Mapping
from dataclasses import dataclass

# Months run January to December.
Months = tuple[float, float, float, float, float, float, float, float, float, float, float, float]


@dataclass(frozen=True)
class Persona:
    key: str
    label: str
    # Relative interest in each category.
    categories: Mapping[str, float]
    # Loans a month, on average across the year.
    loans_per_month: float
    # Relative chance of taking 1, 2, 3, ... books on one visit.
    basket: tuple[float, ...]
    # Relative borrowing in each month; only the shape matters.
    months: Months
    # A Saturday visit is this many times as likely as one on a weekday.
    saturday: float
    # Preferred visiting hours (UTC), when the library is open then.
    hours: tuple[int, int]
    # Visits in the first ten days of a month are this many times as likely as later ones.
    early_month: float
    # Days a book is usually kept, when it comes back on time.
    keeps_days: float
    # Share of loans returned by the due date.
    on_time: float
    # Average days late, when late.
    late_days: float
    # Chance each month that a member stops borrowing.
    churn: float
    # Chance that a pick may be a book the member borrowed before.
    rereads: float
    # Share of new members (start of the history, end of it).
    join_share: tuple[float, float]
    # Relative chance of joining in each month.
    join_months: Months = (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)


PERSONAS: tuple[Persona, ...] = (
    Persona(
        key="student",
        label="University student",
        categories={
            "Technology": 14,
            "Science": 14,
            "Philosophy": 12,
            "Classics": 12,
            "History": 10,
            "Fiction": 10,
            "Science Fiction": 10,
            "Fantasy": 8,
            "Business": 6,
            "Young Adult": 4,
        },
        loans_per_month=2.0,
        basket=(55, 30, 15),
        # Term time; quiet in the summer and over the winter break.
        months=(1.1, 1.25, 1.3, 1.3, 0.9, 0.45, 0.35, 0.4, 1.2, 1.4, 1.4, 0.7),
        saturday=0.8,
        hours=(11, 19),
        early_month=1.0,
        keeps_days=12,
        on_time=0.62,
        late_days=6,
        churn=0.035,
        rereads=0.03,
        join_share=(0.22, 0.20),
        join_months=(1.8, 1.1, 0.6, 0.5, 0.4, 0.3, 0.3, 0.6, 3.0, 2.0, 0.8, 0.4),
    ),
    Persona(
        key="software_professional",
        label="Software professional",
        categories={
            "Technology": 42,
            "Science Fiction": 20,
            "Business": 16,
            "Science": 8,
            "Self-Help": 8,
            "Fantasy": 6,
        },
        loans_per_month=1.3,
        basket=(75, 25),
        months=(1.15, 1.05, 1.0, 1.0, 1.0, 0.95, 0.8, 0.8, 1.05, 1.05, 1.05, 0.75),
        saturday=2.6,
        hours=(17, 19),
        early_month=1.0,
        keeps_days=12,
        on_time=0.8,
        late_days=4,
        churn=0.02,
        rereads=0.03,
        join_share=(0.08, 0.26),
    ),
    Persona(
        key="retiree",
        label="Retiree",
        categories={
            "Mystery & Thriller": 24,
            "History": 20,
            "Biography": 18,
            "Fiction": 16,
            "Classics": 14,
            "Science": 5,
            "Philosophy": 3,
        },
        loans_per_month=3.2,
        basket=(45, 35, 20),
        # More reading in the winter, travelling in the summer.
        months=(1.2, 1.2, 1.05, 1.0, 0.95, 0.85, 0.75, 0.8, 1.0, 1.05, 1.15, 1.0),
        saturday=0.5,
        hours=(9, 13),
        early_month=1.0,
        keeps_days=10,
        on_time=0.94,
        late_days=3,
        churn=0.01,
        rereads=0.05,
        join_share=(0.16, 0.12),
    ),
    Persona(
        key="parent",
        label="Parent",
        categories={
            "Children": 50,
            "Young Adult": 15,
            "Fiction": 12,
            "Self-Help": 8,
            "Mystery & Thriller": 8,
            "Biography": 7,
        },
        loans_per_month=3.0,
        basket=(30, 30, 25, 15),
        # School holidays: the summer and December.
        months=(0.9, 0.85, 0.9, 1.0, 0.9, 1.1, 1.5, 1.45, 0.85, 0.9, 0.9, 1.25),
        saturday=2.2,
        hours=(15, 19),
        early_month=1.0,
        keeps_days=8,
        on_time=0.82,
        late_days=5,
        churn=0.02,
        rereads=0.35,
        join_share=(0.18, 0.15),
    ),
    Persona(
        key="casual_reader",
        label="Casual reader",
        categories={
            "Fiction": 28,
            "Mystery & Thriller": 24,
            "Self-Help": 14,
            "Biography": 10,
            "Fantasy": 8,
            "Science Fiction": 6,
            "History": 5,
            "Business": 5,
        },
        loans_per_month=0.7,
        basket=(85, 15),
        months=(1.0, 0.95, 0.95, 0.95, 1.0, 1.05, 1.2, 1.25, 0.9, 0.9, 0.95, 1.15),
        saturday=1.6,
        hours=(10, 19),
        early_month=1.0,
        keeps_days=12,
        on_time=0.7,
        late_days=9,
        churn=0.045,
        rereads=0.03,
        join_share=(0.20, 0.16),
    ),
    Persona(
        key="book_club_member",
        label="Book-club member",
        categories={
            "Fiction": 44,
            "Classics": 20,
            "Mystery & Thriller": 10,
            "Biography": 10,
            "History": 8,
            "Fantasy": 5,
            "Philosophy": 3,
        },
        loans_per_month=1.7,
        basket=(80, 20),
        months=(1.1, 1.05, 1.05, 1.05, 1.05, 0.9, 0.7, 0.75, 1.05, 1.05, 1.05, 0.85),
        saturday=1.2,
        hours=(10, 18),
        # The club picks its books at the start of the month.
        early_month=2.4,
        keeps_days=13,
        on_time=0.86,
        late_days=4,
        churn=0.018,
        rereads=0.03,
        join_share=(0.08, 0.06),
    ),
    Persona(
        key="teen_reader",
        label="Teen reader",
        categories={
            "Young Adult": 48,
            "Fantasy": 22,
            "Science Fiction": 10,
            "Classics": 8,
            "Mystery & Thriller": 7,
            "Children": 5,
        },
        loans_per_month=1.6,
        basket=(60, 30, 10),
        months=(0.95, 0.95, 0.95, 0.95, 0.95, 1.3, 1.45, 1.35, 0.8, 0.85, 0.85, 1.2),
        saturday=2.0,
        hours=(15, 19),
        early_month=1.0,
        keeps_days=9,
        on_time=0.72,
        late_days=6,
        churn=0.03,
        rereads=0.1,
        join_share=(0.08, 0.05),
    ),
)

PERSONAS_BY_KEY = {persona.key: persona for persona in PERSONAS}
