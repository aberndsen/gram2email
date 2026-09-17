# Gram2Email

A lightweight Python service designed to periodically fetch posts from public Instagram accounts and email their contents (captions, metadata, and inline images).

Built to run unattended as a cronjob without requiring an Instagram account or login.

## Features

- **Anonymous Public Access:** Fetches posts from public profiles using Instaloader.
- **Embedded Inline Images:** Embeds media directly into responsive HTML emails (`cid:` attachments) so images display immediately without broken CDN links or external image blockers.
- **Duplicate Prevention:** Tracks seen post shortcodes across runs in a local JSON state file.
- **Flexible Configuration:** Uses `jsonargparse` and Python `dataclasses` supporting YAML configuration files and CLI overrides.
- **Lifecycle Hooks:** Functional hook registry for logging, metrics, or custom post-processing.
- **Cron-Friendly:** Fast-fail timeouts and rate-limit handling to avoid hanging scheduled cron jobs.

## Installation & Setup

Ensure you have [uv](https://github.com/astral-sh/uv) installed.

1. Clone or navigate to the repository:
   ```bash
   cd gram2email
   ```

2. Create your configuration from the example template:
   ```bash
   cp config.example.yaml config.yaml
   ```

3. Edit `config.yaml` with your list of Instagram accounts to follow, the list of users (names and emails) receiving the emails, and your SMTP credentials.

## Usage

### Test with a Dry Run
To scan accounts and check which emails would be generated without actually sending them or altering state:
```bash
uv run gram2email --config config.yaml --dry_run true
```

### Run the Pipeline
```bash
uv run gram2email --config config.yaml
```

### CLI Overrides
You can override any configuration setting from the command line:
```bash
uv run gram2email --config config.yaml --accounts "[nasa, natgeo]" --max_posts_per_account 3 --verbose true
```

## Scheduling via Cron

To run every hour and email new posts:

```bash
crontab -e
```

Add the following entry:
```cron
0 * * * * cd /path/to/gram2email && /path/to/uv run gram2email --config /path/to/gram2email/config.yaml >> /path/to/gram2email/cron.log 2>&1
```

## Development

Run tests:
```bash
uv run pytest
```

Check code quality with `ruff`:
```bash
uv run ruff check .
uv run ruff format --check .
```

Build package distributions:
```bash
uv build
```
