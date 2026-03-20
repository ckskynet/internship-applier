"""We Work Remotely job scraper using RSS feeds (bypasses Cloudflare)."""

import xml.etree.ElementTree as ET
import requests
from utils.database import insert_job


_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Category RSS feed slugs
CATEGORY_FEEDS = [
    "remote-programming-jobs",
    "remote-devops-sysadmin-jobs",
    "remote-customer-support-jobs",
    "remote-product-jobs",
]


def _matches_keyword(title, description, skills, keyword):
    """Check if a job matches the search keyword."""
    kw = keyword.lower()
    terms = kw.replace(" intern", "").strip().split()
    searchable = f"{title} {skills} {description[:500]}".lower()
    return any(term in searchable for term in terms)


def _parse_title_company(raw_title):
    """Parse 'Company: Job Title' format from RSS."""
    if ": " in raw_title:
        company, title = raw_title.split(": ", 1)
        return title.strip(), company.strip()
    return raw_title.strip(), "Unknown"


def scrape_listings(keyword, location="", posted_within_days=7, max_pages=1):
    """Scrape We Work Remotely RSS feeds for matching jobs.

    WWR is remote-only so the location parameter is ignored.
    """
    jobs_found = []
    seen_urls = set()

    for category in CATEGORY_FEEDS:
        url = f"https://weworkremotely.com/categories/{category}.rss"
        try:
            resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [WWR] Failed to fetch {category}: {e}")
            continue

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            continue

        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            region = (item.findtext("region") or "Remote").strip()
            skills = (item.findtext("skills") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()

            if not raw_title or not link:
                continue

            if link in seen_urls:
                continue
            seen_urls.add(link)

            title, company = _parse_title_company(raw_title)

            if not _matches_keyword(title, description, skills, keyword):
                continue

            job = {
                "platform": "weworkremotely",
                "title": title,
                "company": company,
                "location": region or "Remote",
                "url": link,
                "description": description[:2000],
                "date_posted": pub_date,
            }
            jobs_found.append(job)
            insert_job(**job)

    return jobs_found
