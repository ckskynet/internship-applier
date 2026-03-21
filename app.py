"""Flask web UI for the Internship Applier."""

import math
import os
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from utils.database import (
    init_db, get_jobs_paginated, get_job_by_id, get_stats,
    update_job_status,
)

app = Flask(__name__)

PER_PAGE = 50

PLATFORM_NAMES = {
    "indeed": "Indeed",
    "ziprecruiter": "ZipRecruiter",
    "handshake": "Handshake",
    "remoteok": "Remote OK",
    "weworkremotely": "WWR",
}


@app.template_filter("platform_name")
def platform_name_filter(value):
    return PLATFORM_NAMES.get(value, value.capitalize())


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


def _enrich_job(job):
    """Add _applied_elsewhere flag to a single job dict."""
    from utils.database import get_jobs
    applied_jobs = get_jobs(status="applied")
    applied_keys = {
        (j["title"].lower(), j["company"].lower()) for j in applied_jobs
    }
    key = (job["title"].lower(), job["company"].lower())
    job["_applied_elsewhere"] = (job["status"] == "new" and key in applied_keys)
    return job


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
    job = _enrich_job(job)
    return render_template("partials/job_row.html", job=job)


@app.route("/jobs/<int:job_id>/apply", methods=["POST"])
def apply_job(job_id):
    """Open job URL in default browser and mark as applied."""
    import subprocess
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Use cmd.exe on WSL to open in the Windows default browser
    try:
        subprocess.Popen(["cmd.exe", "/c", "start", job["url"]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        import webbrowser
        webbrowser.open(job["url"])

    update_job_status(job_id, "applied")
    job = get_job_by_id(job_id)
    job = _enrich_job(job)
    return render_template("partials/job_row.html", job=job)


@app.route("/jobs/<int:job_id>/cover-letter", methods=["POST"])
def generate_cover_letter_route(job_id):
    """Fetch job description and generate a tailored cover letter via Claude API."""
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    from automation.applier import fetch_job_description
    from automation.cover_letter import generate_cover_letter, detect_cover_letter_needed

    # Fetch the job page content
    page_text = fetch_job_description(job["url"])

    # Check if cover letter is needed
    cl_status = detect_cover_letter_needed(page_text)

    # Generate regardless (user explicitly clicked the button)
    cl_path = generate_cover_letter(
        job_title=job["title"],
        company=job["company"],
        job_description=page_text,
    )

    if cl_path:
        # Read the .txt version for display (same base name, .txt extension)
        txt_path = cl_path.replace(".docx", ".txt")
        with open(txt_path, "r") as f:
            cl_text = f.read()
        # Pass the docx filename for the download link
        docx_filename = os.path.basename(cl_path)
        return render_template("partials/cover_letter_result.html",
                               job=job, cl_status=cl_status, cl_text=cl_text,
                               cl_path=cl_path, docx_filename=docx_filename)
    else:
        return render_template("partials/cover_letter_result.html",
                               job=job, cl_status=cl_status, cl_text=None, cl_path=None,
                               error="Failed to generate cover letter. Check ANTHROPIC_API_KEY.")


@app.route("/cover-letters/<path:filename>")
def download_cover_letter(filename):
    """Serve a generated cover letter file for download."""
    cl_dir = os.path.join(os.path.dirname(__file__), "data", "cover_letters")
    filepath = os.path.join(cl_dir, filename)
    if not os.path.isfile(filepath):
        return "File not found", 404
    return send_file(filepath, as_attachment=True)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
