# Job Scanner

Job search and AI fit analysis tool for internship applications. Scrapes listings from Indeed, ZipRecruiter, Handshake, Remote OK, and We Work Remotely, then runs AI-powered fit scoring to rank opportunities.

## Commands

### search

Scrape new job listings from all enabled platforms.

```bash
cd /mnt/c/Users/Chris/documents/Claude/internship-applier
python main.py search
```

Searches across configured keywords and locations. Results are saved to the database and a summary is sent to Discord.

### analyze

Run AI fit analysis on all unanalyzed jobs.

```bash
cd /mnt/c/Users/Chris/documents/Claude/internship-applier
python main.py analyze
```

Scores each new job on a 1-10 fit scale using Claude, producing a recommendation (apply/skip/maybe), strengths, gaps, and talking points. Results are stored in the database for sorting and review.

### report

After running `search` and `analyze`, report a ranked summary of top matches back via Discord. The summary should include:

- Job title, company, and platform
- AI fit score (1-10)
- Recommendation (apply / skip / maybe)
- Key talking points for each top match

Use the existing `send_search_summary()` pattern in `utils/discord.py` as a reference for formatting Discord embeds.

## Typical Workflow

1. Run `search` to scrape fresh listings
2. Run `analyze` to score all new jobs
3. Report the top-ranked matches (sorted by fit score descending) with scores, recommendations, and talking points to Discord
4. Optionally run `apply` to walk through top matches interactively

## Configuration

- Search keywords, locations, and platform toggles are in `config/profile.yaml`
- `ANTHROPIC_API_KEY` and `DISCORD_WEBHOOK_URL` must be set in `.env`
