"""ZipRecruiter job scraper using Playwright with persistent browser session."""

import os
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from urllib.parse import quote_plus
from utils.database import insert_job

# Persistent profile directory so cookies/session survive between runs
PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "browser_profiles", "ziprecruiter")


def build_url(keyword, location, posted_within_days=7):
    """Build ZipRecruiter search URL."""
    base = "https://www.ziprecruiter.com/jobs-search"
    return f"{base}?search={quote_plus(keyword)}&location={quote_plus(location)}&days={posted_within_days}"


def _handle_captcha(page):
    """Check for CAPTCHA / Cloudflare challenge and wait for user to solve it. Returns True if ok to proceed."""
    content = page.content().lower()
    title = page.title().lower()
    is_blocked = (
        "captcha" in content
        or "challenge" in content
        or "just a moment" in title
        or "verifying you are human" in content
    )
    if is_blocked:
        print("\n[ZipRecruiter] CAPTCHA/Cloudflare challenge detected — please solve it in the browser window.")
        print("[ZipRecruiter] Waiting for you to complete it...")
        try:
            # Wait until the page title changes away from Cloudflare's interstitial
            # AND the body no longer contains challenge text
            page.wait_for_function(
                """() => {
                    const t = document.title.toLowerCase();
                    const b = document.body.innerHTML.toLowerCase();
                    return !t.includes('just a moment')
                        && !b.includes('verifying you are human')
                        && !b.includes('captcha');
                }""",
                timeout=120000,
            )
            print("[ZipRecruiter] Challenge passed! Continuing...")
            page.wait_for_timeout(3000)
            return True
        except Exception:
            print("[ZipRecruiter] Challenge timeout — skipping ZipRecruiter.")
            return False
    return True


def scrape_listings(keyword, location, posted_within_days=7, max_pages=3):
    """Scrape ZipRecruiter for internship listings."""
    jobs_found = []
    os.makedirs(PROFILE_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        for page_num in range(1, max_pages + 1):
            url = build_url(keyword, location, posted_within_days)
            if page_num > 1:
                url += f"&page={page_num}"

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                break
            page.wait_for_timeout(3000)

            if not _handle_captcha(page):
                break

            # Cards are divs with class containing 'job_result_two_pane'
            cards = page.query_selector_all("[class*='job_result_two_pane']")

            if not cards:
                break

            for card in cards:
                try:
                    # Title is in an h2 element
                    title_el = card.query_selector("h2")
                    # Company and location use data-testid attributes
                    company_el = card.query_selector("[data-testid='job-card-company']")
                    location_el = card.query_selector("[data-testid='job-card-location']")

                    if not title_el:
                        continue

                    title = title_el.inner_text().strip()
                    if not title:
                        continue

                    company = company_el.inner_text().strip() if company_el else "Unknown"
                    loc = location_el.inner_text().strip() if location_el else ""

                    # Job URL: extract job_id from article id and build search URL with lk param
                    article = card.query_selector("article[id^='job-card-']")
                    if article:
                        article_id = article.get_attribute("id") or ""
                        job_id = article_id.replace("job-card-", "")
                        href = (f"https://www.ziprecruiter.com/jobs-search"
                                f"?search={quote_plus(keyword)}"
                                f"&location={quote_plus(location)}"
                                f"&lk={job_id}")
                    else:
                        # Fallback: use first link in the card
                        link = card.query_selector("a[href]")
                        href = link.get_attribute("href") if link else ""
                        if href and href.startswith("/"):
                            href = "https://www.ziprecruiter.com" + href

                    if not href:
                        continue

                    # Detect "1-Click Apply" via card text content
                    card_text = card.inner_text().lower()
                    is_quick = "1-click apply" in card_text or "one click apply" in card_text

                    job = {
                        "platform": "ziprecruiter",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "url": href,
                        "quick_apply": is_quick,
                    }
                    jobs_found.append(job)
                    insert_job(**job)

                except Exception:
                    continue

        context.close()
        browser.close()

    return jobs_found
