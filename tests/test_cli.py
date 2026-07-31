"""Tests for CLI subcommands - verifying capture and parse are fully isolated."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from cli import (
    build_parser,
    run_capture,
    run_parse,
    execute_capture_only,
    execute_parse_only,
)


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


def test_parse_subcommand_does_not_invoke_capture():
    """Verify that the parse subcommand does NOT invoke any network/capture code.

    This test ensures complete isolation: running 'parse' should only read from
    a local JSON file and sync to the database - no network operations allowed.
    """
    parser = build_parser()
    parse_args = parser.parse_args(["parse", "--dump", "local_dump.json"])

    # Mock all the functions that parse should call
    with patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db") as mock_sync, \
         patch("cli.reset_database") as mock_reset:

        mock_parse_dump.return_value = {"metadata": {"total_items": 5}}
        parse_args.func(parse_args)

        # Verify parse was called with the correct local file
        mock_parse_dump.assert_called_once_with(Path("local_dump.json"))
        mock_sync.assert_called_once()

        # Verify reset was NOT called (no --reset flag)
        mock_reset.assert_not_called()

    # Now verify that capture_library is NEVER called when running parse
    with patch("cli.capture_library") as mock_capture, \
         patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db"):

        mock_parse_dump.return_value = {"metadata": {"total_items": 5}}
        parse_args.func(parse_args)

        # capture_library should NOT be invoked by parse subcommand
        mock_capture.assert_not_called()


def test_capture_subcommand_does_not_invoke_parse_or_database():
    """Verify that the capture subcommand does NOT invoke any parsing or database code.

    This test ensures complete isolation: running 'capture' should only perform
    network fetching and save to a file - no database operations allowed.
    """
    parser = build_parser()
    capture_args = parser.parse_args(["capture", "--output", "output.json"])

    with patch("cli.capture_library") as mock_capture, \
         patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db") as mock_sync, \
         patch("cli.reset_database") as mock_reset:

        capture_args.func(capture_args)

        # capture_library should be called
        mock_capture.assert_called_once_with(
            dump_file=Path("output.json"),
            auth_file=Path("auth.json"),
            headless=False,
        )

        # parse and database functions should NOT be invoked by capture subcommand
        mock_parse_dump.assert_not_called()
        mock_sync.assert_not_called()
        mock_reset.assert_not_called()


def test_parse_subcommand_with_reset_provides_feedback(capsys):
    """Verify that parse --reset provides visual terminal feedback."""
    parser = build_parser()
    parse_args = parser.parse_args(["parse", "--dump", "test.json", "--reset"])

    with patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db"), \
         patch("cli.reset_database"):

        mock_parse_dump.return_value = {"metadata": {"total_items": 3}}
        parse_args.func(parse_args)

        captured = capsys.readouterr()
        assert "Resetting database" in captured.out
        assert "database reset complete" in captured.out.lower()


def test_parse_subcommand_default_dump_path():
    """Verify that parse subcommand defaults to raw_library_dump.json if --dump is omitted."""
    parser = build_parser()
    parse_args = parser.parse_args(["parse"])

    assert parse_args.dump == Path("raw_library_dump.json")

    # Verify it works without specifying --dump
    with patch("cli.parse_dump") as mock_parse_dump, patch("cli.sync_catalog_to_db"):
        mock_parse_dump.return_value = {"metadata": {"total_items": 1}}
        parse_args.func(parse_args)
        mock_parse_dump.assert_called_once_with(Path("raw_library_dump.json"))


def test_execute_capture_only_calls_capture_library():
    """Verify execute_capture_only calls capture_library and NOT parse/database functions."""
    with patch("cli.capture_library") as mock_capture, \
         patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db") as mock_sync, \
         patch("cli.reset_database") as mock_reset:

        execute_capture_only(Path("test_dump.json"))

        mock_capture.assert_called_once_with(dump_file=Path("test_dump.json"))
        mock_parse_dump.assert_not_called()
        mock_sync.assert_not_called()
        mock_reset.assert_not_called()


def test_execute_parse_only_calls_parse_and_sync():
    """Verify execute_parse_only calls parse_dump and sync_catalog_to_db, NOT capture_library."""
    with patch("cli.capture_library") as mock_capture, \
         patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db") as mock_sync, \
         patch("cli.reset_database") as mock_reset:

        mock_parse_dump.return_value = {"metadata": {"total_items": 7}}
        execute_parse_only(Path("test_dump.json"), reset=False)

        mock_capture.assert_not_called()
        mock_parse_dump.assert_called_once_with(Path("test_dump.json"))
        mock_sync.assert_called_once()
        mock_reset.assert_not_called()


def test_execute_parse_only_with_reset():
    """Verify execute_parse_only with reset=True calls reset_database before parsing."""
    with patch("cli.capture_library") as mock_capture, \
         patch("cli.parse_dump") as mock_parse_dump, \
         patch("cli.sync_catalog_to_db") as mock_sync, \
         patch("cli.reset_database") as mock_reset:

        mock_parse_dump.return_value = {"metadata": {"total_items": 5}}
        execute_parse_only(Path("test_dump.json"), reset=True)

        mock_capture.assert_not_called()
        mock_reset.assert_called_once()
        mock_parse_dump.assert_called_once_with(Path("test_dump.json"))
        mock_sync.assert_called_once()


def test_interactive_menu_choices_include_separated_capture_parse():
    """Verify that the interactive menu includes the separated capture and parse options."""
    import cli as cli_module

    # Read the source to verify menu choices are correct
    import inspect
    source = inspect.getsource(cli_module.run_interactive_menu)

    # Verify the menu contains the separated options
    assert "📥 Capture Library (Fetch raw data)" in source
    assert "⚡ Parse Local Dump (Update database)" in source
    assert "🔄 Parse Local Dump with Reset (Clean slate)" in source

    # Verify the old combined option is removed
    assert "🔄 Sync Library (Capture & Parse)" not in source


def test_menu_capture_wires_to_execute_capture_only():
    """Verify that the Capture Library menu option is wired to execute_capture_only."""
    import cli as cli_module
    import inspect
    source = inspect.getsource(cli_module.run_interactive_menu)

    # Verify the capture menu option calls execute_capture_only
    assert 'choice == "📥 Capture Library (Fetch raw data)"' in source
    assert "execute_capture_only(dump_path)" in source


def test_menu_parse_wires_to_execute_parse_only():
    """Verify that the Parse Local Dump menu option is wired to execute_parse_only without reset."""
    import cli as cli_module
    import inspect
    source = inspect.getsource(cli_module.run_interactive_menu)

    # Verify the parse menu option calls execute_parse_only with reset=False
    assert 'choice == "⚡ Parse Local Dump (Update database)"' in source
    assert "execute_parse_only(dump_path, reset=False)" in source


def test_menu_parse_with_reset_wires_to_execute_parse_only_with_reset():
    """Verify that the Parse Local Dump with Reset menu option calls execute_parse_only with reset=True."""
    import cli as cli_module
    import inspect
    source = inspect.getsource(cli_module.run_interactive_menu)

    # Verify the parse with reset menu option calls execute_parse_only with reset=True
    assert 'choice == "🔄 Parse Local Dump with Reset (Clean slate)"' in source
    assert "execute_parse_only(dump_path, reset=True)" in source
