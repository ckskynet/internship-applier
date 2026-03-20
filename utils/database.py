"""SQLite database for tracking job listings and application status."""

import sqlite3
import os
from datetime import datetime
from urllib.parse import urlparse, urlencode, parse_qs

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "applications.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            url TEXT UNIQUE NOT NULL,
            description TEXT,
            date_posted TEXT,
            date_scraped TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            date_applied TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def _normalize_url(url):
    """Strip tracking/session query params so the same job doesn't get inserted twice."""
    parsed = urlparse(url)
    # Keep only the base path for Indeed (jk param is the job key)
    if "indeed.com" in parsed.netloc:
        params = parse_qs(parsed.query)
        if "jk" in params:
            return f"{parsed.scheme}://{parsed.netloc}/viewjob?jk={params['jk'][0]}"
    # For ZipRecruiter, normalize on the lk (listing key) param
    if "ziprecruiter.com" in parsed.netloc:
        params = parse_qs(parsed.query)
        if "lk" in params:
            return f"{parsed.scheme}://{parsed.netloc}/jobs-search?lk={params['lk'][0]}"
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return url


def _is_duplicate(conn, platform, title, company):
    """Check if we already have a job with the same title+company (catches URL variants)."""
    row = conn.execute(
        "SELECT id FROM jobs WHERE platform = ? AND LOWER(title) = LOWER(?) AND LOWER(company) = LOWER(?)",
        (platform, title, company),
    ).fetchone()
    return row is not None


def insert_job(platform, title, company, location, url, description="", date_posted=""):
    conn = get_connection()
    try:
        url = _normalize_url(url)
        if _is_duplicate(conn, platform, title, company):
            return
        conn.execute(
            """INSERT OR IGNORE INTO jobs
               (platform, title, company, location, url, description, date_posted, date_scraped)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (platform, title, company, location, url, description, date_posted,
             datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_jobs(status=None, platform=None):
    conn = get_connection()
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    query += " ORDER BY date_scraped DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_already_applied(title, company):
    """Check if we've already applied to a job with this title at this company."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, status FROM jobs WHERE LOWER(title) = LOWER(?) AND LOWER(company) = LOWER(?) AND status = 'applied'",
        (title, company),
    ).fetchone()
    conn.close()
    return row is not None


def update_job_status(job_id, status, notes=""):
    conn = get_connection()
    now = datetime.now().isoformat() if status == "applied" else None
    conn.execute(
        "UPDATE jobs SET status = ?, date_applied = COALESCE(?, date_applied), notes = ? WHERE id = ?",
        (status, now, notes, job_id),
    )
    conn.commit()
    conn.close()
