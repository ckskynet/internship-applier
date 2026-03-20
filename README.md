# Internship Applier

Semi-automated tool for searching and applying to internship listings across multiple job platforms.

## Features

- **Multi-platform scraping** — Indeed, ZipRecruiter, and Handshake
- **SQLite tracking** — deduplicates listings and tracks application status
- **Semi-automated applications** — walks you through each listing with options to apply, skip, or open in browser
- **Discord notifications** — get summaries of new listings and application updates
- **Anti-detection** — uses playwright-stealth and fresh browser sessions to avoid bot detection

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create `config/profile.yaml` with your personal info, search preferences, and enabled platforms:

```yaml
personal:
  name: "Your Name"
  email: "you@example.com"

search:
  keywords:
    - "cybersecurity intern"
    - "security analyst intern"
  locations:
    - "Remote"
    - "United States"
  posted_within_days: 7

platforms:
  indeed: true
  ziprecruiter: true
  handshake: false
```

Optionally create a `.env` file for API keys:

```
ANTHROPIC_API_KEY=your_key_here
DISCORD_WEBHOOK_URL=your_webhook_url
```

## Usage

```bash
# Scrape new listings from all enabled platforms
python main.py search

# View all saved listings
python main.py list

# View only new (unapplied) listings
python main.py new

# Walk through new listings and apply
python main.py apply

# Show application statistics
python main.py stats
```

## How It Works

1. **`search`** scrapes job boards using Playwright, saves listings to a local SQLite database, and sends a Discord summary
2. **`apply`** iterates through new listings — for each job you can:
   - **apply** — opens the listing and pre-fills your application
   - **open** — opens in browser for manual application
   - **skip** — marks as skipped
   - **quit** — stops the review loop
3. **`stats`** shows a breakdown of applications by status and platform
