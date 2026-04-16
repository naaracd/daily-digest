#!/usr/bin/env python3
"""
Daily Digest Email Generator — friendly, modern card layout
"""

import json
import os
import sys
from datetime import datetime

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/tmp/digest_output")

TOPIC_META = {
    "Middle East":   {"color": "#e74c3c", "emoji": "🔥"},
    "Palestine":     {"color": "#e74c3c", "emoji": "🕊️"},
    "US Politics":   {"color": "#2c3e50", "emoji": "🇺🇸"},
    "Economy":       {"color": "#2980b9", "emoji": "📈"},
    "Trade":         {"color": "#2980b9", "emoji": "🤝"},
    "Markets":       {"color": "#2980b9", "emoji": "💹"},
    "China":         {"color": "#c0392b", "emoji": "🇨🇳"},
    "Russia":        {"color": "#922b21", "emoji": "🇷🇺"},
    "Climate":       {"color": "#27ae60", "emoji": "🌍"},
    "Environment":   {"color": "#27ae60", "emoji": "🌿"},
    "Peru":          {"color": "#e67e22", "emoji": "🇵🇪"},
    "Latin America": {"color": "#e67e22", "emoji": "🌎"},
    "Technology":    {"color": "#8e44ad", "emoji": "💻"},
    "Science":       {"color": "#8e44ad", "emoji": "🔬"},
    "Europe":        {"color": "#1f618d", "emoji": "🇪🇺"},
    "Africa":        {"color": "#d4ac0d", "emoji": "🌍"},
    "Asia":          {"color": "#d4ac0d", "emoji": "🌏"},
    "Security":      {"color": "#7f8c8d", "emoji": "🛡️"},
    "Health":        {"color": "#16a085", "emoji": "🏥"},
    "default":       {"color": "#5d6d7e", "emoji": "📰"},
}

SOURCE_COLORS = {
    "Wall Street Journal": "#0080c6",
    "New York Times":      "#1a1a1a",
    "Al Jazeera":          "#c8a400",
    "The Economist":       "#e03030",
    "RFI en Español":      "#005baa",
    "Comité de Lectura":   "#e07b39",
}

def get_topic_meta(topic):
    for key, meta in TOPIC_META.items():
        if key.lower() in topic.lower():
            return meta
    return TOPIC_META["default"]

def source_pill(source):
    color = SOURCE_COLORS.get(source, "#888")
    return (
        f'<span style="display:inline-block;background:{color};color:#fff;'
        f'padding:2px 9px;border-radius:20px;font-size:11px;font-weight:600;'
        f'margin:2px 3px 2px 0;letter-spacing:0.2px;">{source}</span>'
    )

def rank_badge(rank):
    if rank == 1:
        bg = "#f39c12"
    elif rank == 2:
        bg = "#95a5a6"
    elif rank == 3:
        bg = "#cd7f32"
    else:
        bg = "#dde1e7"
    color = "#fff" if rank <= 3 else "#555"
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:22px;height:22px;background:{bg};color:{color};border-radius:50%;'
        f'font-size:11px;font-weight:700;flex-shrink:0;">{rank}</span>'
    )

def generate_html_email(digest_path):
    if not os.path.exists(digest_path):
        print(f"Error: Digest not found at {digest_path}", file=sys.stderr)
        return None

    with open(digest_path, 'r', encoding='utf-8') as f:
        digest = json.load(f)

    date_str   = digest.get("date", datetime.now().strftime("%A, %B %d, %Y"))
    stories    = digest.get("stories", [])
    rfi_url    = digest.get("rfi_audio_url")
    comite_url = digest.get("comite_audio_url")

    # ── Story cards ──────────────────────────────────────────────────────────
    story_cards = ""
    for i, story in enumerate(stories):
        rank     = story.get("rank", i + 1)
        topic    = story.get("topic", "World")
        headline = story.get("headline", "")
        summary  = story.get("summary", "")
        sources  = story.get("sources", [])
        url      = story.get("url", "#")
        is_new   = story.get("is_new_development", False)
        meta     = get_topic_meta(topic)
        color    = meta["color"]
        emoji    = meta["emoji"]

        badges_html = "".join(source_pill(s) for s in sources)
        new_dev_badge = (
            f'<span style="background:#e74c3c;color:#fff;padding:1px 7px;'
            f'border-radius:3px;font-size:10px;font-weight:700;margin-left:6px;'
            f'letter-spacing:0.5px;vertical-align:middle;">NEW DEV</span>'
            if is_new else ""
        )

        # Alternating card background for readability
        card_bg = "#ffffff" if i % 2 == 0 else "#f9fafb"

        story_cards += f"""
        <div style="margin-bottom:0;padding:18px 22px;background:{card_bg};border-bottom:1px solid #edf2f7;">

          <!-- Topic row -->
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            {rank_badge(rank)}
            <span style="background:{color}18;color:{color};padding:3px 10px;border-radius:20px;
                         font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;">
              {emoji} {topic}
            </span>
            {new_dev_badge}
          </div>

          <!-- Headline -->
          <h3 style="margin:0 0 8px 0;font-size:16px;line-height:1.45;color:#1a202c;font-weight:700;">
            <a href="{url}" style="color:#1a202c;text-decoration:none;">{headline}</a>
          </h3>

          <!-- Summary -->
          <p style="margin:0 0 12px 0;font-size:14px;color:#4a5568;line-height:1.65;">{summary}</p>

          <!-- Sources + Read more -->
          <div style="display:flex;flex-wrap:wrap;align-items:center;">
            {badges_html}
            <a href="{url}" style="margin-left:auto;font-size:12px;color:{color};
               font-weight:600;text-decoration:none;white-space:nowrap;">Read more →</a>
          </div>

        </div>
        """

    # ── Audio section ─────────────────────────────────────────────────────────
    audio_section = ""
    if rfi_url or comite_url:
        audio_links = ""
        if rfi_url:
            audio_links += f"""
            <a href="{rfi_url}" style="display:inline-block;margin:4px 8px 4px 0;padding:7px 14px;
               background:#005baa;color:#fff;border-radius:20px;font-size:12px;font-weight:600;
               text-decoration:none;">▶ RFI Informativo (ES)</a>"""
        if comite_url:
            audio_links += f"""
            <a href="{comite_url}" style="display:inline-block;margin:4px 0;padding:7px 14px;
               background:#e07b39;color:#fff;border-radius:20px;font-size:12px;font-weight:600;
               text-decoration:none;">▶ Comité de Lectura</a>"""
        audio_section = f"""
        <div style="padding:16px 22px;background:#f0f7ff;border-top:1px solid #dbeafe;">
          <p style="margin:0 0 10px 0;font-size:13px;font-weight:700;color:#1e40af;">
            🎧 Original Audio Sources
          </p>
          <div>{audio_links}</div>
        </div>"""

    # ── Top topics summary bar ────────────────────────────────────────────────
    topics_seen = []
    for s in stories[:6]:
        t = s.get("topic", "")
        if t and t not in topics_seen:
            topics_seen.append(t)
    topics_bar = " &nbsp;·&nbsp; ".join(
        f'<span style="color:{get_topic_meta(t)["color"]};font-weight:600;">'
        f'{get_topic_meta(t)["emoji"]} {t}</span>'
        for t in topics_seen
    )

    # ── Full HTML ─────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Daily Digest — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#edf2f7;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

  <div style="max-width:640px;margin:24px auto 40px;background:#fff;
    border-radius:14px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.10);">

    <!-- ── HEADER ── -->
    <div style="background:linear-gradient(135deg,#1a2a4a 0%,#2d4a7a 100%);
      padding:32px 28px 26px;text-align:center;">
      <p style="margin:0 0 6px 0;font-size:11px;color:#93b4d8;
        letter-spacing:2px;text-transform:uppercase;">Your Morning Briefing</p>
      <h1 style="margin:0 0 6px 0;font-size:26px;font-weight:800;color:#fff;
        letter-spacing:-0.5px;">☕ The Daily Digest</h1>
      <p style="margin:0;font-size:14px;color:#a8c4e0;">{date_str}</p>
    </div>

    <!-- ── STATS BAR ── -->
    <div style="background:#1e3a5f;padding:10px 22px;text-align:center;
      font-size:12px;color:#7fb3d3;letter-spacing:0.3px;">
      <strong style="color:#fff;">{len(stories)} stories</strong> &nbsp;·&nbsp;
      fresh from the last 24 hours &nbsp;·&nbsp; no repeats
    </div>

    <!-- ── TODAY'S TOPICS ── -->
    <div style="padding:14px 22px;background:#f8faff;border-bottom:1px solid #e2e8f0;
      font-size:12px;text-align:center;line-height:2;">
      {topics_bar}
    </div>

    <!-- ── STORIES ── -->
    <div>
      {story_cards}
    </div>

    <!-- ── AUDIO SOURCES ── -->
    {audio_section}

    <!-- ── FOOTER ── -->
    <div style="padding:18px 22px;text-align:center;font-size:11px;
      color:#a0aec0;background:#f8fafc;border-top:1px solid #edf2f7;">
      Delivered every day at 7:30 AM ET &nbsp;·&nbsp;
      Sources: WSJ · NYT · Al Jazeera · The Economist · RFI · Comité de Lectura<br>
      <span style="color:#cbd5e0;">Your personal AI news assistant ✨</span>
    </div>

  </div>
</body>
</html>"""

    return html


def find_latest_digest():
    try:
        digests = sorted(
            [f for f in os.listdir(OUTPUT_DIR) if f.startswith("digest_") and f.endswith(".json")],
            reverse=True
        )
        return os.path.join(OUTPUT_DIR, digests[0]) if digests else None
    except Exception:
        return None


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
