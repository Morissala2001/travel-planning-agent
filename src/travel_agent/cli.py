"""Command line: `travel-agent cities | plan | book | benchmark`."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .booking import book
from .data import DEFAULT_BROCHURES, DEFAULT_DB, cities, connect, date_range, load_brochures
from .i18n import DEFAULT_LANGUAGE, LANGUAGES, city_key, city_name, detect_language
from .planner import Request, TravelAgent
from .render import attempt_line, booking_text, summary
from .tools import HotelSearch, load_encoder


def _agent(args, conn) -> TravelAgent:
    print("Loading the sentence encoder ...", file=sys.stderr)
    return TravelAgent(conn, HotelSearch(load_brochures(args.brochures), load_encoder()),
                       restore_activities=not args.no_restore)


def _request(args) -> Request:
    city = city_key(args.city)
    if city is None:
        sys.exit(f"Unknown city: {args.city}. Run `travel-agent cities` to see them.")
    return Request(city, date.fromisoformat(args.date).isoformat(), args.nights, args.travellers, args.budget, args.wish)


def _language(args) -> str:
    return args.lang if args.lang != "auto" else detect_language(args.wish) or DEFAULT_LANGUAGE


def cmd_cities(args) -> None:
    conn = connect(args.db)
    first, last = date_range(conn)
    for key in cities(conn):
        print(f"{key:10s} {city_name(key, 'en'):10s} {city_name(key, 'ru')}")
    print(f"\nFlights from {first} to {last}.")


def cmd_plan(args) -> None:
    conn = connect(args.db)
    plan = _agent(args, conn).plan(_request(args))
    lang = _language(args)
    if args.verbose:
        for attempt in plan.attempts:
            print(attempt_line(attempt, lang))
        print()
    print(summary(plan, lang))


def cmd_book(args) -> None:
    conn = connect(args.db)
    plan = _agent(args, conn).plan(_request(args))
    lang = _language(args)
    print(summary(plan, lang), end="\n\n")
    print(booking_text(book(conn, plan.trip, args.name, confirm=args.yes), lang))


def cmd_benchmark(args) -> None:
    from .benchmark import run

    run(connect(args.db), load_brochures(args.brochures), load_encoder())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="travel-agent", description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database of flights, activities and bookings")
    parser.add_argument("--brochures", default=DEFAULT_BROCHURES, help="folder of hotel brochures (PDF)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("cities", help="list the destinations and the dates covered").set_defaults(func=cmd_cities)

    for name, func, text in (("plan", cmd_plan, "compose a trip"), ("book", cmd_book, "compose a trip and book it")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--city", required=True, help="destination, in English, French or Russian")
        p.add_argument("--date", required=True, help="departure day, YYYY-MM-DD")
        p.add_argument("--nights", type=int, default=4)
        p.add_argument("--travellers", type=int, default=2)
        p.add_argument("--budget", type=float, required=True, help="per person, everything included, in euros")
        p.add_argument("--wish", required=True, help="what you are looking for, in your own words")
        p.add_argument("--lang", choices=["auto", *LANGUAGES], default="auto",
                       help="language of the answer (auto: the language of --wish)")
        p.add_argument("--no-restore", action="store_true",
                       help="do not put activities back after stepping down to a cheaper hotel (original behaviour)")
        p.add_argument("-v", "--verbose", action="store_true", help="print every combination the agent priced")
        p.set_defaults(func=func)
        if name == "book":
            p.add_argument("--name", required=True, help="name for the booking")
            p.add_argument("--yes", action="store_true", help="confirm: without it, nothing is written")

    sub.add_parser("benchmark", help="measure the agent on a grid of requests").set_defaults(func=cmd_benchmark)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
