"""Handshake job scraper using Playwright with persistent browser session.

Note: Handshake requires university SSO login. The first run will prompt
you to log in; subsequent runs reuse the saved session.
"""

import os
import re
from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus
from utils.database import insert_job

# Persistent profile so SSO session survives between runs
PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "browser_profiles", "handshake")


def scrape_listings(keyword, location="", posted_within_days=7, max_pages=5):
    """Scrape Handshake for internship listings.

    Uses a persistent browser profile so SSO login is only needed once.
    """
    jobs_found = []
    os.makedirs(PROFILE_DIR, exist_ok=True)

    with sync_playwright() as p:
        # Persistent context retains SSO cookies between runs
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
        )
        page = context.new_page()

        # Navigate to Handshake — if session is valid, it'll go straight to job search
        page.goto("https://app.joinhandshake.com/job-search", timeout=30000)
        page.wait_for_timeout(3000)

        # Check if we need to log in (redirected to login page)
        if "/login" in page.url or "/sso" in page.url:
            print("\n[Handshake] Session expired — please log in with your university credentials...")
            print("[Handshake] Waiting for login to complete...")

            try:
                page.wait_for_url("**/job-search**", timeout=120000)
            except Exception:
                print("[Handshake] Login timeout — skipping Handshake.")
                context.close()
                return jobs_found

            print("[Handshake] Login successful!")
        else:
            print("[Handshake] Session restored — already logged in.")

        print("[Handshake] Scraping listings...")

        # Navigate to job search
        search_url = "https://app.joinhandshake.com/job-search?page=1&per_page=25&sort_direction=desc&sort_column=default"
        if keyword:
            search_url += f"&keywords={quote_plus(keyword)}"

        for page_num in range(1, max_pages + 1):
            url = search_url.replace("page=1", f"page={page_num}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Extract job cards via JS — each card is the parent container
            # of an <a> link to /job-search/<id>
            cards_data = page.evaluate(r'''() => {
                const links = [...document.querySelectorAll('a[href*="/job-search/"]')]
                    .filter(a => /\/job-search\/\d+/.test(a.href));
                return links.map(a => {
                    let container = a.parentElement;
                    for (let i = 0; i < 5 && container; i++) {
                        if (container.innerText && container.innerText.length > 30) break;
                        container = container.parentElement;
                    }
                    const text = container ? container.innerText : '';
                    const lines = text.split('\n').map(l => l.trim()).filter(l => l);
                    return {
                        href: a.href,
                        ariaLabel: a.getAttribute('aria-label') || '',
                        lines: lines,
                    };
                });
            }''')

            if not cards_data:
                break

            for card in cards_data:
                try:
                    href = card["href"]
                    lines = card["lines"]
                    aria = card["ariaLabel"]

                    # Extract job ID and build clean URL
                    match = re.search(r'/job-search/(\d+)', href)
                    if match:
                        job_id = match.group(1)
                        href = f"https://app.joinhandshake.com/job-search/{job_id}"
                    elif not href.startswith("http"):
                        href = "https://app.joinhandshake.com" + href

                    # Card text lines: [company, title, pay/type, location, ...]
                    # Title from aria-label ("View <title>") or second line
                    title = ""
                    if aria.startswith("View "):
                        title = aria[5:]
                    elif len(lines) >= 2:
                        title = lines[1]

                    if not title:
                        continue

                    company = lines[0] if lines else "Unknown"
                    # Location is usually after pay/type line, contains state abbrev or "Remote"
                    loc = ""
                    for line in lines[3:]:
                        if any(kw in line for kw in ["Remote", ",", "·"]):
                            loc = line.split("∙")[0].strip().rstrip("·").strip()
                            break

                    job = {
                        "platform": "handshake",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "url": href,
                    }
                    jobs_found.append(job)
                    insert_job(**job)

                except Exception:
                    continue

        context.close()

    return jobs_found
