"""Handshake job scraper using Playwright.

Note: Handshake requires university SSO login. This scraper will open a
browser window for you to log in, then scrape after authentication.
"""

from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus
from utils.database import insert_job


def scrape_listings(keyword, location="", posted_within_days=7, max_pages=3):
    """Scrape Handshake for internship listings.

    Handshake requires login — this opens a visible browser for SSO auth,
    then scrapes once you're logged in.
    """
    jobs_found = []

    with sync_playwright() as p:
        # Handshake needs visible browser for SSO login
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Navigate to Handshake login
        page.goto("https://app.joinhandshake.com/login", timeout=30000)

        # Wait for user to complete SSO login (detect dashboard/jobs page)
        print("\n[Handshake] Please log in with your university credentials...")
        print("[Handshake] Waiting for login to complete...")

        try:
            page.wait_for_url("**/stu/**", timeout=120000)  # 2 min timeout for login
        except Exception:
            print("[Handshake] Login timeout — skipping Handshake.")
            browser.close()
            return jobs_found

        print("[Handshake] Login successful! Scraping listings...")

        # Navigate to job search
        search_url = f"https://app.joinhandshake.com/stu/postings?page=1&per_page=25&sort_direction=desc&sort_column=default"
        if keyword:
            search_url += f"&keywords={quote_plus(keyword)}"

        for page_num in range(1, max_pages + 1):
            url = search_url.replace("page=1", f"page={page_num}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Handshake job card selectors
            cards = page.query_selector_all("[data-hook='jobs-card'], div[class*='style__card'], a[href*='/postings/']")

            if not cards:
                break

            for card in cards:
                try:
                    title_el = card.query_selector("h3, [class*='title'], [data-hook='job-title']")
                    company_el = card.query_selector("[data-hook='employer-name'], [class*='employer']")
                    location_el = card.query_selector("[data-hook='job-location'], [class*='location']")

                    if not title_el:
                        continue

                    title = title_el.inner_text().strip()

                    # Get URL from card link
                    href = card.get_attribute("href") or ""
                    if not href:
                        link_el = card.query_selector("a[href*='/postings/']")
                        href = link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        href = "https://app.joinhandshake.com" + href

                    company = company_el.inner_text().strip() if company_el else "Unknown"
                    loc = location_el.inner_text().strip() if location_el else ""

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

        browser.close()

    return jobs_found
