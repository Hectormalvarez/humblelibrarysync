"""
Automated browser capture engine for Humble Bundle API payloads.
Uses Playwright to passively intercept background network responses.
"""

import json
from pathlib import Path
from typing import Callable, Optional
from playwright.sync_api import Response, sync_playwright


def default_login_prompt() -> None:
    """Default terminal prompt for manual login verification."""
    print("\n" + "=" * 50)
    print(">>> Please log in manually in the browser.")
    print(">>> Once logged in, press ENTER here.")
    print("=" * 50)
    input("\nPress ENTER to save session...\n")


def default_scroll_prompt() -> None:
    """Default terminal prompt pausing execution while user scrolls the page."""
    print("\n" + "=" * 50)
    print("1. Scroll slowly to the bottom so all items load.")
    print("2. Ensure all your books are visible on the page.")
    print("=" * 50)
    input("\n>>> Press ENTER in this terminal when finished scrolling...\n")


def capture_library(
    dump_file: str | Path = "raw_library_dump.json",
    auth_file: str | Path = "auth.json",
    headless: bool = False,
    login_prompt: Optional[Callable[[], None]] = default_login_prompt,
    scroll_prompt: Optional[Callable[[], None]] = default_scroll_prompt,
) -> Path:
    """
    Launches Playwright to intercept and save Humble Bundle API payloads.
    Decouples terminal interactions via injectable callback hooks.
    """
    dump_path = Path(dump_file)
    auth_path = Path(auth_file)

    if dump_path.exists():
        dump_path.unlink()
        print(f"[*] Cleaned up previous dump: {dump_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        if auth_path.exists():
            print("[*] Saved session found. Bypassing login...")
            context = browser.new_context(storage_state=str(auth_path))
            needs_login = False
        else:
            print("[*] No saved session found. Login required.")
            context = browser.new_context()
            needs_login = True

        page = context.new_page()

        def handle_response(response: Response) -> None:
            """Network listener appending valid API responses to disk."""
            if "api/v1/" in response.url and response.status == 200:
                try:
                    data = response.json()
                    with open(dump_path, "a", encoding="utf-8") as f:
                        json.dump({"url": response.url, "data": data}, f)
                        f.write("\n")
                    print(f"[+] Intercepted: {response.url[:60]}...")
                except Exception:
                    pass

        page.on("response", handle_response)

        if needs_login:
            page.goto("https://www.humblebundle.com/login")
            if login_prompt:
                login_prompt()
            context.storage_state(path=str(auth_path))
            print("[*] Session state saved!")

        print("[*] Navigating to Library...")
        page.goto("https://www.humblebundle.com/home/library")

        if not needs_login:
            print("[*] Reloading page to force cache-bust...")
            page.reload()

        if scroll_prompt:
            scroll_prompt()

        print("[*] Flushing network buffer...")
        page.wait_for_timeout(2000)
        browser.close()

    return dump_path


if __name__ == "__main__":
    captured = capture_library()
    if captured.exists():
        print(f"[*] Capture complete -> {captured}")
    else:
        print(f"[!] Warning: {captured} was not created.")