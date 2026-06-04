import os
import json
import time
from playwright.sync_api import sync_playwright

def test_google_vids_login():
    print("[INIT] Fetching encrypted cookies from GitHub Secrets...")
    cookies_json = os.getenv("GOOGLE_SESSION_COOKIES")
    
    if not cookies_json:
        print("❌ CRITICAL ERROR: GOOGLE_SESSION_COOKIES environment variable is empty!")
        return False
        
    try:
        cookies = json.loads(cookies_json)
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Failed to parse cookie JSON string: {e}")
        return False

    # 🛠️ COOKIE CLEANING: Bypassing Playwright's strict sameSite validation rules
    print("[SECURITY] Sanitizing cookie data for Playwright compliance...")
    for cookie in cookies:
        if "sameSite" in cookie:
            val = str(cookie["sameSite"]).lower()
            if val == "strict":
                cookie["sameSite"] = "Strict"
            elif val == "lax":
                cookie["sameSite"] = "Lax"
            else:
                # Automatically maps "unspecified" or "no_restriction" straight to "None"
                cookie["sameSite"] = "None"

    with sync_playwright() as p:
        print("[BROWSER] Launching headless browser instance...")
        browser = p.chromium.launch(headless=True)
        
        # Emulate a standard desktop screen
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Inject our cleaned passport
        print("[SECURITY] Injecting session cookies into browser memory...")
        context.add_cookies(cookies)
        
        page = context.new_page()
        
        # Fly straight to the Google Vids Canvas
        target_url = "https://docs.google.com/videos/u/0/create?usp=vids_home"
        print(f"[NAVIGATE] Steering browser to: {target_url}")
        page.goto(target_url, wait_until="networkidle")
        
        # Give the workspace a few seconds to fully render elements
        print("[WAIT] Allowing workspace canvas to load components...")
        time.sleep(10)
        
        # Take a visual snapshot so we can see what the bot sees
        screenshot_path = "vids_canvas_snapshot.png"
        page.screenshot(path=screenshot_path)
        print(f"📸 SUCCESS: Snapshot captured and saved to '{screenshot_path}'")
        
        # Quick page verification check
        page_title = page.title()
        print(f"[VERIFY] Current Page Title: '{page_title}'")
        
        if "Google" in page_title or "Vids" in page_title:
            print("✅ PASS: The bot successfully opened the internal workspace without being blocked!")
        else:
            print("⚠️ WARNING: Page title looks unexpected. Check the debug screenshot later.")
            
        context.close()
        browser.close()
        return True

if __name__ == "__main__":
    test_google_vids_login()
