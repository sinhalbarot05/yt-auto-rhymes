import os
import sys
import json
import time
import math
import wave
import struct
import random
import textwrap
import subprocess
import urllib.parse
import requests

# Auto-ensure yt-dlp is installed
try:
    import yt_dlp
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"], check=False)

from groq import Groq
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, afx

HISTORY_FILE = "story_history.json"
# Using v2 filename so the workflow replaces the old vocal track with the pure instrumental cut
LOCKED_SONG_PATH = "assets/indila_love_story_instrumental_v2.mp3"
LOCKED_SONG_TITLE = "Love Story (Instrumental Slowed & Reverb) - Indila"

GOLDEN_START_SEC = 45
GOLDEN_DURATION_SEC = 30

STORY_ARCHETYPES = [
    "Enemies to Lovers: Two competitive university rivals who bicker constantly until a sudden storm forces him to protect her",
    "Fake Dating to Real Obsession: A cold popular senior and a quiet girl fake-date to stop rumors, but he falls in love first",
    "The Second Lead Rescue: She cried over a boy who broke his promise, until his handsome best friend holds an umbrella over her in the rain",
    "Childhood Neighbours to Couple: Growing up next door from teasing kids to an emotional rooftop confession",
    "CEO & The Fearless Intern: Everyone fears the young company heir except the clumsy intern who accidentally bumps into him",
    "Brother's Best Friend Forbidden Crush: He treated her like a little sister for years until another guy asks her out and he gets jealous",
    "Subway Strangers to Soulmates: Taking the same 7 AM train every morning in silence until he finally speaks to her",
    "Cold Ice Prince & Sunshine Girl: The aloof campus genius who ignores everyone melts only when she smiles at him",
    "Secret Identity Crush: Academic rivals by day who don't realize they are anonymous late-night texting confidants",
    "Bodyguard & Heiress: Hired strictly to protect her from afar, he breaks his own rule the night she cries alone"
]


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"used_titles": [], "used_archetypes": [], "used_dialogues": [], "total_videos": 0}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def get_bold_font(size):
    """Loads crisp sans-serif bold font for clean English lettering."""
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_clean_floating_ages(male_age, female_age, output_path):
    """
    Renders neat, non-overlapping floating age numbers in the top-left (Blue) and top-right (Pink)
    using 2x supersampling so they never duplicate or corrupt.
    """
    scale = 2
    w, h = 1080 * scale, 180 * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_age = get_bold_font(64 * scale)
    font_lbl = get_bold_font(20 * scale)

    def draw_badge(cx, cy, label, age_text, color_rgb):
        pw, ph = 150 * scale, 92 * scale
        x0, y0 = cx - pw // 2, cy - ph // 2
        x1, y1 = cx + pw // 2, cy + ph // 2
        # Sleek dark glass pill
        draw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=24 * scale,
            fill=(14, 18, 28, 210),
            outline=color_rgb + (230,),
            width=3 * scale
        )
        draw.text((cx, y0 + 21 * scale), label, font=font_lbl, fill=color_rgb + (255,), anchor="mm")
        draw.text((cx, y0 + 60 * scale), str(age_text).strip(), font=font_age, fill=(255, 255, 255, 255), anchor="mm")

    if male_age:
        draw_badge(135 * scale, 90 * scale, "HIM", male_age, (65, 175, 255))
    if female_age:
        draw_badge(945 * scale, 90 * scale, "HER", female_age, (255, 85, 140))

    img.resize((1080, 180), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def render_single_speaker_bubble(text, side, bubble_type, output_path):
    """
    Renders a single character's comic bubble in 100% pure English:
    - side='left' (Boy): Tail/dots point down-left toward the boy's head.
    - side='right' (Girl): Tail/dots point down-right toward the girl's head.
    - bubble_type='speech': Smooth comic oval with sharp pointer tail.
    - bubble_type='thought': Fluffy scalloped cloud with 3 trailing thought circles.
    """
    scale = 2
    cw, ch = 560 * scale, 300 * scale
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_text = get_bold_font(27 * scale)
    font_tag = get_bold_font(17 * scale)

    # Sanitize text to pure ASCII/English printable characters only (zero foreign glyphs possible)
    clean_text = "".join(ch for ch in str(text) if ord(ch) < 128).strip()
    if not clean_text:
        clean_text = "..."

    wrapped = textwrap.wrap(clean_text, width=21)[:3]
    multiline = "\n".join(wrapped)

    bbox = draw.multiline_textbbox((0, 0), multiline, font=font_text, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    bw = min(cw - 60 * scale, max(310 * scale, tw + 76 * scale))
    bh = max(125 * scale, th + 64 * scale)

    bx0 = (cw - bw) // 2
    by0 = 32 * scale
    bx1 = bx0 + bw
    by1 = by0 + bh
    cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2

    is_left = (side == "left")
    accent = (40, 140, 250) if is_left else (240, 70, 135)
    who_label = "HIM" if is_left else "HER"

    if bubble_type == "thought":
        # Scalloped cloud border
        rx, ry = bw // 2, bh // 2
        num_puffs = 14
        puff_r = 28 * scale
        for i in range(num_puffs):
            ang = (2 * math.pi * i) / num_puffs
            px = int(cx + (rx - 8 * scale) * math.cos(ang))
            py = int(cy + (ry - 6 * scale) * math.sin(ang))
            draw.ellipse(
                [px - puff_r, py - puff_r, px + puff_r, py + puff_r],
                fill=(255, 255, 255, 255),
                outline=(20, 20, 25, 255),
                width=4 * scale
            )
        # Clean inner cloud core
        draw.rounded_rectangle(
            [bx0 + 10 * scale, by0 + 8 * scale, bx1 - 10 * scale, by1 - 8 * scale],
            radius=30 * scale,
            fill=(255, 255, 255, 255)
        )
        # Trailing thought circles pointing down to the specific speaker
        tx_start = cx - 45 * scale if is_left else cx + 45 * scale
        step = -14 * scale if is_left else 14 * scale
        dots = [
            (tx_start, by1 + 18 * scale, 11 * scale),
            (tx_start + step, by1 + 42 * scale, 8 * scale),
            (tx_start + step * 2, by1 + 60 * scale, 5 * scale)
        ]
        for dx, dy, dr in dots:
            draw.ellipse(
                [dx - dr, dy - dr, dx + dr, dy + dr],
                fill=(255, 255, 255, 255),
                outline=(20, 20, 25, 255),
                width=3 * scale
            )
        tag_text = f"{who_label} (THOUGHT)"
    else:
        # Smooth oval speech bubble
        draw.rounded_rectangle(
            [bx0, by0, bx1, by1],
            radius=42 * scale,
            fill=(255, 255, 255, 255),
            outline=(20, 20, 25, 255),
            width=4 * scale
        )
        # Single directional pointer tail toward speaker
        if is_left:
            tx = bx0 + int(bw * 0.32)
            tail = [
                (tx - 15 * scale, by1 - 3 * scale),
                (tx - 36 * scale, by1 + 42 * scale),
                (tx + 15 * scale, by1 - 3 * scale)
            ]
        else:
            tx = bx0 + int(bw * 0.68)
            tail = [
                (tx - 15 * scale, by1 - 3 * scale),
                (tx + 36 * scale, by1 + 42 * scale),
                (tx + 15 * scale, by1 - 3 * scale)
            ]
        draw.polygon(tail, fill=(255, 255, 255, 255), outline=(20, 20, 25, 255))
        draw.line([(tx - 13 * scale, by1 - 2 * scale), (tx + 13 * scale, by1 - 2 * scale)], fill=(255, 255, 255, 255), width=6 * scale)
        tag_text = who_label

    # Speaker tag pill at top of bubble
    pw = (145 if bubble_type == "thought" else 80) * scale
    ph = 26 * scale
    draw.rounded_rectangle([cx - pw // 2, by0 - ph // 2, cx + pw // 2, by0 + ph // 2], radius=12 * scale, fill=accent + (255,))
    draw.text((cx, by0), tag_text, font=font_tag, fill=(255, 255, 255, 255), anchor="mm")

    # Crisp English dialogue text
    draw.multiline_text(
        (cx, cy + 4 * scale),
        multiline,
        font=font_text,
        fill=(15, 15, 20, 255),
        align="center",
        anchor="mm",
        spacing=5 * scale
    )

    img.resize((560, 300), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def select_groq_chat_model(client):
    """Filters out whisper/audio/guard models so Groq always uses a true text LLM."""
    models_resp = client.models.list().data
    all_ids = [m.id for m in models_resp]
    banned = ("whisper", "guard", "tts", "playai", "embed", "vision", "allam")
    chat_models = [m for m in all_ids if not any(b in m.lower() for b in banned)]

    preferred = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "deepseek-r1-distill-llama-70b",
        "qwen-qwq-32b",
        "gemma2-9b-it",
        "llama3-70b-8192",
        "llama3-8b-8192"
    ]
    for p in preferred:
        if p in chat_models:
            return p
    return chat_models[0] if chat_models else "llama-3.3-70b-versatile"


def build_story_prompts(chosen_archetype, used_titles):
    entropy = f"{int(time.time())}-{random.randint(10000, 99999)}"
    system_prompt = (
        "You are an elite Korean Manhwa romance scriptwriter. "
        "You write 100% English scripts where EVERY scene features a back-and-forth exchange "
        "between the male lead (left) and female lead (right). Output strictly valid JSON."
    )
    user_prompt = f"""Create a brand-new, original 5-scene vertical Korean Manhwa romance Short script.
Run Seed: {entropy}
Concept Direction: "{chosen_archetype}"
Previously Used Titles (DO NOT REPEAT): {json.dumps(used_titles[-8:])}

RULES FOR PERFECT TWO-SPEAKER DIALOGUE & ANATOMY:
1. Every scene has TWO separate bubbles:
   - "male_bubble_type": "speech" or "thought"
   - "male_text": What the boy says or thinks (pure English, 4 to 9 words).
   - "female_bubble_type": "speech" or "thought"
   - "female_text": How the girl replies or thinks back (pure English, 4 to 9 words).
2. "scene_action" describes ONLY the visual artwork and characters facing each other naturally (NO back-turned twisted necks, NO text in the art).

Return ONLY valid JSON matching this exact structure:
{{
  "trope": "Short catchy trope title",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "video_title": "Catchy emotional English title with emojis #Shorts #manhwa #lovestory",
  "male_dna": "handsome Korean manhwa male lead with [hair color/style], [eye color] eyes, wearing [stylish outfit]",
  "female_dna": "beautiful Korean manhwa female lead with [hair color/style], [eye color] eyes, wearing [stylish outfit]",
  "scenes": [
    {{
      "male_age": "19",
      "female_age": "18",
      "male_bubble_type": "speech",
      "male_text": "Why are you out in the rain?",
      "female_bubble_type": "thought",
      "female_text": "He actually came looking for me...",
      "scene_action": "medium shot of both characters facing each other under an umbrella in the rain, warm streetlight glow, romantic eye contact"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_combinatorial_fallback(history):
    """Dynamic combinatorial generator if both LLMs are unreachable."""
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    m_hair = random.choice(["jet-black", "silver-grey", "dark ash-brown", "midnight-blue"])
    f_hair = random.choice(["long chestnut", "wavy dark-brown", "soft caramel", "raven-black"])

    return {
        "trope": f"Manhwa Romance Story #{run_id}",
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": f"He Pretended Not To Care... Until That Night 💔✨ #{run_id} #Shorts #manhwa #lovestory",
        "male_dna": f"handsome Korean manhwa boy with {m_hair} hair, sharp warm eyes, wearing a fitted dark jacket",
        "female_dna": f"cute Korean manhwa girl with {f_hair} hair, bright expressive eyes, wearing a cozy pastel cardigan",
        "scenes": [
            {
                "male_age": "18", "female_age": "17",
                "male_bubble_type": "speech", "male_text": "Stop sitting alone. Sit next to me.",
                "female_bubble_type": "thought", "female_text": "Why is the coldest guy talking to me?",
                "scene_action": "university lecture hall, boy on left looking at blushing girl on right, warm afternoon sunlight through windows"
            },
            {
                "male_age": "18", "female_age": "17",
                "male_bubble_type": "thought", "male_text": "She looks freezing. Take my scarf.",
                "female_bubble_type": "speech", "female_text": "Wait, aren't you cold too?",
                "scene_action": "snowy evening bus stop, boy gently wrapping a warm scarf around the girl's neck while facing her, soft snow falling"
            },
            {
                "male_age": "19", "female_age": "18",
                "male_bubble_type": "speech", "male_text": "Stay behind me. Don't let go.",
                "female_bubble_type": "thought", "female_text": "His hand is holding mine so tightly...",
                "scene_action": "dramatic rainy street at night, boy holding umbrella over girl while shielding her, glowing neon reflections"
            },
            {
                "male_age": "20", "female_age": "19",
                "male_bubble_type": "speech", "male_text": "I never hated you. I was scared.",
                "female_bubble_type": "speech", "female_text": "Scared of what?",
                "scene_action": "rooftop balcony under starry night sky, boy gently touching girl's cheek, emotional close-up facing each other"
            },
            {
                "male_age": "21", "female_age": "20",
                "male_bubble_type": "speech", "male_text": "Scared of how much I love you.",
                "female_bubble_type": "thought", "female_text": "I've loved you from the very start.",
                "scene_action": "golden sunset rooftop, couple holding both hands and smiling warmly into each other's eyes, floating cherry blossom petals"
            }
        ]
    }


def generate_fresh_story(history):
    used_arch = history.get("used_archetypes", [])[-6:]
    used_titles = history.get("used_titles", [])
    avail = [a for a in STORY_ARCHETYPES if a not in used_arch] or STORY_ARCHETYPES
    chosen_arch = random.choice(avail)
    sys_p, usr_p = build_story_prompts(chosen_arch, used_titles)

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            model = select_groq_chat_model(client)
            print(f"[GROQ] Generating two-speaker English script with {model}...")
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                response_format={"type": "json_object"},
                temperature=0.88
            )
            data = json.loads(res.choices[0].message.content.strip())
            if "scenes" in data and len(data["scenes"]) >= 4:
                data["archetype_used"] = chosen_arch
                return data
        except Exception as e:
            print(f"⚠️ Groq fallback ({e}). Trying secondary LLM...")

    try:
        resp = requests.post(
            "https://text.pollinations.ai/openai",
            json={
                "model": "openai",
                "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                "response_format": {"type": "json_object"}
            },
            timeout=45
        )
        if resp.status_code == 200:
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            data = json.loads(raw)
            if "scenes" in data and len(data["scenes"]) >= 4:
                data["archetype_used"] = chosen_arch
                return data
    except Exception:
        pass

    return generate_combinatorial_fallback(history)


def fetch_clean_anatomical_manhwa_art(scene, male_dna, female_dna, story_seed, idx, output_path):
    """
    Generates 100% TEXT-FREE, anatomically natural romantic Manhwa art.
    Strictly forbids Flux from drawing speech bubbles, Chinese text, or backward necks.
    Leaves clean upper headroom for our Python vector bubbles and age badges.
    """
    api_key = os.getenv("POLLINATIONS_API_KEY")
    action = scene.get("scene_action", "romantic couple looking at each other")

    prompt = (
        f"Masterpiece Korean webtoon romance illustration, 9:16 vertical composition. "
        f"Characters positioned in the lower two-thirds with generous sky/ceiling headroom above their heads: "
        f"On the left side is {male_dna} in natural three-quarter front profile facing right; "
        f"On the right side is {female_dna} in natural three-quarter front profile facing left. "
        f"Action: {action}. "
        f"Anatomical perfection: natural human neck and shoulder alignment, front-facing torsos, warm expressive eyes, "
        f"clean cel-shaded manhwa art style, soft romantic lighting. "
        f"STRICTLY NO TEXT, NO SPEECH BUBBLES, NO NUMBERS, NO CHINESE CHARACTERS, NO LETTERS, NO WATERMARK."
    )

    encoded = urllib.parse.quote(prompt)
    seed = story_seed + (idx * 131)
    url = (
        f"https://gen.pollinations.ai/image/{encoded}"
        f"?width=1080&height=1920&model=flux&seed={seed}&nologo=true&enhance=false"
    )
    if api_key:
        url += f"&key={api_key}"

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"[ART] Generating clean text-free Manhwa frame {idx + 1}/5...")
    for attempt in range(4):
        try:
            res = requests.get(url, headers=headers, timeout=75)
            if res.status_code == 200 and "image" in res.headers.get("Content-Type", "") and len(res.content) > 15000:
                with open(output_path, "wb") as f:
                    f.write(res.content)
                # Ensure exact 1080x1920 dimensions
                with Image.open(output_path) as im:
                    im.convert("RGB").resize((1080, 1920), Image.LANCZOS).save(output_path, "JPEG", quality=95)
                print(f"✅ Clean Scene {idx + 1} saved: {output_path}")
                return True
            time.sleep(4)
        except Exception:
            time.sleep(4)
    return False


def synthesize_indila_waltz_fallback(output_mp3, duration_sec=30):
    raw_wav = "workspace/waltz_raw.wav"
    sample_rate = 44100
    num_samples = int(sample_rate * duration_sec)
    waltz_bars = [
        ([146.83, 293.66, 349.23, 440.00], [587.33, 523.25, 440.00]),
        ([116.54, 233.08, 293.66, 349.23], [523.25, 466.16, 392.00]),
        ([98.00, 196.00, 233.08, 293.66], [466.16, 440.00, 349.23]),
        ([110.00, 220.00, 277.18, 329.63], [440.00, 392.00, 329.63])
    ]
    beat_len = 0.65
    bar_len = beat_len * 3.0

    with wave.open(raw_wav, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(num_samples):
            t = i / sample_rate
            bar_idx = int(t / bar_len) % len(waltz_bars)
            beat_in_bar = min(2, max(0, int((t % bar_len) / beat_len)))
            note_t = max(0.0, (t % bar_len) - (beat_in_bar * beat_len))

            arp_notes, mel_notes = waltz_bars[bar_idx]
            arp_freq = arp_notes[min(beat_in_bar + 1, 3)]
            bass_freq = arp_notes[0]
            mel_freq = mel_notes[beat_in_bar]

            env_arp = math.exp(-note_t * 3.2) * min(1.0, note_t * 40.0)
            env_bass = math.exp(-(t % bar_len) * 1.4)

            signal = 0.35 * math.sin(2 * math.pi * bass_freq * t) * env_bass
            signal += 0.35 * (math.sin(2 * math.pi * arp_freq * t) + 0.4 * math.sin(4 * math.pi * arp_freq * t)) * env_arp

            if t >= 10.4:
                swell = min(1.0, (t - 10.4) / 1.5)
                vibrato = 1.0 + 0.004 * math.sin(2 * math.pi * 5.2 * t)
                signal += 0.45 * swell * (
                    math.sin(2 * math.pi * mel_freq * vibrato * t)
                    + 0.5 * math.sin(2 * math.pi * (mel_freq * 2) * vibrato * t)
                )

            sample = int(max(-1.0, min(1.0, signal * 0.6)) * 32767)
            wf.writeframesraw(struct.pack("<h", sample))

    subprocess.run([
        "ffmpeg", "-y", "-i", raw_wav,
        "-af", "aecho=0.8:0.88:65:0.45,lowpass=f=3800",
        "-b:a", "192k", output_mp3
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3 if os.path.exists(output_mp3) else raw_wav


def get_indila_pure_instrumental():
    """
    Fetches the PURE INSTRUMENTAL (no French vocals) of Indila - Love Story (Slowed & Reverb),
    slices the 0:45-1:15 climax window, and caches it in assets/indila_love_story_instrumental_v2.mp3.
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 40000:
        print(f"✅ Using cached pure instrumental cut: {LOCKED_SONG_PATH}")
        return LOCKED_SONG_PATH

    raw_download = "workspace/indila_inst_raw.mp3"
    # Strictly query piano/violin/karaoke instrumentals without vocals
    queries = [
        "scsearch5:Indila Love Story instrumental piano slowed reverb",
        "scsearch5:Indila Love Story violin instrumental slowed",
        "ytsearch5:Indila Love Story instrumental no vocals slowed reverb"
    ]

    downloaded = False
    for q in queries:
        print(f"[MUSIC] Searching pure instrumental via: {q}...")
        try:
            if os.path.exists(raw_download):
                os.remove(raw_download)
            cmd = [
                sys.executable, "-m", "yt_dlp",
                q,
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "--match-filter", "duration > 90 & duration < 420",
                "--max-downloads", "1",
                "--no-playlist",
                "--quiet",
                "--output", raw_download
            ]
            subprocess.run(cmd, timeout=65, check=False)
            if os.path.exists(raw_download) and os.path.getsize(raw_download) > 50000:
                downloaded = True
                break
        except Exception:
            continue

    if downloaded:
        print("[AUDIO] Mastering 0:45-1:15 instrumental climax cut...")
        slice_cmd = [
            "ffmpeg", "-y",
            "-ss", str(GOLDEN_START_SEC),
            "-t", str(GOLDEN_DURATION_SEC),
            "-i", raw_download,
            "-af", "aecho=0.8:0.85:50:0.25,loudnorm=I=-14:TP=-1.5:LRA=11",
            "-b:a", "192k",
            LOCKED_SONG_PATH
        ]
        subprocess.run(slice_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 30000:
            return LOCKED_SONG_PATH

    return synthesize_indila_waltz_fallback("workspace/indila_waltz_fallback.mp3", duration_sec=30)


def build_pipeline():
    print("=== STARTING CLEAN ENGLISH VECTOR BUBBLE + ANATOMY-SAFE MANHWA PIPELINE ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    history = load_history()
    story_data = generate_fresh_story(history)

    history["used_titles"].append(story_data.get("video_title", ""))
    history.setdefault("used_archetypes", []).append(story_data.get("archetype_used", ""))
    history["total_videos"] = history.get("total_videos", 0) + 1
    save_history(history)

    with open("workspace/video_metadata.json", "w", encoding="utf-8") as f:
        json.dump(story_data, f, indent=2, ensure_ascii=False)

    male_dna = story_data.get("male_dna", "")
    female_dna = story_data.get("female_dna", "")
    scenes = story_data.get("scenes", [])
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.2
    second_bubble_delay = 2.0  # Girl's bubble pops in at 2.0s for natural conversation flow
    clips = []

    for idx, sc in enumerate(scenes):
        bg_path = f"workspace/scene_bg_{idx}.jpg"
        if not fetch_clean_anatomical_manhwa_art(sc, male_dna, female_dna, story_seed, idx, bg_path):
            continue

        # 1. Clean Text-Free Manhwa Artwork with subtle slow zoom
        base_clip = ImageClip(bg_path).set_duration(scene_duration).resize((1080, 1920))
        base_clip = base_clip.resize(lambda t: 1.0 + (0.018 * t))
        layers = [base_clip]

        # 2. Neat, Non-Overlapping Floating Age Badges (Top-Left Blue, Top-Right Pink)
        age_png = f"workspace/ages_{idx}.png"
        render_clean_floating_ages(sc.get("male_age", "20"), sc.get("female_age", "19"), age_png)
        age_clip = ImageClip(age_png).set_position(("center", 28)).set_duration(scene_duration)
        layers.append(age_clip)

        # 3. Bubble 1: Male Lead (Left Side, appears at 0.0s, tail points down-left to boy)
        m_text = sc.get("male_text", sc.get("dialogue", ""))
        m_type = sc.get("male_bubble_type", "speech").lower()
        if m_text:
            m_png = f"workspace/bubble_male_{idx}.png"
            render_single_speaker_bubble(m_text, side="left", bubble_type=m_type, output_path=m_png)
            m_clip = (
                ImageClip(m_png)
                .set_position((30, 210))
                .set_start(0.0)
                .set_duration(scene_duration)
            )
            layers.append(m_clip)

        # 4. Bubble 2: Female Lead (Right Side, pops in at 2.0s, tail/dots point down-right to girl)
        f_text = sc.get("female_text", "")
        f_type = sc.get("female_bubble_type", "thought").lower()
        if f_text:
            f_png = f"workspace/bubble_female_{idx}.png"
            render_single_speaker_bubble(f_text, side="right", bubble_type=f_type, output_path=f_png)
            f_clip = (
                ImageClip(f_png)
                .set_position((490, 480))
                .set_start(second_bubble_delay)
                .set_duration(scene_duration - second_bubble_delay)
            )
            layers.append(f_clip)

        comp = CompositeVideoClip(layers, size=(1080, 1920)).set_duration(scene_duration)
        clips.append(comp)

    if not clips:
        raise RuntimeError("❌ No scenes were generated.")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration

    audio_path = get_indila_pure_instrumental()
    if audio_path and os.path.exists(audio_path):
        audio_clip = AudioFileClip(audio_path)
        if audio_clip.duration < total_dur:
            audio_clip = afx.audio_loop(audio_clip, duration=total_dur)
        else:
            audio_clip = audio_clip.subclip(0, total_dur)
        audio_clip = audio_clip.audio_fadein(0.8).audio_fadeout(1.5).volumex(0.95)
        final_video = final_video.set_audio(audio_clip)

    output_mp4 = "videos/final_manhwa_short.mp4"
    final_video.write_videofile(
        output_mp4,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"]
    )
    print(f"🎉 FLAWLESS ENGLISH MANHWA SHORT READY: {output_mp4}")


if __name__ == "__main__":
    build_pipeline()
