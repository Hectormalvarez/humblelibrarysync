"""CLI entrypoint unifying capture, parse, duplicate, and view subcommands."""

import argparse
from pathlib import Path

from capture import capture_library
from library_duplicates import find_duplicates, format_duplicate_report, load_library
from parse import export_to_csv, export_to_json, export_to_txt, parse_dump


def run_capture(args: argparse.Namespace) -> None:
    """Executes the capture pipeline to log raw network responses."""
    capture_library(
        dump_file=args.dump,
        auth_file=args.auth,
        headless=args.headless,
    )


def run_parse(args: argparse.Namespace) -> None:
    """Executes the parser engine and exports structured catalog formats."""
    catalog = parse_dump(args.dump)
    export_to_json(catalog, args.json_out)
    export_to_csv(catalog, args.csv_out)
    export_to_txt(catalog, args.txt_out)
    print(f"[*] Parsed {catalog['metadata']['total_items']} items into JSON, CSV, and TXT.")


def run_duplicates(args: argparse.Namespace) -> None:
    """Executes duplicate detection and prints the formatted summary."""
    items, _ = load_library(args.input)
    duplicates = find_duplicates(items)
    report = format_duplicate_report(
        duplicates=duplicates,
        total_items=len(items),
        source_file=str(args.input),
    )
    print(report)


def run_view(args: argparse.Namespace) -> None:
    """Placeholder handler for interactive library viewing."""
    print("[*] Interactive viewer module under construction...")


def build_parser() -> argparse.ArgumentParser:
    """Constructs and configures the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="humble-sync",
        description="Capture, parse, analyze, and browse your Humble Bundle library.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Capture subcommand
    cap_parser = subparsers.add_parser("capture", help="Intercept raw API data from Humble Bundle.")
    cap_parser.add_argument("--dump", type=Path, default=Path("raw_library_dump.json"), help="Output JSONL dump path.")
    cap_parser.add_argument("--auth", type=Path, default=Path("auth.json"), help="Saved auth state path.")
    cap_parser.add_argument("--headless", action="store_true", help="Run browser without GUI.")
    cap_parser.set_defaults(func=run_capture)

    # Parse subcommand
    parse_parser = subparsers.add_parser("parse", help="Parse raw dump into structured catalog files.")
    parse_parser.add_argument("--dump", type=Path, default=Path("raw_library_dump.json"), help="Input dump path.")
    parse_parser.add_argument("--json-out", type=Path, default=Path("my_library.json"), help="Output JSON path.")
    parse_parser.add_argument("--csv-out", type=Path, default=Path("my_library.csv"), help="Output CSV path.")
    parse_parser.add_argument("--txt-out", type=Path, default=Path("my_library.txt"), help="Output TXT path.")
    parse_parser.set_defaults(func=run_parse)

    # Duplicates subcommand
    dup_parser = subparsers.add_parser("duplicates", help="Check catalog for duplicate titles across bundles.")
    dup_parser.add_argument("--input", type=Path, default=Path("my_library.json"), help="Catalog JSON path.")
    dup_parser.set_defaults(func=run_duplicates)

    # View subcommand
    view_parser = subparsers.add_parser("view", help="Interactively browse and search cataloged items.")
    view_parser.set_defaults(func=run_view)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()