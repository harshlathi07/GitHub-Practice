"""
YouTube Ad Scraper v2
-----------------------------------
Features:
✅ 2-account persona system
✅ Detects ads reliably using player state
✅ Handles sequential ads (2 ads back-to-back)
✅ Pauses ads instantly
✅ Extracts:
    - ad title
    - advertiser
    - paid for by
    - destination link
    - duration
✅ Fast-forwards video to discover mid-rolls
✅ Uses persistent Chrome profiles
✅ Network interception support
✅ Robust JS-based DOM extraction
✅ Saves JSON + CSV

INSTALL:
pip install playwright pandas
playwright install chromium

RUN:
python scraper_v2.py
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
from playwright.async_api import async_playwright

# =========================================================
# CONFIG
# =========================================================

OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(exist_ok=True)

ACCOUNTS = [
    {
        "id": "tech_delhi",
        "persona": "Male, Delhi, Tech Enthusiast",
        "email": "akshay12kumar866@gmail.com",
        "password": "AK472047",
        "seed_videos": [
            "https://www.youtube.com/watch?v=bHKN1TDIP08",
            "https://www.youtube.com/watch?v=3N_q9o8gTOE",
        ],
    },
    {
        "id": "beauty_mumbai",
        "persona": "Female, Mumbai, Beauty & Lifestyle",
        "email": "abhay12kumar877@gmail.com",
        "password": "AK472047",
        "seed_videos": [
            "https://www.youtube.com/watch?v=aBXbMkFpFgQ",
            "https://www.youtube.com/watch?v=VOx8yCmT4lE",
        ],
    },
]

ALL_ADS = []

# =========================================================
# UTILITIES
# =========================================================


async def safe_click(page, selector, timeout=3000):
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)
        return True
    except:
        return False


async def safe_text(page, selector, timeout=2000):
    try:
        el = await page.wait_for_selector(selector, timeout=timeout)
        return (await el.inner_text()).strip()
    except:
        return ""


# =========================================================
# AD DETECTION
# =========================================================


async def is_ad_playing(page):
    try:
        return await page.evaluate("""
        () => {
            const p = document.querySelector('.html5-video-player');
            return p && p.classList.contains('ad-showing');
        }
        """)
    except:
        return False


async def wait_for_ad(page, timeout=20):
    for _ in range(timeout * 2):

        if await is_ad_playing(page):
            return True

        await asyncio.sleep(0.5)

    return False


# =========================================================
# VIDEO CONTROL
# =========================================================


async def pause_video(page):
    try:
        await page.evaluate("""
        () => {
            const v = document.querySelector('video');
            if(v && !v.paused) v.pause();
        }
        """)
    except:
        pass


async def resume_video(page):
    try:
        await page.evaluate("""
        () => {
            const v = document.querySelector('video');
            if(v && v.paused) v.play();
        }
        """)
    except:
        pass


# =========================================================
# EXTRACT AD DATA
# =========================================================


async def extract_ad_data(page):

    data = await page.evaluate("""
    () => {

        const txt = (sel) => {
            const el = document.querySelector(sel);
            return el ? el.innerText.trim() : '';
        };

        const attr = (sel, attrName) => {
            const el = document.querySelector(sel);
            return el ? el.getAttribute(attrName) || '' : '';
        };

        const title =
            txt('.ytp-ad-text') ||
            txt('.ytp-ad-headline') ||
            txt('.ytp-ad-button-text') ||
            txt('[class*="headline"]');

        const advertiser =
            txt('.ytp-ad-visit-advertiser-button') ||
            txt('.ytp-ad-advertiser-name');

        const link =
            attr('.ytp-ad-visit-advertiser-button', 'href') ||
            attr('a[href]', 'href');

        const duration =
            txt('.ytp-ad-duration-remaining');

        const skip =
            !!document.querySelector('.ytp-skip-ad-button');

        const sponsored =
            !!document.querySelector('.ytp-ad-simple-ad-badge');

        return {
            title,
            advertiser,
            link,
            duration,
            skip,
            sponsored
        };
    }
    """)

    return data


# =========================================================
# GET PAID FOR BY
# =========================================================


async def get_paid_for_by(page):

    try:

        await pause_video(page)

        await page.mouse.move(600, 300)

        await asyncio.sleep(1)

        clicked = await page.evaluate("""
        () => {

            const buttons = [...document.querySelectorAll('button')];

            const btn = buttons.find(b =>
                b.ariaLabel?.toLowerCase().includes('ad') ||
                b.innerText?.toLowerCase().includes('ad')
            );

            if(btn){
                btn.click();
                return true;
            }

            return false;
        }
        """)

        if not clicked:
            return ""

        await asyncio.sleep(2)

        body = await page.evaluate("""
        () => document.body.innerText
        """)

        match = re.search(
            r"Paid for by\\s*:?\\s*(.+)",
            body,
            re.IGNORECASE
        )

        if match:
            return match.group(1).split("\\n")[0].strip()

    except Exception as e:
        print("paid-for-by error:", e)

    return ""


# =========================================================
# NETWORK INTERCEPTION
# =========================================================


async def setup_network_logging(page):

    async def handle_response(response):

        try:

            url = response.url

            if "youtubei/v1/player" in url:

                text = await response.text()

                if "adPlacements" in text:
                    print("📡 Ad API detected")

        except:
            pass

    page.on("response", handle_response)


# =========================================================
# SCREENSHOT
# =========================================================


async def take_screenshot(page, label):

    ts = datetime.now().strftime("%H%M%S")

    path = OUTPUT_DIR / f"{label}_{ts}.png"

    await page.screenshot(path=str(path))

    return str(path)


# =========================================================
# HANDLE ADS
# =========================================================


async def handle_video_ads(page, account, video_url):

    captured = []

    ad_counter = 0

    found = await wait_for_ad(page)

    if not found:
        print("No ads found")
        return captured

    print("🎯 Ad detected")

    previous_signature = ""

    while await is_ad_playing(page):

        await pause_video(page)

        data = await extract_ad_data(page)

        signature = f"{data['title']}|{data['advertiser']}"

        if signature != previous_signature:

            ad_counter += 1

            print(f"\n📺 AD #{ad_counter}")
            print("Title:", data["title"])
            print("Advertiser:", data["advertiser"])
            print("Link:", data["link"])

            paid_for_by = await get_paid_for_by(page)

            screenshot = await take_screenshot(
                page,
                f"{account['id']}_ad{ad_counter}"
            )

            record = {
                "timestamp": datetime.now().isoformat(),
                "account": account["id"],
                "persona": account["persona"],
                "video_url": video_url,
                "ad_number": ad_counter,
                "title": data["title"],
                "advertiser": data["advertiser"],
                "paid_for_by": paid_for_by,
                "link": data["link"],
                "duration": data["duration"],
                "skip": data["skip"],
                "screenshot": screenshot,
            }

            ALL_ADS.append(record)
            captured.append(record)

            previous_signature = signature

        await resume_video()

        # WAIT FOR AD CHANGE
        stale = 0

        while await is_ad_playing(page):

            cur = await extract_ad_data(page)

            new_sig = f"{cur['title']}|{cur['advertiser']}"

            if new_sig != previous_signature:
                break

            stale += 1

            if stale > 40:
                break

            await asyncio.sleep(0.5)

    return captured


# =========================================================
# FAST FORWARD
# =========================================================


async def seek_percent(page, pct):

    await page.evaluate(f"""
    () => {{

        const v = document.querySelector('video');

        if(v && isFinite(v.duration)){{
            v.currentTime = v.duration * {pct};
        }}
    }}
    """)

    await asyncio.sleep(2)


async def scan_midrolls(page, account, video_url):

    duration = await page.evaluate("""
    () => {
        const v = document.querySelector('video');
        return v ? v.duration : 0;
    }
    """)

    if duration < 120:
        return

    for pct in [0.25, 0.5, 0.75]:

        print(f"\n⏩ Seeking to {int(pct*100)}%")

        await seek_percent(page, pct)

        if await wait_for_ad(page, timeout=8):

            print("🎯 Mid-roll found")

            await handle_video_ads(
                page,
                account,
                video_url + f"#{pct}"
            )


# =========================================================
# LOGIN
# =========================================================


async def login(page, email, password):

    print("🔑 Logging in")

    await page.goto(
        "https://accounts.google.com/signin",
        timeout=60000
    )

    await page.wait_for_load_state("domcontentloaded")

    email_selectors = [
        "input[type='email']",
        "#identifierId",
        "input[name='identifier']",
    ]

    filled = False

    for sel in email_selectors:

        try:
            await page.wait_for_selector(sel, timeout=10000)

            await page.fill(sel, email)

            filled = True

            break

        except:
            pass

    if not filled:
        print("❌ Email field not found")
        return False

    await safe_click(page, "#identifierNext")

    await asyncio.sleep(3)

    pwd_selectors = [
        "input[type='password']",
        "input[name='Passwd']",
    ]

    filled = False

    for sel in pwd_selectors:

        try:
            await page.wait_for_selector(sel, timeout=10000)

            await page.fill(sel, password)

            filled = True

            break

        except:
            pass

    if not filled:
        print("❌ Password field not found")
        return False

    await safe_click(page, "#passwordNext")

    print("⏳ Waiting for login")

    await asyncio.sleep(10)

    return True


# =========================================================
# RUN ACCOUNT
# =========================================================


async def run_account(playwright, account):

    print("\n" + "=" * 60)
    print(account["id"])
    print(account["persona"])
    print("=" * 60)

    profile_dir = OUTPUT_DIR / f"profile_{account['id']}"

    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        viewport={"width": 1400, "height": 900},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--autoplay-policy=no-user-gesture-required",
        ],
    )

    page = browser.pages[0]

    await setup_network_logging(page)

    await page.goto(
        "https://www.youtube.com/?gl=IN&hl=en"
    )

    await asyncio.sleep(3)

    avatar = await page.query_selector(
        "button#avatar-btn"
    )

    if not avatar:

        ok = await login(
            page,
            account["email"],
            account["password"]
        )

        if not ok:
            print("Login failed")
            return

    for video in account["seed_videos"]:

        print("\n▶", video)

        await page.goto(video)

        await page.wait_for_load_state(
            "domcontentloaded"
        )

        await asyncio.sleep(4)

        await handle_video_ads(
            page,
            account,
            video
        )

        await scan_midrolls(
            page,
            account,
            video
        )

    await browser.close()


# =========================================================
# SAVE
# =========================================================


def save_results():

    if not ALL_ADS:
        print("No ads captured")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = OUTPUT_DIR / f"ads_{ts}.json"

    with open(json_path, "w") as f:
        json.dump(ALL_ADS, f, indent=2)

    csv_path = OUTPUT_DIR / f"ads_{ts}.csv"

    pd.DataFrame(ALL_ADS).to_csv(
        csv_path,
        index=False
    )

    print("\n💾 Saved")
    print(json_path)
    print(csv_path)

    print("\n📊 TOTAL ADS:", len(ALL_ADS))


# =========================================================
# MAIN
# =========================================================


async def main():

    async with async_playwright() as pw:

        for account in ACCOUNTS:

            try:
                await run_account(pw, account)

            except Exception as e:
                print("Account failed:", e)

    save_results()


if __name__ == "__main__":
    asyncio.run(main())