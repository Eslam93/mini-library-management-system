"""Fictional people: member names and addresses, and the staff at the desk.

Names are drawn from data/names.json, first and last names from many languages mixed freely, as
in any city library. Every address is at example.com, which never delivers mail.
"""

import json
import random
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

NAMES_FILE = Path(__file__).parent / "data" / "names.json"
EMAIL_DOMAIN = "example.com"
# Some members never gave an address.
NO_EMAIL_SHARE = 0.04

_NOT_IN_ADDRESS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Names:
    first: list[str]
    last: list[str]
    staff: list[str]


@dataclass(frozen=True)
class Person:
    full_name: str
    email: str | None


def load_names(path: Path = NAMES_FILE) -> Names:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Names(first=data["first_names"], last=data["last_names"], staff=data["staff"])


def _address_part(name: str) -> str:
    """Lower-case ASCII letters and digits: "Lucía" -> "lucia", "O'Brien" -> "obrien"."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return _NOT_IN_ADDRESS.sub("", plain.lower())


def _address(rng: random.Random, first: str, last: str) -> str:
    given, family = _address_part(first), _address_part(last)
    local = rng.choices(
        [
            f"{given}.{family}",
            f"{given}{family}",
            f"{given[0]}.{family}",
            f"{given}_{family}",
            f"{given}.{family}{rng.randint(1, 99)}",
        ],
        weights=[55, 15, 15, 5, 10],
    )[0]
    return f"{local}@{EMAIL_DOMAIN}"


def make_people(rng: random.Random, names: Names, count: int, *, taken: set[str]) -> list[Person]:
    """count people with different names and addresses. taken holds full names and lower-case
    addresses already in use; the new ones are added to it.
    """
    people: list[Person] = []
    while len(people) < count:
        first, last = rng.choice(names.first), rng.choice(names.last)
        full_name = f"{first} {last}"
        if full_name in taken:
            continue
        taken.add(full_name)
        email = None
        if rng.random() >= NO_EMAIL_SHARE:
            email = _address(rng, first, last)
            while email in taken:
                local, domain = email.split("@")
                email = f"{local}{rng.randint(1, 9)}@{domain}"
            taken.add(email)
        people.append(Person(full_name=full_name, email=email))
    return people
