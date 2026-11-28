import os
import sys
import io
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

# Real 2026 Free-Pollen Models on gen.pollinations.ai (NOT legacy 2-step SANA)
GEN_POLLINATIONS_MODELS = [
    "flux",
    "zimage",
    "klein"
]
CURRENT_WORKING_MODEL = "flux"

NEGATIVE_TAGS = (
    "3d, cgi, semi-realistic, photorealistic, airbrushed, blurry, out of focus, waxy skin, "
    "text, words, letters, speech bubble, watermark, logo, signature, bad anatomy, extra limbs, "
    "close-up, cropped head, multiple boys, multiple girls"
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
                {"male_age": "24", "female_age": "19", "male_mode": "thought", "male_line": "How can my brother ignore her tears?", "female_mode": "speech", "female_line": "It's okay, I'm used to waiting.", "scene_tags": "long dark coat, shivering in rain, streetlamp glow, concerned gaze, teardrops"},
                {"male_age": "24", "female_age": "19", "male_mode": "speech", "male_line": "Take my umbrella. Come with me.", "female_mode": "thought", "female_line": "Why is his gaze so warm?", "scene_tags": "sharing black umbrella, heavy rain, night city lights, standing together, blushing"},
                {"male_age": "24", "female_age": "20", "male_mode": "speech", "male_line": "I bought every cake you missed.", "female_mode": "thought", "female_line": "No one ever treasured me like this...", "scene_tags": "white shirt, cardigan, birthday cake with candles, bright dining room, gentle smile"},
                {"male_age": "25", "female_age": "20", "male_mode": "speech", "male_line": "Step back. You lost your chance.", "female_mode": "thought", "female_line": "He stood right in front of me!", "scene_tags": "tailored suit, evening gown, grand hall chandelier, protective posture, holding her hand"},
                {"male_age": "25", "female_age": "20", "male_mode": "speech", "male_line": "I've loved you in silence for years.", "female_mode": "speech", "female_line": "Stay with me. Never let go.", "scene_tags": "night balcony, starry sky, city bokeh, touching her cheek, tender eye contact"},
                {"male_age": "26", "female_age": "21", "male_mode": "speech", "male_line": "Marry me and be my whole world.", "female_mode": "speech", "female_line": "Yes! Only you, forever.", "scene_tags": "holding ring box, cherry blossom trees, sunset light, happy tears, smiling"},
                {"male_age": "27", "female_age": "22", "male_mode": "thought", "male_line": "I'll protect her smile for life.", "female_mode": "thought", "female_line": "Losing the wrong one led me to you.", "scene_tags": "black tuxedo, white wedding veil, hugging, sunlit garden, floating petals"}
            ]
        },
        {
            "trope": "University Rivals to Rooftop Lovers",
            "title": f"He Fought Me For #1 Rank… Just To Talk To Me 📚💗 Ep.{ep} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "19", "female_age": "19", "male_mode": "speech", "male_line": "First place is mine again.", "female_mode": "thought", "female_line": "Why does he always tease me?", "scene_tags": "university blazer, white shirt, exam board, sunlit hallway, soft smirk, pouting"},
                {"male_age": "19", "female_age": "19", "male_mode": "speech", "male_line": "Why are you crying up here?", "female_mode": "thought", "female_line": "He found my secret spot...", "scene_tags": "campus rooftop, bright sunset sky, offering handkerchief, tearful eyes, warm breeze"},
                {"male_age": "20", "female_age": "20", "male_mode": "speech", "male_line": "Rest on my shoulder for a bit.", "female_mode": "thought", "female_line": "His shoulder feels so safe...", "scene_tags": "library desk, stacked books, warm window light, draping blazer over her, blushing"},
                {"male_age": "20", "female_age": "20", "male_mode": "speech", "male_line": "Don't let him walk you home.", "female_mode": "speech", "female_line": "Wait, are you actually jealous?", "scene_tags": "campus courtyard, autumn leaves, holding her wrist, serious gaze, bright sunset"},
                {"male_age": "21", "female_age": "21", "male_mode": "speech", "male_line": "I studied hard just to stay near you.", "female_mode": "thought", "female_line": "My heart is racing so fast!", "scene_tags": "university garden, cherry blossoms, spring sunlight, standing together, shy smile"},
                {"male_age": "21", "female_age": "21", "male_mode": "speech", "male_line": "Every margin note was about you.", "female_mode": "speech", "female_line": "I liked you since freshman year.", "scene_tags": "rainy evening, transparent umbrella, warm cafe lights, touching her cheek, warm smile"},
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
   - "male_mode" / "female_mode": "speech" or "thought".
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
# 2. HIGH-CLASS 2D MANHWA IMAGE ENGINE (gen.pollinations.ai + SHARPNESS GATE)
# ==============================================================================

def build_clean_manhwa_prompt(scene, boy_tags, girl_tags):
    """
    Crisp 2D Manhwa prompt engineered for gen.pollinations.ai (flux / zimage / klein):
    - Uses 'manhwa style, flat 2d cel shading, crisp black ink lineart' to kill blurry 3D doll faces.
    - Uses 'medium full shot, wide framing, generous empty space above heads' so bubbles NEVER hit faces.
    """
    m_age = clamp_adult_age(scene.get("male_age", "21"), 21)
    f_age = clamp_adult_age(scene.get("female_age", "19"), 19)

    clean_boy = sanitize_tags(boy_tags, "tall male, short black hair, amber eyes")
    clean_girl = sanitize_tags(girl_tags, "petite female, long chestnut hair, bright eyes")
    clean_scene = sanitize_tags(
        scene.get("scene_tags", ""),
        "standing together, romantic lighting, looking at each other"
    )

    tags = [
        "manhwa style",
        "flat 2d cel shading",
        "crisp black ink lineart",
        "vibrant pastel colors",
        "1boy on left",
        "1girl on right",
        clean_boy,
        f"{m_age}yo",
        clean_girl,
        f"{f_age}yo",
        clean_scene,
        "medium full shot",
        "wide framing",
        "generous empty sky background above heads",
        "characters in lower two-thirds",
        "sharp focus",
        "masterpiece"
    ]
    return ", ".join(tags)


def measure_sharpness(pil_img):
    """Computes Laplacian edge variance to reject blurry/smeared SANA frames."""
    gray = np.array(pil_img.convert("L").resize((540, 960)), dtype=np.float32)
    lap = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    return float(np.var(lap))


def evaluate_artwork_bytes(raw_bytes):
    """Returns (is_valid, sharpness_score, pil_img)."""
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
    """
    Trims 3.5% bottom watermark margin, fits cleanly to 1080x1920 with zero stretching,
    and applies a crisp 2D lineart unsharp pass.
    """
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
    # Crisp 2D Manhwa lineart finish
    fitted = fitted.filter(ImageFilter.UnsharpMask(radius=1.1, percent=115, threshold=3))
    fitted = ImageEnhance.Color(fitted).enhance(1.08)
    fitted.save(out_path, "JPEG", quality=96)
    return out_path


def render_scene_image(session, scene, boy_tags, girl_tags, story_seed, idx, total, out_path):
    """
    High-Class 2026 Image Fetcher:
    1. Calls https://gen.pollinations.ai/image/{prompt} with POLLINATIONS_API_KEY (free Pollen)
       so it executes REAL Flux / Z-Image / Klein instead of the blurry 2-step SANA legacy endpoint.
    2. Enforces a Laplacian sharpness gate (rejects blurry smeared images and keeps the sharpest take).
    """
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

    # Build ordered endpoint queue: real gen.pollinations.ai FIRST (with free Pollen key)
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
        # Extra retry on the primary model with fresh seed if sharpness was low
        attempts.append((
            f"gen:{trial_models[0]}-retry",
            f"https://gen.pollinations.ai/image/{enc_pos}"
            f"?model={urllib.parse.quote(trial_models[0])}&width=768&height=1344"
            f"&seed={story_seed + (idx * 131) + 19}&negative_prompt={enc_neg}&nologo=true&enhance=false",
            {"Authorization": f"Bearer {api_key}"}
        ))
    else:
        print("   ⚠️ POLLINATIONS_API_KEY not found in env; gen.pollinations.ai needs a free key from enter.pollinations.ai.")

    # Anonymous fallback only if key is missing or completely out of Pollen
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

                    # Accept immediately if crisp and sharp (Laplacian variance >= 65)
                    if sharpness >= 65.0:
                        if label.startswith("gen:"):
                            CURRENT_WORKING_MODEL = label.split(":")[1].split("-")[0]
                        finalize_vertical_art(pil_im, out_path)
                        print(f"✅ Scene {idx + 1}/{total} crisp 2D art saved ({label}, sharp={sharpness:.1f}) -> {out_path}")
                        return True
                    else:
                        print(f"   ⚠️ Image too blurry (sharp={sharpness:.1f} < 65). Trying sharper model...")
                        time.sleep(4)
                        continue

            wait_s = 10 + (step_idx * 3)
            print(f"   ⏳ '{label}' returned HTTP {res.status_code}. Waiting {wait_s}s...")
            time.sleep(wait_s)
        except Exception as e:
            print(f"   ⏳ Network retry on '{label}' ({e}). Waiting 8s...")
            time.sleep(8)

    # Save the sharpest valid image collected across attempts if none crossed 65
    if best_img is not None:
        finalize_vertical_art(best_img, out_path)
        print(f"✅ Scene {idx + 1}/{total} saved best available take ({best_label}, sharp={best_sharpness:.1f}) -> {out_path}")
        return True

    return False


# ==============================================================================
# 3. CV HEAD/MOUTH ANCHOR + AUTO-ORIENTATION + GUARANTEED HEADROOM ENGINE
# ==============================================================================

def detect_character_anchors(img_path):
    """
    Detects left and right character head-tops and mouths across the upper-to-mid canvas (y: 60..1150).
    """
    default_anchors = {
        "boy_head_top": (285, 505),
        "boy_mouth": (345, 725),
        "girl_head_top": (795, 540),
        "girl_mouth": (725, 760)
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
        y_min, y_max = 60, 1150

        def find_side_face(x_start, x_end, is_left):
            sub_mask = skin_mask[y_min:y_max, x_start:x_end]
            ys, xs = np.where(sub_mask)
            if len(ys) < 350:
                return None

            face_cx = int(x_start + np.median(xs))
            face_top_y = int(y_min + np.percentile(ys, 10))
            face_bot_y = int(y_min + np.percentile(ys, 85))
            face_h = max(120, min(320, face_bot_y - face_top_y))

            head_top_y = max(25, face_top_y - int(face_h * 0.45))
            inward_shift = int(face_h * 0.16) if is_left else -int(face_h * 0.16)
            mouth_x = max(100, min(980, face_cx + inward_shift))
            mouth_y = min(1120, face_top_y + int(face_h * 0.70))
            return (face_cx, head_top_y), (mouth_x, mouth_y)

        left_res = find_side_face(40, 535, is_left=True)
        right_res = find_side_face(545, 1040, is_left=False)

        if left_res:
            default_anchors["boy_head_top"], default_anchors["boy_mouth"] = left_res
        if right_res:
            default_anchors["girl_head_top"], default_anchors["girl_mouth"] = right_res
    except Exception as e:
        print(f"⚠️ Anchor detection fallback used: {e}")

    return default_anchors


def auto_align_and_guarantee_headroom(img_path):
    """
    Two-step geometric safeguard that makes bubble-on-face/body overlaps IMPOSSIBLE:
    1. Auto-Orientation: If the taller character (boy) was drawn on the right (girl_head_y < boy_head_y - 30),
       horizontally flips the clean text-free artwork so the Boy is ALWAYS on the Left and Girl on the Right!
    2. Guaranteed Clean Headroom: If the highest character head sits above y=445, seamlessly extends the
       ambient upper sky/room backdrop upward and shifts the characters down so their heads start at y>=450,
       leaving y=0..435 completely open for the ages and speech/thought bubbles!
    """
    anchors = detect_character_anchors(img_path)

    # Step 1: Fix swapped left/right positions automatically
    boy_hy = anchors["boy_head_top"][1]
    girl_hy = anchors["girl_head_top"][1]
    if girl_hy < boy_hy - 30:
        with Image.open(img_path) as im:
            im.transpose(Image.FLIP_LEFT_RIGHT).save(img_path, "JPEG", quality=96)
        anchors = detect_character_anchors(img_path)
        print("   🔄 Auto-aligned swapped characters (Boy -> Left, Girl -> Right)")

    # Step 2: Guarantee clean upper headroom (y = 0..445) so bubbles NEVER cover faces or bodies
    min_head_y = min(anchors["boy_head_top"][1], anchors["girl_head_top"][1])
    target_min_head_y = 455

    if min_head_y < target_min_head_y:
        shift_y = min(380, target_min_head_y - min_head_y)
        with Image.open(img_path) as im:
            rgb = im.convert("RGB").resize((1080, 1920), Image.LANCZOS)
            arr = np.array(rgb, dtype=np.float32)

            # Build a smooth ambient backdrop from the clean top-left & top-right corners (avoids hair streaks)
            left_corner = np.median(arr[0:110, 0:150, :], axis=(0, 1))
            right_corner = np.median(arr[0:110, 930:1080, :], axis=(0, 1))
            x_t = np.linspace(0.0, 1.0, 1080, dtype=np.float32)[None, :, None]
            top_grad = left_corner[None, None, :] * (1.0 - x_t) + right_corner[None, None, :] * x_t

            canvas_arr = np.zeros((1920, 1080, 3), dtype=np.float32)
            canvas_arr[:shift_y + 50, :, :] = top_grad

            # If there is a clean top sky strip above the highest head, blend a mirrored blurred version
            if min_head_y >= 65:
                strip_h = min(120, min_head_y - 20)
                sky_strip = rgb.crop((0, 0, 1080, strip_h)).transpose(Image.FLIP_TOP_BOTTOM)
                sky_ext = sky_strip.resize((1080, shift_y + 40), Image.BICUBIC).filter(ImageFilter.GaussianBlur(18))
                sky_arr = np.array(sky_ext, dtype=np.float32)
                canvas_arr[:shift_y + 40, :, :] = 0.65 * sky_arr + 0.35 * top_grad

            # Paste original artwork shifted down by shift_y with a 42px vertical feather blend at the seam
            paste_h = 1920 - shift_y
            art_part = arr[:paste_h, :, :]
            feather = min(42, paste_h)
            alpha = np.linspace(0.0, 1.0, feather, dtype=np.float32)[:, None, None]

            canvas_arr[shift_y:shift_y + feather, :, :] = (
                canvas_arr[shift_y:shift_y + feather, :, :] * (1.0 - alpha)
                + art_part[:feather, :, :] * alpha
            )
            canvas_arr[shift_y + feather:, :, :] = art_part[feather:, :, :]

            Image.fromarray(np.clip(canvas_arr, 0, 255).astype(np.uint8), "RGB").save(img_path, "JPEG", quality=96)

        # Update anchor Y-coordinates by exact shift_y
        anchors = {
            "boy_head_top": (anchors["boy_head_top"][0], anchors["boy_head_top"][1] + shift_y),
            "boy_mouth": (anchors["boy_mouth"][0], anchors["boy_mouth"][1] + shift_y),
            "girl_head_top": (anchors["girl_head_top"][0], anchors["girl_head_top"][1] + shift_y),
            "girl_mouth": (anchors["girl_mouth"][0], anchors["girl_mouth"][1] + shift_y)
        }
        print(f"   📐 Extended clean top headroom by +{shift_y}px (Heads now safely below y={min_head_y + shift_y})")

    return anchors


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


def quad_bezier_points(p0, p1, p2, steps=32):
    pts = []
    for i in range(steps + 1):
        t = i / float(steps)
        inv = 1.0 - t
        pts.append((
            inv * inv * p0[0] + 2 * inv * t * p1[0] + t * t * p2[0],
            inv * inv * p0[1] + 2 * inv * t * p1[1] + t * t * p2[1]
        ))
    return pts


def render_webtoon_bubble_layer(text, bubble_type, side, head_top, mouth_pt, out_path):
    """
    Zero-Overlap Webtoon Bubble Renderer (2x supersampled 2160x3840):
    - Bubble body sits strictly ABOVE the character's hair-top (bottom edge <= hy - 62px).
    - Curved Bezier speech tail (or 4-dot Garfield thought chain) reaches down cleanly and
      STOPS 16px above the character's hair-top—pointing right at them without EVER touching
      their face, eyes, or body!
    """
    scale = 2
    W, H = 1080 * scale, 1920 * scale
    clean_t = ascii_clean(text)
    wrapped = "\n".join(textwrap.wrap(clean_t, width=17)[:3])

    font = load_font(30 * scale)
    tmp = ImageDraw.Draw(Image.new("L", (8, 8)))
    bbox = tmp.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=7 * scale)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    # Strict center separation across x=540 so left & right bubbles never collide
    rx = max(138 * scale, min(230 * scale, int(tw * 0.5 + 46 * scale)))
    ry = max(68 * scale, min(115 * scale, int(th * 0.5 + 34 * scale)))

    hx, hy = head_top[0] * scale, head_top[1] * scale
    mx, my = mouth_pt[0] * scale, mouth_pt[1] * scale

    # Strict vertical ceiling (below ages at y=110) and strict floor (at least 62px above hair-top hy!)
    max_safe_cy = max((115 * scale) + ry, hy - ry - (62 * scale))

    if side == "left":
        cx = max(rx + 24 * scale, min(518 * scale - rx, hx - 8 * scale))
        cy = min(max_safe_cy, max((112 * scale) + ry, 230 * scale))
    else:
        cx = max(562 * scale + rx, min(W - rx - 24 * scale, hx + 8 * scale))
        cy = min(max_safe_cy, max((135 * scale) + ry, 275 * scale))

    # Aim tail horizontally toward the character's head/mouth X
    raw_tx = (hx * 0.65 + mx * 0.35)
    tx = max(cx - rx + 22 * scale, min(cx + rx - 22 * scale, raw_tx))

    # Tail tip stops cleanly 16px ABOVE hair-top hy (NEVER entering the face or body!)
    ty = max(cy + ry + 38 * scale, min(hy - 16 * scale, cy + ry + 135 * scale))

    mask = Image.new("L", (W, H), 0)
    mdraw = ImageDraw.Draw(mask)

    if str(bubble_type).lower() == "thought":
        mdraw.ellipse(
            [cx - rx + 14 * scale, cy - ry + 12 * scale, cx + rx - 14 * scale, cy + ry - 12 * scale],
            fill=255
        )
        for i in range(16):
            ang = (2.0 * math.pi * i) / 16
            px = cx + (rx - 12 * scale) * math.cos(ang)
            py = cy + (ry - 8 * scale) * math.sin(ang)
            pr = (26 if i % 2 == 0 else 21) * scale
            mdraw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=255)

        sx = cx + (int(rx * 0.12) if side == "left" else -int(rx * 0.12))
        sy = cy + ry + 20 * scale
        ctrl_x = (sx + tx) * 0.5 + (-10 * scale if side == "left" else 10 * scale)
        ctrl_y = sy + (ty - sy) * 0.52

        for t_val, r_dot in [(0.08, 13.0 * scale), (0.40, 9.5 * scale), (0.70, 6.8 * scale), (0.96, 4.5 * scale)]:
            inv = 1.0 - t_val
            dx = inv * inv * sx + 2 * inv * t_val * ctrl_x + t_val * t_val * tx
            dy = inv * inv * sy + 2 * inv * t_val * ctrl_y + t_val * t_val * ty
            mdraw.ellipse([dx - r_dot, dy - r_dot, dx + r_dot, dy + r_dot], fill=255)
    else:
        poly = []
        for i in range(96):
            th_ang = (2.0 * math.pi * i) / 96
            ct, st = math.cos(th_ang), math.sin(th_ang)
            poly.append((
                cx + rx * (1 if ct >= 0 else -1) * (abs(ct) ** (2.0 / 2.35)),
                cy + ry * (1 if st >= 0 else -1) * (abs(st) ** (2.0 / 2.35))
            ))
        mdraw.polygon(poly, fill=255)

        bx = cx + (int(rx * 0.10) if side == "left" else -int(rx * 0.10))
        by = cy + ry - 8 * scale
        pl, pr = (bx - 18 * scale, by), (bx + 18 * scale, by)
        pull = -10 * scale if side == "left" else 10 * scale
        cl = ((pl[0] + tx) * 0.5 + pull, by + (ty - by) * 0.55)
        cr = ((pr[0] + tx) * 0.5 + pull, by + (ty - by) * 0.45)
        mdraw.polygon(quad_bezier_points(pl, cl, (tx, ty)) + quad_bezier_points((tx, ty), cr, pr), fill=255)

    outer = mask.filter(ImageFilter.MaxFilter(7))
    shadow = outer.filter(ImageFilter.GaussianBlur(7 * scale))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (W, H), (12, 15, 24, 55)), (0, 6 * scale), mask=shadow)
    canvas.paste(Image.new("RGBA", (W, H), (24, 24, 30, 255)), (0, 0), mask=outer)
    canvas.paste(Image.new("RGBA", (W, H), (254, 254, 255, 255)), (0, 0), mask=mask)

    cdraw = ImageDraw.Draw(canvas)
    cdraw.multiline_text((cx, cy), wrapped, font=font, fill=(20, 22, 28, 255), align="center", anchor="mm", spacing=7 * scale)
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
                    "-af", "stereotools=mlev=0.02,aecho=0.8:0.86:50:0.22,loudnorm=I=-14:TP=-1.5:LRA=11",
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
    print("=== STARTING HIGH-CLASS 2D MANHWA + ZERO-OVERLAP HEADROOM PIPELINE ===")
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

        # Auto-align Boy->Left/Girl->Right AND guarantee clean headroom above both heads
        anchors = auto_align_and_guarantee_headroom(art_path)
        print(
            f"[CV-ANCHORS] Scene {idx + 1}: Boy Head={anchors['boy_head_top']} Mouth={anchors['boy_mouth']} | "
            f"Girl Head={anchors['girl_head_top']} Mouth={anchors['girl_mouth']}"
        )

        base = ImageClip(art_path).set_duration(scene_dur).resize((1080, 1920))
        layers = [base]

        age_path = f"workspace/age_{idx}.png"
        draw_age_layer(sc.get("male_age", "21"), sc.get("female_age", "19"), age_path)
        layers.append(ImageClip(age_path).set_position(("center", 12)).set_duration(scene_dur))

        if sc.get("male_line"):
            b_left = f"workspace/b_left_{idx}.png"
            render_webtoon_bubble_layer(
                sc["male_line"], sc.get("male_mode", "speech"),
                "left", anchors["boy_head_top"], anchors["boy_mouth"], b_left
            )
            layers.append(ImageClip(b_left).set_position((0, 0)).set_start(0.0).set_duration(scene_dur))

        if sc.get("female_line"):
            b_right = f"workspace/b_right_{idx}.png"
            render_webtoon_bubble_layer(
                sc["female_line"], sc.get("female_mode", "thought"),
                "right", anchors["girl_head_top"], anchors["girl_mouth"], b_right
            )
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

        # Even 1080x1920 frame lock so libx264 never fails
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
