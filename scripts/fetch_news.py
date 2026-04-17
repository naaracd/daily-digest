#!/usr/bin/env python3
"""
Daily Digest News Fetcher — GitHub Actions version
Rules:
  1. Only include articles published within the last 24 hours.
  2. Skip stories already sent in previous days unless significant new development.
  3. ALL output (headlines, summaries, topics, date) MUST be in Spanish.
  4. Fetch daily poem from Zaiden Werg Substack (no repeats).
"""

import feedparser
import json
import os
import re
import sys
import html as html_module
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

def parse_pub_date(entry):
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    return None

# ─── History / Deduplication ──────────────────────────────────────────────────

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_history(history):
    cutoff = (now_et() - timedelta(days=7)).strftime("%Y-%m-%d")
    pruned = {date: data for date, data in history.items() if date >= cutoff}
    with open(HISTORY_FILE, 'w') as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)

def get_previous_headlines(history):
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
    - Falls back to the most recent unsent poem if nothing fresh
    """
    sent_poem_urls = get_sent_poem_urls(history)
    cutoff_48h = now_et() - timedelta(hours=48)
    best_fresh = None
    best_fallback = None

    try:
        feed = feedparser.parse(SUBSTACK_FEED)
        print(f"  [Poem] Feed has {len(feed.entries)} entries", file=sys.stderr)

        for entry in feed.entries[:20]:
            link = entry.get("link", "")

            if link in sent_poem_urls:
                print(f"  [Poem] Already sent: {entry.get('title', '')}", file=sys.stderr)
                continue

            pub_date = parse_pub_date(entry)
            is_fresh = pub_date and pub_date.astimezone(ET) >= cutoff_48h

            # Extract poem text — try <pre> block first (Substack poetry format)
            content_raw = ""
            if hasattr(entry, 'content') and entry.content:
                content_raw = entry.content[0].value
            elif hasattr(entry, 'summary'):
                content_raw = entry.summary

            # Try <pre> tag (preformatted poetry block)
            pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', content_raw, re.DOTALL)
            if pre_match:
                poem_text = clean_html(pre_match.group(1)).strip()
            else:
                poem_text = clean_html(content_raw).strip()

            # Decode HTML entities
            poem_text = html_module.unescape(poem_text)
            poem_text = poem_text.strip()

            if len(poem_text) < 50:
                print(f"  [Poem] Too short, skipping: {entry.get('title', '')}", file=sys.stderr)
                continue

            # Author note from description
            author_note = html_module.unescape(clean_html(entry.get('summary', '')).strip())

            candidate = {
                "title":       entry.get("title", "").strip(),
                "text":        poem_text,
                "author_note": author_note,
                "link":        link,
                "pub_date":    str(pub_date) if pub_date else None,
            }

            if is_fresh and best_fresh is None:
                best_fresh = candidate
                print(f"  [Poem] Fresh poem found: \"{candidate['title']}\"", file=sys.stderr)
                break
            elif best_fallback is None:
                best_fallback = candidate
                print(f"  [Poem] Fallback poem found: \"{candidate['title']}\"", file=sys.stderr)

        result = best_fresh or best_fallback
        if result:
            print(f"  [Poem] Using: \"{result['title']}\"", file=sys.stderr)
        else:
            print("  [Poem] No poem found — all already sent or feed empty.", file=sys.stderr)
        return result

    except Exception as e:
        print(f"  [Poem] Error: {e}", file=sys.stderr)
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
        raw_text += f"\n\n=== RFI en Español (transcripción de audio) ===\n{rfi_transcript[:3000]}\n"
    if comite_episode:
        raw_text += f"\n\n=== Comite de Lectura (podcast Perú) ===\nTítulo: {comite_episode['title']}\n{comite_episode['description'][:1500]}\n"
    for item in all_raw_items:
        pub_str = item['pub_date'].astimezone(ET).strftime("%Y-%m-%d %H:%M ET") if item['pub_date'] else "desconocido"
        raw_text += (
            f"\n[{item['source']}] {item['title']} (publicado: {pub_str})\n"
            f"  {item['description'][:200]}\n"
            f"  URL: {item['link']}\n"
        )

    prev_context = ""
    if previous_headlines:
        sample = list(previous_headlines)[:40]
        prev_context = "\n\nNOTICIAS YA ENVIADAS EN DÍAS ANTERIORES (omitir a menos que haya un desarrollo nuevo significativo):\n"
        prev_context += "\n".join(f"- {h}" for h in sample)

    system_msg = (
        "Eres un editor de noticias de primer nivel. "
        "DEBES escribir TODA tu respuesta en ESPAÑOL. "
        "Esto incluye: titulares, resúmenes, etiquetas de tema, y la fecha. "
        "Los nombres de fuentes (Wall Street Journal, Al Jazeera, etc.) pueden quedar en inglés. "
        "NUNCA escribas titulares o resúmenes en inglés. "
        "Responde ÚNICAMENTE con JSON válido, sin markdown, sin texto extra."
    )

    user_msg = f"""Crea un resumen de noticias diario conciso para un profesional ocupado.

FECHA DE HOY: {now_et().strftime("%A, %d de %B de %Y")}

REGLAS ESTRICTAS:
1. FRESCURA: Solo incluye noticias publicadas en las últimas 24 horas. Descarta todo lo más antiguo.
2. SIN REPETICIONES: NO incluyas noticias iguales o muy similares a la lista de "ya enviadas" abajo, A MENOS que haya un desarrollo significativo nuevo. Si incluyes una actualización, marca is_new_development como true.
3. DEDUPLICACIÓN: Si la misma noticia aparece en múltiples fuentes, combínalas en UNA sola entrada.
4. ORDEN: De más a menos importante globalmente.
5. RESÚMENES: 2 oraciones por noticia — directas, claras, sin relleno. Oración 1 = qué pasó. Oración 2 = por qué importa o qué sigue.
6. TITULARES LLAMATIVOS EN ESPAÑOL: Específicos, contundentes, con verbos fuertes. NADA de frases genéricas. BUENOS ejemplos: "Trump Congela $2,000 Millones a Harvard por Exigencias sobre DEI", "Irán Acepta Negociar — Pero Solo si las Bombas Quedan Fuera de la Mesa", "El Alto el Fuego en Gaza Colapsa Horas Después de Ser Anunciado". MALOS: "La Situación Empeora", "Continúa la Incertidumbre".
7. ETIQUETA DE TEMA en español: "Medio Oriente", "Política EE.UU.", "Economía", "Perú", "Clima", "América Latina", "Europa", "Asia", "Seguridad", "Tecnología", etc.
8. IDIOMA OBLIGATORIO: TODO en español. Titulares en español. Resúmenes en español. Temas en español.
{prev_context}

Devuelve SOLO JSON válido en este formato exacto:
{{
  "date": "jueves, 17 de abril de 2025",
  "stories": [
    {{
      "rank": 1,
      "topic": "Medio Oriente",
      "headline": "Titular llamativo en español (máx 14 palabras)",
      "summary": "Primera oración qué pasó en español. Segunda oración por qué importa en español.",
      "sources": ["Wall Street Journal", "Al Jazeera"],
      "url": "https://enlace-a-la-noticia",
      "is_new_development": false
    }}
  ]
}}

Incluye 10-14 noticias. Prioriza impacto global. Incluye al menos 1-2 noticias de Perú/América Latina si están disponibles y son recientes.

Noticias de entrada (últimas 24 horas):
{raw_text[:12000]}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens=3500,
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

# ─── Main ─────────────────────────────────────────────────────────────────────

def aggregate_news():
    today = now_et().strftime("%A, %d de %B de %Y")
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
    if poem:
        print(f"  Poem: \"{poem['title']}\"", file=sys.stderr)
    else:
        print("  No poem available today.", file=sys.stderr)

    print("Building unified digest (Spanish, dedup, catchy headlines)...", file=sys.stderr)
    unified = build_unified_digest(all_items, rfi_transcript, comite_episode, previous_headlines)

    if not unified:
        fresh_items = [
            item for item in all_items
            if not is_duplicate_of_previous(item["title"], previous_headlines)
        ]
        unified = {
            "date": today,
            "stories": [{"rank": i+1, "topic": "Noticias", "headline": item["title"],
                          "summary": item["description"][:200],
                          "sources": [item["source"]], "url": item["link"],
                          "is_new_development": False}
                        for i, item in enumerate(fresh_items[:12])]
        }

    unified["date"] = today
    unified["date_iso"] = today_iso
    unified["rfi_audio_url"] = rfi_audio_url
    unified["comite_audio_url"] = comite_episode.get("audio_url") if comite_episode else None
    unified["poem"] = poem  # Always set, even if None

    # Update history
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
