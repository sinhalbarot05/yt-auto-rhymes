import os
import sys
import io
import json
import time
import math
import wave
import struct
import base64
import random
import textwrap
import subprocess
import urllib.parse
import requests

for pkg in ("yt-dlp", "numpy"):
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", pkg], check=False)

import numpy as np
from groq import Groq
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips
)

HISTORY_FILE = "story_history.json"
AUDIO_CACHE_PATH = "assets/indila_love_story_ethereal_inst_v7.mp3"

# Real 2026 Free-Pollen Models on gen.pollinations.ai
GEN_POLLINATIONS_MODELS = [
    "flux",
    "zimage",
    "klein"
]
CURRENT_WORKING_MODEL = "flux"

NEGATIVE_TAGS = (
    "3d, cgi, photorealistic, waxy skin, blurry, out of focus, text, words, letters, "
    "speech bubble, thought bubble, watermark, logo, signature, bad anatomy, extra limbs, "
    "cropped head, extreme close-up, tiny distant figures, multiple boys, multiple girls"
)

# 100% Adult (18+) Manhwa Romance Plots
ROMANCE_PLOTS = [
    "Uncherished fiancée left in the rain on her birthday is rescued and treasured by her fiancé's older brother",
    "University next-door neighbours grow from bickering rivals into a rainy rooftop confession and marriage proposal",
    "Cold university student council president hides his feelings until jealousy makes him confess in the rain",
    "Contract marriage couple with a strict no-love rule fall deeply in love when he tears up the divorce papers",
    "Two commuters on the 7 AM subway train share an umbrella during a thunderstorm and become soulmates",
    "Quiet university art prodigy secretly sketches the girl ignored by her crush, winning her heart under cherry blossoms",
    "Separated childhood friends reunite in college when she recognizes the red ribbon still tied on his wrist",
    "Time-leap romance where a regretful husband wakes up five years earlier in university to cherish his wife from day one",
    "Overworked young CEO pretends to hate coffee breaks just to talk to the shy bakery owner across the street every morning",
    "Bodyguard hired to protect an adult heiress breaks his own strict rules when she cries alone under night fireworks"
]


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"used_titles": [], "used_plots": [], "used_dialogues": [], "total_runs": 0}


def save_history(history):
    history["used_titles"] = history.get("used_titles", [])[-25:]
    history["used_plots"] = history.get("used_plots", [])[-8:]
    history["used_dialogues"] = history.get("used_dialogues", [])[-30:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def load_font(size):
    for p in (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def ascii_clean(text):
    cleaned = "".join(c for c in str(text) if 32 <= ord(c) <= 126)
    return " ".join(cleaned.split()) or "..."


def clamp_adult_age(raw_age, default_age=21):
    """Enforces guideline-safe adult age tags (18 to 30) across all scenes."""
    digits = "".join(c for c in str(raw_age) if c.isdigit())
    val = int(digits) if digits else default_age
    return str(max(18, min(30, val)))


def sanitize_tags(raw_tags, fallback):
    """Strips redundant style words or bloat from LLM-generated tags."""
    if not raw_tags:
        return fallback
    cleaned = str(raw_tags).lower()
    for redundant in (
        "manhwa style", "korean webtoon", "2d anime illustration",
        "2d anime", "3d", "cgi", "realistic", "close-up", "closeup",
        "child", "kid", "minor", "loli", "shota"
    ):
        cleaned = cleaned.replace(redundant, "")
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    return ", ".join(parts[:8]) if parts else fallback


# ==============================================================================
# 1. FREE GROQ STORY & TAG ARCHITECT
# ==============================================================================

def get_free_groq_models(client):
    try:
        all_ids = [m.id for m in client.models.list().data]
    except Exception:
        return ["qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    blocked = (
        "gpt-oss", "whisper", "orpheus", "canopylabs", "guard", "tts",
        "playai", "embed", "vision", "audio", "speech", "safeguard", "allam"
    )
    valid = [m for m in all_ids if not any(b in m.lower() for b in blocked)]

    priority = [
        "qwen/qwen3.8-27b",
        "qwen/qwen3-32b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "llama3-70b-8192",
        "llama3-8b-8192"
    ]
    ordered = [p for p in priority if p in valid]
    for m in valid:
        if m not in ordered:
            ordered.append(m)
    return ordered or ["qwen/qwen3.8-27b"]


def generate_procedural_story(history, chosen_plot):
    """Multi-plot deduplicated fallback generator if external LLMs are temporarily unavailable."""
    ep = history.get("total_runs", 0) + 1
    used_titles = set(history.get("used_titles", []))
    m_hair = random.choice(["short black hair", "silver hair", "dark brown hair", "navy hair"])
    f_hair = random.choice(["long chestnut hair", "long black hair", "wavy honey hair", "caramel hair"])

    templates = [
        {
            "trope": "Rescued By His Older Brother",
            "title": f"Left In The Rain… Until His Brother Stepped In ☔💔 Ep.{ep} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "21", "female_age": "19", "male_mode": "speech", "male_line": "Wait outside. I'm busy tonight.", "female_mode": "thought", "female_line": "He forgot my birthday again...", "scene_tags": "suit jacket, pastel dress, holding small cake box, evening sidewalk, cold expression, sad eyes"},
                {"male_age": "24", "female_age": "19", "male_mode": "thought", "male_line": "How can my brother ignore her tears?", "female_mode": "whisper", "female_line": "It's okay, I'm used to waiting.", "scene_tags": "long dark coat, shivering in rain, warm streetlamp glow, concerned gaze, teardrops"},
                {"male_age": "24", "female_age": "19", "male_mode": "speech", "male_line": "Take my umbrella. Come with me.", "female_mode": "thought", "female_line": "Why is his gaze so warm?", "scene_tags": "sharing umbrella, heavy rain, glowing city lights, standing close, blushing"},
                {"male_age": "24", "female_age": "20", "male_mode": "speech", "male_line": "I bought every cake you missed.", "female_mode": "thought", "female_line": "No one ever treasured me like this...", "scene_tags": "white shirt, cardigan, birthday cake with candles, warm dining room, gentle smile"},
                {"male_age": "25", "female_age": "20", "male_mode": "shout", "male_line": "Step back! You lost your chance!", "female_mode": "thought", "female_line": "He stood right in front of me!", "scene_tags": "tailored suit, evening gown, grand hall chandelier, protective posture, holding her hand"},
                {"male_age": "25", "female_age": "20", "male_mode": "whisper", "male_line": "I've loved you in silence for years.", "female_mode": "speech", "female_line": "Stay with me. Never let go.", "scene_tags": "night balcony, starry sky, city bokeh, touching her cheek, tender eye contact"},
                {"male_age": "26", "female_age": "21", "male_mode": "speech", "male_line": "Marry me and be my whole world.", "female_mode": "speech", "female_line": "Yes! Only you, forever.", "scene_tags": "holding ring box, cherry blossom trees, golden sunset light, happy tears, smiling"},
                {"male_age": "27", "female_age": "22", "male_mode": "thought", "male_line": "I'll protect her smile for life.", "female_mode": "thought", "female_line": "Losing the wrong one led me to you.", "scene_tags": "black tuxedo, white wedding veil, hugging, sunlit garden, floating petals"}
            ]
        },
        {
            "trope": "University Rivals to Rooftop Lovers",
            "title": f"He Fought Me For #1 Rank… Just To Talk To Me 📚💗 Ep.{ep} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "19", "female_age": "19", "male_mode": "speech", "male_line": "First place is mine again.", "female_mode": "thought", "female_line": "Why does he always tease me?", "scene_tags": "university blazer, white shirt, exam board, sunlit hallway, soft smirk, pouting"},
                {"male_age": "19", "female_age": "19", "male_mode": "whisper", "male_line": "Why are you crying up here?", "female_mode": "thought", "female_line": "He found my secret spot...", "scene_tags": "campus rooftop, golden sunset sky, offering handkerchief, tearful eyes, warm breeze"},
                {"male_age": "20", "female_age": "20", "male_mode": "speech", "male_line": "Rest on my shoulder for a bit.", "female_mode": "thought", "female_line": "His shoulder feels so safe...", "scene_tags": "library desk, stacked books, warm window light, draping blazer over her, blushing"},
                {"male_age": "20", "female_age": "20", "male_mode": "shout", "male_line": "Don't let him walk you home!", "female_mode": "speech", "female_line": "Wait, are you actually jealous?", "scene_tags": "campus courtyard, autumn leaves, holding her wrist, serious gaze, bright sunset"},
                {"male_age": "21", "female_age": "21", "male_mode": "speech", "male_line": "I studied hard just to stay near you.", "female_mode": "thought", "female_line": "My heart is racing so fast!", "scene_tags": "university garden, cherry blossoms, spring sunlight, standing together, shy smile"},
                {"male_age": "21", "female_age": "21", "male_mode": "whisper", "male_line": "Every margin note was about you.", "female_mode": "speech", "female_line": "I liked you since freshman year.", "scene_tags": "rainy evening, transparent umbrella, warm cafe lights, touching her cheek, warm smile"},
                {"male_age": "23", "female_age": "23", "male_mode": "speech", "male_line": "Be my partner for life?", "female_mode": "speech", "female_line": "Yes, my favourite rival!", "scene_tags": "starry rooftop, fairy lights, holding ring box, joyful tears, romantic night"},
                {"male_age": "24", "female_age": "24", "male_mode": "thought", "male_line": "Winning her heart was my real prize.", "female_mode": "thought", "female_line": "From rivals to soulmates forever.", "scene_tags": "golden sunrise, bright sky, city skyline, holding hands, loving gaze"}
            ]
        }
    ]

    picked = random.choice(templates)
    title = picked["title"]
    if title in used_titles:
        title = f"{picked['trope']} ❤️✨ Part {ep} #Shorts #manhwa #lovestory"

    return {
        "trope": picked["trope"],
        "plot_used": chosen_plot,
        "video_title": title,
        "boy_tags": f"tall male, {m_hair}, amber eyes",
        "girl_tags": f"petite female, {f_hair}, bright eyes",
        "scenes": picked["scenes"]
    }


def generate_story(history):
    used_plots = history.get("used_plots", [])[-5:]
    used_titles = history.get("used_titles", [])[-10:]
    used_lines = history.get("used_dialogues", [])[-12:]

    custom_topic = os.getenv("CUSTOM_STORY_THEME", "").strip()
    if custom_topic:
        chosen_plot = custom_topic
    else:
        candidates = [p for p in ROMANCE_PLOTS if p not in used_plots] or ROMANCE_PLOTS
        chosen_plot = random.choice(candidates)

    nonce = f"{int(time.time())}-{random.randint(1000, 9999)}"

    sys_msg = (
        "You are a Korean Manhwa writer and tag prompt engineer. "
        "Write an 8-scene adult romance story (all characters ages 19 to 28) using short visual tags. "
        "Use 'speech' for spoken dialogue, 'thought' for inner monologue (unspoken thoughts), "
        "'whisper' for soft shy lines, and 'shout' for emotional outbursts. "
        "Output strictly valid, compact JSON."
    )
    usr_msg = f"""Create a new 8-scene romantic Manhwa Short (MUST have 8 scenes in "scenes").
Seed: {nonce} | Plot: "{chosen_plot}"
Avoid titles: {json.dumps(used_titles[-5:])}
Avoid lines: {json.dumps(used_lines[-8:])}

RULES:
1. All characters must be adults (male_age and female_age between 19 and 28).
2. "boy_tags": 3-5 visual tags for male lead (e.g., "tall male, short black hair, amber eyes").
3. "girl_tags": 3-5 visual tags for female lead (e.g., "petite female, long brown hair, blue eyes").
4. For each of the 8 scenes:
   - "scene_tags": 5-7 short visual tags for outfit, action, setting, and lighting (NO close-ups, NO style names).
   - "male_mode" / "female_mode": "speech", "thought", "whisper", or "shout" (mix speech and thought naturally!).
   - "male_line" / "female_line": 4 to 6 English words.

JSON Schema:
{{
  "trope": "Short 4-word trope title",
  "video_title": "Emotional title with emojis #Shorts #manhwa #lovestory",
  "boy_tags": "tall male, short black hair, sharp amber eyes",
  "girl_tags": "petite female, long chestnut hair, bright eyes",
  "scenes": [
    {{
      "male_age": "21",
      "female_age": "19",
      "male_mode": "speech",
      "male_line": "Take my umbrella right now.",
      "female_mode": "thought",
      "female_line": "He actually came back for me...",
      "scene_tags": "dark coat, white cardigan, sharing umbrella, rain, evening street, looking at each other"
    }}
  ]
}}"""

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            for model in get_free_groq_models(client)[:4]:
                try:
                    print(f"[STORY] Requesting 8-scene script from Groq ({model})...")
                    res = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": usr_msg}],
                        response_format={"type": "json_object"},
                        max_tokens=920,
                        temperature=0.82
                    )
                    raw = res.choices[0].message.content.strip()
                    if raw.startswith("```"):
                        raw = raw.split("```")[1].lstrip("json").strip()
                    data = json.loads(raw)
                    if len(data.get("scenes", [])) >= 6:
                        data["plot_used"] = chosen_plot
                        print(f"✅ Story Ready ({len(data['scenes'])} scenes): {data.get('video_title')}")
                        return data
                except Exception as e:
                    print(f"⚠️ Groq {model} skipped ({e})")
                    time.sleep(2)
        except Exception:
            pass

    return generate_procedural_story(history, chosen_plot)


# ==============================================================================
# 2. HIGH-CLASS MANHWA IMAGE ENGINE (BALANCED gXlmlO4comg FRAMING + SHARPNESS)
# ==============================================================================

def build_clean_manhwa_prompt(scene, boy_tags, girl_tags):
    """
    Balanced, authentic Korean Manhwa prompt modeled directly on gXlmlO4comg:
    - Uses lush Manhwa romantic lighting & soft shading (restores the luminous Manhwa look).
    - Uses clean thigh-up two-shot framing with natural top margin (so characters command the frame
      instead of being squashed tiny into the bottom 40%!).
    """
    m_age = clamp_adult_age(scene.get("male_age", "21"), 21)
    f_age = clamp_adult_age(scene.get("female_age", "19"), 19)

    clean_boy = sanitize_tags(boy_tags, "tall male, short black hair, amber eyes")
    clean_girl = sanitize_tags(girl_tags, "petite female, long chestnut hair, bright eyes")
    clean_scene = sanitize_tags(
        scene.get("scene_tags", ""),
        "standing together, warm romantic lighting, looking at each other"
    )

    tags = [
        "manhwa style",
        "luminous romantic lighting",
        "soft anime shading",
        "detailed expressive eyes",
        "1boy on left",
        "1girl on right",
        clean_boy,
        f"{m_age}yo",
        clean_girl,
        f"{f_age}yo",
        clean_scene,
        "thigh-up two-shot",
        "standing side by side",
        "clean top margin above heads",
        "sharp focus",
        "masterpiece"
    ]
    return ", ".join(tags)


def measure_sharpness(pil_img):
    """Computes Laplacian edge variance to reject blurry/smeared frames."""
    gray = np.array(pil_img.convert("L").resize((540, 960)), dtype=np.float32)
    lap = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    return float(np.var(lap))


def evaluate_artwork_bytes(raw_bytes):
    if not raw_bytes or len(raw_bytes) < 16000:
        return False, 0.0, None
    try:
        im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
        w, h = im.size
        if w < 450 or h < 600:
            return False, 0.0, None
        arr = np.array(im, dtype=np.float32)
        if np.std(arr) < 22.0:
            return False, 0.0, None
        sharpness = measure_sharpness(im)
        return True, sharpness, im
    except Exception:
        return False, 0.0, None


def finalize_vertical_art(pil_img, out_path):
    """Trims bottom 3.5% watermark margin, center-fits to 1080x1920 cleanly with crisp polish."""
    w, h = pil_img.size
    cropped = pil_img.crop((int(w * 0.018), int(h * 0.005), int(w * 0.982), int(h * 0.965)))
    cw, ch = cropped.size

    target_ratio = 1080.0 / 1920.0
    cur_ratio = cw / float(ch)
    if abs(cur_ratio - target_ratio) > 0.02:
        if cur_ratio > target_ratio:
            nw = int(ch * target_ratio)
            left = (cw - nw) // 2
            cropped = cropped.crop((left, 0, left + nw, ch))
        else:
            nh = int(cw / target_ratio)
            top = max(0, (ch - nh) // 3)
            cropped = cropped.crop((0, top, cw, top + nh))

    fitted = cropped.resize((1080, 1920), Image.LANCZOS)
    fitted = fitted.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=3))
    fitted = ImageEnhance.Color(fitted).enhance(1.06)
    fitted.save(out_path, "JPEG", quality=96)
    return out_path


def render_scene_image(session, scene, boy_tags, girl_tags, story_seed, idx, total, out_path):
    """Renders crisp 9:16 Manhwa artwork via gen.pollinations.ai with sharpness gating."""
    global CURRENT_WORKING_MODEL
    pos_prompt = build_clean_manhwa_prompt(scene, boy_tags, girl_tags)
    enc_pos = urllib.parse.quote(pos_prompt)
    enc_neg = urllib.parse.quote(NEGATIVE_TAGS)
    api_key = os.getenv("POLLINATIONS_API_KEY", "").strip()

    if idx > 0:
        time.sleep(5.0)

    trial_models = [CURRENT_WORKING_MODEL] + [m for m in GEN_POLLINATIONS_MODELS if m != CURRENT_WORKING_MODEL]
    print(f"[MANHWA-GEN] Scene {idx + 1}/{total} | Prompt: {pos_prompt}")

    best_img = None
    best_sharpness = -1.0
    best_label = ""

    attempts = []
    if api_key:
        for i, m in enumerate(trial_models):
            seed = story_seed + idx if i == 0 else story_seed + (idx * 73) + i
            attempts.append((
                f"gen:{m}",
                f"https://gen.pollinations.ai/image/{enc_pos}"
                f"?model={urllib.parse.quote(m)}&width=768&height=1344"
                f"&seed={seed}&negative_prompt={enc_neg}&nologo=true&enhance=false",
                {"Authorization": f"Bearer {api_key}"}
            ))
        attempts.append((
            f"gen:{trial_models[0]}-retry",
            f"https://gen.pollinations.ai/image/{enc_pos}"
            f"?model={urllib.parse.quote(trial_models[0])}&width=768&height=1344"
            f"&seed={story_seed + (idx * 131) + 19}&negative_prompt={enc_neg}&nologo=true&enhance=false",
            {"Authorization": f"Bearer {api_key}"}
        ))
    else:
        print("   ⚠️ POLLINATIONS_API_KEY not found in env; falling back to public endpoint.")

    attempts.append((
        "legacy-fallback",
        f"https://image.pollinations.ai/prompt/{enc_pos}"
        f"?width=768&height=1344&seed={story_seed + idx}&negative_prompt={enc_neg}&nologo=true&enhance=false",
        {}
    ))

    for step_idx, (label, url, extra_headers) in enumerate(attempts):
        try:
            res = session.get(url, headers=extra_headers, timeout=85)
            ctype = res.headers.get("Content-Type", "")
            if res.status_code == 200 and "image" in ctype:
                ok, sharpness, pil_im = evaluate_artwork_bytes(res.content)
                if ok and pil_im is not None:
                    print(f"   ↳ Received '{label}' | Sharpness={sharpness:.1f}")
                    if sharpness > best_sharpness:
                        best_sharpness = sharpness
                        best_img = pil_im
                        best_label = label

                    if sharpness >= 65.0:
                        if label.startswith("gen:"):
                            CURRENT_WORKING_MODEL = label.split(":")[1].split("-")[0]
                        finalize_vertical_art(pil_im, out_path)
                        print(f"✅ Scene {idx + 1}/{total} crisp art saved ({label}, sharp={sharpness:.1f}) -> {out_path}")
                        return True
                    else:
                        print(f"   ⚠️ Too blurry (sharp={sharpness:.1f} < 65). Trying sharper model...")
                        time.sleep(4)
                        continue

            wait_s = 10 + (step_idx * 3)
            print(f"   ⏳ '{label}' returned HTTP {res.status_code}. Waiting {wait_s}s...")
            time.sleep(wait_s)
        except Exception as e:
            print(f"   ⏳ Network retry on '{label}' ({e}). Waiting 8s...")
            time.sleep(8)

    if best_img is not None:
        finalize_vertical_art(best_img, out_path)
        print(f"✅ Scene {idx + 1}/{total} saved best take ({best_label}, sharp={best_sharpness:.1f}) -> {out_path}")
        return True

    return False


# ==============================================================================
# 3. SEMANTIC VISION LANDMARKS + 2D INTEGRAL-IMAGE ENERGY LAYOUT SOLVER
# ==============================================================================

def get_groq_vision_models(client):
    """Finds active free-tier Groq Vision models (Llama-4 Scout / Maverick)."""
    try:
        all_ids = [m.id for m in client.models.list().data]
    except Exception:
        return ["meta-llama/llama-4-scout-17b-16e-instruct"]

    preferred = [
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "meta-llama/llama-4-maverick-17b-128e-instruct"
    ]
    ordered = [p for p in preferred if p in all_ids]
    for m in all_ids:
        if ("vision" in m.lower() or "llama-4" in m.lower()) and "guard" not in m.lower():
            if m not in ordered:
                ordered.append(m)
    return ordered


def detect_landmarks_with_vision_ai(img_path):
    """
    Uses Groq's free Vision LLM to pinpoint exact head bounding boxes and mouth coordinates
    for both the male lead and female lead (normalized 0..1000 -> mapped to 1080x1920 pixels).
    Returns a validated landmark dict or None if unavailable.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        return None

    try:
        with Image.open(img_path) as im:
            thumb = im.convert("RGB").resize((360, 640), Image.LANCZOS)
            buf = io.BytesIO()
            thumb.save(buf, format="JPEG", quality=82)
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")

        client = Groq(api_key=groq_key)
        vision_models = get_groq_vision_models(client)
        if not vision_models:
            return None

        prompt = (
            "Locate the TWO anime/manhwa characters (the male character and the female character) in this 9:16 image. "
            "Use normalized coordinates from 0 to 1000 where (0,0) is top-left and (1000,1000) is bottom-right. "
            "Include full hair inside each head box [x1, y1, x2, y2]. "
            "Return ONLY valid JSON matching this schema:\n"
            '{"boy_head":[x1,y1,x2,y2],"boy_mouth":[mx,my],"girl_head":[x1,y1,x2,y2],"girl_mouth":[mx,my]}'
        )

        for v_model in vision_models[:2]:
            try:
                res = client.chat.completions.create(
                    model=v_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}}
                        ]
                    }],
                    response_format={"type": "json_object"},
                    max_tokens=220,
                    temperature=0.0
                )
                raw = res.choices[0].message.content.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1].lstrip("json").strip()
                data = json.loads(raw)

                bh = data.get("boy_head")
                bm = data.get("boy_mouth")
                gh = data.get("girl_head")
                gm = data.get("girl_mouth")
                if not (isinstance(bh, list) and len(bh) == 4 and isinstance(gh, list) and len(gh) == 4):
                    continue

                def to_px_box(b):
                    x1 = max(0, min(1070, int(round(float(b[0]) * 1.08))))
                    y1 = max(0, min(1900, int(round(float(b[1]) * 1.92))))
                    x2 = max(x1 + 70, min(1080, int(round(float(b[2]) * 1.08))))
                    y2 = max(y1 + 80, min(1920, int(round(float(b[3]) * 1.92))))
                    return (x1, y1, x2, y2)

                def to_px_pt(pt, box):
                    if isinstance(pt, list) and len(pt) == 2:
                        mx = max(box[0], min(box[2], int(round(float(pt[0]) * 1.08))))
                        my = max(box[1], min(box[3], int(round(float(pt[1]) * 1.92))))
                        return (mx, my)
                    return ((box[0] + box[2]) // 2, int(box[1] + (box[3] - box[1]) * 0.72))

                b_box = to_px_box(bh)
                g_box = to_px_box(gh)
                b_cx = (b_box[0] + b_box[2]) // 2
                g_cx = (g_box[0] + g_box[2]) // 2

                # Reject degenerate detections where both boxes collapsed onto the same person
                if abs(b_cx - g_cx) < 120:
                    continue

                return {
                    "boy_box": b_box,
                    "boy_mouth": to_px_pt(bm, b_box),
                    "girl_box": g_box,
                    "girl_mouth": to_px_pt(gm, g_box),
                    "source": f"vision:{v_model}"
                }
            except Exception:
                continue
    except Exception:
        pass
    return None


def detect_landmarks_cv_fallback(img_path):
    """
    Pure-NumPy Multi-Cue Anime Face/Head Detector (works offline if Vision AI is unavailable):
    Combines warm anime skin-tone segmentation with percentile face bounding & hair height estimation.
    """
    fallback = {
        "boy_box": (175, 420, 415, 760),
        "boy_mouth": (320, 675),
        "girl_box": (655, 470, 895, 810),
        "girl_mouth": (740, 725),
        "source": "cv-default"
    }
    try:
        with Image.open(img_path) as im:
            rgb = np.array(im.convert("RGB").resize((1080, 1920)), dtype=np.float32)

        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        skin_mask = (
            (r > 155) & (g > 110) & (b > 85) &
            ((r - g) > 8) & ((r - b) > 16) & ((r - b) < 125) &
            (g > b)
        )
        y_min, y_max = 80, 1380

        def scan_half(x_start, x_end, is_left):
            ys, xs = np.where(skin_mask[y_min:y_max, x_start:x_end])
            if len(ys) < 350:
                return None

            fx1 = int(x_start + np.percentile(xs, 10))
            fx2 = int(x_start + np.percentile(xs, 90))
            fy1 = int(y_min + np.percentile(ys, 10))
            fy2 = int(y_min + np.percentile(ys, 85))

            fw = max(130, min(320, fx2 - fx1))
            fh = max(140, min(340, fy2 - fy1))
            cx = int(x_start + np.median(xs))

            hx1 = max(20, cx - int(fw * 0.65))
            hx2 = min(1060, cx + int(fw * 0.65))
            hy1 = max(25, fy1 - int(fh * 0.50))
            hy2 = min(1450, fy2 + int(fh * 0.12))

            shift = int(fw * 0.15) if is_left else -int(fw * 0.15)
            mx = max(hx1 + 10, min(hx2 - 10, cx + shift))
            my = max(hy1 + 20, min(hy2 - 10, fy1 + int(fh * 0.72)))
            return (hx1, hy1, hx2, hy2), (mx, my)

        left_res = scan_half(30, 535, True)
        right_res = scan_half(545, 1050, False)
        if left_res:
            fallback["boy_box"], fallback["boy_mouth"] = left_res
            fallback["source"] = "cv-skin"
        if right_res:
            fallback["girl_box"], fallback["girl_mouth"] = right_res
            fallback["source"] = "cv-skin"
    except Exception:
        pass
    return fallback


def align_couple_and_gentle_headroom(img_path):
    """
    1. Detects exact boy & girl head boxes via Vision AI (with CV fallback).
    2. If the boy was drawn on the right side (boy_cx > girl_cx), mirrors the text-free artwork
       horizontally and transforms the exact coordinates so Boy is ALWAYS Left (Blue Age) and Girl Right (Pink Age).
    3. ONLY applies a gentle top headroom extension if a head clips dangerously close to the top (< 305px),
       lifting it to ~345px (preserving full commanding character presence like gXlmlO4comg!).
    """
    lm = detect_landmarks_with_vision_ai(img_path) or detect_landmarks_cv_fallback(img_path)

    boy_cx = (lm["boy_box"][0] + lm["boy_box"][2]) * 0.5
    girl_cx = (lm["girl_box"][0] + lm["girl_box"][2]) * 0.5

    # Mirror if Vision AI saw boy on right, or if CV fallback saw significantly taller head on right
    should_flip = (boy_cx > girl_cx) if lm["source"].startswith("vision:") else (lm["girl_box"][1] < lm["boy_box"][1] - 35)

    if should_flip:
        with Image.open(img_path) as im:
            im.transpose(Image.FLIP_LEFT_RIGHT).save(img_path, "JPEG", quality=96)

        def flip_box(b):
            return (1080 - b[2], b[1], 1080 - b[0], b[3])

        def flip_pt(p):
            return (1080 - p[0], p[1])

        if lm["source"].startswith("vision:"):
            lm["boy_box"] = flip_box(lm["boy_box"])
            lm["boy_mouth"] = flip_pt(lm["boy_mouth"])
            lm["girl_box"] = flip_box(lm["girl_box"])
            lm["girl_mouth"] = flip_pt(lm["girl_mouth"])
        else:
            # In CV mode, left/right slots swapped labels
            old_boy_box, old_boy_m = lm["boy_box"], lm["boy_mouth"]
            lm["boy_box"], lm["boy_mouth"] = flip_box(lm["girl_box"]), flip_pt(lm["girl_mouth"])
            lm["girl_box"], lm["girl_mouth"] = flip_box(old_boy_box), flip_pt(old_boy_m)
        print("   🔄 Horizontally aligned artwork (Boy -> Left, Girl -> Right)")

    # Gentle headroom guard ONLY when a character's hair touches the top edge (y < 305)
    min_head_y = min(lm["boy_box"][1], lm["girl_box"][1])
    if min_head_y < 305:
        shift_y = min(230, 345 - min_head_y)
        with Image.open(img_path) as im:
            rgb = im.convert("RGB").resize((1080, 1920), Image.LANCZOS)
            arr = np.array(rgb, dtype=np.float32)

            left_c = np.median(arr[0:90, 0:140, :], axis=(0, 1))
            right_c = np.median(arr[0:90, 940:1080, :], axis=(0, 1))
            x_t = np.linspace(0.0, 1.0, 1080, dtype=np.float32)[None, :, None]
            top_grad = left_c[None, None, :] * (1.0 - x_t) + right_c[None, None, :] * x_t

            canvas = np.zeros((1920, 1080, 3), dtype=np.float32)
            canvas[:shift_y + 45, :, :] = top_grad

            if min_head_y >= 55:
                strip_h = min(110, min_head_y - 15)
                sky_strip = rgb.crop((0, 0, 1080, strip_h)).transpose(Image.FLIP_TOP_BOTTOM)
                sky_ext = sky_strip.resize((1080, shift_y + 36), Image.BICUBIC).filter(ImageFilter.GaussianBlur(14))
                canvas[:shift_y + 36, :, :] = 0.65 * np.array(sky_ext, dtype=np.float32) + 0.35 * top_grad

            paste_h = 1920 - shift_y
            art_part = arr[:paste_h, :, :]
            feather = min(38, paste_h)
            alpha = np.linspace(0.0, 1.0, feather, dtype=np.float32)[:, None, None]

            canvas[shift_y:shift_y + feather, :, :] = (
                canvas[shift_y:shift_y + feather, :, :] * (1.0 - alpha) + art_part[:feather, :, :] * alpha
            )
            canvas[shift_y + feather:, :, :] = art_part[feather:, :, :]
            Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGB").save(img_path, "JPEG", quality=96)

        def shift_box(b):
            return (b[0], b[1] + shift_y, b[2], min(1920, b[3] + shift_y))

        lm["boy_box"] = shift_box(lm["boy_box"])
        lm["boy_mouth"] = (lm["boy_mouth"][0], min(1920, lm["boy_mouth"][1] + shift_y))
        lm["girl_box"] = shift_box(lm["girl_box"])
        lm["girl_mouth"] = (lm["girl_mouth"][0], min(1920, lm["girl_mouth"][1] + shift_y))
        print(f"   📐 Gentle headroom guard applied (+{shift_y}px)")

    return lm


def build_integral_image(grid):
    """Constructs a 2D Summed-Area Table for O(1) rectangular region integration."""
    padded = np.pad(grid, ((1, 0), (1, 0)), mode="constant", constant_values=0.0)
    return np.cumsum(np.cumsum(padded, axis=0), axis=1)


def build_visual_energy_grid(img_path, landmarks, grid_scale=4):
    """
    Constructs a mathematical Visual Importance & Exclusion Energy Field E(y, x) on a 270x480 grid:
    - Sobel gradient magnitude |∇I| (high on detailed lineart, bright lights, umbrellas, hands, objects)
    - Local grayscale variance (rewards smooth open negative space like sky/walls/bokeh)
    - Hard impenetrable exclusion masks (E = 1e6) over BOTH heads, BOTH character bodies/torsos,
      top age badges, outer frame margins, and YouTube Shorts bottom UI!
    """
    GW = 1080 // grid_scale  # 270
    GH = 1920 // grid_scale  # 480

    with Image.open(img_path) as im:
        gray = np.array(im.convert("L").resize((GW, GH), Image.BILINEAR), dtype=np.float64)

    # 1. Sobel Gradient Magnitude |∇I|
    gx = (
        -gray[:-2, :-2] + gray[:-2, 2:]
        - 2.0 * gray[1:-1, :-2] + 2.0 * gray[1:-1, 2:]
        - gray[2:, :-2] + gray[2:, 2:]
    )
    gy = (
        -gray[:-2, :-2] - 2.0 * gray[:-2, 1:-1] - gray[:-2, 2:]
        + gray[2:, :-2] + 2.0 * gray[2:, 1:-1] + gray[2:, 2:]
    )
    grad = np.pad(np.hypot(gx, gy), ((1, 1), (1, 1)), mode="edge")
    grad_norm = np.clip(grad / 160.0, 0.0, 1.5) * 45.0

    # 2. Local Variance via Integral Image (9x9 window)
    k = 9
    r = k // 2
    g_pad = np.pad(gray, ((r, r), (r, r)), mode="edge")
    s1 = build_integral_image(g_pad)
    s2 = build_integral_image(g_pad * g_pad)
    mean_v = (s1[k:, k:] - s1[:-k, k:] - s1[k:, :-k] + s1[:-k, :-k]) / float(k * k)
    sq_v = (s2[k:, k:] - s2[:-k, k:] - s2[k:, :-k] + s2[:-k, :-k]) / float(k * k)
    local_std = np.sqrt(np.maximum(0.0, sq_v - mean_v * mean_v))
    var_norm = np.clip(local_std / 55.0, 0.0, 1.5) * 35.0

    # 3. High-glare bright light penalty (e.g., ceiling lamps)
    glare_pen = np.where(gray > 246.0, 28.0, 0.0)

    energy = grad_norm + var_norm + glare_pen

    def forbid_rect(x1, y1, x2, y2, weight=1e6):
        gx1 = max(0, min(GW, int(math.floor(x1 / grid_scale))))
        gy1 = max(0, min(GH, int(math.floor(y1 / grid_scale))))
        gx2 = max(0, min(GW, int(math.ceil(x2 / grid_scale))))
        gy2 = max(0, min(GH, int(math.ceil(y2 / grid_scale))))
        if gx2 > gx1 and gy2 > gy1:
            energy[gy1:gy2, gx1:gx2] += weight

    # Hard Forbidden Zones:
    # (a) Outer edges & YouTube Shorts bottom UI
    forbid_rect(0, 0, 1080, 44, 1e6)
    forbid_rect(0, 0, 20, 1920, 1e6)
    forbid_rect(1060, 0, 1080, 1920, 1e6)
    forbid_rect(0, 1340, 1080, 1920, 1e6)

    # (b) Top-left & Top-right glowing Age Badges
    forbid_rect(0, 0, 185, 148, 1e6)
    forbid_rect(895, 0, 1080, 148, 1e6)

    # (c) Both Character Heads (+24px padding) AND Torso/Body Cones below their heads!
    for key in ("boy_box", "girl_box"):
        hx1, hy1, hx2, hy2 = landmarks[key]
        hw = hx2 - hx1
        # Protect full head + hair halo
        forbid_rect(hx1 - 24, hy1 - 26, hx2 + 24, hy2 + 18, 1e6)
        # Protect shoulders & torso below the head so bubbles NEVER appear on character's body
        shoulder_pad = int(max(55, hw * 0.42))
        forbid_rect(hx1 - shoulder_pad, hy2 - 12, hx2 + shoulder_pad, 1920, 1e6)

    return energy


def measure_bubble_geometry(text):
    """Computes balanced comic text wrapping and super-ellipse radii (rx, ry) in 1080p pixels."""
    clean_t = ascii_clean(text)
    # Choose balanced line width (15-18 chars) for pleasing oval aspect ratio
    wrap_w = 15 if len(clean_t) <= 30 else 18
    wrapped = "\n".join(textwrap.wrap(clean_t, width=wrap_w)[:3])

    font = load_font(30 * 2)  # measured at 2x resolution
    tmp = ImageDraw.Draw(Image.new("L", (8, 8)))
    bbox = tmp.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=7 * 2)
    tw = (bbox[2] - bbox[0]) / 2.0
    th = (bbox[3] - bbox[1]) / 2.0

    rx = max(134, min(232, int(round(tw * 0.5 + 44))))
    ry = max(66, min(116, int(round(th * 0.5 + 34))))
    return wrapped, rx, ry


def solve_optimal_bubble_placement(energy_grid, rx, ry, speaker_box, side, is_second_speaker=False, grid_scale=4):
    """
    Exact Global Energy-Minimization Solver via 2D Integral Image:
    Evaluates ALL ~100,000 candidate positions (cx, cy) simultaneously in <3ms and selects
    the mathematically optimal bubble placement that:
    1. NEVER overlaps heads, bodies, age badges, or the other bubble (hard exclusion E=1e6).
    2. Sits intimately right above the speaker's actual head (head_top - ry - 86px) — NEVER stuck
       at the ceiling 500px away!
    3. Automatically dodges busy visual details (lights, umbrellas, background clutter) into
       clean negative space.
    """
    GH, GW = energy_grid.shape
    bw = max(6, min(GW - 4, int(round((2 * rx + 18) / grid_scale))))
    bh = max(6, min(GH - 4, int(round((2 * ry + 18) / grid_scale))))

    S = build_integral_image(energy_grid)
    occ = S[bh:, bw:] - S[:-bh, bw:] - S[bh:, :-bw] + S[:-bh, :-bw]
    mean_occ = occ / float(bw * bh)

    ny, nx = mean_occ.shape
    cx_px = (np.arange(nx, dtype=np.float64)[None, :] + bw * 0.5) * grid_scale
    cy_px = (np.arange(ny, dtype=np.float64)[:, None] + bh * 0.5) * grid_scale

    hx1, hy1, hx2, hy2 = speaker_box
    head_cx = (hx1 + hx2) * 0.5

    # Ideal reading position: right above the speaker's head with subtle diagonal comic rhythm
    outward_nudge = -28.0 if side == "left" else 28.0
    ideal_x = max(rx + 28.0, min(1080.0 - rx - 28.0, head_cx + outward_nudge))

    # Ideal Y tracks the ACTUAL head height (never pinned to y=230 when head is at y=850!)
    stagger_y = 22.0 if is_second_speaker else -8.0
    ideal_y = max(ry + 92.0, min(1240.0 - ry, hy1 - ry - 86.0 + stagger_y))

    # Distance penalty keeps bubble intimately close to the speaker's head (strong vertical pull)
    dx = cx_px - ideal_x
    dy = cy_px - ideal_y
    dist_cost = 0.0018 * (dx * dx) + 0.0028 * (dy * dy)

    # Strongly prefer staying ABOVE the character's eye line rather than dropping beside their neck
    below_head_pen = np.where(cy_px > (hy1 - ry * 0.25), 220.0, 0.0)

    # Gentle hemisphere preference (left speaker prefers left half, right speaker prefers right half)
    if side == "left":
        hemi_pen = np.where(cx_px > 540.0, (cx_px - 540.0) * 0.35, 0.0)
    else:
        hemi_pen = np.where(cx_px < 540.0, (540.0 - cx_px) * 0.35, 0.0)

    total_cost = mean_occ + dist_cost + below_head_pen + hemi_pen
    best_flat = int(np.argmin(total_cost))
    best_iy, best_ix = divmod(best_flat, nx)

    best_cx = int(round((best_ix + bw * 0.5) * grid_scale))
    best_cy = int(round((best_iy + bh * 0.5) * grid_scale))

    best_cx = max(rx + 22, min(1080 - rx - 22, best_cx))
    best_cy = max(ry + 48, min(1320 - ry, best_cy))
    return best_cx, best_cy


def compute_exact_tail_target(cx, cy, rx, ry, speaker_box, mouth_pt):
    """
    Casts a geometric ray from bubble center (cx, cy) toward the speaker's mouth/face (mx, my)
    and stops cleanly right outside the character's head ellipse (18px safety clearance)
    so the tail points unmistakably at the speaker without ever poking into their face or hair!
    """
    hx1, hy1, hx2, hy2 = speaker_box
    hcx = (hx1 + hx2) * 0.5
    hcy = (hy1 + hy2) * 0.5
    hrx = max(55.0, (hx2 - hx1) * 0.5 + 16.0)
    hry = max(65.0, (hy2 - hy1) * 0.5 + 18.0)

    # Target point biased slightly toward the speaker's upper cheek/mouth
    aim_x = hcx * 0.55 + mouth_pt[0] * 0.45
    aim_y = hcy * 0.55 + mouth_pt[1] * 0.45

    vx = aim_x - cx
    vy = aim_y - cy
    dist = math.hypot(vx, vy)
    if dist < 1.0:
        return cx, cy + ry + 65

    ux, uy = vx / dist, vy / dist

    # Distance from bubble center to bubble perimeter along ray (ux, uy)
    denom_b = math.hypot(ux / max(1.0, rx), uy / max(1.0, ry))
    d_bubble = 1.0 / max(1e-6, denom_b)

    # Find exact intersection distance where ray enters the speaker's head safety ellipse
    # Solve ((cx + t*ux - hcx)/hrx)^2 + ((cy + t*uy - hcy)/hry)^2 = 1
    ox = (cx - hcx) / hrx
    oy = (cy - hcy) / hry
    dux = ux / hrx
    duy = uy / hry

    A = dux * dux + duy * duy
    B = 2.0 * (ox * dux + oy * duy)
    C = ox * ox + oy * oy - 1.0
    disc = B * B - 4.0 * A * C

    if disc >= 0.0 and A > 1e-8:
        t_hit = (-B - math.sqrt(disc)) / (2.0 * A)
        if t_hit > d_bubble + 26.0:
            t_tip = min(t_hit, d_bubble + 175.0)
        else:
            t_tip = d_bubble + 46.0
    else:
        t_tip = min(dist * 0.72, d_bubble + 145.0)

    t_tip = max(d_bubble + 44.0, min(d_bubble + 185.0, t_tip))
    tx = int(round(max(24, min(1056, cx + ux * t_tip))))
    ty = int(round(max(60, min(1860, cy + uy * t_tip))))
    return tx, ty


def mark_bubble_occupied(energy_grid, cx, cy, rx, ry, tx, ty, grid_scale=4):
    """Marks a placed bubble and its tail corridor as forbidden so Bubble 2 never collides with it."""
    GH, GW = energy_grid.shape

    def block(x1, y1, x2, y2):
        gx1 = max(0, min(GW, int(math.floor(x1 / grid_scale))))
        gy1 = max(0, min(GH, int(math.floor(y1 / grid_scale))))
        gx2 = max(0, min(GW, int(math.ceil(x2 / grid_scale))))
        gy2 = max(0, min(GH, int(math.ceil(y2 / grid_scale))))
        if gx2 > gx1 and gy2 > gy1:
            energy_grid[gy1:gy2, gx1:gx2] += 1e6

    # Block main bubble with 26px spacing buffer
    block(cx - rx - 26, cy - ry - 26, cx + rx + 26, cy + ry + 26)
    # Block tail corridor
    for f in (0.35, 0.65, 0.90):
        px = cx + (tx - cx) * f
        py = cy + (ty - cy) * f
        block(px - 28, py - 28, px + 28, py + 28)


def draw_age_layer(male_age, female_age, out_path):
    scale = 2
    W, H = 1080 * scale, 160 * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = load_font(58 * scale)

    def draw_num(cx, cy, val, col):
        txt = clamp_adult_age(val, 20)
        draw.text(
            (cx, cy), txt, font=font,
            fill=col + (255,), anchor="mm",
            stroke_width=6 * scale, stroke_fill=(14, 16, 24, 255)
        )

    draw_num(90 * scale, 68 * scale, male_age, (75, 185, 255))
    draw_num(990 * scale, 68 * scale, female_age, (255, 90, 140))
    img.resize((1080, 160), Image.LANCZOS).save(out_path, "PNG")
    return out_path


def super_ellipse_pt(cx, cy, rx, ry, theta, exp=2.35):
    ct, st = math.cos(theta), math.sin(theta)
    x = cx + rx * (1.0 if ct >= 0 else -1.0) * (abs(ct) ** (2.0 / exp))
    y = cy + ry * (1.0 if st >= 0 else -1.0) * (abs(st) ** (2.0 / exp))
    return (x, y)


def quad_bezier_points(p0, p1, p2, steps=28):
    pts = []
    for i in range(steps + 1):
        t = i / float(steps)
        inv = 1.0 - t
        pts.append((
            inv * inv * p0[0] + 2.0 * inv * t * p1[0] + t * t * p2[0],
            inv * inv * p0[1] + 2.0 * inv * t * p1[1] + t * t * p2[1]
        ))
    return pts


def render_master_comic_bubble(wrapped, rx, ry, cx, cy, tx, ty, bubble_mode, out_path):
    """
    2x Supersampled (2160x3840) Morphological Ink-and-Shadow Comic Bubble Engine:
    - 'speech'  -> Smooth Manhwa super-ellipse + vector-aligned curved Bezier tail pointing right to (tx, ty).
    - 'thought' -> Fluffy scalloped cloud + 4 detached shrinking circular bubbles along a smooth curve to (tx, ty).
    - 'whisper' -> Soft dashed-outline oval + slender curved tail.
    - 'shout'   -> Dynamic comic starburst + crisp pointed tail.
    """
    scale = 2
    W, H = 1080 * scale, 1920 * scale
    cx_s, cy_s = cx * scale, cy * scale
    rx_s, ry_s = rx * scale, ry * scale
    tx_s, ty_s = tx * scale, ty * scale

    mode = str(bubble_mode or "speech").lower().strip()
    if mode not in ("speech", "thought", "whisper", "shout"):
        mode = "speech"

    # Exact direction angle from bubble center toward tail tip
    theta0 = math.atan2((ty_s - cy_s) / max(1.0, ry_s), (tx_s - cx_s) / max(1.0, rx_s))
    perp_x = -(ty_s - cy_s)
    perp_y = (tx_s - cx_s)
    plen = max(1.0, math.hypot(perp_x, perp_y))
    perp_x /= plen
    perp_y /= plen
    bow_sign = 1.0 if tx_s >= cx_s else -1.0

    mask = Image.new("L", (W, H), 0)
    mdraw = ImageDraw.Draw(mask)

    if mode == "thought":
        # Scalloped cloud body (zero solid wedge tail!)
        mdraw.ellipse(
            [cx_s - rx_s + 14 * scale, cy_s - ry_s + 12 * scale,
             cx_s + rx_s - 14 * scale, cy_s + ry_s - 12 * scale],
            fill=255
        )
        num_puffs = 16
        for i in range(num_puffs):
            ang = (2.0 * math.pi * i) / num_puffs
            px = cx_s + (rx_s - 10 * scale) * math.cos(ang)
            py = cy_s + (ry_s - 8 * scale) * math.sin(ang)
            pr = (27 if i % 2 == 0 else 22) * scale
            mdraw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=255)

        # Start 4 detached circular thought bubbles just outside the cloud puff along theta0
        perim = super_ellipse_pt(cx_s, cy_s, rx_s + 22 * scale, ry_s + 22 * scale, theta0, exp=2.0)
        sx, sy = perim
        ctrl_x = (sx + tx_s) * 0.5 + perp_x * (16 * scale * bow_sign)
        ctrl_y = (sy + ty_s) * 0.5 + perp_y * (16 * scale * bow_sign)

        curve_pts = quad_bezier_points((sx, sy), (ctrl_x, ctrl_y), (tx_s, ty_s), steps=40)
        # Arc-length parameterization so dots are spaced evenly and never fuse together
        arc = [0.0]
        for i in range(1, len(curve_pts)):
            arc.append(arc[-1] + math.hypot(curve_pts[i][0] - curve_pts[i - 1][0], curve_pts[i][1] - curve_pts[i - 1][1]))
        total_arc = max(1.0, arc[-1])

        dot_specs = [(0.05, 13.5 * scale), (0.37, 10.0 * scale), (0.69, 7.2 * scale), (0.97, 4.8 * scale)]
        for frac, r_dot in dot_specs:
            target_len = frac * total_arc
            idx_a = 0
            while idx_a < len(arc) - 2 and arc[idx_a + 1] < target_len:
                idx_a += 1
            dx, dy = curve_pts[idx_a]
            mdraw.ellipse([dx - r_dot, dy - r_dot, dx + r_dot, dy + r_dot], fill=255)

    elif mode == "shout":
        # Dynamic comic starburst + crisp wedge tail
        poly_burst = []
        spikes = 28
        for i in range(spikes * 2):
            th = (math.pi * i) / spikes
            mult = 1.09 if i % 2 == 0 else 0.90
            poly_burst.append((cx_s + rx_s * mult * math.cos(th), cy_s + ry_s * mult * math.sin(th)))
        mdraw.polygon(poly_burst, fill=255)

        p_l = super_ellipse_pt(cx_s, cy_s, rx_s * 0.85, ry_s * 0.85, theta0 - 0.16, exp=2.0)
        p_r = super_ellipse_pt(cx_s, cy_s, rx_s * 0.85, ry_s * 0.85, theta0 + 0.16, exp=2.0)
        mdraw.polygon([p_l, (tx_s, ty_s), p_r], fill=255)

    else:
        # Smooth Manhwa super-ellipse + tangent-continuous curved Bezier tail
        poly = [super_ellipse_pt(cx_s, cy_s, rx_s, ry_s, (2.0 * math.pi * i) / 96, exp=2.35) for i in range(96)]
        mdraw.polygon(poly, fill=255)

        half_ang = 0.11 if mode == "whisper" else 0.16
        p_l = super_ellipse_pt(cx_s, cy_s, rx_s * 0.90, ry_s * 0.90, theta0 - half_ang, exp=2.35)
        p_r = super_ellipse_pt(cx_s, cy_s, rx_s * 0.90, ry_s * 0.90, theta0 + half_ang, exp=2.35)

        ctrl_l = (
            (p_l[0] + tx_s) * 0.5 + perp_x * (14 * scale * bow_sign),
            (p_l[1] + ty_s) * 0.5 + perp_y * (14 * scale * bow_sign)
        )
        ctrl_r = (
            (p_r[0] + tx_s) * 0.5 + perp_x * (8 * scale * bow_sign),
            (p_r[1] + ty_s) * 0.5 + perp_y * (8 * scale * bow_sign)
        )
        tail_poly = quad_bezier_points(p_l, ctrl_l, (tx_s, ty_s)) + quad_bezier_points((tx_s, ty_s), ctrl_r, p_r)
        mdraw.polygon(tail_poly, fill=255)

    # Seamless charcoal comic ink stroke + soft ambient drop shadow
    outer = mask.filter(ImageFilter.MaxFilter(7))
    shadow = outer.filter(ImageFilter.GaussianBlur(7 * scale))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (W, H), (12, 15, 24, 52)), (0, 6 * scale), mask=shadow)
    canvas.paste(Image.new("RGBA", (W, H), (24, 24, 30, 255)), (0, 0), mask=outer)
    canvas.paste(Image.new("RGBA", (W, H), (254, 254, 255, 255)), (0, 0), mask=mask)

    cdraw = ImageDraw.Draw(canvas)
    if mode == "whisper":
        # Subtle comic dashed-border breaks around perimeter (excluding tail root)
        for i in range(0, 36, 2):
            ang = (2.0 * math.pi * i) / 36
            diff = abs(math.atan2(math.sin(ang - theta0), math.cos(ang - theta0)))
            if diff < 0.30:
                continue
            gx, gy = super_ellipse_pt(cx_s, cy_s, rx_s, ry_s, ang, exp=2.35)
            rg = 5 * scale
            cdraw.ellipse([gx - rg, gy - rg, gx + rg, gy + rg], fill=(254, 254, 255, 255))

    font = load_font(30 * scale)
    txt_col = (44, 48, 58, 255) if mode in ("thought", "whisper") else (18, 20, 26, 255)
    cdraw.multiline_text((cx_s, cy_s), wrapped, font=font, fill=txt_col, align="center", anchor="mm", spacing=7 * scale)

    canvas.resize((1080, 1920), Image.LANCZOS).save(out_path, "PNG")
    return out_path


# ==============================================================================
# 4. CONTINUOUS FORWARD AUDIO ENGINE
# ==============================================================================

def get_audio_duration(path):
    if not os.path.exists(path) or os.path.getsize(path) < 70000:
        return 0.0
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ], timeout=10).decode("utf-8").strip()
        return float(out)
    except Exception:
        return 0.0


def get_indila_audio(needed_sec):
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    if get_audio_duration(AUDIO_CACHE_PATH) >= needed_sec:
        print(f"✅ Using cached Indila Ethereal Instrumental: {AUDIO_CACHE_PATH}")
        return AUDIO_CACHE_PATH

    raw_mp3 = "workspace/raw_indila.mp3"
    slice_len = max(75, int(needed_sec) + 6)

    for q, offset in [
        ("scsearch3:Love Story by Indila Ethereal Instrumental Full Version", 20),
        ("scsearch3:Indila Love Story Extended Instrumental Slowed Reverb", 20),
        ("scsearch3:Indila Love Story Piano Instrumental Slowed Reverb", 0)
    ]:
        try:
            if os.path.exists(raw_mp3):
                os.remove(raw_mp3)
            subprocess.run([
                sys.executable, "-m", "yt_dlp", q,
                "--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K",
                "--match-filter", "duration > 90", "--max-downloads", "1",
                "--no-playlist", "--quiet", "--output", raw_mp3
            ], timeout=60, check=False)
            if os.path.exists(raw_mp3) and os.path.getsize(raw_mp3) > 90000:
                subprocess.run([
                    "ffmpeg", "-y", "-ss", str(offset), "-t", str(slice_len), "-i", raw_mp3,
                    "-af", "aecho=0.8:0.86:50:0.20,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-b:a", "192k", AUDIO_CACHE_PATH
                ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if get_audio_duration(AUDIO_CACHE_PATH) >= needed_sec:
                    return AUDIO_CACHE_PATH
        except Exception:
            continue

    wav_p = "workspace/synth.wav"
    sr = 44100
    with wave.open(wav_p, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        notes = [293.66, 349.23, 440.00, 587.33, 523.25, 466.16, 440.00, 392.00]
        for i in range(int(sr * slice_len)):
            t = i / float(sr)
            f = notes[int(t / 0.64) % len(notes)]
            env = math.exp(-(t % 0.64) * 2.2)
            val = 0.4 * math.sin(2 * math.pi * f * t) * env
            wf.writeframesraw(struct.pack("<h", int(max(-1.0, min(1.0, val)) * 32767)))
    subprocess.run(["ffmpeg", "-y", "-i", wav_p, "-b:a", "192k", AUDIO_CACHE_PATH], check=False)
    return AUDIO_CACHE_PATH


# ==============================================================================
# 5. MAIN PIPELINE ASSEMBLER
# ==============================================================================

def build_pipeline():
    print("=== STARTING VISION-GUIDED INTEGRAL-IMAGE LAYOUT MANHWA PIPELINE ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    history = load_history()
    story = generate_story(history)

    history.setdefault("used_titles", []).append(story.get("video_title", ""))
    history.setdefault("used_plots", []).append(story.get("plot_used", ""))
    for sc in story.get("scenes", []):
        if sc.get("male_line"):
            history.setdefault("used_dialogues", []).append(sc["male_line"])
        if sc.get("female_line"):
            history.setdefault("used_dialogues", []).append(sc["female_line"])
    history["total_runs"] = history.get("total_runs", 0) + 1
    save_history(history)

    with open("workspace/video_metadata.json", "w", encoding="utf-8") as f:
        json.dump(story, f, indent=2, ensure_ascii=False)

    boy_tags = story.get("boy_tags", "tall male, short black hair, amber eyes")
    girl_tags = story.get("girl_tags", "petite female, long chestnut hair, bright eyes")
    scenes = story.get("scenes", [])[:8]
    story_seed = random.randint(10000, 999999)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0.0.0"})

    scene_dur = 5.3
    reply_delay = 1.8
    clips = []

    for idx, sc in enumerate(scenes):
        art_path = f"workspace/art_{idx}.jpg"
        if not render_scene_image(session, sc, boy_tags, girl_tags, story_seed, idx, len(scenes), art_path):
            continue

        # 1. Semantic Vision + CV Head/Mouth Landmarks & Gentle Headroom Guard
        lm = align_couple_and_gentle_headroom(art_path)
        print(
            f"[LANDMARKS:{lm['source']}] Scene {idx + 1}: "
            f"BoyBox={lm['boy_box']} Mouth={lm['boy_mouth']} | "
            f"GirlBox={lm['girl_box']} Mouth={lm['girl_mouth']}"
        )

        # 2. Compute 2D Visual Saliency & Hard Exclusion Energy Field
        energy_grid = build_visual_energy_grid(art_path, lm, grid_scale=4)

        base = ImageClip(art_path).set_duration(scene_dur).resize((1080, 1920))
        layers = [base]

        age_path = f"workspace/age_{idx}.png"
        draw_age_layer(sc.get("male_age", "21"), sc.get("female_age", "19"), age_path)
        layers.append(ImageClip(age_path).set_position(("center", 12)).set_duration(scene_dur))

        # 3. Solve Optimal Non-Occluding Placement for Boy's Bubble (Left)
        if sc.get("male_line"):
            m_wrap, m_rx, m_ry = measure_bubble_geometry(sc["male_line"])
            m_cx, m_cy = solve_optimal_bubble_placement(
                energy_grid, m_rx, m_ry, lm["boy_box"], side="left", is_second_speaker=False
            )
            m_tx, m_ty = compute_exact_tail_target(m_cx, m_cy, m_rx, m_ry, lm["boy_box"], lm["boy_mouth"])
            mark_bubble_occupied(energy_grid, m_cx, m_cy, m_rx, m_ry, m_tx, m_ty)

            b_left = f"workspace/b_left_{idx}.png"
            render_master_comic_bubble(
                m_wrap, m_rx, m_ry, m_cx, m_cy, m_tx, m_ty,
                sc.get("male_mode", "speech"), b_left
            )
            print(f"   💬 Boy ({sc.get('male_mode', 'speech')}): Center=({m_cx},{m_cy}) -> TailTip=({m_tx},{m_ty})")
            layers.append(ImageClip(b_left).set_position((0, 0)).set_start(0.0).set_duration(scene_dur))

        # 4. Solve Optimal Non-Occluding Placement for Girl's Bubble (Right, avoids Boy's bubble + tail!)
        if sc.get("female_line"):
            f_wrap, f_rx, f_ry = measure_bubble_geometry(sc["female_line"])
            f_cx, f_cy = solve_optimal_bubble_placement(
                energy_grid, f_rx, f_ry, lm["girl_box"], side="right", is_second_speaker=True
            )
            f_tx, f_ty = compute_exact_tail_target(f_cx, f_cy, f_rx, f_ry, lm["girl_box"], lm["girl_mouth"])

            b_right = f"workspace/b_right_{idx}.png"
            render_master_comic_bubble(
                f_wrap, f_rx, f_ry, f_cx, f_cy, f_tx, f_ty,
                sc.get("female_mode", "thought"), b_right
            )
            print(f"   💭 Girl ({sc.get('female_mode', 'thought')}): Center=({f_cx},{f_cy}) -> TailTip=({f_tx},{f_ty})")
            layers.append(
                ImageClip(b_right)
                .set_position((0, 0))
                .set_start(reply_delay)
                .set_duration(scene_dur - reply_delay)
                .crossfadein(0.15)
            )

        comp = CompositeVideoClip(layers, size=(1080, 1920)).set_duration(scene_dur)
        if idx % 2 == 0:
            zoomed = comp.resize(lambda t: 1.0 + (0.012 * t))
        else:
            zoomed = comp.resize(lambda t: 1.064 - (0.012 * t))

        # Even 1080x1920 frame lock so libx264 never hits odd dimensions
        scene_clip = (
            CompositeVideoClip([zoomed.set_position("center")], size=(1080, 1920))
            .set_duration(scene_dur)
        )
        clips.append(scene_clip)

    if len(clips) < 5:
        raise RuntimeError(f"❌ Aborted: only {len(clips)} scenes generated.")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration

    audio_file = get_indila_audio(total_dur)
    if audio_file and os.path.exists(audio_file):
        aclip = AudioFileClip(audio_file)
        aclip = aclip.subclip(0, min(total_dur, aclip.duration)).audio_fadein(0.8).audio_fadeout(1.8).volumex(0.95)
        final_video = final_video.set_audio(aclip)

    out_mp4 = "videos/final_manhwa_short.mp4"
    final_video.write_videofile(
        out_mp4, fps=24, codec="libx264", audio_codec="aac",
        preset="medium", ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"]
    )
    print(f"🎉 SHORT COMPLETE ({total_dur:.1f}s): {out_mp4}")


if __name__ == "__main__":
    build_pipeline()
