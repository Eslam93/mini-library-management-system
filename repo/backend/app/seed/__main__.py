"""python -m app.seed: fills an empty library with generated history and ensures the demo
sign-in accounts. --reset replaces the library's data first (not in production).
"""

import argparse
import asyncio
import time
from datetime import date

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import create_engine, create_session_factory
from app.seed.run import seed
from app.seed.simulation import DEFAULT_SEED, DEFAULT_YEARS, GeneratorOptions, years_before
from app.services.circulation import today_utc

log = get_logger(__name__)


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed",
        description=(
            "Generate a library from reader personas: real books, members and years of loans "
            "ending today. Without --reset it only fills a library that has no books or members."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the library's activity, loans, copies, books and members first "
        "(users and sessions stay; refused in production)",
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help=f"random seed (default {DEFAULT_SEED})"
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="the history ends before this day, YYYY-MM-DD (default: today in UTC)",
    )
    parser.add_argument(
        "--years",
        type=_positive,
        default=DEFAULT_YEARS,
        help=f"years of history (default {DEFAULT_YEARS})",
    )
    return parser.parse_args(argv)


async def _main(args: argparse.Namespace) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if args.reset and settings.is_production:
        raise SystemExit("--reset deletes the library's data and is refused in production.")

    today = args.today or today_utc()
    options = GeneratorOptions(
        today=today,
        start=years_before(today, args.years),
        seed=args.seed,
        loan_period_days=settings.loan_period_days,
    )
    started = time.perf_counter()
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            summary = await seed(session, options, reset=args.reset)
    finally:
        await engine.dispose()

    if summary is None:
        log.info(
            "seed_skipped",
            reason="the library already has books or members; --reset replaces them",
        )
        return
    log.info(
        "seed_done",
        titles=summary.titles,
        copies=summary.copies,
        members=summary.members,
        loans=summary.loans,
        active=summary.active,
        overdue=summary.overdue,
        isbns=summary.isbns,
        demo_member=summary.demo_member,
        seconds=round(time.perf_counter() - started, 1),
    )


if __name__ == "__main__":
    asyncio.run(_main(_parse_args(None)))
