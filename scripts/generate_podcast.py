#!/usr/bin/env python3
"""
Daily Digest Podcast Generator
- Generates a playful, energetic Spanish podcast script from the digest JSON
- Uses gTTS for text-to-speech (Spanish, 1.25x speed via ffmpeg)
- Includes poem at the end
"""

import json
import os
import sys
import subprocess
from datetime import datetime
from openai import OpenAI

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/tmp/digest_output")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def generate_podcast_script(digest_path):
    with open(digest_path, 'r', encoding='utf-8') as f:
        digest = json.load(f)

    date_str = digest.get("date", datetime.now().strftime("%A, %d de %B de %Y"))
    stories  = digest.get("stories", [])
    poem     = digest.get("poem")

    # Build stories block — translate to Spanish if needed
    stories_text = ""
    for s in stories:
        stories_text += (
            f"[{s.get('topic','Mundo')}] {s.get('headline','')}\n"
            f"{s.get('summary','')}\n\n"
        )

    # Build poem block for the script
    poem_block = ""
    if poem and poem.get("text"):
        poem_block = f"""

--- POEMA DEL DÍA ---
Título: {poem.get('title', 'Poema')}
{poem.get('text', '')}
"""

    prompt = f"""Eres el conductor de "El Digest del Día" — un podcast de noticias diarias con MUCHA personalidad.
Fecha de hoy: {date_str}

TU ESTILO (MUY IMPORTANTE — no negociable):
- Eres inteligente, rápido, con humor seco y un toque de ironía cuando la noticia lo merece
- Hablas como un amigo brillante que leyó todo el periódico antes del desayuno y te lo cuenta en el camino al trabajo
- Usas frases cortas y directas. Nada de relleno. Cada palabra cuenta.
- Tienes ENERGÍA — no eres monótono ni aburrido. Varía el ritmo: a veces urgente, a veces irónico, a veces con una pausa dramática
- Puedes hacer comentarios ligeros o reacciones breves (ej. "Sí, leyeron bien.", "No es broma.", "Spoiler: no terminó bien.", "Como si no tuviéramos suficiente con eso...", "Esto sí que es un giro.")
- Usas transiciones naturales y variadas — NUNCA "la siguiente noticia es..." — más bien: "Mientras tanto en...", "Hablando de cosas que no salen bien...", "Saltamos al otro lado del mundo...", "Y ahora algo que sí es buena noticia...", "Esto no te lo puedes perder..."
- Agrupa noticias relacionadas de forma orgánica
- NO menciones fuentes ni URLs en el audio
- Duración objetivo: 4–5 minutos al leerlo (unas 600–750 palabras)
- Abre con un GANCHO que haga que la persona quiera seguir escuchando — algo específico de hoy, no genérico
- Cierra con algo memorable después del poema: una reflexión rápida, un chiste sutil, o simplemente algo cálido

IDIOMA: TODO EN ESPAÑOL LATINOAMERICANO. Si algún titular o resumen está en inglés, tradúcelo al español antes de usarlo. Sin excepción.

NOTICIAS DE HOY:
{stories_text}

{f'''AL FINAL DEL PODCAST, lee este poema de forma natural y cálida, como si lo compartieras con un amigo. Preséntalo brevemente (ej. "Y para cerrar, un poema de Zaiden Werg que llegó hoy...") y luego léelo completo:
{poem_block}''' if poem_block else ''}

IMPORTANTE: Escribe SOLO el guión hablado. Sin títulos, sin numeración, sin corchetes, sin markdown, sin indicaciones de escena. Solo las palabras exactas que se van a decir en voz alta. TODO EN ESPAÑOL."""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Eres un conductor de podcast en español latinoamericano. SIEMPRE escribes en español. Nunca en inglés. Eres energético, inteligente y entretenido."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.85,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  GPT script error: {e}", file=sys.stderr)
        # Fallback: basic Spanish script
        lines = [f"Bienvenidos al Digest del Día. Hoy es {date_str}."]
        for s in stories:
            headline = s.get('headline', '')
            summary  = s.get('summary', '')
            lines.append(f"{headline}. {summary}")
        if poem and poem.get("text"):
            lines.append(f"Y para cerrar, un poema de Zaiden Werg: {poem['title']}.")
            lines.append(poem['text'])
        lines.append("Eso es todo por hoy. Hasta mañana.")
        return " ".join(lines)


def synthesize_audio(script_text, output_path):
    """Convert text to speech using gTTS (Spanish) then speed up 1.25x with ffmpeg."""
    try:
        from gtts import gTTS
        tmp_path = output_path.replace(".mp3", "_raw.mp3")
        print(f"  Synthesizing Spanish TTS...", file=sys.stderr)
        tts = gTTS(text=script_text, lang='es', slow=False)
        tts.save(tmp_path)
        print(f"  Speeding up to 1.25x...", file=sys.stderr)
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_path,
             "-filter:a", "atempo=1.25",
             "-q:a", "4", output_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  ffmpeg error: {result.stderr[:200]}", file=sys.stderr)
            import shutil
            shutil.copy(tmp_path, output_path)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  Podcast generated: {output_path} ({size_mb:.1f} MB)", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  TTS error: {e}", file=sys.stderr)
        return False


def find_latest_digest():
    try:
        digests = sorted(
            [f for f in os.listdir(OUTPUT_DIR)
             if f.startswith("digest_") and f.endswith(".json")],
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

    print(f"Generating podcast from: {digest_path}", file=sys.stderr)
    script = generate_podcast_script(digest_path)

    # Save script text
    script_path = digest_path.replace(".json", "_podcast_script.txt")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script)
    print(f"Podcast script saved: {script_path}", file=sys.stderr)

    # Generate audio
    audio_path = digest_path.replace(".json", "_podcast.mp3")
    success = synthesize_audio(script, audio_path)
    if success:
        print(f"Podcast audio saved: {audio_path}")
    else:
        print("Podcast audio generation failed.", file=sys.stderr)
        sys.exit(1)
