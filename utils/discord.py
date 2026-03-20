"""Discord webhook notifications for job search and application updates."""

import os
import requests
from datetime import datetime


def _get_webhook_url():
    return os.environ.get("DISCORD_WEBHOOK_URL", "")


def send_search_summary(jobs_by_platform):
    """Send a summary of new listings found after a search run.

    Args:
        jobs_by_platform: dict like {"indeed": [job, ...], "ziprecruiter": [job, ...]}
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return

    total = sum(len(jobs) for jobs in jobs_by_platform.values())
    if total == 0:
        return

    # Build embed fields for each platform
    fields = []
    for platform, jobs in jobs_by_platform.items():
        if not jobs:
            continue
        # Show top 5 listings per platform
        listings = []
        for j in jobs[:5]:
            company = j.get("company", "Unknown")
            title = j.get("title", "")[:50]
            location = j.get("location", "")[:20]
            listings.append(f"**{title}**\n{company} — {location}")
        value = "\n\n".join(listings)
        if len(jobs) > 5:
            value += f"\n\n*...and {len(jobs) - 5} more*"
        fields.append({
            "name": f"{platform.title()} ({len(jobs)} new)",
            "value": value[:1024],
            "inline": False,
        })

    payload = {
        "embeds": [{
            "title": f"🔍 Job Search Complete — {total} New Listings",
            "color": 0x5865F2,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Internship Applier"},
        }]
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        print(f"  [Discord] Failed to send notification: {e}")


def send_application_update(job, status):
    """Send a notification when a job application status changes.

    Args:
        job: dict with job details (title, company, location, platform, url)
        status: 'applied', 'skipped', or 'error'
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return

    status_config = {
        "applied": {"emoji": "✅", "color": 0x57F287, "label": "Applied"},
        "skipped": {"emoji": "⏭️", "color": 0x99AAB5, "label": "Skipped"},
        "error":   {"emoji": "❌", "color": 0xED4245, "label": "Error"},
    }
    cfg = status_config.get(status, {"emoji": "📋", "color": 0x5865F2, "label": status})

    payload = {
        "embeds": [{
            "title": f"{cfg['emoji']} {cfg['label']}: {job.get('title', 'Unknown')[:60]}",
            "color": cfg["color"],
            "fields": [
                {"name": "Company", "value": job.get("company", "Unknown"), "inline": True},
                {"name": "Location", "value": job.get("location", "N/A") or "N/A", "inline": True},
                {"name": "Platform", "value": job.get("platform", "").title(), "inline": True},
            ],
            "url": job.get("url", ""),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Internship Applier"},
        }]
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        print(f"  [Discord] Failed to send notification: {e}")
