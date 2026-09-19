"""Years of library life, simulated day by day from reader personas.

The first catalog is shelved in the first week. Titles published during the years arrive in
their year, and a few older ones are bought along the way; nobody borrows a title before it
arrives. Members join over the whole period, most in the founding weeks and at the start of the
academic year, each drawn from a persona that decides what they read, how often, in which months
and hours, and how punctually they bring books back; some stop coming.

On each opening day the members who visit are served in time order. A member borrows only a copy
that is on the shelf and picks another title when every copy of the first choice is out. A loan
is due after the loan period. A return that would fall on or after the end date has not happened
yet, so that loan is still open, and some open loans are overdue.

The history ends before `today` starts (UTC), so no timestamp lies in the future and the same
seed and date always give the same library. Nothing is written here: the result is plain records
that app.seed.run stores.
"""

import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.seed import opening
from app.seed.catalog import CatalogEntry, load_catalog, pick_titles
from app.seed.opening import ONE_DAY
from app.seed.people import Person, load_names, make_people
from app.seed.personas import PERSONAS, PERSONAS_BY_KEY, Persona
from app.seed.sampling import clamp, new_id, pick, split_count, stream
from app.services.circulation import due_at_for

DEFAULT_SEED = 1
DEFAULT_YEARS = 3
DEFAULT_MEMBERS = 200
DEFAULT_LOAN_PERIOD_DAYS = 14

# The member the demo member account signs in as: a book-club member since the first week, with
# two books out at the end, one of them overdue.
DEMO_MEMBER = Person(full_name="Maya Hassan", email="maya.hassan@example.com")
DEMO_PERSONA = "book_club_member"
DEMO_OVERDUE_DAYS = 4

# Opening days spent shelving the first catalog before members can join.
SHELVING_DAYS = 5
# Share of older titles bought during the years instead of shelved at the start.
LATER_PURCHASE_SHARE = 0.06
# Demand for a title falls with its position in its category.
POPULARITY_SKEW = 0.9
# A new arrival is in demand for a while: extra weight that fades over about this many days.
NOVELTY_BOOST = 1.5
NOVELTY_DAYS = 120.0
# Titles published in the last few years are a little more popular.
RECENT_YEARS = 4
RECENT_BOOST = 1.3
# Popular titles get more copies; others sometimes get one more.
EXTRA_COPY_SHARE = 0.35

# More members join each year than the year before.
YEARLY_GROWTH = 0.15
# The founding weeks bring a rush of new members that fades over about this many days.
OPENING_RUSH = 8.0
OPENING_RUSH_DAYS = 30.0
BORROWS_ON_JOINING = 0.7

OPEN_DAYS_PER_YEAR = 310
AVERAGE_OPEN_DAYS_PER_MONTH = OPEN_DAYS_PER_YEAR / 12
EARLY_MONTH_DAYS = 10
# Share of visits outside the member's usual hours.
ANY_TIME_SHARE = 0.25
MAX_ACTIVE_LOANS = 6
# Titles tried before a member leaves without a book.
CHOICE_ATTEMPTS = 6
# A few loans come back weeks late.
VERY_LATE_SHARE = 0.004
VERY_LATE_DAYS = (25, 120)


@dataclass(frozen=True)
class GeneratorOptions:
    # The history ends before this day starts (UTC).
    today: date
    start: date
    seed: int = DEFAULT_SEED
    # How many catalog titles to use (each category's most borrowed first); None uses them all.
    titles: int | None = None
    members: int = DEFAULT_MEMBERS
    loan_period_days: int = DEFAULT_LOAN_PERIOD_DAYS

    def __post_init__(self) -> None:
        if self.start >= self.today or self.members < 1 or self.loan_period_days < 1:
            raise ValueError("The history needs a start before today, a member and a loan period.")
        if self.titles is not None and self.titles < 1:
            raise ValueError("The library needs at least one title.")


def years_before(day: date, years: int) -> date:
    """The same date the given number of years earlier; 29 February becomes the 28th."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


@dataclass(frozen=True)
class BookRecord:
    id: uuid.UUID
    entry: CatalogEntry
    added_at: datetime
    added_by: str
    copy_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class MemberRecord:
    id: uuid.UUID
    full_name: str
    email: str | None
    persona: str
    joined_at: datetime
    added_by: str


@dataclass(frozen=True)
class LoanRecord:
    id: uuid.UUID
    book: BookRecord
    copy_id: uuid.UUID
    member: MemberRecord
    borrowed_at: datetime
    borrowed_by: str
    due_at: datetime
    returned_at: datetime | None
    returned_by: str | None


@dataclass(frozen=True)
class History:
    today: date
    # Each in the order it happened.
    books: list[BookRecord]
    members: list[MemberRecord]
    loans: list[LoanRecord]
    demo_member: MemberRecord
    isbns_kept: int
    isbns_dropped: int


def simulate(options: GeneratorOptions) -> History:
    return _Simulation(options).run()


@dataclass
class _Title:
    book: BookRecord
    # The first day it can be borrowed: the day after it arrives.
    shelved_from: date
    weight: float
    arrived_later: bool
    # Per copy, the first day it is on the shelf again; None when it is not back before the end.
    free_from: list[date | None]

    def demand(self, day: date) -> float:
        if not self.arrived_later:
            return self.weight
        age = (day - self.shelved_from).days
        return self.weight * (1 + NOVELTY_BOOST * math.exp(-age / NOVELTY_DAYS))


@dataclass
class _Reader:
    member: MemberRecord
    persona: Persona
    joined: date
    # No visits from this day on; None for a member who keeps coming.
    stops: date | None
    # Personal multiplier on the persona's borrowing rate.
    activity: float
    on_time: float
    # For each book borrowed, the day the last loan of it comes back; None when it stays out.
    borrowed: dict[uuid.UUID, date | None] = field(default_factory=dict)
    # The return day of each loan that may still be out; None for one kept past the end.
    back_on: list[date | None] = field(default_factory=list)

    def loans_out(self, day: date) -> int:
        self.back_on = [back for back in self.back_on if back is None or back > day]
        return len(self.back_on)

    def would_pick(self, book_id: uuid.UUID, day: date, *, rereading: bool) -> bool:
        """A book not borrowed before, or, when in the mood to reread, one already brought back."""
        if book_id not in self.borrowed:
            return True
        back = self.borrowed[book_id]
        return rereading and back is not None and back < day


@dataclass(frozen=True)
class _Rhythm:
    """A persona's visits as a chance per opening day, normalized so that the monthly, weekly and
    early-month shapes keep the persona's average rate.
    """

    per_day: float
    months: tuple[float, ...]
    weekday: float
    saturday: float
    early_month: float
    rest_of_month: float

    @classmethod
    def of(cls, persona: Persona) -> "_Rhythm":
        basket = persona.basket
        books_per_visit = sum((size + 1) * weight for size, weight in enumerate(basket)) / sum(
            basket
        )
        month_mean = sum(persona.months) / 12
        week_mean = (5 + persona.saturday) / 6
        early_share = EARLY_MONTH_DAYS / 30.4
        part_mean = early_share * persona.early_month + 1 - early_share
        return cls(
            per_day=persona.loans_per_month / books_per_visit / AVERAGE_OPEN_DAYS_PER_MONTH,
            months=tuple(value / month_mean for value in persona.months),
            weekday=1 / week_mean,
            saturday=persona.saturday / week_mean,
            early_month=persona.early_month / part_mean,
            rest_of_month=1 / part_mean,
        )

    def chance(self, day: date) -> float:
        week = self.saturday if day.weekday() == opening.SATURDAY else self.weekday
        part = self.early_month if day.day <= EARLY_MONTH_DAYS else self.rest_of_month
        return self.per_day * self.months[day.month - 1] * week * part


class _Simulation:
    def __init__(self, options: GeneratorOptions) -> None:
        self.options = options
        self.last_day = options.today - ONE_DAY
        self.days = opening.open_days(options.start, self.last_day)
        if len(self.days) <= SHELVING_DAYS + 1:
            raise ValueError("The history must span more than a week of opening days.")
        self.shelving_days = self.days[:SHELVING_DAYS]
        self.first_member_day = self.days[SHELVING_DAYS]
        self.names = load_names()
        self.ids = stream(options.seed, "ids")
        self.shelves: dict[str, list[_Title]] = {}
        self.loans: list[LoanRecord] = []

    def run(self) -> History:
        catalog = load_catalog()
        titles = self._shelve(catalog.entries)
        readers = self._members()
        self._circulate(readers)
        books = sorted((title.book for title in titles), key=lambda book: book.added_at)
        return History(
            today=self.options.today,
            books=books,
            members=sorted((reader.member for reader in readers), key=lambda m: m.joined_at),
            loans=sorted(self.loans, key=lambda loan: loan.borrowed_at),
            demo_member=readers[0].member,
            isbns_kept=sum(1 for book in books if book.entry.isbn is not None),
            isbns_dropped=catalog.isbns_dropped,
        )

    def _staff(self, moment: datetime) -> str:
        return opening.staff_on_duty(moment, self.names.staff)

    # The catalog

    def _shelve(self, entries: list[CatalogEntry]) -> list[_Title]:
        rng = stream(self.options.seed, "catalog")
        published = [
            entry
            for entry in entries
            if entry.published_year is None or entry.published_year <= self.options.today.year
        ]
        titles: list[_Title] = []
        for entry in pick_titles(published, self.options.titles):
            arrival = self._arrival(rng, entry)
            if arrival is None:
                continue
            shelf = self.shelves.setdefault(entry.category, [])
            rank = len(shelf)
            arrived_later = arrival > self.shelving_days[-1]
            copies = 3 if rank < 2 else 2 if rank < 6 else 1
            if copies < 3 and rng.random() < EXTRA_COPY_SHARE:
                copies += 1
            if arrived_later and rank < 6:
                copies = max(copies, 2)
            weight = rng.lognormvariate(0, 0.25) / (rank + 1) ** POPULARITY_SKEW
            year = entry.published_year
            if year is not None and year >= self.options.today.year - RECENT_YEARS:
                weight *= RECENT_BOOST

            added_at = opening.moment_on(rng, arrival)
            book = BookRecord(
                id=new_id(self.ids),
                entry=entry,
                added_at=added_at,
                added_by=self._staff(added_at),
                copy_ids=tuple(new_id(self.ids) for _ in range(copies)),
            )
            title = _Title(
                book=book,
                shelved_from=arrival + ONE_DAY,
                weight=weight,
                arrived_later=arrived_later,
                free_from=[arrival + ONE_DAY] * copies,
            )
            shelf.append(title)
            titles.append(title)
        return titles

    def _arrival(self, rng: random.Random, entry: CatalogEntry) -> date | None:
        """The day the title is added: in the first week, or later for a title published during
        the history and for a few bought along the way. None when it has not arrived yet.
        """
        start, year = self.options.start, entry.published_year
        first_week = rng.choice(self.shelving_days)
        if year is not None and year >= start.year:
            already_out = (start - date(start.year, 1, 1)).days / 365
            if year == start.year and rng.random() < already_out:
                return first_week
            return self._day_between(
                rng,
                max(date(year, 1, 1), self.first_member_day),
                min(date(year, 12, 31), self.last_day),
            )
        if rng.random() < LATER_PURCHASE_SHARE:
            return self._day_between(rng, self.first_member_day, self.last_day)
        return first_week

    def _day_between(self, rng: random.Random, first: date, last: date) -> date | None:
        """A random opening day from first to last, or None when there is none."""
        if first > last:
            return None
        day = opening.next_open_day(first + timedelta(days=rng.randint(0, (last - first).days)))
        if day > last:
            day = opening.previous_open_day(last)
        return day if day >= first else None

    # Members

    def _members(self) -> list[_Reader]:
        """The demo member first, then the others in the order they join."""
        rng = stream(self.options.seed, "members")
        member_days = [day for day in self.days if day >= self.first_member_day]
        # About a year of opening days each.
        span_days = [
            member_days[i : i + OPEN_DAYS_PER_YEAR]
            for i in range(0, len(member_days), OPEN_DAYS_PER_YEAR)
        ]
        per_span = split_count(
            self.options.members - 1,
            [len(days) * (1 + YEARLY_GROWTH * i) for i, days in enumerate(span_days)],
        )
        history_days = max(1, (self.last_day - self.first_member_day).days)
        plans: list[tuple[date, Persona]] = []
        for days, count in zip(span_days, per_span, strict=True):
            progress = (days[len(days) // 2] - self.first_member_day).days / history_days
            shares = [
                low + (high - low) * progress
                for low, high in (persona.join_share for persona in PERSONAS)
            ]
            for persona, joining in zip(PERSONAS, split_count(count, shares), strict=True):
                weights = [
                    self._join_weight(day) * persona.join_months[day.month - 1] for day in days
                ]
                plans.extend((day, persona) for day in rng.choices(days, weights, k=joining))
        plans.sort(key=lambda plan: plan[0])

        taken = {DEMO_MEMBER.full_name, str(DEMO_MEMBER.email)}
        people = make_people(rng, self.names, len(plans), taken=taken)
        demo = self._reader(rng, self.first_member_day, PERSONAS_BY_KEY[DEMO_PERSONA], DEMO_MEMBER)
        demo.activity, demo.on_time, demo.stops = 1.6, 0.95, None
        return [demo] + [
            self._reader(rng, day, persona, person)
            for (day, persona), person in zip(plans, people, strict=True)
        ]

    def _join_weight(self, day: date) -> float:
        days_open = (day - self.first_member_day).days
        return 1 + OPENING_RUSH * math.exp(-days_open / OPENING_RUSH_DAYS)

    def _reader(self, rng: random.Random, day: date, persona: Persona, person: Person) -> _Reader:
        joined_at = opening.moment_on(rng, day, persona.hours)
        member = MemberRecord(
            id=new_id(self.ids),
            full_name=person.full_name,
            email=person.email,
            persona=persona.key,
            joined_at=joined_at,
            added_by=self._staff(joined_at),
        )
        # Months until the member stops coming: the first month the churn chance comes up.
        months = math.floor(math.log(1 - rng.random()) / math.log(1 - persona.churn))
        stops = day + timedelta(days=round(max(1, months) * 30.4))
        return _Reader(
            member=member,
            persona=persona,
            joined=day,
            stops=None if stops >= self.options.today else stops,
            activity=clamp(rng.lognormvariate(-0.08, 0.4), 0.3, 3.0),
            on_time=clamp(persona.on_time + rng.gauss(0, 0.06), 0.3, 0.99),
        )

    # Borrowing and returning

    def _circulate(self, readers: list[_Reader]) -> None:
        rng = stream(self.options.seed, "visits")
        rhythms = {persona.key: _Rhythm.of(persona) for persona in PERSONAS}
        demo = readers[0]
        demo_days = self._demo_days(demo)
        for day in self.days:
            if day < self.first_member_day:
                continue
            # (when, reader's position, reader, keeps the book past the end)
            visits: list[tuple[datetime, int, _Reader, bool]] = []
            for position, reader in enumerate(readers):
                if day < reader.joined or (reader.stops is not None and day >= reader.stops):
                    continue
                if day == reader.joined:
                    if rng.random() < BORROWS_ON_JOINING:
                        moment = reader.member.joined_at + timedelta(minutes=rng.randint(3, 12))
                        visits.append((moment, position, reader, False))
                    continue
                if rng.random() < rhythms[reader.persona.key].chance(day) * reader.activity:
                    hours = None if rng.random() < ANY_TIME_SHARE else reader.persona.hours
                    visits.append((opening.moment_on(rng, day, hours), position, reader, False))
            if day in demo_days:
                visits.append((opening.moment_on(rng, day, demo.persona.hours), 0, demo, True))

            visits.sort(key=lambda visit: (visit[0], visit[1]))
            for moment, _, reader, keeps in visits:
                basket = reader.persona.basket
                books = 1 if keeps else rng.choices(range(1, len(basket) + 1), basket)[0]
                for n in range(books):
                    at = moment + timedelta(seconds=50 * n + rng.randint(0, 20))
                    self._borrow(rng, reader, day, at, keeps=keeps)

    def _demo_days(self, demo: _Reader) -> set[date]:
        """The days the demo member borrows the two books she still has at the end: one now
        overdue, one due in about ten days.
        """
        period = timedelta(days=self.options.loan_period_days)
        today = self.options.today
        overdue = opening.previous_open_day(today - period - timedelta(days=DEMO_OVERDUE_DAYS))
        current = opening.previous_open_day(today - timedelta(days=3))
        return {day for day in (overdue, current) if day > demo.joined}

    def _borrow(
        self, rng: random.Random, reader: _Reader, day: date, moment: datetime, *, keeps: bool
    ) -> None:
        if not keeps and reader.loans_out(day) >= MAX_ACTIVE_LOANS:
            return
        found = self._choose(rng, reader, day, attempts=CHOICE_ATTEMPTS * (5 if keeps else 1))
        if found is None:
            return
        title, copy_index = found
        due_at = due_at_for(None, today=day, loan_period_days=self.options.loan_period_days)
        back = None if keeps else self._return_day(rng, reader, day, due_at.date())
        if back is not None and back >= self.options.today:
            back = None
        title.free_from[copy_index] = None if back is None else back + ONE_DAY
        reader.borrowed[title.book.id] = back
        reader.back_on.append(back)

        returned_at = None if back is None else opening.moment_on(rng, back, reader.persona.hours)
        self.loans.append(
            LoanRecord(
                id=new_id(self.ids),
                book=title.book,
                copy_id=title.book.copy_ids[copy_index],
                member=reader.member,
                borrowed_at=moment,
                borrowed_by=self._staff(moment),
                due_at=due_at,
                returned_at=returned_at,
                returned_by=None if returned_at is None else self._staff(returned_at),
            )
        )

    def _choose(
        self, rng: random.Random, reader: _Reader, day: date, *, attempts: int
    ) -> tuple[_Title, int] | None:
        """A title the member would pick and the copy of it on the shelf. When every copy of the
        chosen title is out, the member tries another title.
        """
        interests = {
            category: weight
            for category, weight in reader.persona.categories.items()
            if category in self.shelves
        } or {category: 1.0 for category in self.shelves}
        for _ in range(attempts):
            category = pick(rng, interests)
            rereading = rng.random() < reader.persona.rereads
            candidates = [
                title
                for title in self.shelves[category]
                if title.shelved_from <= day
                and reader.would_pick(title.book.id, day, rereading=rereading)
            ]
            if not candidates:
                continue
            title = rng.choices(candidates, [title.demand(day) for title in candidates])[0]
            for index, free_from in enumerate(title.free_from):
                if free_from is not None and free_from <= day:
                    return title, index
        return None

    def _return_day(self, rng: random.Random, reader: _Reader, day: date, due: date) -> date:
        """When the member brings the book back, by the persona's habits: usually on time after
        reading it, sometimes some days late, rarely weeks late.
        """
        if rng.random() < VERY_LATE_SHARE:
            late = rng.randint(*VERY_LATE_DAYS)
        elif rng.random() < reader.on_time:
            kept = int(clamp(round(rng.gauss(reader.persona.keeps_days, 3)), 1, (due - day).days))
            back = opening.previous_open_day(day + timedelta(days=kept))
            return back if back > day else opening.next_open_day(day + ONE_DAY)
        else:
            late = 1 + int(rng.expovariate(1 / reader.persona.late_days))
        return opening.next_open_day(due + timedelta(days=late))
