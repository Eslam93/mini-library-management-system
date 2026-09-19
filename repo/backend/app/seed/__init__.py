"""The demo library: a persona-driven generator of catalog, members and years of loans, plus the
demo sign-in accounts.

Run with: python -m app.seed [--reset] [--seed N] [--today YYYY-MM-DD] [--years N]

Modules: catalog (the curated books), personas (reader habits), people (fictional names),
opening (hours and the staff rota), simulation (the day-by-day history, no database) and run
(storing it and the demo accounts).
"""

from app.seed.run import SeedSummary, ensure_demo_accounts, seed
from app.seed.simulation import GeneratorOptions

__all__ = ["GeneratorOptions", "SeedSummary", "ensure_demo_accounts", "seed"]
