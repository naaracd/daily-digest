#!/usr/bin/env python3
"""
Daily Digest Email Generator — GitHub Actions version
"""

import json
import os
import sys
from datetime import datetime

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/tmp/digest_output")

TOPIC_COLORS = {
    "Middle East":   "#c0392b",
    "US Politics":   "#2c3e50",
    "Economy":       "#1a5276",
    "Trade":         "#1a5276",
    "Markets":       "#1a5276",
    "China":         "#922b21",
    "Russia":        "#922b21",
    "Climate":       "#1e8449",
    "Environment":   "#1e8449",
    "Peru":          "#d35400",
    "Latin America": "#d35400",
    "Technology":    "#6c3483",
    "Science":       "#6c3483",
    "Europe":        "#1f618d",
    "Africa":        "#7d6608",
    "Asia":          "#7d6608",
    "World":         "#2e4057",
    "default":       "#2e4057",
}

def topic_color(topic):
    for key, color in TOPIC_COLORS.items():
        if key.lower() in topic.lower():
            return color
    return TOPIC_COLORS["default"]

def source_badge(source):
    badges = {
        "Wall Street Journal": "#0080c6",
        "New York Times":      "#000000",
        "Al Jazeera":          "#d4a017",
        "The Economist":       "#e03030",
        "RFI en Español":      "#005baa",
        "Comité de Lectura":   "#e07b39",
    }
    color = badges.get(source, "#888888")
    return f'<span style="background:{color};color:#fff;padding:2px 7px;border-radius:3px;font-size:11px;font-weight:600;margin-right:4px;white-space:nowrap;">{source}</span>'

def generate_html_email(digest_path):
    if not os.path.exists(digest_path):
        print(f"Error: Digest not found at {digest_path}", file=sys.stderr)
        return None

    with open(digest_path, 'r', encoding='utf-8') as f:
        digest = json.load(f)

    date_str  = digest.get("date", datetime.now().strftime("%A, %B %d, %Y"))
    stories   = digest.get("stories", [])
    rfi_url   = digest.get("rfi_audio_url")
    comite_url= digest.get("comite_audio_url")

    # Build story cards HTML
    story_cards = ""
    for story in stories:
        rank     = story.get("rank", "")
        topic    = story.get("topic", "World")
        headline = story.get("headline", "")
        summary  = story.get("summary", "")
        sources  = story.get("sources", [])
        url      = story.get("url", "#")
        color    = topic_color(topic)

        badges_html = "".join(source_badge(s) for s in sources)

        story_cards += f"""
        <div style="margin-bottom:22px;padding:16px 18px;border-left:4px solid {color};background:#fafafa;border-radius:0 6px 6px 0;">
          <div style="margin-bottom:6px;">
            <span style="background:{color};color:#fff;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">{topic}</span>
          </div>
          <h3 style="margin:6px 0 8px 0;font-size:16px;line-height:1.4;color:#1a1a1a;">
            <a href="{url}" style="color:#1a1a1a;text-decoration:none;">{headline}</a>
          </h3>
          <p style="margin:0 0 10px 0;font-size:14px;color:#444;line-height:1.6;">{summary}</p>
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;">
            {badges_html}
            <a href="{url}" style="margin-left:6px;font-size:12px;color:#0066cc;text-decoration:none;">Read more →</a>
          </div>
        </div>
        """

    # Audio links section
    audio_section = ""
    if rfi_url or comite_url:
        audio_section = '<div style="margin-top:10px;padding:14px 18px;background:#eef6ff;border-radius:6px;">'
        audio_section += '<p style="margin:0 0 8px 0;font-size:13px;font-weight:600;color:#2c5282;">🎧 Original Audio Sources</p>'
        if rfi_url:
            audio_section += f'<p style="margin:0 0 5px 0;font-size:13px;"><a href="{rfi_url}" style="color:#0066cc;">▶ RFI en Español — Informativo (original Spanish audio)</a></p>'
        if comite_url:
            audio_section += f'<p style="margin:0;font-size:13px;"><a href="{comite_url}" style="color:#0066cc;">▶ Comité de Lectura — Latest Episode</a></p>'
        audio_section += '</div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Daily News Digest — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:620px;margin:20px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:#1a2a4a;padding:28px 24px 22px;text-align:center;">
      <p style="margin:0 0 4px 0;font-size:12px;color:#8fa8c8;letter-spacing:1.5px;text-transform:uppercase;">Your Daily Briefing</p>
      <h1 style="margin:0;font-size:22px;font-weight:700;color:#ffffff;">The Daily Digest</h1>
      <p style="margin:8px 0 0 0;font-size:14px;color:#a8bfd8;">{date_str}</p>
    </div>

    <!-- Intro bar -->
    <div style="background:#e8f0fe;padding:10px 24px;font-size:13px;color:#3d5a99;text-align:center;">
      {len(stories)} stories · ranked by relevance · sources merged &amp; deduplicated
    </div>

    <!-- Stories -->
    <div style="padding:20px 24px 10px;">
      {story_cards}
    </div>

    <!-- Audio -->
    <div style="padding:0 24px 20px;">
      {audio_section}
    </div>

    <!-- Footer -->
    <div style="background:#f8fafc;padding:16px 24px;text-align:center;font-size:11px;color:#9aa5b4;border-top:1px solid #edf2f7;">
      Generated automatically every day at 8 AM ET &nbsp;·&nbsp; Your personal AI news assistant
    </div>
  </div>
</body>
</html>"""

    return html


def find_latest_digest():
    digests = sorted(
        [f for f in os.listdir(OUTPUT_DIR) if f.startswith("digest_") and f.endswith(".json")],
        reverse=True
    )
    return os.path.join(OUTPUT_DIR, digests[0]) if digests else None


if __name__ == "__main__":
    digest_path = sys.argv[1] if len(sys.argv) > 1 else find_latest_digest()
    if not digest_path:
        print("No digest found.", file=sys.stderr)
        sys.exit(1)

    html = generate_html_email(digest_path)
    if html:
        out_path = digest_path.replace(".json", ".html")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"HTML email generated: {out_path}")
