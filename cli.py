"""CLI entrypoint for Humble Library Sync featuring an interactive menu loop."""

import argparse
import os
import sys
from pathlib import Path
import questionary

from capture import capture_library
from library_duplicates import find_duplicates, format_duplicate_report, load_library
from parse import export_to_csv, export_to_json, export_to_txt, parse_dump
from status import check_status, format_status_report


def clear_screen() -> None:
    """Clears the terminal screen for a clean UI state."""
    os.system("cls" if os.name == "nt" else "clear")


def run_status(args: argparse.Namespace) -> None:
    """Executes catalog health check and outputs status report."""
    data = check_status(args.input)
    print(format_status_report(data))


def run_capture(args: argparse.Namespace) -> None:
    """Executes the capture pipeline to log raw network responses."""
    capture_library(
        dump_file=args.dump,
        auth_file=args.auth,
        headless=args.headless,
    )


def run_parse(args: argparse.Namespace) -> None:
    """Executes parser engine and exports structured catalog formats."""
    catalog = parse_dump(args.dump)
    export_to_json(catalog, args.json_out)
    export_to_csv(catalog, args.csv_out)
    export_to_txt(catalog, args.txt_out)
    print(f"[*] Parsed {catalog['metadata']['total_items']} items into JSON, CSV, and TXT.")


def run_duplicates(args: argparse.Namespace) -> None:
    """Executes duplicate detection and prints formatted summary."""
    items, _ = load_library(args.input)
    duplicates = find_duplicates(items)
    report = format_duplicate_report(
        duplicates=duplicates,
        total_items=len(items),
        source_file=str(args.input),
    )
    print(report)


def execute_full_sync(
    dump_path: Path = Path("raw_library_dump.json"),
    library_path: Path = Path("my_library.json"),
) -> None:
    """Helper running capture followed by parsing and exporting."""
    capture_library(dump_file=dump_path)
    catalog = parse_dump(dump_path)
    export_to_json(catalog, library_path)
    export_to_csv(catalog, "my_library.csv")
    export_to_txt(catalog, "my_library.txt")
    print(f"[*] Successfully synced {catalog['metadata']['total_items']} items.")


def handle_onboarding(
    library_path: Path = Path("my_library.json"),
    dump_path: Path = Path("raw_library_dump.json"),
) -> None:
    """Detects missing state on boot and offers guided setup."""
    if library_path.exists():
        return

    clear_screen()
    status_data = check_status(library_path)
    print(format_status_report(status_data) + "\n")

    if dump_path.exists():
        # Case B: Raw dump exists, but catalog json is missing
        confirm = questionary.confirm(
            "Unparsed dump 'raw_library_dump.json' found. Parse into library catalog now?"
        ).ask()
        if confirm:
            catalog = parse_dump(dump_path)
            export_to_json(catalog, library_path)
            export_to_csv(catalog, "my_library.csv")
            export_to_txt(catalog, "my_library.txt")
            print(f"[*] Successfully parsed {catalog['metadata']['total_items']} items.")
            questionary.press_any_key_to_continue("Press any key to enter main menu...").ask()
    else:
        # Case A: Neither dump nor library json exists
        confirm = questionary.confirm(
            "No library catalog found. Run your first Humble Bundle sync now?"
        ).ask()
        if confirm:
            execute_full_sync(dump_path, library_path)
            questionary.press_any_key_to_continue("Press any key to enter main menu...").ask()


def run_interactive_menu(library_path: Path = Path("my_library.json")) -> None:
    """Runs a persistent interactive terminal menu loop."""
    dump_path = Path("raw_library_dump.json")
    
    # Run onboarding check before entering main loop
    handle_onboarding(library_path, dump_path)

    while True:
        clear_screen()
        status_data = check_status(library_path)
        print(format_status_report(status_data) + "\n")

        choice = questionary.select(
            "Select an action:",
            choices=[
                "📊 View Duplicate Analysis",
                "🔄 Sync Library (Capture & Parse)",
                "🌐 Inspect Live Bundle (Deal Evaluator)",
                "❌ Exit",
            ],
        ).ask()

        if choice is None or choice == "❌ Exit":
            print("[*] Exiting Humble Library Sync.")
            sys.exit(0)

        if choice == "📊 View Duplicate Analysis":
            if not library_path.exists():
                print(f"[!] {library_path} not found. Run sync first.")
            else:
                items, _ = load_library(library_path)
                duplicates = find_duplicates(items)
                print("\n" + format_duplicate_report(duplicates, len(items), str(library_path)))

        elif choice == "🔄 Sync Library (Capture & Parse)":
            execute_full_sync(dump_path, library_path)

        elif choice == "🌐 Inspect Live Bundle (Deal Evaluator)":
            print("[*] Bundle inspector module under construction...")

        questionary.press_any_key_to_continue("Press any key to return to menu...").ask()


def build_parser() -> argparse.ArgumentParser:
    """Constructs and configures the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="humble-sync",
        description="Capture, parse, analyze, and browse your Humble Bundle library.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Status subcommand
    status_parser = subparsers.add_parser("status", help="Check catalog age and link health status.")
    status_parser.add_argument("--input", type=Path, default=Path("my_library.json"), help="Catalog JSON path.")
    status_parser.set_defaults(func=run_status)

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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        run_interactive_menu()
        return

    args.func(args)


if __name__ == "__main__":
    main()