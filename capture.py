from playwright.sync_api import sync_playwright
import json
import os

DUMP_FILE = "raw_library_dump.json"
AUTH_FILE = "auth.json"

def capture_library():
    """
    Launches an attended Playwright session to passively intercept and log
    Humble Bundle library data requests via background API calls.
    """
    # Ensure a clean capture state by removing previous session dumps
    if os.path.exists(DUMP_FILE):
        os.remove(DUMP_FILE)
        print(f"[*] Cleaned up previous {DUMP_FILE}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        if os.path.exists(AUTH_FILE):
            print("[*] Found saved session. Bypassing login...")
            context = browser.new_context(storage_state=AUTH_FILE)
            needs_login = False
        else:
            print("[*] No saved session found. First-time login required.")
            context = browser.new_context()
            needs_login = True

        page = context.new_page()

        def intercept_response(response):
            """
            Event handler attached to the browser's network layer.
            Filters for successful API responses and dumps the JSON payload locally.
            """
            if "api/v1/" in response.url and response.status == 200:
                try:
                    # Parse JSON while the context is guaranteed alive
                    data = response.json()
                    
                    with open(DUMP_FILE, "a", encoding="utf-8") as f:
                        json.dump({"url": response.url, "data": data}, f)
                        f.write("\n")
                    print(f"[+] Intercepted and saved data from: {response.url[:60]}...")
                except Exception as e:
                    # Ignore errors if the context closes mid-request
                    pass

        # Attach network listener before navigating
        page.on("response", intercept_response)
        
        if needs_login:
            page.goto("https://www.humblebundle.com/login")
            print("\n" + "="*50)
            print(">>> Please log in manually in the browser.")
            print(">>> Once you are completely logged in, press ENTER here.")
            print("="*50)
            
            input("\nPress ENTER to save session...\n")
            context.storage_state(path=AUTH_FILE)
            print("[*] Session saved successfully!")
        
        print("[*] Navigating to Library...")
        page.goto("https://www.humblebundle.com/home/library")
        
        # Bypass SPA local storage caching
        if not needs_login:
            print("[*] Forcing automated refresh to bypass cache...")
            page.reload()
        
        print("\n" + "="*50)
        print("1. Scroll slowly to the very bottom so all items load.")
        print("2. Ensure all your books are visible on the page.")
        print("="*50)
        
        input("\n>>> Press ENTER in this terminal when you are completely finished scrolling...\n")
        
        # Flush buffer: Allow 2 seconds for any remaining background API writes to finalize
        print("[*] Flushing network buffer before closing browser...")
        page.wait_for_timeout(2000)
        
        browser.close()
        
        if os.path.exists(DUMP_FILE):
            print(f"[*] Success! Capture complete. Data saved to {DUMP_FILE}")
        else:
            print(f"[!] Warning: {DUMP_FILE} was not created. Did you scroll to trigger API calls?")

if __name__ == "__main__":
    capture_library()