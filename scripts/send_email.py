#!/usr/bin/env python3
"""
Daily Digest Email Sender
Sends the HTML digest email and podcast MP3 via Gmail SMTP.
"""

import os
import sys
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

OUTPUT_DIR    = os.environ.get("OUTPUT_DIR", "/tmp/digest_output")
GMAIL_USER    = os.environ.get("GMAIL_USER", "naaracancino95@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
RECIPIENT     = os.environ.get("RECIPIENT_EMAIL", "naaracancino95@gmail.com")

def send_digest(html_path, podcast_path=None, digest_path=None):
    """Send the daily digest email with optional podcast attachment."""
    
    # Read HTML content
    if not os.path.exists(html_path):
        print(f"Error: HTML file not found at {html_path}", file=sys.stderr)
        return False
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Get date and top headline from digest JSON if available
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    top_headline_teaser = ""
    if digest_path and os.path.exists(digest_path):
        with open(digest_path, 'r', encoding='utf-8') as f:
            digest = json.load(f)
        date_str = digest.get("date", date_str)
        stories = digest.get("stories", [])
        if stories:
            top_headline = stories[0].get("headline", "")
            # Take first 3 meaningful words from the top headline
            words = [w for w in top_headline.split() if len(w) > 1]
            top_headline_teaser = " ".join(words[:3])

    # Build subject line: "Daily News | Trump Congela Harvard" style
    if top_headline_teaser:
        subject = f"Daily News | {top_headline_teaser}"
    else:
        subject = f"Daily News | {date_str}"

    # Build email
    msg = MIMEMultipart('mixed')
    msg['From'] = GMAIL_USER
    msg['To'] = RECIPIENT
    msg['Subject'] = subject
    
    # Attach HTML body
    msg_alt = MIMEMultipart('alternative')
    
    # Plain text fallback
    plain_text = f"Your Daily News Digest for {date_str}\n\nPlease view this email in an HTML-capable email client."
    msg_alt.attach(MIMEText(plain_text, 'plain', 'utf-8'))
    msg_alt.attach(MIMEText(html_content, 'html', 'utf-8'))
    msg.attach(msg_alt)
    
    # Attach podcast MP3 if available
    if podcast_path and os.path.exists(podcast_path):
        podcast_size_mb = os.path.getsize(podcast_path) / (1024 * 1024)
        print(f"  Attaching podcast ({podcast_size_mb:.1f} MB)...", file=sys.stderr)
        
        with open(podcast_path, 'rb') as f:
            podcast_data = f.read()
        
        podcast_attachment = MIMEBase('audio', 'mpeg')
        podcast_attachment.set_payload(podcast_data)
        encoders.encode_base64(podcast_attachment)
        
        filename = os.path.basename(podcast_path)
        podcast_attachment.add_header(
            'Content-Disposition',
            'attachment',
            filename=f"Daily_Digest_{date_str.replace(', ', '_').replace(' ', '_')}.mp3"
        )
        msg.attach(podcast_attachment)
    
    # Send via Gmail SMTP
    try:
        print(f"  Connecting to Gmail SMTP...", file=sys.stderr)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, RECIPIENT, msg.as_string())
        print(f"Email sent successfully to {RECIPIENT}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}", file=sys.stderr)
        return False

def find_latest_files():
    """Find the most recent digest files."""
    digests = sorted(
        [f for f in os.listdir(OUTPUT_DIR) if f.startswith("digest_") and f.endswith(".json")],
        reverse=True
    )
    if not digests:
        return None, None, None
    base = digests[0].replace(".json", "")
    digest_path  = os.path.join(OUTPUT_DIR, f"{base}.json")
    html_path    = os.path.join(OUTPUT_DIR, f"{base}.html")
    podcast_path = os.path.join(OUTPUT_DIR, f"{base}_podcast.mp3")
    return (
        digest_path  if os.path.exists(digest_path)  else None,
        html_path    if os.path.exists(html_path)    else None,
        podcast_path if os.path.exists(podcast_path) else None,
    )

if __name__ == "__main__":
    digest_path, html_path, podcast_path = find_latest_files()
    
    if not html_path:
        print("No HTML digest found. Run generate_email.py first.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Sending digest: {html_path}", file=sys.stderr)
    if podcast_path:
        print(f"With podcast: {podcast_path}", file=sys.stderr)
    
    success = send_digest(html_path, podcast_path, digest_path)
    sys.exit(0 if success else 1)
