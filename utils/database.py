"""SQLite database for tracking job listings and application status."""

import json
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
            notes TEXT,
            ai_fit_score INTEGER,
            ai_recommendation TEXT,
            ai_summary TEXT,
            ai_talking_points TEXT
        )
    """)
    # Add AI columns to existing databases
    for col, col_type in [
        ("ai_fit_score", "INTEGER"),
        ("ai_recommendation", "TEXT"),
        ("ai_summary", "TEXT"),
        ("ai_talking_points", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists
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
    # For ZipRecruiter, keep search + location + lk params (lk needs search context to work)
    if "ziprecruiter.com" in parsed.netloc:
        params = parse_qs(parsed.query)
        if "lk" in params:
            kept = {}
            for key in ("search", "location", "lk"):
                if key in params:
                    kept[key] = params[key][0]
            return f"{parsed.scheme}://{parsed.netloc}/jobs-search?{urlencode(kept)}"
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return url


def _is_duplicate(conn, platform, title, company):
    """Check if we already have a job with the same title+company (catches URL variants)."""
    row = conn.execute(
        "SELECT id FROM jobs WHERE platform = ? AND LOWER(title) = LOWER(?) AND LOWER(company) = LOWER(?)",
        (platform, title, company),
    ).fetchone()
    return row is not None


def _is_excluded_title(title):
    """Check if a job title matches any excluded keywords from config."""
    try:
        from utils.config import get_search_prefs
        prefs = get_search_prefs()
        excludes = prefs.get("exclude_title_keywords", [])
        title_lower = title.lower()
        return any(kw.lower() in title_lower for kw in excludes)
    except Exception:
        return False


def insert_job(platform, title, company, location, url, description="", date_posted=""):
    if _is_excluded_title(title):
        return
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


def get_job_by_id(job_id):
    """Fetch a single job by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats():
    """Return status and platform counts."""
    conn = get_connection()
    status_counts = conn.execute(
        "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
    ).fetchall()
    platform_counts = conn.execute(
        "SELECT platform, COUNT(*) as count FROM jobs GROUP BY platform"
    ).fetchall()
    conn.close()
    return {
        "by_status": {r["status"]: r["count"] for r in status_counts},
        "by_platform": {r["platform"]: r["count"] for r in platform_counts},
        "total": sum(r["count"] for r in status_counts),
    }


def get_jobs_paginated(status=None, platform=None, search=None, page=1, per_page=50):
    """Fetch jobs with pagination and optional filters."""
    conn = get_connection()
    query = "SELECT * FROM jobs WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM jobs WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        count_query += " AND status = ?"
        params.append(status)
    if platform:
        query += " AND platform = ?"
        count_query += " AND platform = ?"
        params.append(platform)
    if search:
        query += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        count_query += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        term = f"%{search.lower()}%"
        params.extend([term, term])
    query += " ORDER BY date_scraped DESC LIMIT ? OFFSET ?"

    total = conn.execute(count_query, params).fetchone()[0]
    params.extend([per_page, (page - 1) * per_page])
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def update_job_status(job_id, status, notes=""):
    conn = get_connection()
    now = datetime.now().isoformat() if status == "applied" else None
    conn.execute(
        "UPDATE jobs SET status = ?, date_applied = COALESCE(?, date_applied), notes = ? WHERE id = ?",
        (status, now, notes, job_id),
    )
    conn.commit()
    conn.close()


def update_job_analysis(job_id, analysis):
    """Store AI fit analysis results for a job.

    Args:
        job_id: The job's database ID
        analysis: dict with keys fit_score, recommendation, summary, talking_points,
                  strengths, gaps
    """
    conn = get_connection()
    # Store talking_points, strengths, and gaps together as JSON
    talking_points_data = json.dumps({
        "talking_points": analysis.get("talking_points", []),
        "strengths": analysis.get("strengths", []),
        "gaps": analysis.get("gaps", []),
    })
    conn.execute(
        """UPDATE jobs SET ai_fit_score = ?, ai_recommendation = ?,
           ai_summary = ?, ai_talking_points = ? WHERE id = ?""",
        (
            analysis.get("fit_score"),
            analysis.get("recommendation"),
            analysis.get("summary"),
            talking_points_data,
            job_id,
        ),
    )
    conn.commit()
    conn.close()


def get_unanalyzed_jobs():
    """Get all new jobs that haven't been analyzed yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status = 'new' AND ai_fit_score IS NULL ORDER BY date_scraped DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
