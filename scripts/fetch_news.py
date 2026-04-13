#!/usr/bin/env python3
"""
Daily Digest News Fetcher — GitHub Actions version
Uses environment variables for secrets and OUTPUT_DIR for file paths.
"""

import feedparser
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/tmp/digest_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

FEEDS = {
    "rfi":               "https://www.rfi.fr/es/noticieros/podcast",
    "wsj_world":         "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "wsj_us":            "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "wsj_opinion":       "https://feeds.a.dj.com/rss/RSSOpinion.xml",
    "nyt":               "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "aljazeera":         "https://www.aljazeera.com/xml/rss/all.xml",
    "economist_leaders": "https://www.economist.com/leaders/rss.xml",
    "economist_opinion": "https://www.economist.com/opinion/rss.xml",
    "comite":            "https://feeds.transistor.fm/comite",
}

SOURCE_LABELS = {
    "rfi":               "RFI en Español",
    "wsj_world":         "Wall Street Journal",
    "wsj_us":            "Wall Street Journal",
    "wsj_opinion":       "Wall Street Journal",
    "nyt":               "New York Times",
    "aljazeera":         "Al Jazeera",
    "economist_leaders": "The Economist",
    "economist_opinion": "The Economist",
    "comite":            "Comité de Lectura",
}

ET = timezone(timedelta(hours=-4))

def now_et():
    return datetime.now(ET)

def clean_html(text):
    return re.sub(r'<[^>]+>', '', text or '').strip()

def parse_pub_date(entry):
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return None

def fetch_feed(feed_key, max_items=10):
    url = FEEDS[feed_key]
    label = SOURCE_LABELS[feed_key]
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            items.append({
                "title":       entry.get("title", "").strip(),
                "description": clean_html(entry.get("summary", entry.get("description", ""))),
                "link":        entry.get("link", ""),
                "pub_date":    parse_pub_date(entry),
                "source":      label,
                "audio_url":   next(
                    (enc.get('href') or enc.get('url')
                     for enc in getattr(entry, 'enclosures', [])
                     if 'audio' in enc.get('type', '')),
                    None
                ),
            })
        return items
    except Exception as e:
        print(f"  Error fetching {feed_key}: {e}", file=sys.stderr)
        return []

def get_latest_rfi_informativo():
    items = fetch_feed("rfi", max_items=20)
    informativos = [i for i in items if "informativo" in i["title"].lower()]
    today_8am = now_et().replace(hour=8, minute=0, second=0, microsecond=0)
    for item in informativos:
        if item["pub_date"] is None or item["pub_date"].astimezone(ET) <= today_8am:
            return item
    return informativos[0] if informativos else None

def get_latest_comite_episode():
    items = fetch_feed("comite", max_items=10)
    noticias = [i for i in items if "noticias" in i["title"].lower()]
    return noticias[0] if noticias else (items[0] if items else None)

def transcribe_audio(audio_url, language="es"):
    if not audio_url:
        return None
    audio_path = "/tmp/podcast_audio.mp3"
    try:
        print(f"  Downloading audio...", file=sys.stderr)
        req = urllib.request.Request(audio_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=90) as r:
            with open(audio_path, 'wb') as f:
                f.write(r.read())
        print(f"  Transcribing...", file=sys.stderr)
        with open(audio_path, 'rb') as af:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=af, language=language)
        return transcript.text
    except Exception as e:
        print(f"  Transcription error: {e}", file=sys.stderr)
        return None

def build_unified_digest(all_raw_items, rfi_transcript=None, comite_episode=None):
    raw_text = ""
    if rfi_transcript:
        raw_text += f"\n\n=== RFI en Español (audio transcript, Spanish→English) ===\n{rfi_transcript[:3000]}\n"
    if comite_episode:
        raw_text += f"\n\n=== Comité de Lectura (Peru podcast) ===\nTitle: {comite_episode['title']}\n{comite_episode['description'][:1500]}\n"
    for item in all_raw_items:
        raw_text += (
            f"\n[{item['source']}] {item['title']}\n"
            f"  {item['description'][:200]}\n"
            f"  URL: {item['link']}\n"
        )

    prompt = f"""You are a world-class news editor creating a concise daily digest for a busy professional.

Below are raw headlines and descriptions from multiple sources: Wall Street Journal, New York Times, Al Jazeera, The Economist, RFI en Español (translated), and Comité de Lectura (Peru).

Your job:
1. **Deduplicate**: If the same story appears in multiple sources, merge them into ONE entry. Combine the best details and perspectives from each source.
2. **Rank**: Order all stories from most to least globally important/relevant.
3. **Summarize**: Write a 2-sentence summary per story — punchy, clear, no fluff. First sentence = what happened. Second sentence = why it matters or what comes next.
4. **Cite sources**: For each story, list which source(s) covered it and include the best URL for more info.
5. **Label topic**: Assign a short topic tag (e.g., "Middle East", "US Politics", "Economy", "Peru", "Climate", etc.)

Return ONLY valid JSON in this exact format (no markdown, no extra text):
{{
  "date": "...",
  "stories": [
    {{
      "rank": 1,
      "topic": "Middle East",
      "headline": "Short punchy headline (max 12 words)",
      "summary": "First sentence what happened. Second sentence why it matters.",
      "sources": ["Wall Street Journal", "Al Jazeera"],
      "url": "https://best-link-for-more-info"
    }},
    ...
  ]
}}

Include 10–14 stories total. Prioritize global impact. Include at least 1–2 Peru stories from Comité de Lectura if relevant.

Raw input:
{raw_text[:12000]}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  GPT error: {e}", file=sys.stderr)
        return None

def aggregate_news():
    today = now_et().strftime("%A, %B %d, %Y")
    today_iso = now_et().strftime("%Y-%m-%d")
    print(f"Aggregating news for {today}...", file=sys.stderr)

    print("Fetching RFI en Español...", file=sys.stderr)
    rfi_episode = get_latest_rfi_informativo()
    rfi_transcript = None
    rfi_audio_url = None
    if rfi_episode:
        rfi_audio_url = rfi_episode.get("audio_url")
        rfi_transcript = transcribe_audio(rfi_audio_url)

    print("Fetching Comité de Lectura...", file=sys.stderr)
    comite_episode = get_latest_comite_episode()

    all_items = []
    for key in ["wsj_world", "wsj_us", "wsj_opinion", "nyt", "aljazeera",
                "economist_leaders", "economist_opinion"]:
        print(f"Fetching {SOURCE_LABELS[key]} ({key})...", file=sys.stderr)
        all_items.extend(fetch_feed(key, max_items=8))

    print("Building unified digest (dedup + rank + summarize)...", file=sys.stderr)
    unified = build_unified_digest(all_items, rfi_transcript, comite_episode)

    if not unified:
        unified = {
            "date": today,
            "stories": [{"rank": i+1, "topic": "News", "headline": item["title"],
                          "summary": item["description"][:200],
                          "sources": [item["source"]], "url": item["link"]}
                        for i, item in enumerate(all_items[:12])]
        }

    unified["date"] = today
    unified["date_iso"] = today_iso
    unified["rfi_audio_url"] = rfi_audio_url
    unified["comite_audio_url"] = comite_episode.get("audio_url") if comite_episode else None

    output_path = os.path.join(OUTPUT_DIR, f"digest_{today_iso}.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(unified, f, ensure_ascii=False, indent=2, default=str)
    print(f"Digest saved to {output_path}", file=sys.stderr)
    print(output_path)
    return unified

if __name__ == "__main__":
    result = aggregate_news()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
