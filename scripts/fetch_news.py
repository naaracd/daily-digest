#!/usr/bin/env python3
"""
Daily Digest News Fetcher — GitHub Actions version
Rules:
  1. Only include articles published within the last 24 hours.
  2. Skip stories already sent in previous days unless significant new development.
  3. Fetch daily poem from Zaiden Werg Substack (no repeats).
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

HISTORY_FILE = os.path.join(OUTPUT_DIR, "sent_stories_history.json")

SUBSTACK_FEED = "https://zaidenwerg.substack.com/feed"

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
    "comite":            "Comite de Lectura",
}

ET = timezone(timedelta(hours=-4))

def now_et():
    return datetime.now(ET)

def clean_html(text):
    return re.sub(r'<[^>]+>', '', text or '').strip()

def decode_entities(text):
    """Decode common HTML entities in poem text."""
    replacements = {
        '&#233;': 'e', '&#237;': 'i', '&#243;': 'o', '&#250;': 'u', '&#225;': 'a',
        '&#241;': 'n', '&#191;': '?', '&#161;': '!', '&#8211;': '-', '&#8212;': '-',
        '&#8220;': '"', '&#8221;': '"', '&#8216;': "'", '&#8217;': "'",
        '&amp;': '&', '&lt;': '<', '&gt;': '>', '&nbsp;': ' ', '&quot;': '"',
        # Accented versions
        '\xe9': 'e', '\xed': 'i', '\xf3': 'o', '\xfa': 'u', '\xe1': 'a',
        '\xf1': 'n', '\xfc': 'u', '\xe0': 'a', '\xe8': 'e',
    }
    import html
    text = html.unescape(text)
    return text

def parse_pub_date(entry):
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    return None

# ─── History / Deduplication ──────────────────────────────────────────────────

def load_history():
    """Load previously sent story headlines and poem URLs (last 7 days)."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_history(history):
    """Save story history, pruning entries older than 7 days."""
    cutoff = (now_et() - timedelta(days=7)).strftime("%Y-%m-%d")
    pruned = {date: data for date, data in history.items() if date >= cutoff}
    with open(HISTORY_FILE, 'w') as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)

def get_previous_headlines(history):
    """Return a flat set of all headlines sent in the last 7 days."""
    all_headlines = set()
    today_iso = now_et().strftime("%Y-%m-%d")
    for date, day_data in history.items():
        if date < today_iso:
            if isinstance(day_data, dict):
                headlines = day_data.get("headlines", [])
            else:
                headlines = day_data  # old list format
            all_headlines.update(h.lower().strip() for h in headlines)
    return all_headlines

def get_sent_poem_urls(history):
    """Return set of poem URLs already sent."""
    sent = set()
    for date, day_data in history.items():
        if isinstance(day_data, dict):
            url = day_data.get("poem_url")
            if url:
                sent.add(url)
    return sent

def normalize_headline(headline):
    return re.sub(r'[^a-z0-9 ]', '', headline.lower().strip())

def is_duplicate_of_previous(headline, previous_headlines, threshold=0.6):
    norm = normalize_headline(headline)
    norm_words = set(norm.split())
    if len(norm_words) < 3:
        return False
    for prev in previous_headlines:
        prev_words = set(normalize_headline(prev).split())
        if not prev_words:
            continue
        intersection = norm_words & prev_words
        union = norm_words | prev_words
        similarity = len(intersection) / len(union) if union else 0
        if similarity >= threshold:
            return True
    return False

# ─── Poem Fetcher ─────────────────────────────────────────────────────────────

def get_daily_poem(history):
    """
    Fetch the latest poem from Zaiden Werg Substack.
    - Prefers poems published within last 48h
    - Never repeats a poem already sent
    Returns dict with title, text, author_note, link, pub_date — or None.
    """
    sent_poem_urls = get_sent_poem_urls(history)
    cutoff_48h = now_et() - timedelta(hours=48)
    best_fresh = None
    best_fallback = None

    try:
        feed = feedparser.parse(SUBSTACK_FEED)
        for entry in feed.entries[:15]:
            link = entry.get("link", "")
            if link in sent_poem_urls:
                print(f"  [Poem] Skipping already-sent: {entry.get('title', '')}", file=sys.stderr)
                continue

            pub_date = parse_pub_date(entry)
            is_fresh = pub_date and pub_date.astimezone(ET) >= cutoff_48h

            # Extract poem text from <pre> tag (Substack preformatted poetry blocks)
            content_raw = ""
            if hasattr(entry, 'content') and entry.content:
                content_raw = entry.content[0].value
            elif hasattr(entry, 'summary'):
                content_raw = entry.summary

            pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', content_raw, re.DOTALL)
            if pre_match:
                poem_text = clean_html(pre_match.group(1)).strip()
            else:
                poem_text = clean_html(content_raw).strip()

            poem_text = decode_entities(poem_text)

            if len(poem_text) < 50:
                continue  # Not a real poem

            author_note = decode_entities(clean_html(entry.get('summary', '')).strip())
            candidate = {
                "title":       entry.get("title", "").strip(),
                "text":        poem_text,
                "author_note": author_note,
                "link":        link,
                "pub_date":    pub_date,
            }

            if is_fresh and best_fresh is None:
                best_fresh = candidate
                break  # Found a fresh unsent poem — use it
            elif best_fallback is None:
                best_fallback = candidate

        result = best_fresh or best_fallback
        if result:
            print(f"  [Poem] Using: \"{result['title']}\" ({result.get('pub_date', 'unknown date')})", file=sys.stderr)
        else:
            print("  [Poem] No poem found.", file=sys.stderr)
        return result

    except Exception as e:
        print(f"  [Poem] Error fetching Substack: {e}", file=sys.stderr)
        return None

# ─── Feed Fetching ────────────────────────────────────────────────────────────

def fetch_feed(feed_key, max_items=15):
    url = FEEDS[feed_key]
    label = SOURCE_LABELS[feed_key]
    cutoff = now_et() - timedelta(hours=24)
    try:
        feed = feedparser.parse(url)
        items = []
        skipped_old = 0
        for entry in feed.entries[:max_items]:
            pub_date = parse_pub_date(entry)
            if pub_date is not None:
                pub_et = pub_date.astimezone(ET)
                if pub_et < cutoff:
                    skipped_old += 1
                    continue
            items.append({
                "title":       entry.get("title", "").strip(),
                "description": clean_html(entry.get("summary", entry.get("description", ""))),
                "link":        entry.get("link", ""),
                "pub_date":    pub_date,
                "source":      label,
                "audio_url":   next(
                    (enc.get('href') or enc.get('url')
                     for enc in getattr(entry, 'enclosures', [])
                     if 'audio' in enc.get('type', '')),
                    None
                ),
            })
        if skipped_old > 0:
            print(f"  [{feed_key}] Skipped {skipped_old} articles older than 24h", file=sys.stderr)
        return items
    except Exception as e:
        print(f"  Error fetching {feed_key}: {e}", file=sys.stderr)
        return []

def get_latest_rfi_informativo():
    items = fetch_feed("rfi", max_items=20)
    if not items:
        url = FEEDS["rfi"]
        try:
            feed = feedparser.parse(url)
            items = []
            for entry in feed.entries[:20]:
                pub_date = parse_pub_date(entry)
                items.append({
                    "title": entry.get("title", "").strip(),
                    "description": clean_html(entry.get("summary", "")),
                    "link": entry.get("link", ""),
                    "pub_date": pub_date,
                    "source": "RFI en Español",
                    "audio_url": next(
                        (enc.get('href') or enc.get('url')
                         for enc in getattr(entry, 'enclosures', [])
                         if 'audio' in enc.get('type', '')),
                        None
                    ),
                })
        except Exception as e:
            print(f"  Error fetching RFI: {e}", file=sys.stderr)
            return None

    informativos = [i for i in items if "informativo" in i["title"].lower()]
    today_730am = now_et().replace(hour=7, minute=30, second=0, microsecond=0)
    for item in informativos:
        if item["pub_date"] is None or item["pub_date"].astimezone(ET) <= today_730am:
            return item
    return informativos[0] if informativos else None

def get_latest_comite_episode():
    url = FEEDS["comite"]
    cutoff_48h = now_et() - timedelta(hours=48)
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:10]:
            pub_date = parse_pub_date(entry)
            pub_et = pub_date.astimezone(ET) if pub_date else None
            if pub_et and pub_et < cutoff_48h:
                continue
            items.append({
                "title": entry.get("title", "").strip(),
                "description": clean_html(entry.get("summary", "")),
                "link": entry.get("link", ""),
                "pub_date": pub_date,
                "source": "Comite de Lectura",
                "audio_url": next(
                    (enc.get('href') or enc.get('url')
                     for enc in getattr(entry, 'enclosures', [])
                     if 'audio' in enc.get('type', '')),
                    None
                ),
            })
        noticias = [i for i in items if "noticias" in i["title"].lower()]
        return noticias[0] if noticias else (items[0] if items else None)
    except Exception as e:
        print(f"  Error fetching Comite de Lectura: {e}", file=sys.stderr)
        return None

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

# ─── Unified Digest Builder ───────────────────────────────────────────────────

def build_unified_digest(all_raw_items, rfi_transcript=None, comite_episode=None,
                          previous_headlines=None):
    raw_text = ""
    if rfi_transcript:
        raw_text += f"\n\n=== RFI en Español (audio transcript, Spanish to English) ===\n{rfi_transcript[:3000]}\n"
    if comite_episode:
        raw_text += f"\n\n=== Comite de Lectura (Peru podcast) ===\nTitle: {comite_episode['title']}\n{comite_episode['description'][:1500]}\n"
    for item in all_raw_items:
        pub_str = item['pub_date'].astimezone(ET).strftime("%Y-%m-%d %H:%M ET") if item['pub_date'] else "unknown"
        raw_text += (
            f"\n[{item['source']}] {item['title']} (published: {pub_str})\n"
            f"  {item['description'][:200]}\n"
            f"  URL: {item['link']}\n"
        )

    prev_context = ""
    if previous_headlines:
        sample = list(previous_headlines)[:40]
        prev_context = "\n\nSTORIES ALREADY SENT IN PREVIOUS DAYS (skip unless significant new development):\n"
        prev_context += "\n".join(f"- {h}" for h in sample)

    prompt = f"""You are a world-class news editor creating a concise daily digest for a busy professional.

TODAY'S DATE: {now_et().strftime("%A, %B %d, %Y")}

STRICT RULES:
1. FRESHNESS: Only include stories published within the last 24 hours. Discard anything older.
2. NO REPEATS: Do NOT include stories that are the same as or very similar to the "already sent" list below, UNLESS there is a significant new development (e.g., a ceasefire broke down, a vote happened, a new leader was named). If you include an update to a previous story, mark is_new_development as true.
3. DEDUPLICATION: If the same story appears in multiple sources, merge into ONE entry with the best details from each.
4. RANKING: Order from most to least globally important.
5. SUMMARIES: 2 sentences per story — punchy, clear, no fluff. Sentence 1 = what happened. Sentence 2 = why it matters or what's next.
6. CATCHY HEADLINES: Every headline must be specific, punchy, and compelling — like a great newspaper front page. Use strong verbs. Be specific. Create intrigue. NO generic phrases like "tensions rise", "concerns grow", "situation escalates". GOOD examples: "Trump Freezes $2B in Harvard Funding Over DEI Demands", "Iran Agrees to Talks — But Only If Bombs Stay Off the Table", "Peru's Election: 35 Candidates, Zero Clear Frontrunner", "Gaza Ceasefire Collapses After Israel Resumes Strikes". BAD examples: "Middle East Situation Worsens", "Economic Uncertainty Continues".
7. TOPIC TAG: Short label (e.g., "Middle East", "US Politics", "Economy", "Peru", "Climate").
8. SPECIFICITY RULE: Every headline must tell the reader exactly what happened — who did what to whom. If you can't be specific, dig deeper into the summary to find the real news hook.
{prev_context}

Return ONLY valid JSON in this exact format (no markdown, no extra text):
{{
  "date": "...",
  "stories": [
    {{
      "rank": 1,
      "topic": "Middle East",
      "headline": "Catchy specific headline (max 14 words)",
      "summary": "First sentence what happened. Second sentence why it matters.",
      "sources": ["Wall Street Journal", "Al Jazeera"],
      "url": "https://best-link-for-more-info",
      "is_new_development": false
    }}
  ]
}}

Include 10-14 stories total. Prioritize global impact. Include at least 1-2 Peru/Latin America stories if available and fresh.

Raw input (all from last 24 hours):
{raw_text[:12000]}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3500,
            temperature=0.4,
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

# ─── Main ─────────────────────────────────────────────────────────────────────

def aggregate_news():
    today = now_et().strftime("%A, %B %d, %Y")
    today_iso = now_et().strftime("%Y-%m-%d")
    print(f"Aggregating news for {today}...", file=sys.stderr)

    history = load_history()
    previous_headlines = get_previous_headlines(history)
    print(f"  Loaded {len(previous_headlines)} previously sent headlines for dedup", file=sys.stderr)

    print("Fetching RFI en Español...", file=sys.stderr)
    rfi_episode = get_latest_rfi_informativo()
    rfi_transcript = None
    rfi_audio_url = None
    if rfi_episode:
        rfi_audio_url = rfi_episode.get("audio_url")
        rfi_transcript = transcribe_audio(rfi_audio_url)

    print("Fetching Comite de Lectura...", file=sys.stderr)
    comite_episode = get_latest_comite_episode()

    all_items = []
    for key in ["wsj_world", "wsj_us", "wsj_opinion", "nyt", "aljazeera",
                "economist_leaders", "economist_opinion"]:
        print(f"Fetching {SOURCE_LABELS[key]} ({key})...", file=sys.stderr)
        items = fetch_feed(key, max_items=10)
        all_items.extend(items)

    total_fresh = len(all_items)
    print(f"  Total fresh articles (last 24h): {total_fresh}", file=sys.stderr)

    print("Fetching daily poem from Zaiden Werg Substack...", file=sys.stderr)
    poem = get_daily_poem(history)

    print("Building unified digest (dedup + rank + catchy headlines + freshness filter)...", file=sys.stderr)
    unified = build_unified_digest(all_items, rfi_transcript, comite_episode, previous_headlines)

    if not unified:
        fresh_items = [
            item for item in all_items
            if not is_duplicate_of_previous(item["title"], previous_headlines)
        ]
        unified = {
            "date": today,
            "stories": [{"rank": i+1, "topic": "News", "headline": item["title"],
                          "summary": item["description"][:200],
                          "sources": [item["source"]], "url": item["link"],
                          "is_new_development": False}
                        for i, item in enumerate(fresh_items[:12])]
        }

    unified["date"] = today
    unified["date_iso"] = today_iso
    unified["rfi_audio_url"] = rfi_audio_url
    unified["comite_audio_url"] = comite_episode.get("audio_url") if comite_episode else None
    unified["poem"] = poem

    # Update history: store headlines + poem URL
    today_headlines = [s["headline"] for s in unified.get("stories", [])]
    history[today_iso] = {
        "headlines": today_headlines,
        "poem_url": poem["link"] if poem else None,
    }
    save_history(history)
    print(f"  Saved {len(today_headlines)} headlines + poem URL to history", file=sys.stderr)

    output_path = os.path.join(OUTPUT_DIR, f"digest_{today_iso}.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(unified, f, ensure_ascii=False, indent=2, default=str)
    print(f"Digest saved to {output_path}", file=sys.stderr)
    print(output_path)
    return unified

if __name__ == "__main__":
    result = aggregate_news()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
