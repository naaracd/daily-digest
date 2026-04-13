#!/usr/bin/env python3
"""
Daily Digest Podcast Generator — v3
- Script written in Spanish (conversational, engaging)
- Audio generated at 1.25x speed via ffmpeg atempo filter
- Email digest stays in English (separate pipeline)
"""

import json
import os
import sys
import re
from datetime import datetime
from gtts import gTTS
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/tmp/digest_output")


def build_spanish_script(digest):
    """
    Use GPT to write a natural, conversational Spanish podcast script.
    Style: like a smart Latin American friend catching you up on the news.
    """
    date_str = digest.get("date", datetime.now().strftime("%A, %B %d, %Y"))
    stories  = digest.get("stories", [])

    stories_text = ""
    for s in stories:
        stories_text += (
            f"[{s.get('topic','World')}] {s.get('headline','')}\n"
            f"{s.get('summary','')}\n"
            f"Fuentes: {', '.join(s.get('sources',[]))}\n\n"
        )

    prompt = f"""Eres el conductor de un podcast de noticias diarias llamado "El Digest del Día".
Fecha: {date_str}

Guía de estilo:
- Habla como un amigo inteligente y bien informado que te pone al día — NO como un locutor rígido de televisión
- Conversacional pero sustancioso. Frases cortas. Ritmo natural.
- Usa transiciones ligeras como "Mientras tanto...", "En ese mismo contexto...", "Más cerca de casa...", "Y esto es interesante...", "Cambiando de tema..."
- Varía tu energía — algunas noticias son urgentes, otras son para reflexionar, algunas tienen un toque irónico
- NO digas "número uno", "historia uno", etc. Fluye naturalmente entre temas
- Agrupa noticias relacionadas de forma natural (ej. todo Medio Oriente junto)
- Duración total: unos 5–7 minutos al leerlo en voz alta (aproximadamente 800–1000 palabras)
- Termina con un cierre breve y cálido
- Escribe TODO en español latinoamericano natural

Aquí están las noticias a cubrir (resúmenes en inglés — tradúcelos y adáptalos al español):
{stories_text}

Escribe SOLO el guión hablado — sin indicaciones escénicas, sin encabezados, sin markdown. Solo las palabras que se van a decir."""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1600,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  GPT script error: {e}", file=sys.stderr)
        # Fallback: basic Spanish script
        lines = [f"Bienvenidos al Digest del Día. Hoy es {date_str}."]
        for s in stories:
            lines.append(f"{s.get('headline','')}. {s.get('summary','')}")
        lines.append("Eso es todo por hoy. Hasta mañana.")
        return " ".join(lines)


def text_to_speech_chunked(text, output_path, lang='es'):
    """Convert text to speech using gTTS in Spanish, chunked for long texts."""
    max_chunk = 500
    sentences = re.split(r'(?<=[.!?…])\s+', text)

    chunks, current = [], ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if sent[-1] not in '.!?…':
            sent += '.'
        if len(current) + len(sent) + 1 > max_chunk:
            if current:
                chunks.append(current.strip())
            current = sent
        else:
            current = (current + ' ' + sent).strip()
    if current:
        chunks.append(current)

    print(f"  Generating Spanish TTS ({len(chunks)} chunks)...", file=sys.stderr)
    raw_path = output_path.replace(".mp3", "_raw.mp3")
    audio_files = []

    for i, chunk in enumerate(chunks):
        try:
            tts = gTTS(text=chunk, lang=lang, slow=False)
            path = f"/tmp/pc_{i:04d}.mp3"
            tts.save(path)
            audio_files.append(path)
        except Exception as e:
            print(f"  Chunk {i} error: {e}", file=sys.stderr)

    if not audio_files:
        return None

    # Concatenate all chunks into raw file
    if len(audio_files) == 1:
        import shutil
        shutil.copy(audio_files[0], raw_path)
    else:
        concat = "/tmp/concat.txt"
        with open(concat, 'w') as f:
            for p in sorted(audio_files):
                f.write(f"file '{p}'\n")
        ret = os.system(f"ffmpeg -y -f concat -safe 0 -i {concat} -c copy '{raw_path}' 2>/dev/null")
        if ret != 0:
            import shutil
            shutil.copy(audio_files[0], raw_path)

    # Apply 1.25x speed using ffmpeg atempo filter
    print(f"  Applying 1.25x speed...", file=sys.stderr)
    ret = os.system(
        f"ffmpeg -y -i '{raw_path}' -filter:a 'atempo=1.25' -vn '{output_path}' 2>/dev/null"
    )
    if ret != 0:
        # Fallback: use raw without speed change
        import shutil
        shutil.copy(raw_path, output_path)
        print(f"  Speed filter failed, using original speed.", file=sys.stderr)

    # Cleanup
    try: os.remove(raw_path)
    except: pass
    for p in audio_files:
        try: os.remove(p)
        except: pass

    return output_path


def generate_podcast(digest_path=None):
    if digest_path is None:
        digests = sorted(
            [f for f in os.listdir(OUTPUT_DIR)
             if f.startswith("digest_") and f.endswith(".json")],
            reverse=True
        )
        if not digests:
            print("No digest found.", file=sys.stderr)
            return None
        digest_path = os.path.join(OUTPUT_DIR, digests[0])

    with open(digest_path, 'r', encoding='utf-8') as f:
        digest = json.load(f)

    print("Writing conversational Spanish podcast script...", file=sys.stderr)
    script = build_spanish_script(digest)

    script_path = digest_path.replace(".json", "_podcast_script.txt")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script)
    print(f"Script saved: {script_path}", file=sys.stderr)

    audio_path = digest_path.replace(".json", "_podcast.mp3")
    result = text_to_speech_chunked(script, audio_path, lang='es')

    if result:
        size_mb = os.path.getsize(result) / (1024 * 1024)
        print(f"Podcast generated: {audio_path} ({size_mb:.1f} MB)")
        return audio_path
    else:
        print("Podcast generation failed.", file=sys.stderr)
        return None


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    result = generate_podcast(path)
    sys.exit(0 if result else 1)
