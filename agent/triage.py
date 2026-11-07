"""Triage manuel des signalements."""

import argparse

from agent.catalog import Catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_id")
    parser.add_argument("decision", choices=["confirmed", "dismissed"])
    args = parser.parse_args()
    Catalog().triage(args.ticket_id, args.decision == "confirmed")


if __name__ == "__main__":
    main()
