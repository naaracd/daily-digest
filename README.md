# Daily News Digest

Automated daily news digest delivered every day at **8 AM ET** via GitHub Actions.

## What it does

1. Fetches the latest **RFI en Español Informativo** (transcribes & translates from Spanish audio)
2. Pulls top headlines from **Wall Street Journal**, **New York Times**, **Al Jazeera**, and **The Economist**
3. Fetches the latest **Comité de Lectura** Peru podcast and summarizes it
4. Uses GPT-4 to **deduplicate** cross-source stories, **merge perspectives**, and **rank by relevance**
5. Generates a beautiful **HTML email digest** organized by topic with source links
6. Generates a **Spanish podcast MP3** at 1.25x speed
7. Sends both to your Gmail inbox

## Required GitHub Secrets

Set these in your repository under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Your Gmail app password (16 chars, no spaces) |
| `RECIPIENT_EMAIL` | Email address to receive the digest |

## Manual trigger

Go to **Actions → Daily News Digest → Run workflow** to trigger a run immediately.
