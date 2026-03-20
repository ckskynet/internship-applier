# Internship Applier

Semi-automated tool for searching and applying to internship listings across multiple job platforms.

## Features

- **Multi-platform scraping** — Indeed, ZipRecruiter, Handshake, Remote OK, and We Work Remotely
- **AI fit analysis** — scores jobs 1-10 using Claude with strengths, gaps, and talking points
- **SQLite tracking** — deduplicates listings and tracks application status
- **Semi-automated applications** — walks you through each listing ranked by fit score, with options to apply, skip, or open in browser
- **Cover letter generation** — auto-generates tailored cover letters using Claude when required
- **Web dashboard** — Flask UI for browsing, filtering, and managing applications
- **Discord notifications** — get summaries of new listings and application updates
- **Anti-detection** — uses playwright-stealth and persistent browser profiles to avoid bot detection
- **OpenClaw skill** — trigger searches and reports through an OpenClaw agent

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create `config/profile.yaml` with your personal info, search preferences, and enabled platforms:

```yaml
personal:
  first_name: "Chris"
  last_name: "Adams"
  email: "you@example.com"
  phone: "555-555-5555"
  location: "United States"
  linkedin_url: "https://linkedin.com/in/you"

education:
  university: "Your University"
  degree: "Bachelor of Science"
  major: "Your Major"
  graduation_date: "May 2026"

search:
  keywords:
    - "cybersecurity intern"
    - "security analyst intern"
  locations:
    - "Remote"
    - "United States"
  posted_within_days: 7
  exclude_title_keywords:
    - "senior"
    - "manager"

platforms:
  indeed: true
  ziprecruiter: true
  handshake: false
  remoteok: true
  weworkremotely: true
```

Create a `.env` file for API keys:

```
ANTHROPIC_API_KEY=your_key_here
DISCORD_WEBHOOK_URL=your_webhook_url
```

Drop your resume PDF into the `resume/` folder. The tool automatically picks up the most recent PDF. Falls back to the path in `profile.yaml` if the folder is empty.

## Usage

```bash
# Scrape new listings from all enabled platforms
python main.py search

# Run AI fit analysis on new jobs
python main.py analyze

# View all saved listings
python main.py list

# View only new (unapplied) listings
python main.py new

# Walk through new listings and apply (sorted by fit score)
python main.py apply

# Show application statistics
python main.py stats

# Export all listings to CSV
python main.py export
```

### Web Dashboard

```bash
python app.py
```

Opens a browser dashboard at `http://localhost:5000` for filtering, applying, and generating cover letters.

### Update Script

```bash
bash scripts/update.sh
```

Pulls latest changes, installs dependencies, and logs the update to `logs/update.log`.

## How It Works

1. **`search`** scrapes job boards (Indeed, ZipRecruiter, Handshake via Playwright; Remote OK via JSON API; We Work Remotely via RSS), saves listings to a local SQLite database, and sends a Discord summary
2. **`analyze`** runs each unscored job through Claude to produce a fit score (1-10), recommendation (apply/skip/maybe), talking points, strengths, and gaps — results include clickable job links
3. **`apply`** iterates through new listings sorted by fit score — for each job you can:
   - **apply** — opens the listing and pre-fills your application (name, email, resume, cover letter)
   - **open** — opens in browser for manual application
   - **skip** — marks as skipped
   - **quit** — stops the review loop
4. **`stats`** shows a breakdown of applications by status and platform

## OpenClaw Skill

The `.agents/skills/job-scanner/` directory defines this project as an OpenClaw skill with three commands: `search`, `analyze`, and `report`. See `SKILL.md` for details.
