"""Indeed job scraper using Playwright for dynamic content."""

from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus
from utils.database import insert_job


def build_url(keyword, location, posted_within_days=7):
    """Build Indeed search URL."""
    # fromage maps: 1=last 24h, 3=last 3 days, 7=last 7 days, 14=last 14 days
    fromage = min(posted_within_days, 14)
    base = "https://www.indeed.com/jobs"
    return f"{base}?q={quote_plus(keyword)}&l={quote_plus(location)}&fromage={fromage}&sort=date"


def scrape_listings(keyword, location, posted_within_days=7, max_pages=3):
    """Scrape Indeed for internship listings."""
    jobs_found = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for page_num in range(max_pages):
            url = build_url(keyword, location, posted_within_days)
            if page_num > 0:
                url += f"&start={page_num * 10}"

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)  # let dynamic content load

            # Indeed uses various card selectors depending on layout
            cards = page.query_selector_all("div.job_seen_beacon, div.jobsearch-ResultsList > div")

            if not cards:
                break

            for card in cards:
                try:
                    title_el = card.query_selector("h2.jobTitle a, h2 a")
                    company_el = card.query_selector("[data-testid='company-name'], span.companyName")
                    location_el = card.query_selector("[data-testid='text-location'], div.companyLocation")
                    date_el = card.query_selector("span.date, span[data-testid='myJobsStateDate']")

                    if not title_el:
                        continue

                    title = title_el.inner_text().strip()
                    href = title_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://www.indeed.com" + href

                    company = company_el.inner_text().strip() if company_el else "Unknown"
                    loc = location_el.inner_text().strip() if location_el else ""
                    date_posted = date_el.inner_text().strip() if date_el else ""

                    job = {
                        "platform": "indeed",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "url": href,
                        "date_posted": date_posted,
                    }
                    jobs_found.append(job)
                    insert_job(**job)

                except Exception:
                    continue

        browser.close()

    return jobs_found
