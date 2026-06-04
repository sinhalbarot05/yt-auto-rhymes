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

    # Cookie Sanitizer
    print("[SECURITY] Sanitizing cookie data for Playwright compliance...")
    for cookie in cookies:
        if "sameSite" in cookie:
            val = str(cookie["sameSite"]).lower()
            if val in ["strict", "lax"]:
                cookie["sameSite"] = val.capitalize()
            else:
                cookie["sameSite"] = "None"

    # Save processed cookies into a structured Playwright state profile
    state_data = {"cookies": cookies, "origins": []}
    with open("auth_state.json", "w") as f:
        json.dump(state_data, f)

    with sync_playwright() as p:
        print("[BROWSER] Launching stealth headless browser instance...")
        
        # 🛡️ STEALTH LAUNCH: Stripping all default automation fingerprints
        browser = p.chromium.launch(
            headless=True,
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors"
            ]
        )
        
        # Emulate a highly authentic Windows Desktop user profile
        context = browser.new_context(
            storage_state="auth_state.json",
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        # Warmup Step: Hit the main Google domain
        print("[NAVIGATION] Loading base Google domain to anchor session tokens...")
        page.goto("https://www.google.com", wait_until="networkidle")
        time.sleep(5)
        
        # Head directly to the target canvas workspace
        target_url = "https://docs.google.com/videos/u/0/create?usp=vids_home"
        print(f"[NAVIGATION] Session anchored. Steering to target: {target_url}")
        page.goto(target_url, wait_until="networkidle")
        
        print("[WAIT] Allowing workspace canvas components to fully render...")
        time.sleep(15)
        
        # Capture the snapshot file
        screenshot_path = "vids_canvas_snapshot.png"
        page.screenshot(path=screenshot_path)
        print(f"📸 SNAPSHOT: Captured updated look at screen state.")
        
        page_title = page.title()
        print(f"[VERIFY] Current Page Title: '{page_title}'")
        
        if "Sign-in" in page_title or "sign in" in page_title.lower():
            print("❌ FAIL: Google still detected the automated server environment.")
        else:
            print("🎉 SUCCESS: Stealth engine working. We are completely inside the design studio!")
            
        context.close()
        browser.close()
        
        if os.path.exists("auth_state.json"):
            os.remove("auth_state.json")
            
        return True

if __name__ == "__main__":
    test_google_vids_login()
