"""
YouTube Ad Scraper - 2 Account Version
Fixes:
  1. Robust ad detail capture using JS DOM scanning (not fragile CSS selectors)
  2. India-specific seed videos + YouTube forced to IN locale
  3. Fast-forward jumps to 25/50/75% of video duration instead of fixed seconds
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page

# ─────────────────────────────────────────
# CONFIG — fill in your details
# ─────────────────────────────────────────
ACCOUNTS = [
    {
        "id": "account_1",
        "persona": "Tech Enthusiast, Male, Delhi",
        "email": "akshay12kumar866@gmail.com",
        "password": "AK472047",
        # Indian tech / news content — high ad density
        "seed_videos": [
            "https://www.youtube.com/watch?v=aU6UsXaD2WI&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=3N_q9o8gTOE&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=ONVH_OiP8cg&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=JVyWMKBFhgc&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=pKiyKZLtHrI&gl=IN&hl=en",
        ],
    },
    {
        "id": "account_2",
        "persona": "Beauty & Lifestyle, Female, Mumbai",
        "email": "abhay12kumar877@gmail.com",
        "password": "AK472047",
        # Indian beauty / lifestyle / Bollywood content
        "seed_videos": [
            "https://www.youtube.com/watch?v=aU6UsXaD2WI&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=aBXbMkFpFgQ&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=VOx8yCmT4lE&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=9tPCyOTZ1kA&gl=IN&hl=en",
            "https://www.youtube.com/watch?v=ql8QXFbS4oU&gl=IN&hl=en",
        ],
    },
]

MAX_VIDEOS_PER_ACCOUNT = 5
OUTPUT_DIR             = Path("./output")
# ─────────────────────────────────────────

OUTPUT_DIR.mkdir(exist_ok=True)
ALL_ADS: list[dict] = []


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

async def safe_text(page: Page, selector: str, timeout=4000) -> str:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        return (await el.inner_text()).strip() if el else ""
    except Exception:
        return ""


async def click_if_exists(page: Page, selector: str, timeout=3000) -> bool:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        if el and await el.is_visible():
            await el.click()
            return True
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════
#  AD DETECTION  (JS-based — most reliable)
# ══════════════════════════════════════════════════════════════════

async def is_ad_playing(page: Page) -> bool:
    try:
        return await page.evaluate("""() => {
            const player = document.querySelector('.html5-video-player');
            if (!player) return false;
            if (player.classList.contains('ad-showing')) return true;
            const bar = document.querySelector('.ytp-ad-progress-list');
            if (bar && bar.offsetParent !== null) return true;
            const overlay = document.querySelector('.ytp-ad-player-overlay-instream-info');
            if (overlay && overlay.offsetParent !== null) return true;
            return false;
        }""")
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════
#  AD DETAIL EXTRACTION  (JS DOM scan)
# ══════════════════════════════════════════════════════════════════

async def extract_ad_details_js(page: Page) -> dict:
    return await page.evaluate("""() => {
        const get = (sel) => {
            const el = document.querySelector(sel);
            return el ? (el.innerText || el.textContent || '').trim() : '';
        };
        const getAttr = (sel, attr) => {
            const el = document.querySelector(sel);
            return el ? (el.getAttribute(attr) || '') : '';
        };

        const adTitle =
            get('.ytp-ad-headline') ||
            get('.ytp-ad-simple-ad-badge + .ytp-ad-button-text') ||
            get('.ytp-ad-overlay-ad-info .ytp-ad-button-text') ||
            get('[class*="ad-title"]') ||
            get('[class*="ad-headline"]') ||
            get('.ytp-ad-button-text') || '';

        // ad_link: visit-advertiser button stores URL in data-redirect or as child <a>
        const visitBtn = document.querySelector('.ytp-ad-visit-advertiser-button');
        const adLink =
            (visitBtn ? (visitBtn.getAttribute('data-redirect') || '') : '') ||
            getAttr('a.ytp-ad-visit-advertiser-button', 'href') ||
            getAttr('.ytp-ad-clickable-area a', 'href') ||
            getAttr('a[class*="ad-button"]', 'href') ||
            (() => {
                // last-resort: grab href from any anchor inside the overlay
                const a = document.querySelector('.ytp-ad-player-overlay a[href]');
                return a ? a.href : '';
            })() || '';

        // advertiser_name: the channel/brand name shown under the ad
        const advertiserName =
            get('.ytp-ad-visit-advertiser-button .ytp-ad-button-text') ||
            get('.ytp-ad-visit-advertiser-button') ||
            get('.ytp-ad-advertiser-name') ||
            get('[class*="advertiser-name"]') ||
            get('.ytp-ce-channel-title') ||
            get('.ytd-display-ad-renderer #domain-name') || '';

        // Duration: must match time format like "0:15" — reject words like "banner"
        const rawDuration =
            get('.ytp-ad-duration-remaining') ||
            get('.ytp-time-display.ytp-ad-simple-ad-badge') || '';
        const duration = /\d+:\d+/.test(rawDuration) ? rawDuration : '';

        // Skip: only report actual skip button text, not random [class*="skip"] matches
        const skipEl =
            document.querySelector('.ytp-skip-ad-button') ||
            document.querySelector('.ytp-ad-skip-button-slot button') ||
            document.querySelector('.ytp-ad-skip-button');
        const skipText = skipEl ? (skipEl.innerText || 'Skippable').trim() : 'Non-skippable';

        const companionTitle =
            get('.ytp-ce-covering-overlay .ytp-ce-headline-text') ||
            get('.ytd-companion-slot-renderer #video-title') || '';

        const overlayEl = document.querySelector('.ytp-ad-player-overlay');
        const overlayText = overlayEl ? overlayEl.innerText.trim() : '';

        // Ad type detection
        const player = document.querySelector('.html5-video-player');
        let adType = 'unknown';
        if (player) {
            if (player.classList.contains('ad-interrupting')) adType = 'midroll';
            else if (document.querySelector('.ytp-ad-overlay-container')) adType = 'overlay';
            else if (document.querySelector('.ytp-ad-player-overlay-instream-info')) adType = 'instream';
            else adType = 'preroll';
        }

        return {
            ad_title: adTitle,
            ad_link: adLink,
            advertiser_name: advertiserName,
            ad_duration_remaining: duration,
            skip_available: skipText,
            companion_title: companionTitle,
            overlay_text_dump: overlayText,
            ad_type: adType,
        };
    }""")


# ══════════════════════════════════════════════════════════════════
#  PAUSE / RESUME
# ══════════════════════════════════════════════════════════════════

async def pause_ad(page: Page):
    try:
        await page.evaluate("""() => {
            const v = document.querySelector('.html5-main-video');
            if (v && !v.paused) v.pause();
        }""")
        await asyncio.sleep(0.3)
    except Exception:
        pass


async def resume_video(page: Page):
    try:
        await page.evaluate("""() => {
            const v = document.querySelector('.html5-main-video');
            if (v && v.paused) v.play();
        }""")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  ADVERTISER NAME  (ⓘ → About this advertiser → Paid for by)
# ══════════════════════════════════════════════════════════════════

async def get_advertiser_name(page: Page) -> str:
    # Make sure ad is paused so controls stay visible
    await pause_ad(page)
    await asyncio.sleep(0.3)

    # Hover to reveal controls
    try:
        await page.mouse.move(640, 360)
        await asyncio.sleep(1.0)   # give controls time to appear
    except Exception:
        pass

    # Click ⓘ — try CSS selectors first, then JS dispatch fallback
    info_selectors = [
        ".ytp-ad-info-button button",
        "button.ytp-ad-info-dialog-ad-feedback-button",
        ".ytp-ad-info-button",
        "button[aria-label='Why this ad?']",
        "button[aria-label='About this ad']",
        ".ytp-ad-why-this-ad",
        ".ytp-ad-overlay-ad-info-button",
    ]
    clicked_info = False
    for sel in info_selectors:
        if await click_if_exists(page, sel, timeout=2000):
            print(f"    ✅ ⓘ clicked: {sel}")
            clicked_info = True
            break

    if not clicked_info:
        # JS fallback: find any small circular info/i button inside the ad overlay and click it
        clicked_info = await page.evaluate("""() => {
            const candidates = [
                document.querySelector('.ytp-ad-info-button button'),
                document.querySelector('[class*="ad-info"] button'),
                document.querySelector('[aria-label="Why this ad?"]'),
                document.querySelector('[aria-label="About this ad"]'),
                // YouTube sometimes renders it as an SVG button
                ...Array.from(document.querySelectorAll('.ytp-ad-player-overlay button'))
            ].filter(Boolean);
            for (const btn of candidates) {
                try { btn.click(); return true; } catch(e) {}
            }
            return false;
        }""")
        if clicked_info:
            print("    ✅ ⓘ clicked via JS fallback")
        else:
            print("    ⚠️  ⓘ button not found — skipping advertiser lookup")
            return ""

    await asyncio.sleep(2)

    # First try to extract advertiser name directly from the "Why this ad?" dialog
    # (no new tab needed — YouTube often shows it inline)
    paid_for_by = ""
    try:
        dialog_text = await page.inner_text(
            "ytd-about-this-ad-renderer, ytd-ad-feedback-dialog-renderer, "
            "[class*='why-this-ad'], [class*='ad-feedback']",
            timeout=3000
        )
        match = re.search(r"[Pp]aid\s+for\s+by\s*[:\-]?\s*(.+?)(?:\n|$)", dialog_text)
        if match:
            paid_for_by = match.group(1).strip()
        if not paid_for_by:
            # Try the advertiser name element directly inside the dialog
            paid_for_by = await safe_text(
                page,
                "ytd-about-this-ad-renderer .advertiser-name, "
                "ytd-ad-feedback-dialog-renderer .advertiser-name, "
                "[class*='advertiser-name']",
                timeout=2000
            )
        if paid_for_by:
            print(f"    ✅ Advertiser from inline dialog: {paid_for_by}")
    except Exception:
        pass

    # If inline dialog didn't yield a name, try clicking 'About this advertiser' link
    if not paid_for_by:
        about_selectors = [
            "a[href*='adscenter.google.com']",
            "a[href*='adssettings.google.com']",
            "ytd-button-renderer:has-text('About this advertiser')",
            "button:has-text('About this advertiser')",
            "a:has-text('About this advertiser')",
            ".ytd-ad-feedback-dialog-renderer a",
        ]
        for sel in about_selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=2000)
                if el:
                    await el.evaluate("el => el.removeAttribute('target')")
                    await el.click()
                    print(f"    ✅ 'About this advertiser' clicked")
                    await asyncio.sleep(3)
                    break
            except Exception:
                continue

        # Scrape 'Paid for by' from new tab or same-page navigation
        all_pages = page.context.pages
        if len(all_pages) > 1:
            info_page = all_pages[-1]
            try:
                await info_page.wait_for_load_state("domcontentloaded", timeout=10000)
                body_text = await info_page.inner_text("body")
                match = re.search(r"[Pp]aid\s+for\s+by\s*[:\-]?\s*(.+?)(?:\n|$)", body_text)
                if match:
                    paid_for_by = match.group(1).strip()
                if not paid_for_by:
                    paid_for_by = await safe_text(
                        info_page, ".advertiser-name, [class*='paid-for']", timeout=3000
                    )
            except Exception as e:
                print(f"    ⚠️  New tab error: {e}")
            finally:
                await info_page.close()
        else:
            try:
                body_text = await page.inner_text(
                    "ytd-ad-feedback-dialog-renderer, #content", timeout=4000
                )
                match = re.search(r"[Pp]aid\s+for\s+by\s*[:\-]?\s*(.+?)(?:\n|$)", body_text)
                if match:
                    paid_for_by = match.group(1).strip()
            except Exception:
                pass

    await click_if_exists(page, "button[aria-label='Close']", timeout=2000)
    await asyncio.sleep(0.5)
    return paid_for_by


# ══════════════════════════════════════════════════════════════════
#  SCREENSHOT
# ══════════════════════════════════════════════════════════════════

async def take_screenshot(page: Page, label: str) -> str:
    ts = datetime.now().strftime("%H%M%S%f")
    path = OUTPUT_DIR / f"ad_{label}_{ts}.png"
    try:
        await page.screenshot(path=str(path), clip={"x": 0, "y": 0, "width": 980, "height": 720})
        return str(path)
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════
#  MAIN AD HANDLING LOOP
# ══════════════════════════════════════════════════════════════════

async def handle_ads_for_video(page: Page, account_id: str, persona: str, video_url: str) -> list:
    ads_captured = []
    consecutive_no_ad = 0
    ad_index = 0

    print(f"  ⏳ Waiting for ads…")
    for _ in range(30):   # wait up to 15s
        if await is_ad_playing(page):
            break
        await asyncio.sleep(0.5)
    else:
        print("  ℹ️  No ad in first 15s")
        return ads_captured

    while True:
        playing = await is_ad_playing(page)
        if not playing:
            consecutive_no_ad += 1
            # Allow up to 6 seconds gap between sequential ads (e.g. ad 1 → ad 2)
            if consecutive_no_ad >= 12:
                break
            await asyncio.sleep(0.5)
            continue

        # New ad detected — reset gap counter
        consecutive_no_ad = 0

        # Only process if this is a new ad (not the same ad we already captured)
        ad_index += 1
        print(f"\n  🎯 Ad #{ad_index} detected!")

        await pause_ad(page)
        await asyncio.sleep(0.4)

        details = await extract_ad_details_js(page)
        screenshot = await take_screenshot(page, f"{account_id}_ad{ad_index}")

        print(f"    📦 Title    : {details.get('ad_title') or '—'}")
        print(f"    🔗 Link     : {details.get('ad_link') or '—'}")
        print(f"    ⏱  Duration : {details.get('ad_duration_remaining') or '—'}")

        paid_for_by = await get_advertiser_name(page)
        print(f"    🏢 Paid for by : {paid_for_by or '—'}")

        record = {
            "timestamp":             datetime.now().isoformat(),
            "account_id":            account_id,
            "persona":               persona,
            "video_url":             video_url,
            "ad_index":              ad_index,
            "ad_type":               details.get("ad_type", ""),
            "ad_title":              details.get("ad_title", ""),
            "ad_link":               details.get("ad_link", ""),
            "advertiser_name":       details.get("advertiser_name", ""),
            "paid_for_by":           paid_for_by,
            "ad_duration_remaining": details.get("ad_duration_remaining", ""),
            "skip_available":        details.get("skip_available", ""),
            "companion_title":       details.get("companion_title", ""),
            "overlay_text_dump":     details.get("overlay_text_dump", ""),
            "screenshot":            screenshot,
        }
        ads_captured.append(record)
        ALL_ADS.append(record)

        await resume_video(page)
        await asyncio.sleep(1)

        # Wait for this specific ad to finish before looping for the next one
        prev_dur = details.get("ad_duration_remaining", "X")
        stale = 0
        max_wait = 120  # safety cap: never wait more than 2 minutes per ad
        elapsed = 0
        while await is_ad_playing(page):
            cur_dur = await safe_text(page, ".ytp-ad-duration-remaining", timeout=1500)
            if cur_dur and cur_dur == prev_dur:
                stale += 1
                if stale > 40:  # 20s of no progress → force-continue
                    print("    ⚠️  Ad stuck (no progress), forcing continue")
                    # Try clicking skip button one more time before giving up
                    await click_if_exists(page, ".ytp-skip-ad-button, .ytp-ad-skip-button-slot button", timeout=1500)
                    break
            else:
                stale = 0
                prev_dur = cur_dur
            elapsed += 1
            if elapsed > max_wait * 2:
                print("    ⚠️  Max wait exceeded, moving on")
                break
            await asyncio.sleep(0.5)

        # Brief pause to let YouTube transition between sequential ads
        await asyncio.sleep(1.5)

    print(f"  ✅ {len(ads_captured)} ad(s) captured")
    return ads_captured


# ══════════════════════════════════════════════════════════════════
#  FAST-FORWARD  (percentage-based)
# ══════════════════════════════════════════════════════════════════

async def get_video_duration(page: Page) -> float:
    try:
        return await page.evaluate("""() => {
            const v = document.querySelector('.html5-main-video');
            return (v && isFinite(v.duration)) ? v.duration : 0;
        }""")
    except Exception:
        return 0


async def seek_to_percent(page: Page, pct: float):
    try:
        await page.evaluate(f"""() => {{
            const v = document.querySelector('.html5-main-video');
            if (v && isFinite(v.duration) && v.duration > 0) {{
                v.currentTime = v.duration * {pct} - 2;
            }}
        }}""")
        await asyncio.sleep(1.5)
    except Exception:
        pass


async def check_midroll_ads(page: Page, account_id: str, persona: str, video_url: str):
    duration = await get_video_duration(page)
    if duration < 60:
        print("  ℹ️  Video too short for mid-rolls")
        return

    for pct, label in [(0.25, "25%"), (0.50, "50%"), (0.75, "75%")]:
        target_sec = int(duration * pct)
        print(f"\n  ⏩ Seeking to {label} ({target_sec}s / {int(duration)}s total)")
        await seek_to_percent(page, pct)

        ad_found = False
        for _ in range(16):   # 8s window
            if await is_ad_playing(page):
                print(f"  🎯 Mid-roll at {label}!")
                await handle_ads_for_video(page, account_id, persona, f"{video_url}#{label}")
                ad_found = True
                break
            await asyncio.sleep(0.5)

        if not ad_found:
            print(f"  ℹ️  No mid-roll at {label}")


# ══════════════════════════════════════════════════════════════════
#  LOGIN
# ══════════════════════════════════════════════════════════════════

async def login_google(page: Page, email: str, password: str) -> bool:
    print(f"  🔑 Logging in as {email}…")
    try:
        await page.goto("https://accounts.google.com/signin", timeout=60000)
        # Wait for the page to settle — Google sometimes renders slowly
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass  # continue even if networkidle times out

        # Email field — try multiple selectors Google uses
        email_selectors = [
            "input[type='email']",
            "input#identifierId",
            "input[name='identifier']",
        ]
        filled_email = False
        for sel in email_selectors:
            try:
                await page.wait_for_selector(sel, timeout=15000, state="visible")
                await page.fill(sel, email)
                filled_email = True
                print(f"    ✅ Email field found: {sel}")
                break
            except Exception:
                continue

        if not filled_email:
            print("  ❌ Could not find email input field")
            return False

        # Click Next after email
        next_selectors = ["#identifierNext", "button:has-text('Next')", "[jsname='LgbsSe']"]
        for sel in next_selectors:
            try:
                await page.click(sel, timeout=5000)
                break
            except Exception:
                continue

        await asyncio.sleep(3)

        # Password field
        pwd_selectors = [
            "input[type='password']",
            "input[name='password']",
            "input[name='Passwd']",
        ]
        filled_pwd = False
        for sel in pwd_selectors:
            try:
                await page.wait_for_selector(sel, timeout=15000, state="visible")
                await page.fill(sel, password)
                filled_pwd = True
                print(f"    ✅ Password field found: {sel}")
                break
            except Exception:
                continue

        if not filled_pwd:
            print("  ❌ Could not find password input field")
            return False

        # Click Next after password
        pwd_next_selectors = ["#passwordNext", "button:has-text('Next')", "[jsname='LgbsSe']"]
        for sel in pwd_next_selectors:
            try:
                await page.click(sel, timeout=5000)
                break
            except Exception:
                continue

        # Wait for post-login redirect — give it extra time for 2FA / slow networks
        print("  ⏳ Waiting for login to complete (up to 30s — handle any 2FA prompt now)…")
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            pass

        url = page.url
        if any(x in url for x in ["myaccount.google.com", "youtube.com", "google.com/u/"]):
            print("  ✅ Logged in!")
            return True

        # 2FA / verification prompt — wait an extra 30s for manual completion
        if any(x in url for x in ["signin", "challenge", "verification", "accounts.google"]):
            print("  ⚠️  2FA / verification detected — waiting 30s for manual completion…")
            await asyncio.sleep(30)
            if any(x in page.url for x in ["myaccount.google.com", "youtube.com", "google.com/u/"]):
                print("  ✅ Logged in after 2FA!")
                return True

        print(f"  ⚠️  Unexpected URL after login: {page.url[:70]}")
        return False
    except Exception as e:
        print(f"  ❌ Login error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
#  PER-ACCOUNT RUNNER
# ══════════════════════════════════════════════════════════════════

async def run_account(account: dict, playwright):
    print(f"\n{'═'*60}")
    print(f"🚀  {account['id']}  |  {account['persona']}")
    print(f"{'═'*60}")

    profile_dir = OUTPUT_DIR / f"profile_{account['id']}"
    profile_dir.mkdir(exist_ok=True)

    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        args=[
            "--autoplay-policy=no-user-gesture-required",
            "--disable-blink-features=AutomationControlled",
            "--lang=en-IN",
        ],
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        viewport={"width": 1280, "height": 800},
        geolocation={"latitude": 28.6139, "longitude": 77.2090},
        permissions=["geolocation"],
    )
    page = browser.pages[0] if browser.pages else await browser.new_page()

    # Force YouTube to India locale
    await page.goto("https://www.youtube.com/?gl=IN&hl=en", timeout=30000)
    await asyncio.sleep(2)

    avatar = await page.query_selector("button#avatar-btn, yt-img-shadow#avatar")
    if not avatar:
        ok = await login_google(page, account["email"], account["password"])
        if not ok:
            print("  ❌ Login failed — skipping")
            await browser.close()
            return

    videos_done = 0
    for video_url in account["seed_videos"]:
        if videos_done >= MAX_VIDEOS_PER_ACCOUNT:
            break

        print(f"\n▶  {video_url[:80]}")
        await page.goto(video_url, timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)

        await handle_ads_for_video(page, account["id"], account["persona"], video_url)
        await check_midroll_ads(page, account["id"], account["persona"], video_url)

        videos_done += 1
        await asyncio.sleep(2)

    await browser.close()
    total = sum(1 for a in ALL_ADS if a["account_id"] == account["id"])
    print(f"\n✅ {account['id']} done — {total} ad(s) captured")


# ══════════════════════════════════════════════════════════════════
#  SAVE RESULTS
# ══════════════════════════════════════════════════════════════════

def save_results():
    if not ALL_ADS:
        print("\n⚠️  No ads captured.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = OUTPUT_DIR / f"ads_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(ALL_ADS, f, indent=2, ensure_ascii=False)
    print(f"\n💾 JSON  → {json_path}")

    try:
        import pandas as pd
        df = pd.DataFrame(ALL_ADS)
        csv_path  = OUTPUT_DIR / f"ads_{ts}.csv"
        xlsx_path = OUTPUT_DIR / f"ads_{ts}.xlsx"
        df.to_csv(csv_path, index=False)
        df.to_excel(xlsx_path, index=False)
        print(f"💾 CSV   → {csv_path}")
        print(f"💾 XLSX  → {xlsx_path}")
    except ImportError:
        pass

    print(f"\n{'─'*50}")
    print(f"📊 SUMMARY — {len(ALL_ADS)} total ad(s)")
    print(f"{'─'*50}")
    for acc in ACCOUNTS:
        n = sum(1 for a in ALL_ADS if a["account_id"] == acc["id"])
        print(f"  {acc['id']} ({acc['persona']}) : {n}")

    print("\nSample:")
    for ad in ALL_ADS[:3]:
        print(f"  [{ad['account_id']}] "
              f"{ad.get('ad_title') or ad.get('advertiser_name') or '(no title)'} | "
              f"paid by: {ad.get('paid_for_by') or '—'} | "
              f"link: {ad.get('ad_link','')[:50]}")


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

async def main():
    async with async_playwright() as pw:
        for account in ACCOUNTS:
            await run_account(account, pw)
    save_results()


if __name__ == "__main__":
    asyncio.run(main())