"""Tests for CLI subcommands."""

from pathlib import Path
from unittest.mock import patch

from cli import build_parser, run_capture, run_parse


def test_cli_subcommands_parse_and_capture():
    """Verify that both capture and parse subcommands parse arguments correctly
    and invoke their respective handler functions."""
    parser = build_parser()

    # Test capture subcommand argument parsing
    capture_args = parser.parse_args(["capture", "--output", "custom_dump.json"])
    assert capture_args.command == "capture"
    assert capture_args.output == Path("custom_dump.json")
    assert capture_args.auth == Path("auth.json")
    assert capture_args.headless is False

    # Test capture with short option -o
    capture_args_short = parser.parse_args(["capture", "-o", "short_dump.json"])
    assert capture_args_short.output == Path("short_dump.json")

    # Test parse subcommand argument parsing
    parse_args = parser.parse_args(["parse", "--dump", "input_dump.json"])
    assert parse_args.command == "parse"
    assert parse_args.dump == Path("input_dump.json")
    assert parse_args.reset is False

    # Test parse with short options -d and -r
    parse_args_short = parser.parse_args(["parse", "-d", "short_dump.json", "-r"])
    assert parse_args_short.dump == Path("short_dump.json")
    assert parse_args_short.reset is True

    # Test that capture subcommand invokes run_capture with correct args
    with patch("cli.capture_library") as mock_capture:
        capture_args = parser.parse_args(["capture", "--output", "test_output.json"])
        capture_args.func(capture_args)
        mock_capture.assert_called_once_with(
            dump_file=Path("test_output.json"),
            auth_file=Path("auth.json"),
            headless=False,
        )

    # Test that parse subcommand invokes run_parse with correct args
    with patch("cli.parse_dump") as mock_parse_dump, patch("cli.sync_catalog_to_db") as mock_sync:
        mock_parse_dump.return_value = {"metadata": {"total_items": 42}}
        parse_args = parser.parse_args(["parse", "--dump", "test_input.json"])
        parse_args.func(parse_args)
        mock_parse_dump.assert_called_once_with(Path("test_input.json"))
        mock_sync.assert_called_once_with({"metadata": {"total_items": 42}})

    # Test that parse subcommand with --reset calls reset_database
    with patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db") as mock_sync, \
         patch("cli.reset_database") as mock_reset:
        mock_parse_dump.return_value = {"metadata": {"total_items": 10}}
        parse_args = parser.parse_args(["parse", "--dump", "test_input.json", "--reset"])
        parse_args.func(parse_args)
        mock_reset.assert_called_once()
        mock_parse_dump.assert_called_once_with(Path("test_input.json"))