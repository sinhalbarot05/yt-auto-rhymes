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

# Ensure required packages are installed
for pkg in ("yt-dlp", "numpy"):
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", pkg], check=False)

import numpy as np
import yt_dlp
from groq import Groq
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    afx
)

HISTORY_FILE = "story_history.json"
LOCKED_SONG_PATH = "assets/indila_love_story_ethereal_inst_v7.mp3"
LOCKED_SONG_TITLE = "Love Story - Indila (Ethereal Instrumental Slowed & Reverb)"
MASTER_AUDIO_DURATION = 75

# Diverse pool of viral Korean Manhwa romance concepts
STORY_CONCEPTS = [
    "Uncherished Fiancée Saved by the Older Brother: Her cold fiancé stood her up on her birthday in the rain; his protective older brother steps in with an umbrella, cherishes her, and marries her while the ex begs in regret",
    "Childhood Next-Door Neighbours to Soulmates: From sharing strawberries across balconies at age 10, to walking under high-school cherry blossoms, to a jealous rain confession, to a rooftop proposal",
    "Cold Student Council President's Secret Jealousy: He claims she is just a junior, until another boy makes her laugh in the library—shattering his calm mask as he pulls her close at sunset to confess",
    "Contract Marriage to Real Devotion: Married on paper with a rule to never fall in love; when she hands him divorce papers thinking he loves someone else, he tears them up in the rain",
    "7 AM Subway Strangers to Forever: Standing in the same train car every morning in silence for a year until a thunderstorm stops the train and he pulls her into his arms",
    "Academic Rivals to Midnight Confidants: Fighting for #1 rank every exam while bickering daily, until he finds her crying on the school balcony at dusk and stays beside her every night",
    "The Forgotten Childhood Ribbon: Separated at age 11 when she moved away, she thinks the cold university senior is a stranger—until she sees the faded red ribbon she tied on his wrist ten years ago",
    "Ignored by Crush, Treasured by the Art Prodigy: She always baked cookies for the popular captain who ignored her, while the quiet art prodigy filled a whole sketchbook with her smile before confessing",
    "Time-Leap Second Chance: After losing her in a tragic future where he hid his feelings, he wakes up 5 years in the past on the day they first met and vows to protect her smile",
    "Fake Boyfriend to Obsessive Protector: He agreed to pretend to be her boyfriend for one weekend to stop her ex from harassing her, then refuses to ever let her go"
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


def get_comic_font(size):
    """Loads clean bold font for comic lettering."""
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def clean_english_text(text):
    """Ensures 100% clean printable ASCII English text."""
    allowed = "".join(ch for ch in str(text) if 32 <= ord(ch) <= 126)
    return " ".join(allowed.split()) or "..."


def clean_watermark_and_fit_9_16(raw_bytes, output_path):
    """
    1. Trims 4.0% off the bottom edge to remove any 'pollinations.ai' corner watermark.
    2. Center-crops to exact 9:16 aspect ratio with ZERO vertical or horizontal stretching.
    3. Saves crisp 1080x1920 JPEG preserving Pollinations Flux's vibrant Manhwa colors.
    """
    with Image.open(io.BytesIO(raw_bytes)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size

        x0 = int(w * 0.02)
        x1 = int(w * 0.98)
        y0 = int(h * 0.005)
        y1 = int(h * 0.960)

        cropped = rgb.crop((x0, y0, x1, y1))
        cw, ch = cropped.size

        target_aspect = 1080.0 / 1920.0
        current_aspect = cw / float(ch)

        if abs(current_aspect - target_aspect) > 0.02:
            if current_aspect > target_aspect:
                new_w = int(ch * target_aspect)
                left = (cw - new_w) // 2
                cropped = cropped.crop((left, 0, left + new_w, ch))
            else:
                new_h = int(cw / target_aspect)
                top = max(0, (ch - new_h) // 3)
                cropped = cropped.crop((0, top, cw, top + new_h))

        fitted = cropped.resize((1080, 1920), Image.LANCZOS)
        fitted.save(output_path, "JPEG", quality=96)

    return output_path


def is_valid_artwork(raw_bytes):
    """Verifies the downloaded bytes form a valid, non-blank, colorful image."""
    if not raw_bytes or len(raw_bytes) < 15000:
        return False
    try:
        with Image.open(io.BytesIO(raw_bytes)) as im:
            arr = np.array(im.convert("RGB"), dtype=np.float32)
            if arr.shape[0] < 500 or arr.shape[1] < 400:
                return False
            if np.std(arr) < 18.0:
                return False
        return True
    except Exception:
        return False


def detect_character_anchors(img_path):
    """
    Waist-Up Two-Shot Character Head & Mouth Locator:
    Scans the left half (Boy) and right half (Girl) and strictly clamps the detected
    coordinates to the waist-up character zones so bubbles and tails NEVER drift into blank space!
    """
    default_anchors = {
        "boy_head_top": (280, 465),
        "boy_mouth": (335, 665),
        "girl_head_top": (800, 495),
        "girl_mouth": (740, 695)
    }
    try:
        with Image.open(img_path) as im:
            rgb = np.array(im.convert("RGB").resize((1080, 1920)), dtype=np.float32)

        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        skin_mask = (
            (r > 165) & (g > 120) & (b > 95) &
            ((r - g) > 10) & ((r - b) > 20) & ((r - b) < 115) &
            (g > b)
        )
        y_min, y_max = 350, 980

        def find_clamped_side_face(x_start, x_end, is_left):
            sub_mask = skin_mask[y_min:y_max, x_start:x_end]
            ys, xs = np.where(sub_mask)
            if len(ys) < 400:
                return None

            raw_cx = int(x_start + np.median(xs))
            face_top_y = int(y_min + np.percentile(ys, 12))
            face_bot_y = int(y_min + np.percentile(ys, 88))
            face_h = max(130, min(280, face_bot_y - face_top_y))

            # Strictly clamp horizontal & vertical coordinates so bubbles never sit over empty corners
            if is_left:
                face_cx = max(210, min(380, raw_cx))
                head_top_y = max(390, min(550, face_top_y - int(face_h * 0.45)))
                mouth_x = max(240, min(430, face_cx + int(face_h * 0.16)))
                mouth_y = max(580, min(790, face_top_y + int(face_h * 0.68)))
            else:
                face_cx = max(700, min(870, raw_cx))
                head_top_y = max(410, min(575, face_top_y - int(face_h * 0.45)))
                mouth_x = max(650, min(840, face_cx - int(face_h * 0.16)))
                mouth_y = max(600, min(810, face_top_y + int(face_h * 0.68)))

            return (face_cx, head_top_y), (mouth_x, mouth_y)

        left_res = find_clamped_side_face(70, 520, is_left=True)
        right_res = find_clamped_side_face(560, 1010, is_left=False)

        if left_res:
            default_anchors["boy_head_top"], default_anchors["boy_mouth"] = left_res
        if right_res:
            default_anchors["girl_head_top"], default_anchors["girl_mouth"] = right_res
    except Exception:
        pass

    return default_anchors


def render_floating_manhwa_ages(male_age, female_age, output_path):
    """
    Renders sleek, glowing Manhwa age numbers in the top-left (Electric Blue) and top-right (Ruby Pink)
    exactly like gXlmlO4comg—never floating in random blank space.
    """
    scale = 2
    W, H = 1080 * scale, 180 * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_age = get_comic_font(62 * scale)

    def draw_stylized_age(cx, cy, age_val, main_color, glow_color):
        txt = "".join(c for c in str(age_val) if c.isdigit())[:2] or "19"
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_layer)
        g_draw.text(
            (cx, cy), txt, font=font_age,
            fill=glow_color + (160,), anchor="mm",
            stroke_width=10 * scale, stroke_fill=glow_color + (160,)
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(6 * scale))
        img.alpha_composite(glow_layer)

        draw.text(
            (cx, cy), txt, font=font_age,
            fill=main_color + (255,), anchor="mm",
            stroke_width=5 * scale, stroke_fill=(15, 18, 26, 255)
        )

    if male_age:
        draw_stylized_age(95 * scale, 78 * scale, male_age, (75, 180, 255), (30, 120, 255))
    if female_age:
        draw_stylized_age(985 * scale, 78 * scale, female_age, (255, 85, 135), (255, 40, 100))

    img.resize((1080, 180), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def quad_bezier_points(p0, p1, p2, steps=32):
    pts = []
    for i in range(steps + 1):
        t = i / float(steps)
        inv = 1.0 - t
        x = (inv * inv * p0[0]) + (2 * inv * t * p1[0]) + (t * t * p2[0])
        y = (inv * inv * p0[1]) + (2 * inv * t * p1[1]) + (t * t * p2[1])
        pts.append((x, y))
    return pts


def render_webtoon_bubble_layer(text, bubble_type, side, head_top, mouth_pt, output_path):
    """
    Renders professional comic bubbles at 2x supersampled resolution (2160x3840) matching gXlmlO4comg:
    - 'speech'  -> Horizontal egg / super-ellipse + SOLID curved Bezier wedge tail pointing to speaker's mouth.
    - 'thought' -> Fluffy scalloped cloud + 4 DETACHED shrinking circular thought bubbles (Garfield style).
    - 'whisper' -> Smooth horizontal egg with dashed ink border.
    - 'shout'   -> Spiky comic starburst oval for dramatic/jealous lines.
    """
    scale = 2
    W, H = 1080 * scale, 1920 * scale
    clean_txt = clean_english_text(text)

    b_type = str(bubble_type or "speech").lower().strip()
    if b_type not in ("speech", "thought", "whisper", "shout"):
        b_type = "speech"

    wrapped_lines = textwrap.wrap(clean_txt, width=18)[:3]
    multiline_str = "\n".join(wrapped_lines)

    font = get_comic_font(32 * scale)
    dummy = Image.new("L", (10, 10))
    d_draw = ImageDraw.Draw(dummy)
    bbox = d_draw.multiline_textbbox((0, 0), multiline_str, font=font, align="center", spacing=8 * scale)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    rx = max(145 * scale, int(tw * 0.5 + 52 * scale))
    ry = max(76 * scale, int(th * 0.5 + 40 * scale))

    hx, hy = head_top[0] * scale, head_top[1] * scale
    mx, my = mouth_pt[0] * scale, mouth_pt[1] * scale

    if side == "left":
        cx = max(rx + 28 * scale, min(515 * scale - rx, hx - 10 * scale))
        cy = max(ry + 115 * scale, min(hy - ry - 22 * scale, 260 * scale))
    else:
        cx = max(565 * scale + rx, min(W - rx - 28 * scale, hx + 10 * scale))
        cy = max(ry + 145 * scale, min(hy - ry - 18 * scale, 305 * scale))

    raw_tx = mx + (-18 * scale if side == "left" else 18 * scale)
    tx = max(cx - rx + 20 * scale, min(cx + rx - 20 * scale, raw_tx))
    if side == "left":
        tx = max(tx, cx + int(rx * 0.16))
    else:
        tx = min(tx, cx - int(rx * 0.16))

    tail_bottom_limit = cy + ry + 120 * scale
    ty = max(cy + ry + 64 * scale, min(tail_bottom_limit, my - 55 * scale))

    mask = Image.new("L", (W, H), 0)
    m_draw = ImageDraw.Draw(mask)

    if b_type == "thought":
        m_draw.ellipse(
            [cx - rx + 14 * scale, cy - ry + 12 * scale, cx + rx - 14 * scale, cy + ry - 12 * scale],
            fill=255
        )
        num_puffs = 16
        for i in range(num_puffs):
            ang = (2.0 * math.pi * i) / num_puffs
            px = cx + (rx - 12 * scale) * math.cos(ang)
            py = cy + (ry - 8 * scale) * math.sin(ang)
            pr = (28 if i % 2 == 0 else 23) * scale
            m_draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=255)

        start_x = cx + (int(rx * 0.14) if side == "left" else -int(rx * 0.14))
        start_y = cy + ry + 24 * scale
        ctrl_x = (start_x + tx) * 0.5 + (-14 * scale if side == "left" else 14 * scale)
        ctrl_y = start_y + (ty - start_y) * 0.52

        dot_specs = [
            (0.08, 14.0 * scale),
            (0.40, 10.0 * scale),
            (0.70, 7.0 * scale),
            (0.96, 4.8 * scale)
        ]
        for t_val, r_dot in dot_specs:
            inv = 1.0 - t_val
            dx = (inv * inv * start_x) + (2 * inv * t_val * ctrl_x) + (t_val * t_val * tx)
            dy = (inv * inv * start_y) + (2 * inv * t_val * ctrl_y) + (t_val * t_val * ty)
            m_draw.ellipse([dx - r_dot, dy - r_dot, dx + r_dot, dy + r_dot], fill=255)

    elif b_type == "shout":
        poly_burst = []
        num_spikes = 28
        for i in range(num_spikes * 2):
            theta = (math.pi * i) / num_spikes
            rad_mult = 1.08 if i % 2 == 0 else 0.90
            x_pt = cx + (rx * rad_mult) * math.cos(theta)
            y_pt = cy + (ry * rad_mult) * math.sin(theta)
            poly_burst.append((x_pt, y_pt))
        m_draw.polygon(poly_burst, fill=255)

        base_x = cx + (int(rx * 0.12) if side == "left" else -int(rx * 0.12))
        base_y = cy + int(ry * 0.85)
        tail_poly = [
            (base_x - 20 * scale, base_y),
            (tx, ty),
            (base_x + 20 * scale, base_y)
        ]
        m_draw.polygon(tail_poly, fill=255)

    else:
        poly_body = []
        steps_body = 96
        exp = 2.35
        for i in range(steps_body):
            theta = (2.0 * math.pi * i) / steps_body
            ct, st = math.cos(theta), math.sin(theta)
            x_pt = cx + rx * (1 if ct >= 0 else -1) * (abs(ct) ** (2.0 / exp))
            y_pt = cy + ry * (1 if st >= 0 else -1) * (abs(st) ** (2.0 / exp))
            poly_body.append((x_pt, y_pt))
        m_draw.polygon(poly_body, fill=255)

        base_x = cx + (int(rx * 0.12) if side == "left" else -int(rx * 0.12))
        base_y = cy + ry - 8 * scale
        half_base = (14 if b_type == "whisper" else 19) * scale

        p_left = (base_x - half_base, base_y)
        p_right = (base_x + half_base, base_y)

        curve_pull_x = -12 * scale if side == "left" else 12 * scale
        ctrl_left = ((p_left[0] + tx) * 0.5 + curve_pull_x, base_y + (ty - base_y) * 0.55)
        ctrl_right = ((p_right[0] + tx) * 0.5 + curve_pull_x, base_y + (ty - base_y) * 0.45)

        left_edge = quad_bezier_points(p_left, ctrl_left, (tx, ty), steps=24)
        right_edge = quad_bezier_points((tx, ty), ctrl_right, p_right, steps=24)
        m_draw.polygon(left_edge + right_edge, fill=255)

    stroke_px = 7
    outer_mask = mask.filter(ImageFilter.MaxFilter(stroke_px))
    shadow_mask = outer_mask.filter(ImageFilter.GaussianBlur(7 * scale))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    shadow_layer = Image.new("RGBA", (W, H), (12, 15, 24, 55))
    canvas.paste(shadow_layer, (0, 6 * scale), mask=shadow_mask)

    ink_layer = Image.new("RGBA", (W, H), (24, 24, 30, 255))
    canvas.paste(ink_layer, (0, 0), mask=outer_mask)

    fill_layer = Image.new("RGBA", (W, H), (254, 254, 255, 255))
    canvas.paste(fill_layer, (0, 0), mask=mask)

    c_draw = ImageDraw.Draw(canvas)
    if b_type == "whisper":
        dash_steps = 36
        for i in range(0, dash_steps, 2):
            ang = (2.0 * math.pi * i) / dash_steps
            if 0.35 * math.pi < ang < 0.65 * math.pi:
                continue
            dx = cx + rx * math.cos(ang)
            dy = cy + ry * math.sin(ang)
            r_gap = 5 * scale
            c_draw.ellipse([dx - r_gap, dy - r_gap, dx + r_gap, dy + r_gap], fill=(254, 254, 255, 255))

    text_color = (42, 46, 58, 255) if b_type in ("thought", "whisper") else (18, 18, 22, 255)
    c_draw.multiline_text(
        (cx, cy),
        multiline_str,
        font=font,
        fill=text_color,
        align="center",
        anchor="mm",
        spacing=8 * scale
    )

    canvas.resize((1080, 1920), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def get_valid_groq_chat_models(client):
    """Returns active Groq text-chat LLMs while blocking TTS/Whisper/Guard models."""
    models_resp = client.models.list().data
    all_ids = [m.id for m in models_resp]

    banned = (
        "orpheus", "canopylabs", "whisper", "guard", "tts", "playai",
        "embed", "vision", "allam", "distil", "audio", "speech", "safeguard"
    )
    allowed_families = ("llama", "qwen", "deepseek", "gemma", "mixtral", "compound", "kimi")

    chat_models = [
        m for m in all_ids
        if not any(b in m.lower() for b in banned)
        and any(f in m.lower() for f in allowed_families)
    ]

    preferred_order = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3-32b",
        "qwen-qwq-32b",
        "qwen/qwen3.8-27b",
        "deepseek-r1-distill-llama-70b",
        "gemma2-9b-it",
        "llama3-70b-8192",
        "llama3-8b-8192"
    ]

    ordered = [p for p in preferred_order if p in chat_models]
    for m in chat_models:
        if m not in ordered:
            ordered.append(m)

    return ordered if ordered else ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def build_story_prompts(concept, used_titles, used_dialogues):
    """
    Compact, high-impact 8-scene prompt (~520 output tokens) so it succeeds on EVERY Groq tier
    (including 1,000 OTPM models like qwen3.8-27b) without throwing 429 errors.
    """
    entropy = f"{int(time.time())}-{random.randint(1000, 9999)}"
    system_prompt = (
        "You are an elite Korean Manhwa romance scriptwriter. "
        "You write emotionally gripping 8-scene vertical Shorts with a unique viral title every run. "
        "Output strictly valid, compact JSON."
    )
    user_prompt = f"""Write a brand-new, complete 8-scene Korean Manhwa romance Short script.
Run Seed: {entropy}
Concept: "{concept}"
NEVER repeat these past titles: {json.dumps(used_titles[-12:])}

STORY STRUCTURE (8 SCENES = ~43s COMPLETE STORY):
- Scenes 1-2: Setup & emotional hook.
- Scenes 3-4: Heartbreak, jealousy, or rain tension.
- Scenes 5-6: Dramatic rescue, umbrella protection, or confrontation.
- Scenes 7-8: Raw confession & romantic payoff (proposal, kiss, or embrace).

RULES:
- Every scene features ONE male lead (left) and ONE female lead (right) in a waist-up two-shot.
- Bubble types: "speech" (spoken), "thought" (inner monologue cloud), "whisper" (shy), "shout" (urgent/jealous).
- Keep male_line and female_line between 4 and 7 English words.

Return ONLY valid JSON matching this schema:
{{
  "trope": "Unique 3-5 word trope name",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "video_title": "Brand-new emotional English title with emojis #Shorts #manhwa #lovestory",
  "male_dna": "handsome 2D anime boy with [hair color] short hair, [eye color] eyes, wearing [jacket/blazer]",
  "female_dna": "beautiful 2D anime girl with long [hair color] hair, [eye color] eyes, wearing [cardigan/blouse]",
  "scenes": [
    {{
      "male_age": "21",
      "female_age": "19",
      "male_bubble_type": "speech",
      "male_line": "Why are you standing in the rain?",
      "female_bubble_type": "thought",
      "female_line": "He actually came looking for me...",
      "lighting_and_atmosphere": "warm streetlamp bokeh, falling rain droplets",
      "scene_setting_and_pose": "standing close under a black umbrella on a rainy evening street facing each other"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def build_procedural_unique_story(history):
    """
    Procedural Multi-Plot Fallback Engine:
    If all external LLMs are offline, procedurally builds a fresh 8-scene story from a large
    library of plots and checks history so it NEVER repeats a title!
    """
    used_titles = set(history.get("used_titles", []))
    run_num = history.get("total_videos", 0) + 1

    m_hairs = ["jet-black tousled", "silver-white", "dark ash-brown", "midnight-blue", "espresso-brown"]
    f_hairs = ["long wavy chestnut", "silky raven-black", "warm honey-blonde", "soft caramel", "dark cherry-brown"]
    m_eyes = ["amber", "sapphire-blue", "obsidian", "crimson-grey", "emerald"]
    f_eyes = ["bright hazel", "violet", "sky-blue", "warm jade", "golden-brown"]

    plot_library = [
        {
            "trope": "When Her Fiancé Stood Her Up, His Brother Stepped In",
            "titles": [
                "When Her Fiancé Stood Her Up, His Brother Saved Her 🌂❤️ #Shorts #manhwa #lovestory",
                "He Left Her In The Rain… So His Older Brother Stepped In 💔☔ #Shorts #manhwa #lovestory",
                "Ignored By Her Fiancé, Cherished By His Older Brother 🥀💍 #Shorts #manhwa #lovestory"
            ],
            "scenes": [
                {"male_age": "21", "female_age": "19", "male_bubble_type": "speech", "male_line": "Wait outside. I'm busy tonight.", "female_bubble_type": "thought", "female_line": "He forgot my birthday again...", "lighting_and_atmosphere": "cold blue twilight outside a glowing restaurant window", "scene_setting_and_pose": "cold boy turning away while the girl holds a small birthday cake box"},
                {"male_age": "24", "female_age": "19", "male_bubble_type": "thought", "male_line": "How can my brother ignore her tears?", "female_bubble_type": "whisper", "female_line": "It's fine... I'm used to waiting.", "lighting_and_atmosphere": "warm amber streetlamp glow as rain begins to fall", "scene_setting_and_pose": "tall older brother in a dark tailored coat approaching the shivering girl"},
                {"male_age": "24", "female_age": "19", "male_bubble_type": "speech", "male_line": "Take my umbrella. Come with me.", "female_bubble_type": "thought", "female_line": "Why is his gaze so warm?", "lighting_and_atmosphere": "pouring rain and glowing golden reflections", "scene_setting_and_pose": "standing close under a large black umbrella in heavy rain facing each other"},
                {"male_age": "24", "female_age": "20", "male_bubble_type": "speech", "male_line": "I bought every cake you missed.", "female_bubble_type": "thought", "female_line": "No one ever treasured me like this...", "lighting_and_atmosphere": "warm candlelight inside a luxury penthouse dining room", "scene_setting_and_pose": "boy smiling gently over birthday candles while the girl blushes"},
                {"male_age": "25", "female_age": "20", "male_bubble_type": "shout", "male_line": "Step back! You lost your chance!", "female_bubble_type": "thought", "female_line": "He stepped right in front of me...", "lighting_and_atmosphere": "dramatic marble lobby lighting with crystal chandeliers", "scene_setting_and_pose": "protective older brother shielding the girl behind his shoulder"},
                {"male_age": "25", "female_age": "20", "male_bubble_type": "whisper", "male_line": "I've loved you in silence for years.", "female_bubble_type": "speech", "female_line": "Stay with me. Never let go.", "lighting_and_atmosphere": "starry rooftop balcony with glowing city bokeh", "scene_setting_and_pose": "standing close on a night balcony, boy gently cupping her blushing cheek"},
                {"male_age": "26", "female_age": "21", "male_bubble_type": "speech", "male_line": "Marry me and be my queen.", "female_bubble_type": "speech", "female_line": "Yes! Only you, forever.", "lighting_and_atmosphere": "golden sunset garden with floating cherry blossom petals", "scene_setting_and_pose": "handsome man holding a velvet ring box under cherry blossoms while she cries happy tears"},
                {"male_age": "27", "female_age": "22", "male_bubble_type": "thought", "male_line": "I'll protect her smile for life.", "female_bubble_type": "thought", "female_line": "Losing the wrong one led me to you.", "lighting_and_atmosphere": "magical sunlit wedding glow and floating sparkles", "scene_setting_and_pose": "bride and groom embracing tenderly face-to-face with warm smiles"}
            ]
        },
        {
            "trope": "Academic Rivals to Midnight Rooftop Lovers",
            "titles": [
                "My Cold Academic Rival Caught Me Crying On The Roof 😭🌙 #Shorts #manhwa #lovestory",
                "He Fought Me For #1 Rank… Just To Get My Attention 📚💗 #Shorts #manhwa #lovestory",
                "When The Cold Class PresidentSaw Her Tears 💔✨ #Shorts #manhwa #lovestory"
            ],
            "scenes": [
                {"male_age": "17", "female_age": "17", "male_bubble_type": "speech", "male_line": "First place is mine again.", "female_bubble_type": "thought", "female_line": "Why does he always tease me?", "lighting_and_atmosphere": "sunlit high school hallway with floating dust motes", "scene_setting_and_pose": "handsome boy in school blazer smirking softly at the stubborn girl beside the exam board"},
                {"male_age": "17", "female_age": "17", "male_bubble_type": "whisper", "male_line": "Why are you crying out here?", "female_bubble_type": "thought", "female_line": "He found my hiding spot...", "lighting_and_atmosphere": "purple-gold twilight on a quiet school rooftop", "scene_setting_and_pose": "boy offering a warm handkerchief to the tearful girl by the rooftop railing"},
                {"male_age": "18", "female_age": "18", "male_bubble_type": "speech", "male_line": "Lean on my shoulder and rest.", "female_bubble_type": "thought", "female_line": "His shoulder feels so warm...", "lighting_and_atmosphere": "amber evening lamp light in an empty library", "scene_setting_and_pose": "studying side-by-side at a wooden library desk as he drapes his blazer over her"},
                {"male_age": "18", "female_age": "18", "male_bubble_type": "shout", "male_line": "Don't let that guy walk you home!", "female_bubble_type": "speech", "female_line": "Wait... are you jealous?", "lighting_and_atmosphere": "dramatic sunset shadows in the school courtyard", "scene_setting_and_pose": "jealous boy gently catching the girl's wrist under autumn trees"},
                {"male_age": "19", "female_age": "19", "male_bubble_type": "speech", "male_line": "I only studied hard so you'd look at me.", "female_bubble_type": "thought", "female_line": "My heart is beating so loud!", "lighting_and_atmosphere": "falling pink cherry blossoms in spring sunlight", "scene_setting_and_pose": "standing close under blooming cherry trees on university campus facing each other"},
                {"male_age": "20", "female_age": "20", "male_bubble_type": "whisper", "male_line": "Every note in my book was for you.", "female_bubble_type": "speech", "female_line": "I've liked you since tenth grade.", "lighting_and_atmosphere": "rainy evening outside a cozy campus cafe", "scene_setting_and_pose": "sharing a single umbrella in the rain, boy gently touching her cheek"},
                {"male_age": "22", "female_age": "22", "male_bubble_type": "speech", "male_line": "Be my partner for the rest of our lives?", "female_bubble_type": "speech", "female_line": "Yes, my favourite rival!", "lighting_and_atmosphere": "starry night rooftop with glowing fairy lights", "scene_setting_and_pose": "man in dark suit proposing with a diamond ring on the rooftop"},
                {"male_age": "23", "female_age": "23", "male_bubble_type": "thought", "male_line": "Winning her heart was my real prize.", "female_bubble_type": "thought", "female_line": "From rivals to soulmates forever.", "lighting_and_atmosphere": "golden sunrise over the city skyline", "scene_setting_and_pose": "couple holding hands and smiling warmly into each other's eyes"}
            ]
        },
        {
            "trope": "Contract Marriage to Obsessive Devotion",
            "titles": [
                "She Handed Him Divorce Papers… So He Tore Them Up In Panic 💔🔥 #Shorts #manhwa #lovestory",
                "Our 30-Day Contract Marriage Was Supposed To Be Fake 💍🥺 #Shorts #manhwa #lovestory",
                "The Cold CEO Broke His Own Rule For Her 🌧️❤️ #Shorts #manhwa #lovestory"
            ],
            "scenes": [
                {"male_age": "24", "female_age": "21", "male_bubble_type": "speech", "male_line": "Remember, this marriage is only a contract.", "female_bubble_type": "thought", "female_line": "His voice is as cold as ice...", "lighting_and_atmosphere": "sleek moonlight inside a modern penthouse office", "scene_setting_and_pose": "handsome young CEO in dark suit standing across from the quiet bride"},
                {"male_age": "24", "female_age": "21", "male_bubble_type": "thought", "male_line": "She fell asleep waiting for me...", "female_bubble_type": "whisper", "female_line": "Don't catch a cold...", "lighting_and_atmosphere": "warm fireplace glow in a grand living room", "scene_setting_and_pose": "man gently draping his cashmere coat over her shoulders as she wakes up blushing"},
                {"male_age": "25", "female_age": "22", "male_bubble_type": "speech", "male_line": "Who gave you permission to get hurt?", "female_bubble_type": "thought", "female_line": "Why do his eyes look so worried?", "lighting_and_atmosphere": "soft evening rain outside tall glass windows", "scene_setting_and_pose": "man kneeling slightly to tend to her bandaged hand, intense tender gaze"},
                {"male_age": "25", "female_age": "22", "male_bubble_type": "whisper", "male_line": "I signed the divorce papers for you.", "female_bubble_type": "thought", "female_line": "I have to let him go before I cry...", "lighting_and_atmosphere": "dramatic blue storm light in the hallway", "scene_setting_and_pose": "girl handing over a white envelope while looking down with teary eyes"},
                {"male_age": "25", "female_age": "22", "male_bubble_type": "shout", "male_line": "I'm tearing this up! You're not leaving!", "female_bubble_type": "thought", "female_line": "Paper shards are flying everywhere!", "lighting_and_atmosphere": "lightning flash and flying white paper pieces", "scene_setting_and_pose": "man tearing the contract in half and pulling her close by the waist"},
                {"male_age": "25", "female_age": "22", "male_bubble_type": "speech", "male_line": "The contract was just my excuse to keep you.", "female_bubble_type": "speech", "female_line": "You loved me from the start?", "lighting_and_atmosphere": "warm golden streetlamp glow in pouring rain", "scene_setting_and_pose": "holding her face gently in both hands under a rainy archway"},
                {"male_age": "26", "female_age": "23", "male_bubble_type": "speech", "male_line": "Let's have a real wedding this time.", "female_bubble_type": "speech", "female_line": "No contracts. Just us forever.", "lighting_and_atmosphere": "blooming white roses and golden sunset rays", "scene_setting_and_pose": "man placing a sparkling diamond ring on her finger in a sunlit garden"},
                {"male_age": "26", "female_age": "23", "male_bubble_type": "thought", "male_line": "She is my only weakness and my whole world.", "female_bubble_type": "thought", "female_line": "His cold mask melted only for me.", "lighting_and_atmosphere": "sparkling night fireworks over the balcony", "scene_setting_and_pose": "embracing passionately under night fireworks with happy smiles"}
            ]
        }
    ]

    # Pick a plot & title not used recently
    random.shuffle(plot_library)
    chosen_plot = plot_library[0]
    chosen_title = None
    for plot in plot_library:
        for t in plot["titles"]:
            if t not in used_titles:
                chosen_plot = plot
                chosen_title = t
                break
        if chosen_title:
            break

    if not chosen_title:
        base_t = chosen_plot["titles"][0].replace("#Shorts", f"Ep.{run_num} #Shorts")
        chosen_title = base_t

    return {
        "trope": chosen_plot["trope"],
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": chosen_title,
        "male_dna": f"handsome 2D anime boy with {random.choice(m_hairs)} hair, {random.choice(m_eyes)} eyes, wearing a tailored dark jacket over a crisp shirt",
        "female_dna": f"beautiful 2D anime girl with {random.choice(f_hairs)} hair, {random.choice(f_eyes)} eyes, wearing a soft pastel cardigan over a blouse",
        "scenes": chosen_plot["scenes"]
    }


def generate_fresh_story(history):
    used_concepts = history.get("used_archetypes", [])[-6:]
    used_titles = history.get("used_titles", [])
    used_dialogues = history.get("used_dialogues", [])

    avail = [c for c in STORY_CONCEPTS if c not in used_concepts] or STORY_CONCEPTS
    chosen_concept = random.choice(avail)
    sys_p, usr_p = build_story_prompts(chosen_concept, used_titles, used_dialogues)

    # Tier 1: Groq Chat LLM Loop
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            candidate_models = get_valid_groq_chat_models(client)
            for model in candidate_models[:5]:
                try:
                    print(f"[STORY-ENGINE] Writing fresh 8-scene script via Groq ({model})...")
                    res = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                        response_format={"type": "json_object"},
                        max_tokens=850,
                        temperature=0.85
                    )
                    raw_content = res.choices[0].message.content.strip()
                    if raw_content.startswith("```"):
                        raw_content = raw_content.split("```")[1].lstrip("json").strip()
                    data = json.loads(raw_content)
                    if "scenes" in data and len(data["scenes"]) >= 6:
                        data["archetype_used"] = chosen_concept
                        print(f"✅ Fresh {len(data['scenes'])}-Scene Script Ready: {data.get('video_title')}")
                        return data
                except Exception as model_err:
                    print(f"⚠️ Model {model} skipped ({model_err}). Trying next chat model...")
                    time.sleep(2)
                    continue
        except Exception as e:
            print(f"⚠️ Groq client fallback ({e})...")

    # Tier 2: Pollinations Free OpenAI Text LLM
    try:
        print("[STORY-ENGINE] Calling secondary Pollinations OpenAI Text LLM...")
        resp = requests.post(
            "https://text.pollinations.ai/openai",
            json={
                "model": "openai",
                "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                "response_format": {"type": "json_object"},
                "temperature": 0.85
            },
            timeout=45
        )
        if resp.status_code == 200:
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            data = json.loads(raw)
            if "scenes" in data and len(data["scenes"]) >= 6:
                data["archetype_used"] = chosen_concept
                print(f"✅ Fresh {len(data['scenes'])}-Scene Script Ready via Secondary LLM: {data.get('video_title')}")
                return data
    except Exception as e:
        print(f"⚠️ Secondary LLM skipped ({e})...")

    # Tier 3: Multi-Plot Deduplicated Procedural Engine
    return build_procedural_unique_story(history)


def build_age_matched_character_desc(age_str, is_male, base_dna):
    """Ensures character proportions match their age while locking clear male vs female contrast."""
    digits = "".join(c for c in str(age_str) if c.isdigit())
    age = int(digits) if digits else 20

    if age <= 12:
        if is_male:
            return f"cute {age}yo 2D anime child boy with short male haircut ({base_dna})"
        return f"cute {age}yo 2D anime child girl with long hair ({base_dna})"
    elif age <= 18:
        if is_male:
            return f"tall {age}yo 2D anime high-school boy with masculine features and short male hair ({base_dna})"
        return f"petite {age}yo 2D anime high-school girl with feminine features and long flowing hair ({base_dna})"
    else:
        if is_male:
            return f"tall handsome {age}yo 2D anime young man with broad shoulders and short male haircut ({base_dna})"
        return f"slender beautiful {age}yo 2D anime young woman with feminine features and long flowing hair ({base_dna})"


def fetch_clean_manhwa_artwork(scene, male_dna, female_dna, story_seed, idx, total_scenes, output_path):
    """
    Restores the exact Makoto Shinkai / Korean Manhwa Waist-Up Two-Shot framing that made gXlmlO4comg look great:
    - Enforces EXACTLY 1 Boy on the LEFT and 1 Girl on the RIGHT facing each other in the lower two-thirds,
      with 30% clean scenic sky/ceiling headroom at the top for our bubbles and ages.
    """
    m_age = scene.get("male_age", "21")
    f_age = scene.get("female_age", "19")
    atmos = scene.get("lighting_and_atmosphere", "warm golden streetlamp glow and soft bokeh")
    pose = scene.get("scene_setting_and_pose", "standing close facing each other with romantic eye contact")

    boy_desc = build_age_matched_character_desc(m_age, True, male_dna)
    girl_desc = build_age_matched_character_desc(f_age, False, female_dna)

    prompt = (
        f"Vertical 9:16 Korean anime romance illustration, Makoto Shinkai webtoon style, vibrant luminous colors, clean 2D cel-shaded lineart. "
        f"Top 30 percent is clean scenic sky or ceiling headroom above characters' heads. "
        f"Lower two-thirds waist-up two-shot portrait of EXACTLY TWO people facing each other: "
        f"On the LEFT side stands ONE male ({boy_desc}); on the RIGHT side stands ONE female ({girl_desc}). "
        f"Action: {pose}. Atmosphere: {atmos}. "
        f"Front-facing chests, natural neck anatomy, strictly 1 boy and 1 girl, no text, no speech bubbles, no watermark."
    )
    encoded = urllib.parse.quote(prompt[:490])

    if idx > 0:
        time.sleep(10.0)

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
    ]

    print(f"[ARTWORK] Generating Waist-Up Two-Shot Scene {idx + 1}/{total_scenes} (Ages {m_age} & {f_age})...")

    for attempt in range(6):
        seed = story_seed + (idx * 317) + (attempt * 53)
        if attempt % 2 == 0:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1344&model=flux&seed={seed}&nologo=true"
        else:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&seed={seed}&nologo=true"

        headers = {"User-Agent": user_agents[attempt % len(user_agents)]}

        try:
            res = requests.get(url, headers=headers, timeout=85)
            ctype = res.headers.get("Content-Type", "")
            if res.status_code == 200 and "image" in ctype and is_valid_artwork(res.content):
                clean_watermark_and_fit_9_16(res.content, output_path)
                print(f"✅ Clean Scene {idx + 1}/{total_scenes} saved: {output_path}")
                return True

            cooldown = 20 + (attempt * 5)
            print(f"   ⏳ Pollinations rate-limit refill (status {res.status_code}). Waiting {cooldown}s...")
            time.sleep(cooldown)
        except Exception as e:
            cooldown = 15 + (attempt * 4)
            print(f"   ⏳ Network retry ({e}). Waiting {cooldown}s...")
            time.sleep(cooldown)

    return False


def probe_audio_duration_ffprobe(file_path):
    """Checks exact duration of an audio file via ffprobe."""
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 70000:
        return 0.0
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ], timeout=10).decode("utf-8").strip()
        return float(out)
    except Exception:
        return 0.0


def synthesize_indila_continuous_75s_orchestra(output_mp3, duration_sec=75):
    """Emergency zero-crash 75s orchestral D-minor waltz fallback if all external networks are down."""
    raw_wav = "workspace/indila_orchestral_75s.wav"
    sr = 44100
    total_samples = int(sr * duration_sec)

    bars = [
        (146.83, [293.66, 349.23, 440.00], [440.00, 587.33, 523.25]),
        (116.54, [233.08, 293.66, 349.23], [466.16, 440.00, 392.00]),
        (98.00,  [196.00, 293.66, 349.23], [349.23, 440.00, 392.00]),
        (110.00, [220.00, 277.18, 329.63], [349.23, 329.63, 293.66]),
        (146.83, [293.66, 440.00, 587.33], [587.33, 659.25, 698.46]),
        (116.54, [233.08, 349.23, 466.16], [659.25, 587.33, 523.25]),
        (98.00,  [196.00, 293.66, 440.00], [587.33, 523.25, 466.16]),
        (110.00, [220.00, 329.63, 440.00], [523.25, 440.00, 440.00]),
    ]
    beat_sec = 0.64
    bar_sec = beat_sec * 3.0

    with wave.open(raw_wav, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)

        for i in range(total_samples):
            t = i / float(sr)
            bar_idx = int(t / bar_sec) % len(bars)
            in_bar_t = t % bar_sec
            beat_idx = min(2, max(0, int(in_bar_t / beat_sec)))
            note_t = max(0.0, in_bar_t - beat_idx * beat_sec)

            bass_f, arp_list, mel_list = bars[bar_idx]
            arp_f = arp_list[beat_idx]
            mel_f = mel_list[beat_idx]

            bass_gain = 0.18 if t < 12.0 else min(0.36, 0.18 + (t - 12.0) * 0.03)
            lead_gain = 0.20 if t < 11.5 else min(0.54, 0.20 + (t - 11.5) * 0.04)
            octave_shimmer = 0.0 if t < 23.0 else min(0.28, (t - 23.0) * 0.03)

            bass_env = math.exp(-in_bar_t * 1.1) * min(1.0, in_bar_t * 35.0)
            bass_sig = bass_gain * (
                math.sin(2 * math.pi * bass_f * t) + 0.35 * math.sin(4 * math.pi * bass_f * t)
            ) * bass_env

            arp_env = math.exp(-note_t * 2.7) * min(1.0, note_t * 50.0)
            arp_sig = 0.30 * (
                math.sin(2 * math.pi * arp_f * t) + 0.25 * math.sin(4 * math.pi * arp_f * t)
            ) * arp_env

            vib = 1.0 + 0.0035 * math.sin(2 * math.pi * 5.0 * t)
            mel_env = math.exp(-note_t * 1.25) * min(1.0, note_t * 18.0)
            lead_sig = (
                lead_gain * math.sin(2 * math.pi * mel_f * vib * t)
                + (lead_gain * 0.45) * math.sin(4 * math.pi * mel_f * vib * t)
                + octave_shimmer * math.sin(2 * math.pi * (mel_f * 2.0) * vib * t)
            ) * mel_env

            val = max(-1.0, min(1.0, (bass_sig + arp_sig + lead_sig) * 0.65))
            wf.writeframesraw(struct.pack("<h", int(val * 32767)))

    subprocess.run([
        "ffmpeg", "-y", "-i", raw_wav,
        "-af", "aecho=0.8:0.90:70|140:0.40|0.25,lowpass=f=3600,loudnorm=I=-14:TP=-1.5:LRA=11",
        "-b:a", "192k", output_mp3
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3


def get_locked_target_song(required_duration_sec):
    """
    1. Checks cached 'assets/indila_love_story_ethereal_inst_v7.mp3' via ffprobe first (instant, zero network calls).
    2. Queries SoundCloud ('scsearch:') first (never blocked on GitHub Actions IPs).
    3. Queries Piped/Invidious stream mirrors for 1NBnN0IAljQ (starting at 00:20).
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    cached_dur = probe_audio_duration_ffprobe(LOCKED_SONG_PATH)
    if cached_dur >= required_duration_sec:
        print(f"✅ Using cached vocal-free Ethereal Instrumental ({cached_dur:.1f}s): {LOCKED_SONG_PATH}")
        return LOCKED_SONG_PATH

    slice_len = max(MASTER_AUDIO_DURATION, int(required_duration_sec) + 6)
    raw_audio = "workspace/raw_target_song.mp3"

    sc_queries = [
        ("scsearch1:Love Story by Indila Ethereal Instrumental Full Version", 20),
        ("scsearch1:Indila Love Story Extended Instrumental Slowed Reverb", 20),
        ("scsearch1:Indila Love Story Piano Instrumental Slowed Reverb", 0),
        ("scsearch1:Love Story Indila Slowed Reverb Instrumental", 20)
    ]
    for sc_query, start_offset in sc_queries:
        print(f"[AUDIO] Fetching Indila Instrumental via SoundCloud: '{sc_query}' (from 00:{start_offset:02d})...")
        try:
            if os.path.exists(raw_audio):
                os.remove(raw_audio)
            cmd = [
                sys.executable, "-m", "yt_dlp",
                sc_query,
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "--no-playlist",
                "--no-warnings",
                "--quiet",
                "--output", raw_audio
            ]
            subprocess.run(cmd, timeout=60, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(raw_audio) and os.path.getsize(raw_audio) > 90000:
                subprocess.run([
                    "ffmpeg", "-y",
                    "-ss", str(start_offset),
                    "-t", str(slice_len),
                    "-i", raw_audio,
                    "-af", "stereotools=mlev=0.02,aecho=0.8:0.86:50:0.22,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-b:a", "192k",
                    LOCKED_SONG_PATH
                ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if probe_audio_duration_ffprobe(LOCKED_SONG_PATH) >= required_duration_sec:
                    print(f"🎉 Locked Vocal-Free Indila Ethereal Instrumental ({slice_len}s) -> {LOCKED_SONG_PATH}")
                    return LOCKED_SONG_PATH
        except Exception:
            continue

    for video_id, start_sec in [("1NBnN0IAljQ", 20), ("e4KMz7PdAmE", 0)]:
        mirror_apis = [
            f"https://pipedapi.kavin.rocks/streams/{video_id}",
            f"https://pipedapi.tokhmi.xyz/streams/{video_id}",
            f"https://inv.nadeko.net/api/v1/videos/{video_id}"
        ]
        for api_url in mirror_apis:
            try:
                r = requests.get(api_url, timeout=15)
                if r.status_code == 200:
                    j = r.json()
                    streams = j.get("audioStreams") or j.get("adaptiveFormats") or []
                    for st in streams:
                        s_url = st.get("url")
                        if s_url and ("audio" in (st.get("mimeType") or st.get("type") or "audio")):
                            audio_res = requests.get(s_url, timeout=40)
                            if audio_res.status_code == 200 and len(audio_res.content) > 80000:
                                with open(raw_audio, "wb") as f:
                                    f.write(audio_res.content)
                                subprocess.run([
                                    "ffmpeg", "-y",
                                    "-ss", str(start_sec),
                                    "-t", str(slice_len),
                                    "-i", raw_audio,
                                    "-af", "stereotools=mlev=0.02,aecho=0.8:0.86:50:0.22,loudnorm=I=-14:TP=-1.5:LRA=11",
                                    "-b:a", "192k",
                                    LOCKED_SONG_PATH
                                ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                if probe_audio_duration_ffprobe(LOCKED_SONG_PATH) >= required_duration_sec:
                                    print(f"🎉 Locked Indila Instrumental via stream mirror -> {LOCKED_SONG_PATH}")
                                    return LOCKED_SONG_PATH
            except Exception:
                continue

    print(f"[AUDIO-FALLBACK] Rendering {slice_len}s Continuous Orchestral Indila Waltz...")
    return synthesize_indila_continuous_75s_orchestra(LOCKED_SONG_PATH, duration_sec=slice_len)


def build_pipeline():
    print("=== STARTING RESTORED gXlmlO4comg VISUAL ENGINE (COMPLETE 8-SCENE STORY) ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    history = load_history()
    story_data = generate_fresh_story(history)

    history["used_titles"].append(story_data.get("video_title", ""))
    history.setdefault("used_archetypes", []).append(story_data.get("archetype_used", ""))
    for sc in story_data.get("scenes", []):
        if sc.get("male_line"):
            history.setdefault("used_dialogues", []).append(sc["male_line"])
        if sc.get("female_line"):
            history.setdefault("used_dialogues", []).append(sc["female_line"])
    history["total_videos"] = history.get("total_videos", 0) + 1
    save_history(history)

    with open("workspace/video_metadata.json", "w", encoding="utf-8") as f:
        json.dump(story_data, f, indent=2, ensure_ascii=False)

    male_dna = story_data.get("male_dna", "handsome 2D anime boy with jet-black short hair and warm amber eyes")
    female_dna = story_data.get("female_dna", "beautiful 2D anime girl with long chestnut hair and bright eyes")
    scenes = story_data.get("scenes", [])[:8]
    total_scenes = len(scenes)
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.3  # 8 scenes * 5.3s = 42.4s complete story
    reply_pop_delay = 1.8
    clips = []

    for idx, sc in enumerate(scenes):
        bg_path = f"workspace/clean_art_{idx}.jpg"
        if not fetch_clean_manhwa_artwork(sc, male_dna, female_dna, story_seed, idx, total_scenes, bg_path):
            print(f"⚠️ Scene {idx + 1} skipped after retries.")
            continue

        anchors = detect_character_anchors(bg_path)
        base_clip = ImageClip(bg_path).set_duration(scene_duration).resize((1080, 1920))
        layers = [base_clip]

        # 1. Fixed Top-Corner Glowing Ages (Blue Top-Left, Pink Top-Right — never floating in blank space)
        age_png = f"workspace/ages_{idx}.png"
        render_floating_manhwa_ages(sc.get("male_age", "21"), sc.get("female_age", "19"), age_png)
        age_clip = ImageClip(age_png).set_position(("center", 12)).set_duration(scene_duration)
        layers.append(age_clip)

        # 2. Left Character Bubble (Boy, appears at 0.0s)
        m_line = sc.get("male_line", "")
        m_type = sc.get("male_bubble_type", "speech").lower()
        if m_line:
            m_png = f"workspace/webtoon_b_left_{idx}.png"
            render_webtoon_bubble_layer(
                text=m_line,
                bubble_type=m_type,
                side="left",
                head_top=anchors["boy_head_top"],
                mouth_pt=anchors["boy_mouth"],
                output_path=m_png
            )
            m_clip = ImageClip(m_png).set_position((0, 0)).set_start(0.0).set_duration(scene_duration)
            layers.append(m_clip)

        # 3. Right Character Bubble (Girl, pops in at 1.8s)
        f_line = sc.get("female_line", "")
        f_type = sc.get("female_bubble_type", "thought").lower()
        if f_line:
            f_png = f"workspace/webtoon_b_right_{idx}.png"
            render_webtoon_bubble_layer(
                text=f_line,
                bubble_type=f_type,
                side="right",
                head_top=anchors["girl_head_top"],
                mouth_pt=anchors["girl_mouth"],
                output_path=f_png
            )
            f_clip = (
                ImageClip(f_png)
                .set_position((0, 0))
                .set_start(reply_pop_delay)
                .set_duration(scene_duration - reply_pop_delay)
            )
            layers.append(f_clip)

        scene_comp = CompositeVideoClip(layers, size=(1080, 1920)).set_duration(scene_duration)
        scene_comp = scene_comp.resize(lambda t: 1.0 + (0.015 * t))
        clips.append(scene_comp)

    if len(clips) < 6:
        raise RuntimeError(f"❌ Pipeline aborted: Only {len(clips)} scenes rendered (minimum 6 required).")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration
    print(f"[TIMELINE] Assembled complete {len(clips)}-scene story ({total_dur:.1f} seconds total).")

    audio_path = get_locked_target_song(required_duration_sec=total_dur)
    if audio_path and os.path.exists(audio_path):
        audio_clip = AudioFileClip(audio_path)
        audio_clip = audio_clip.subclip(0, min(total_dur, audio_clip.duration))
        audio_clip = audio_clip.audio_fadein(0.8).audio_fadeout(1.8).volumex(0.95)
        final_video = final_video.set_audio(audio_clip)

    output_mp4 = "videos/final_manhwa_short.mp4"
    print(f"[RENDER] Exporting {total_dur:.1f}s 9:16 Master MP4...")
    final_video.write_videofile(
        output_mp4,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"]
    )
    print(f"🎉 COMPLETE {total_dur:.1f}s MANHWA SHORT READY: {output_mp4}")


if __name__ == "__main__":
    build_pipeline()
