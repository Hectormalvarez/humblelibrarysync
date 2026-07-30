"""Search and filtering utilities for the Humble Bundle library catalog."""

from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings


def search_catalog(items: list[dict], query: str) -> list[dict]:
    """Filter *items* whose title, publisher, or bundle matches *query* (case-insensitive).

    Only items that contain the query string (as a substring) in at least one of
    the three fields are returned.  Missing publisher or bundle fields are ignored.
    """
    query_lower = query.strip().lower()

    def _matches(item: dict) -> bool:
        return (
            query_lower in item["title"].lower()
            or query_lower in item.get("publisher", "").lower()
            or query_lower in item.get("bundle", "").lower()
        )

    return [item for item in items if _matches(item)]


def format_search_results(matches: list[dict], query: str) -> str:
    """Build a human-readable string of search *matches* for the given *query*.

    Returns a header line with the match count followed by a formatted block for
    each matched item (title, bundle, available formats).
    """
    if not matches:
        return f"[!] No results found for '{query}'."

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"Search results for: '{query}' ({len(matches)} match(es))")
    lines.append("-" * 60)

    for item in matches:
        formats = ", ".join(item.get("available_formats", []))
        lines.append(f"  Title:    {item['title']}")
        lines.append(f"  Bundle:   {item.get('bundle', 'Unknown')}")
        lines.append(f"  Formats:  {formats}")
        lines.append("-" * 60)

    return "\n".join(lines)


class _TitleCompleter(Completer):
    """Prompt_toolkit completer that filters unique item titles as the user types."""

    def __init__(self, items: list[dict]) -> None:
        # Deduplicate by title so each title appears only once in the dropdown
        seen: set[str] = set()
        self._unique_titles: list[str] = []
        for item in items:
            title = item["title"]
            if title not in seen:
                seen.add(title)
                self._unique_titles.append(title)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.strip().lower()
        if not text:
            return

        for title in self._unique_titles:
            if text in title.lower():
                yield Completion(
                    title,
                    start_position=-len(document.text_before_cursor),
                    display=title,
                )


def _build_key_bindings() -> KeyBindings:
    """Return key bindings that allow Esc to cancel the prompt gracefully."""
    kb = KeyBindings()

    @kb.add("escape")
    def _(event):
        event.app.exit(result=None)

    return kb


def _merge_items_by_title(items: list[dict], title: str) -> Optional[dict]:
    """Merge all items matching *title* into a single result dict.

    The returned dict contains the common fields (title, publisher, formats,
    downloads) from the first match, plus a ``bundles`` list with every
    bundle name the title appears in.
    """
    matches = [it for it in items if it["title"] == title]
    if not matches:
        return None

    first = matches[0]
    return {
        "title": first["title"],
        "publisher": first.get("publisher", "Unknown"),
        "available_formats": first.get("available_formats", []),
        "downloads": first.get("downloads", {}),
        "bundles": sorted({m.get("bundle", "Unknown") for m in matches}),
    }


def live_search_prompt(items: list[dict]) -> Optional[dict]:
    """Interactive search-as-you-type prompt that filters unique item titles live.

    As the user types, matching titles appear in an autocomplete dropdown
    (each title shown once, even if it appears in multiple bundles).
    Press *Tab* / *Down* to navigate completions, *Enter* to select,
    or *Esc* to cancel and return ``None``.

    Returns a merged item dictionary (with a ``bundles`` list of every bundle
    the title was purchased in), or ``None`` if cancelled.
    """
    # Header block with instructions
    print("─" * 50)
    print("  🔍  Search Library")
    print("  Type a title to filter.  Esc to cancel.")
    print("─" * 50)

    rprompt = HTML("<ansibrightblack>Esc to cancel</ansibrightblack>")

    session: PromptSession = PromptSession(
        completer=_TitleCompleter(items),
        key_bindings=_build_key_bindings(),
        complete_while_typing=True,
        message=HTML("<ansibrightcyan>🔍  </ansibrightcyan>"),
        rprompt=rprompt,
    )

    try:
        result = session.prompt()
    except (KeyboardInterrupt, EOFError):
        return None

    if result is None:
        return None

    return _merge_items_by_title(items, result.strip())
