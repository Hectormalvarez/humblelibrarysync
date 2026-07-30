"""CLI entrypoint for Humble Library Sync featuring an interactive menu loop."""

import argparse
import os
import sys
from pathlib import Path
import questionary

from bundle_inspector import (
    evaluate_deal,
    fetch_bundle_items,
    format_deal_report,
    format_expired_deals_report,
    format_expired_reading_list,
    get_expired_entries,
    load_active_bundles,
    load_evaluated_bundles_log,
    log_evaluated_bundle,
    mark_expired_entries,
    save_evaluated_bundles_log,
)
from capture import capture_library
from library_duplicates import find_duplicates, format_duplicate_report, load_library
from parse import export_to_csv, export_to_json, export_to_txt, parse_dump
from search import format_search_results, live_search_prompt, search_catalog
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


def _ensure_library_exists(
    library_path: Path,
    dump_path: Path,
) -> bool:
    """Checks library exists; if missing, prompts user to sync. Returns True if available."""
    if library_path.exists():
        return True

    confirm = questionary.confirm(
        "Library catalog missing. Run sync now to generate it?"
    ).ask()
    if confirm:
        execute_full_sync(dump_path, library_path)
        return True
    return False


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
                "📜 View Expired Deal Reading List",
                "🔍 Search Library",
                "❌ Exit",
            ],
        ).ask()

        if choice is None or choice == "❌ Exit":
            print("[*] Exiting Humble Library Sync.")
            sys.exit(0)

        if choice == "📊 View Duplicate Analysis":
            if not _ensure_library_exists(library_path, dump_path):
                pass
            else:
                items, _ = load_library(library_path)
                duplicates = find_duplicates(items)
                print("\n" + format_duplicate_report(duplicates, len(items), str(library_path)))

        elif choice == "🔄 Sync Library (Capture & Parse)":
            execute_full_sync(dump_path, library_path)

        elif choice == "🌐 Inspect Live Bundle (Deal Evaluator)":
            if not _ensure_library_exists(library_path, dump_path):
                pass
            else:
                def _bundle_label(b: dict) -> str:
                    label = b['title']
                    if b.get('author'):
                        label += f" ({b['author']})"
                    if b.get('end_date'):
                        label += f" — ends {b['end_date'][:10]}"
                    return label

                def _bundle_category(url: str) -> str:
                    for cat in ("books", "games", "software"):
                        if f"/{cat}/" in url:
                            return cat
                    return "other"

                category_order = ["books", "games", "software", "other"]
                category_labels = {
                    "books": "📚 Books",
                    "games": "🎮 Games",
                    "software": "💻 Software",
                    "other": "📦 Other",
                }

                while True:
                    try:
                        bundles = load_active_bundles()
                    except RuntimeError as e:
                        print(e)
                        break

                    if not bundles:
                        print("[!] No active bundles found.")
                        break

                    # Group and sort bundles by category
                    grouped: dict[str, list[dict]] = {c: [] for c in category_order}
                    for b in bundles:
                        cat = _bundle_category(b["url"])
                        grouped[cat].append(b)
                    for cat in category_order:
                        grouped[cat].sort(key=lambda b: b["title"].lower())

                    # --- Category selection ---
                    cat_choices = []
                    for cat in category_order:
                        cat_bundles = grouped[cat]
                        if not cat_bundles:
                            continue
                        cat_choices.append(f"{category_labels[cat]} ({len(cat_bundles)})")
                    cat_choices.append("🔗 Enter Custom Bundle URL")
                    cat_choices.append("🔄 Refresh Bundle List")
                    cat_choices.append("← Back to Menu")

                    cat_selected = questionary.select(
                        "Select a category:",
                        choices=cat_choices,
                    ).ask()

                    if cat_selected is None or cat_selected == "← Back to Menu":
                        break
                    elif cat_selected == "🔄 Refresh Bundle List":
                        try:
                            print("[*] Refreshing active bundles...")
                            from bundle_inspector import capture_active_bundles
                            capture_active_bundles(force=True)
                        except RuntimeError as e:
                            print(e)
                        continue
                    elif cat_selected == "🔗 Enter Custom Bundle URL":
                        custom_url = questionary.text(
                            "Enter full bundle URL:",
                            validate=lambda text: (
                                True
                                if text.startswith("https://www.humblebundle.com/")
                                else "URL must start with https://www.humblebundle.com/"
                            ),
                        ).ask()

                        if custom_url:
                            try:
                                print(f"[*] Fetching bundle items from: {custom_url}")
                                bundle_data = fetch_bundle_items(custom_url)
                                items, _ = load_library(library_path)
                                eval_data = evaluate_deal(
                                    bundle_data["items"], items,
                                    pricing=bundle_data.get("pricing"),
                                    tier_item_map=bundle_data.get("tier_item_map"),
                                )
                                print("\n" + format_deal_report(bundle_data["bundle_name"], eval_data))
                                log_evaluated_bundle(
                                    bundle_data["bundle_name"],
                                    custom_url,
                                    bundle_data.get("machine_name", ""),
                                    None,
                                    eval_data,
                                )
                                questionary.press_any_key_to_continue("Press any key to continue...").ask()
                            except RuntimeError as e:
                                print(e)
                        continue
                    else:
                        # Extract category key from the selected label
                        selected_cat = None
                        for cat in category_order:
                            if cat_selected.startswith(category_labels[cat]):
                                selected_cat = cat
                                break

                        if not selected_cat or not grouped.get(selected_cat):
                            continue

                        # --- Bundle selection within category ---
                        cat_bundles = grouped[selected_cat]
                        while True:
                            bundle_choices = [_bundle_label(b) for b in cat_bundles]
                            bundle_choices.append("← Back to Categories")

                            selected = questionary.select(
                                f"Select a bundle from {category_labels[selected_cat]}:",
                                choices=bundle_choices,
                            ).ask()

                            if selected is None or selected == "← Back to Categories":
                                break

                            # Find the selected bundle
                            bundle = None
                            for b in cat_bundles:
                                if _bundle_label(b) == selected:
                                    bundle = b
                                    break

                            if bundle:
                                try:
                                    print(f"[*] Fetching bundle items: {bundle['title']}")
                                    bundle_data = fetch_bundle_items(bundle["url"])
                                    items, _ = load_library(library_path)
                                    eval_data = evaluate_deal(
                                        bundle_data["items"], items,
                                        pricing=bundle_data.get("pricing"),
                                        tier_item_map=bundle_data.get("tier_item_map"),
                                    )
                                    print("\n" + format_deal_report(bundle_data["bundle_name"], eval_data))
                                    log_evaluated_bundle(
                                        bundle_data["bundle_name"],
                                        bundle["url"],
                                        bundle.get("machine_name", ""),
                                        bundle.get("end_date", ""),
                                        eval_data,
                                    )
                                    questionary.press_any_key_to_continue("Press any key to return to bundle list...").ask()
                                except RuntimeError as e:
                                    print(e)

        elif choice == "📜 View Expired Deal Reading List":
            # Load log, mark expired entries, save, and display reading list
            entries = load_evaluated_bundles_log()
            entries = mark_expired_entries(entries)
            save_evaluated_bundles_log(entries)
            expired = get_expired_entries(entries)
            if not expired:
                print("\n" + "=" * 60)
                print("  No expired deals recorded yet.")
                print("  Evaluate some bundles via the Deal Evaluator first.")
                print("=" * 60)
            else:
                print("\n" + format_expired_reading_list(expired))
                # Offer to export to txt
                export_confirm = questionary.confirm(
                    "Export reading list to expired_reading_list.txt?", default=False
                ).ask()
                if export_confirm:
                    Path("expired_reading_list.txt").write_text(
                        format_expired_reading_list(expired), encoding="utf-8"
                    )
                    print("[*] Exported to expired_reading_list.txt")
            questionary.press_any_key_to_continue("Press any key to return to menu...").ask()

        elif choice == "🔍 Search Library":
            if not _ensure_library_exists(library_path, dump_path):
                pass
            else:
                items, _ = load_library(library_path)
                while True:
                    selected = live_search_prompt(items)
                    if selected is None:
                        break  # Esc -> back to main menu
                    print("\n" + "=" * 60)
                    print(f"  Title:     {selected['title']}")
                    bundles = selected.get("bundles", [])
                    if bundles:
                        print(f"  Bundles:   {bundles[0]}")
                        for b in bundles[1:]:
                            print(f"             {b}")
                    print(f"  Publisher: {selected.get('publisher', 'Unknown')}")
                    formats = ", ".join(selected.get("available_formats", []))
                    print(f"  Formats:   {formats}")
                    downloads = selected.get("downloads", {})
                    if downloads:
                        print(f"  File Keys/Downloads:")
                        for fmt, info in downloads.items():
                            url = info.get("url", "N/A")
                            size = info.get("human_size", "")
                            print(f"    {fmt}: {size} — {url}")
                    else:
                        print(f"  File Keys/Downloads: None")
                    print("=" * 60)

                    again = questionary.confirm("Search again?", default=True).ask()
                    if not again:
                        break
                continue

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