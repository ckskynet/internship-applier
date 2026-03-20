"""Remote OK job scraper using their public JSON API."""

import requests
from utils.database import insert_job


_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Map search keywords to Remote OK tag slugs
TAG_MAP = {
    "cybersecurity": "security",
    "security analyst": "security",
    "information security": "security",
    "soc analyst": "security",
    "it support": "support",
    "it help desk": "support",
    "help desk": "support",
}


def _keyword_to_tags(keyword):
    """Convert a search keyword to Remote OK tag slugs."""
    kw = keyword.lower().replace(" intern", "").strip()
    # Direct match
    if kw in TAG_MAP:
        return [TAG_MAP[kw]]
    # Partial match
    for pattern, tag in TAG_MAP.items():
        if pattern in kw:
            return [tag]
    # Fall back to first word as tag
    return [kw.split()[0]]


def _matches_keyword(job, keyword):
    """Check if a job matches the search keyword."""
    kw = keyword.lower()
    title = job.get("position", "").lower()
    tags = [t.lower() for t in job.get("tags", [])]
    description = job.get("description", "").lower()

    # Check title, tags, and description
    terms = kw.replace(" intern", "").strip().split()
    return any(
        term in title or term in " ".join(tags) or term in description[:500]
        for term in terms
    )


def scrape_listings(keyword, location="", posted_within_days=7, max_pages=1):
    """Scrape Remote OK for job listings matching the keyword.

    Remote OK is remote-only so the location parameter is ignored.
    """
    jobs_found = []
    tags = _keyword_to_tags(keyword)

    for tag in tags:
        url = f"https://remoteok.com/remote-{tag}-jobs.json"
        try:
            resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [Remote OK] Failed to fetch {tag} jobs: {e}")
            continue

        # First item is metadata, skip it
        listings = data[1:] if len(data) > 1 else []

        for item in listings:
            if not _matches_keyword(item, keyword):
                continue

            title = item.get("position", "").strip()
            company = item.get("company", "Unknown").strip()
            loc = item.get("location", "Remote").strip() or "Remote"
            job_url = item.get("url", "") or item.get("apply_url", "")
            date_posted = item.get("date", "")
            description = item.get("description", "")[:2000]

            if not title or not job_url:
                continue

            job = {
                "platform": "remoteok",
                "title": title,
                "company": company,
                "location": loc,
                "url": job_url,
                "description": description,
                "date_posted": date_posted,
            }
            jobs_found.append(job)
            insert_job(**job)

    return jobs_found
