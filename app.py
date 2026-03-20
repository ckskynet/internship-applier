"""Flask web UI for the Internship Applier."""

import math
from flask import Flask, render_template, request, redirect, url_for
from utils.database import (
    init_db, get_jobs_paginated, get_job_by_id, get_stats,
    update_job_status,
)

app = Flask(__name__)

PER_PAGE = 50


def _build_applied_set(jobs):
    """Build a set of (title, company) pairs that have been applied to,
    then mark each job with _applied_elsewhere if it's new but matches."""
    from utils.database import get_jobs
    applied_jobs = get_jobs(status="applied")
    applied_keys = {
        (j["title"].lower(), j["company"].lower()) for j in applied_jobs
    }
    for job in jobs:
        key = (job["title"].lower(), job["company"].lower())
        job["_applied_elsewhere"] = (job["status"] == "new" and key in applied_keys)
    return jobs


@app.route("/")
def index():
    status = request.args.get("status", "")
    platform = request.args.get("platform", "")
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)

    jobs, total_count = get_jobs_paginated(
        status=status or None,
        platform=platform or None,
        search=search or None,
        page=page,
        per_page=PER_PAGE,
    )
    jobs = _build_applied_set(jobs)
    stats = get_stats()
    total_pages = math.ceil(total_count / PER_PAGE) if total_count else 1

    return render_template(
        "index.html",
        jobs=jobs,
        stats=stats,
        total_jobs=stats["total"],
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        current_status=status,
        current_platform=platform,
        current_search=search,
    )


@app.route("/jobs/<int:job_id>/status", methods=["POST"])
def update_status(job_id):
    new_status = request.form.get("status", "new")
    update_job_status(job_id, new_status)
    job = get_job_by_id(job_id)

    # Check applied-elsewhere for the updated row
    from utils.database import get_jobs
    applied_jobs = get_jobs(status="applied")
    applied_keys = {
        (j["title"].lower(), j["company"].lower()) for j in applied_jobs
    }
    key = (job["title"].lower(), job["company"].lower())
    job["_applied_elsewhere"] = (job["status"] == "new" and key in applied_keys)

    return render_template("partials/job_row.html", job=job)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
