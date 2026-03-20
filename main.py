#!/usr/bin/env python3
"""Internship Applier — semi-automated job application tool."""

import sys
from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from utils.config import load_profile, get_search_prefs, get_enabled_platforms
from utils.database import (
    init_db, get_jobs, update_job_status, is_already_applied,
    update_job_analysis, get_unanalyzed_jobs,
)
from scrapers import indeed, ziprecruiter, handshake, remoteok, weworkremotely
from automation.applier import apply_to_job
from utils.discord import send_search_summary, send_application_update

console = Console()

SCRAPER_MAP = {
    "indeed": indeed.scrape_listings,
    "ziprecruiter": ziprecruiter.scrape_listings,
    "remoteok": remoteok.scrape_listings,
    "weworkremotely": weworkremotely.scrape_listings,
    "handshake": handshake.scrape_listings,
}


def cmd_search():
    """Search for internship listings across enabled platforms."""
    prefs = get_search_prefs()
    platforms = get_enabled_platforms()

    console.print(f"\n[bold]Searching across: {', '.join(platforms)}[/bold]")
    console.print(f"Keywords: {prefs['keywords']}")
    console.print(f"Locations: {prefs['locations']}")
    console.print()

    total = 0
    jobs_by_platform = {}
    for platform in platforms:
        scraper = SCRAPER_MAP.get(platform)
        if not scraper:
            console.print(f"[yellow]No scraper for {platform}, skipping[/yellow]")
            continue

        console.print(f"[cyan]Scraping {platform}...[/cyan]")
        platform_jobs = []
        # These platforms don't support location filtering — search by keyword only
        no_location = ("handshake", "remoteok", "weworkremotely")
        locations = [""] if platform in no_location else prefs["locations"]
        for keyword in prefs["keywords"]:
            for location in locations:
                try:
                    jobs = scraper(
                        keyword=keyword,
                        location=location,
                        posted_within_days=prefs.get("posted_within_days", 7),
                    )
                    platform_jobs.extend(jobs)
                    total += len(jobs)
                    if location:
                        console.print(f"  Found {len(jobs)} listings for '{keyword}' in '{location}'")
                    else:
                        console.print(f"  Found {len(jobs)} listings for '{keyword}'")
                except Exception as e:
                    console.print(f"  [red]Error: {e}[/red]")
        jobs_by_platform[platform] = platform_jobs

    console.print(f"\n[bold green]Total new listings found: {total}[/bold green]")

    # Send Discord notification
    send_search_summary(jobs_by_platform)


def cmd_list(status=None):
    """Show saved job listings."""
    jobs = get_jobs(status=status)
    if not jobs:
        console.print("[yellow]No jobs found.[/yellow]")
        return

    table = Table(title=f"Job Listings ({len(jobs)} total)")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Platform", width=12)
    table.add_column("Title", width=35)
    table.add_column("Company", width=20)
    table.add_column("Location", width=15)
    table.add_column("Status", width=10)

    for job in jobs:
        status_style = {
            "new": "white",
            "applied": "green",
            "skipped": "dim",
            "error": "red",
        }.get(job["status"], "white")

        table.add_row(
            str(job["id"]),
            job["platform"],
            job["title"][:35],
            job["company"][:20],
            (job["location"] or "")[:15],
            f"[{status_style}]{job['status']}[/{status_style}]",
        )

    console.print(table)


def cmd_analyze():
    """Run AI fit analysis on all unanalyzed new jobs."""
    from utils.ai_analyzer import analyze_job_fit

    jobs = get_unanalyzed_jobs()
    if not jobs:
        console.print("[yellow]No unanalyzed jobs found. Run 'search' first.[/yellow]")
        return

    console.print(f"\n[bold]Analyzing {len(jobs)} jobs...[/bold]\n")

    results = []
    for i, job in enumerate(jobs, 1):
        console.print(f"  [{i}/{len(jobs)}] {job['title'][:40]} @ {job['company'][:20]}...", end=" ")
        analysis = analyze_job_fit(job)
        if analysis:
            update_job_analysis(job["id"], analysis)
            score = analysis.get("fit_score", 0)
            rec = analysis.get("recommendation", "?")
            score_style = "green" if score >= 7 else "yellow" if score >= 4 else "red"
            console.print(f"[{score_style}]{score}/10[/{score_style}] [{rec}]")
            results.append({**job, **analysis})
        else:
            console.print("[red]failed[/red]")

    # Print ranked summary
    results.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
    if results:
        console.print(f"\n[bold]Top Matches[/bold]\n")
        table = Table()
        table.add_column("Score", width=6, justify="center")
        table.add_column("Rec", width=6)
        table.add_column("Title", width=35)
        table.add_column("Company", width=20)
        table.add_column("Summary", width=50)

        for r in results[:15]:
            score = r.get("fit_score", 0)
            score_style = "green" if score >= 7 else "yellow" if score >= 4 else "red"
            rec_style = {"apply": "green", "maybe": "yellow", "skip": "dim"}.get(
                r.get("recommendation", ""), "white"
            )
            table.add_row(
                f"[{score_style}]{score}/10[/{score_style}]",
                f"[{rec_style}]{r.get('recommendation', '?')}[/{rec_style}]",
                r["title"][:35],
                r["company"][:20],
                r.get("summary", "")[:50],
            )
        console.print(table)

    console.print(f"\n[bold green]Analysis complete: {len(results)}/{len(jobs)} jobs scored.[/bold green]")


def cmd_apply():
    """Walk through new listings and apply semi-automatically."""
    import json as _json

    jobs = get_jobs(status="new")
    if not jobs:
        console.print("[yellow]No new jobs to apply to. Run 'search' first.[/yellow]")
        return

    # Sort by AI fit score descending (unscored jobs last)
    jobs.sort(key=lambda j: j.get("ai_fit_score") or 0, reverse=True)

    console.print(f"\n[bold]Found {len(jobs)} new listings to review.[/bold]\n")

    for i, job in enumerate(jobs, 1):
        # Check if already applied to this company+title (prevents re-applying)
        if is_already_applied(job["title"], job["company"]):
            console.print(f"\n[dim]--- Job {i}/{len(jobs)} --- ALREADY APPLIED, skipping ---[/dim]")
            console.print(f"  {job['title']} @ {job['company']}")
            update_job_status(job["id"], "applied", "auto-detected: already applied via another listing")
            continue

        console.print(f"\n[bold]--- Job {i}/{len(jobs)} ---[/bold]")
        console.print(f"  Title:    {job['title']}")
        console.print(f"  Company:  {job['company']}")
        console.print(f"  Location: {job['location']}")
        console.print(f"  Platform: {job['platform']}")
        console.print(f"  URL:      {job['url']}")

        # Show AI analysis if available
        if job.get("ai_fit_score"):
            score = job["ai_fit_score"]
            score_style = "green" if score >= 7 else "yellow" if score >= 4 else "red"
            rec = job.get("ai_recommendation", "?")
            rec_style = {"apply": "green", "maybe": "yellow", "skip": "dim"}.get(rec, "white")

            console.print(f"\n  [bold]AI Analysis:[/bold]")
            console.print(f"  Fit Score:       [{score_style}]{score}/10[/{score_style}]")
            console.print(f"  Recommendation:  [{rec_style}]{rec}[/{rec_style}]")
            if job.get("ai_summary"):
                console.print(f"  Summary:         {job['ai_summary']}")

            if job.get("ai_talking_points"):
                try:
                    tp_data = _json.loads(job["ai_talking_points"])
                    if tp_data.get("talking_points"):
                        console.print(f"  [bold]Talking Points:[/bold]")
                        for tp in tp_data["talking_points"]:
                            console.print(f"    - {tp}")
                    if tp_data.get("strengths"):
                        console.print(f"  [bold]Strengths:[/bold]")
                        for s in tp_data["strengths"]:
                            console.print(f"    [green]+ {s}[/green]")
                    if tp_data.get("gaps"):
                        console.print(f"  [bold]Gaps:[/bold]")
                        for g in tp_data["gaps"]:
                            console.print(f"    [yellow]- {g}[/yellow]")
                except (_json.JSONDecodeError, TypeError):
                    pass

        action = Prompt.ask(
            "\n  Action",
            choices=["apply", "skip", "open", "quit"],
            default="apply",
        )

        if action == "quit":
            break
        elif action == "skip":
            update_job_status(job["id"], "skipped")
            send_application_update(job, "skipped")
            console.print("  [dim]Skipped.[/dim]")
        elif action == "open":
            # Just open in browser without auto-fill
            import webbrowser
            webbrowser.open(job["url"])
            result = Prompt.ask("  Did you apply?", choices=["yes", "no"], default="no")
            status = "applied" if result == "yes" else "new"
            update_job_status(job["id"], status)
            if status == "applied":
                send_application_update(job, "applied")
        elif action == "apply":
            console.print("  [cyan]Opening browser and pre-filling application...[/cyan]")
            result = apply_to_job(job)
            send_application_update(job, result)
            console.print(f"  Result: [bold]{result}[/bold]")


def cmd_stats():
    """Show application statistics."""
    from collections import Counter
    jobs = get_jobs()
    counts = Counter(j["status"] for j in jobs)
    platform_counts = Counter(j["platform"] for j in jobs)

    console.print("\n[bold]Application Stats[/bold]")
    console.print(f"  Total listings: {len(jobs)}")
    console.print(f"  New:     {counts.get('new', 0)}")
    console.print(f"  Applied: [green]{counts.get('applied', 0)}[/green]")
    console.print(f"  Skipped: [dim]{counts.get('skipped', 0)}[/dim]")
    console.print(f"  Errors:  [red]{counts.get('error', 0)}[/red]")
    console.print()
    console.print("[bold]By Platform[/bold]")
    for platform, count in platform_counts.items():
        console.print(f"  {platform}: {count}")


def cmd_export():
    """Export all job listings to a CSV file."""
    import csv
    import os

    jobs = get_jobs()
    if not jobs:
        console.print("[yellow]No jobs to export.[/yellow]")
        return

    os.makedirs("data", exist_ok=True)
    out_path = "data/jobs_export.csv"
    fields = ["id", "platform", "title", "company", "location", "url",
              "status", "date_scraped", "date_applied", "notes"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(jobs)

    console.print(f"[bold green]Exported {len(jobs)} jobs to {out_path}[/bold green]")


def main():
    init_db()

    if len(sys.argv) < 2:
        console.print("[bold]Internship Applier[/bold]")
        console.print()
        console.print("Usage: python main.py <command>")
        console.print()
        console.print("Commands:")
        console.print("  search  — Scrape job listings from enabled platforms")
        console.print("  analyze — Run AI fit analysis on unanalyzed jobs")
        console.print("  list    — Show all saved listings")
        console.print("  new     — Show only new (unapplied) listings")
        console.print("  apply   — Walk through new listings and apply")
        console.print("  stats   — Show application statistics")
        console.print("  export  — Export all listings to data/jobs_export.csv")
        return

    command = sys.argv[1].lower()

    commands = {
        "search": cmd_search,
        "analyze": cmd_analyze,
        "list": cmd_list,
        "new": lambda: cmd_list(status="new"),
        "apply": cmd_apply,
        "stats": cmd_stats,
        "export": cmd_export,
    }

    if command in commands:
        commands[command]()
    else:
        console.print(f"[red]Unknown command: {command}[/red]")


if __name__ == "__main__":
    main()
