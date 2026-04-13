#!/usr/bin/env python3
"""
Daily Digest — GitHub Actions Orchestrator
Runs: fetch → email → podcast → send
All secrets come from environment variables (GitHub Secrets).
"""

import os
import sys
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Setup ────────────────────────────────────────────────────────────────────
ET = timezone(timedelta(hours=-4))
OUTPUT_DIR = "/tmp/digest_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

def run_step(script_name, description, env=None):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    log.info(f"Starting: {description}")
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env["OUTPUT_DIR"] = OUTPUT_DIR

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=600, env=run_env
        )
        if result.stdout:
            log.info(f"  {result.stdout.strip()[:300]}")
        if result.stderr:
            log.info(f"  {result.stderr.strip()[:300]}")
        if result.returncode == 0:
            log.info(f"✓ Completed: {description}")
            return True
        else:
            log.error(f"✗ Failed: {description} (exit {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        log.error(f"✗ Timeout: {description}")
        return False
    except Exception as e:
        log.error(f"✗ Error: {e}")
        return False

def main():
    now = datetime.now(ET)
    log.info(f"=== Daily Digest Pipeline: {now.strftime('%A, %B %d, %Y %I:%M %p ET')} ===")

    # Validate required secrets
    required = ["OPENAI_API_KEY", "GMAIL_USER", "GMAIL_APP_PASSWORD", "RECIPIENT_EMAIL"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        log.error(f"Missing required environment variables: {missing}")
        sys.exit(1)

    if not run_step("fetch_news.py", "Fetching and aggregating news"):
        log.error("Pipeline aborted: fetch failed.")
        sys.exit(1)

    if not run_step("generate_email.py", "Generating HTML email"):
        log.warning("Email generation failed — continuing.")

    if not run_step("generate_podcast.py", "Generating Spanish podcast"):
        log.warning("Podcast generation failed — will send email only.")

    if not run_step("send_email.py", "Sending digest to inbox"):
        log.error("Email delivery failed.")
        sys.exit(1)

    log.info("=== Pipeline Completed Successfully ===")

if __name__ == "__main__":
    main()
