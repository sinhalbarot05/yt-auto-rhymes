import os
import sys
import io
import json
import time
import math
import random
import textwrap
import subprocess
import urllib.parse
import requests

# Auto-install required packages
for pkg in ("yt-dlp", "pytubefix", "numpy"):
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
    concatenate_videoclips
)

HISTORY_FILE = "story_history.json"
# New v6 path so old synthetic piano MP3s are purged and replaced with the real song
LOCKED_SONG_PATH = "assets/indila_love_story_real_v6.mp3"
LOCKED_SONG_TITLE = "Love Story - Indila (Slowed + Reverb)"

# Exact YouTube Audio Sources requested:
# 1) https://youtu.be/e4KMz7PdAmE -> starts right at 00:00
# 2) https://youtu.be/1NBnN0IAljQ -> skips first 20s, starts at 00:20
PRIMARY_YT_URL = "https://youtu.be/e4KMz7PdAmE"
PRIMARY_START_SEC = 0

SECONDARY_YT_URL = "https://youtu.be/1NBnN0IAljQ"
SECONDARY_START_SEC = 20

MASTER_AUDIO_DURATION = 75  # Continuous 75s forward cut (zero looping)

# Complete, emotional multi-act Korean Manhwa romance storylines
STORY_CONCEPTS = [
    "Uncherished to Cherished by True Future Love: For 3 years her cold fiancé ignored her birthday and left her waiting in the rain; when she walks away, his protective older brother steps in with an umbrella and cherishes her like a queen while her ex begs in regret",
    "Childhood Friends to Soulmates: From sharing strawberries across next-door balconies as kids, to walking home under cherry blossoms in high school, to a jealous rain confession, to a tearful rooftop marriage proposal",
    "Intense Jealousy in Secret Love: The cold student council president claims he only sees her as a junior, until a handsome transfer student makes her laugh—shattering his calm mask as he pulls her aside at sunset to confess",
    "Contract Marriage to Real Obsession: Married on paper with a strict rule to never fall in love; when she prepares to leave thinking he loves someone else, he tears up the contract in the rain and begs her to stay",
    "Academic Rivals to Midnight Confidants: Competing for #1 rank every semester while bickering daily, until he discovers her crying on the library balcony at dusk and stays beside her every evening",
    "The Forgotten Childhood Promise: Separated at age 10 when she moved away, she doesn't recognize the popular university senior—until she spots the braided red bracelet she made 10 years ago still on his wrist",
    "Ignored by Crush, Treasured by the Quiet Protector: She always brought lunch for the popular captain who took her for granted, while the quiet art prodigy secretly filled his sketchbook with her smile before stepping forward",
    "7 AM Subway Strangers to Soulmates: Standing in the same train car every morning in silence for a year until a sudden storm stops the train and he finally pulls her close to protect her"
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
    Preserves 100% of Pollinations Flux's natural, vibrant Korean Manhwa beauty (ZERO artificial color filters!).
    1. Trims 3.8% off the bottom edge to cleanly remove any 'pollinations.ai' corner watermark.
    2. Trims 1.9% off the left and right edges to preserve the exact 9:16 aspect ratio with ZERO stretching.
    3. Resizes cleanly to 1080x1920 with LANCZOS interpolation.
    """
    with Image.open(io.BytesIO(raw_bytes)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size

        # Trim bottom 3.8% watermark strip and proportional side margins
        x0 = int(w * 0.019)
        x1 = int(w * 0.981)
        y0 = int(h * 0.005)
        y1 = int(h * 0.962)

        cropped = rgb.crop((x0, y0, x1, y1))
        cw, ch = cropped.size

        target_aspect = 1080.0 / 1920.0  # 0.5625
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

        final_img = cropped.resize((1080, 1920), Image.LANCZOS)
        final_img.save(output_path, "JPEG", quality=96)

    return output_path


def is_valid_colorful_artwork(raw_bytes):
    """Verifies the downloaded bytes form a valid, non-blank, colorful image."""
    if not raw_bytes or len(raw_bytes) < 15000:
        return False
    try:
        with Image.open(io.BytesIO(raw_bytes)) as im:
            arr = np.array(im.convert("RGB"), dtype=np.float32)
            if arr.shape[0] < 500 or arr.shape[1] < 400:
                return False
            # Reject blank/solid frames
            if np.std(arr) < 20.0:
                return False
        return True
    except Exception:
        return False


def detect_character_anchors(img_path):
    """
    Computer-Vision Head & Mouth Locator:
    Detects the Boy (left half) and Girl (right half) head-tops and mouth coordinates
    so bubbles sit cleanly above their hair without covering their eyes.
    """
    default_anchors = {
        "boy_head_top": (280, 430),
        "boy_mouth": (335, 640),
        "girl_head_top": (800, 460),
        "girl_mouth": (735, 670)
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
        y_min, y_max = 320, 1020

        def find_side_face(x_start, x_end, is_left):
            sub_mask = skin_mask[y_min:y_max, x_start:x_end]
            ys, xs = np.where(sub_mask)
            if len(ys) < 380:
                return None

            face_cx = int(x_start + np.median(xs))
            face_top_y = int(y_min + np.percentile(ys, 12))
            face_bot_y = int(y_min + np.percentile(ys, 88))
            face_h = max(130, min(300, face_bot_y - face_top_y))

            head_top_y = max(320, face_top_y - int(face_h * 0.45))
            inward_shift = int(face_h * 0.16) if is_left else -int(face_h * 0.16)
            mouth_x = max(120, min(960, face_cx + inward_shift))
            mouth_y = min(980, face_top_y + int(face_h * 0.68))
            return (face_cx, head_top_y), (mouth_x, mouth_y)

        left_res = find_side_face(50, 530, is_left=True)
        right_res = find_side_face(550, 1030, is_left=False)

        if left_res:
            default_anchors["boy_head_top"], default_anchors["boy_mouth"] = left_res
        if right_res:
            default_anchors["girl_head_top"], default_anchors["girl_mouth"] = right_res
    except Exception:
        pass

    return default_anchors


def quad_bezier_points(p0, p1, p2, steps=32):
    """Generates smooth points along a Quadratic Bezier curve from p0 to p2 via control point p1."""
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
    Renders professional comic bubbles at 2x supersampled resolution (2160x3840):
    - Positioned in the upper headroom band (cy = 195..255) so faces and eyes are NEVER covered.
    - 'speech'  -> Smooth horizontal egg + solid curved Bezier tail pointing toward speaker.
    - 'thought' -> Fluffy scalloped cloud + 4 detached shrinking circular thought bubbles (Garfield style).
    - 'whisper' -> Smooth horizontal egg with dashed border for soft/shy confessions.
    - 'shout'   -> Spiky comic starburst for intense jealousy or dramatic moments.
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

    # Keep bubble bodies in the upper sky/headroom zone (y: 195..255) so they never cover faces!
    if side == "left":
        cx = max(rx + 26 * scale, min(515 * scale - rx, hx - 10 * scale))
        cy = max(ry + 110 * scale, min(hy - ry - 25 * scale, 215 * scale))
    else:
        cx = max(565 * scale + rx, min(W - rx - 26 * scale, hx + 10 * scale))
        cy = max(ry + 135 * scale, min(hy - ry - 20 * scale, 250 * scale))

    raw_tx = mx + (-18 * scale if side == "left" else 18 * scale)
    tx = max(cx - rx + 20 * scale, min(cx + rx - 20 * scale, raw_tx))
    if side == "left":
        tx = max(tx, cx + int(rx * 0.16))
    else:
        tx = min(tx, cx - int(rx * 0.16))

    tail_bottom_limit = cy + ry + 120 * scale
    ty = max(cy + ry + 64 * scale, min(tail_bottom_limit, my - 60 * scale))

    mask = Image.new("L", (W, H), 0)
    m_draw = ImageDraw.Draw(mask)

    if b_type == "thought":
        # Scalloped Cloud Body + 4 Detached Shrinking Circular Bubbles (Garfield Style)
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

    fill_layer = Image.new("RGBA", (W, H), (253, 253, 254, 255))
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
            c_draw.ellipse([dx - r_gap, dy - r_gap, dx + r_gap, dy + r_gap], fill=(253, 253, 254, 255))

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


def render_floating_manhwa_ages(male_age, female_age, output_path):
    """Renders sleek floating Manhwa age numbers in the top corners."""
    scale = 2
    W, H = 1080 * scale, 170 * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_age = get_comic_font(60 * scale)

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
        draw_stylized_age(90 * scale, 70 * scale, male_age, (75, 180, 255), (30, 120, 255))
    if female_age:
        draw_stylized_age(990 * scale, 70 * scale, female_age, (255, 85, 135), (255, 40, 100))

    img.resize((1080, 170), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def get_valid_groq_chat_models(client):
    """Selects verified text-chat LLMs on Groq and blocks TTS/audio/guard models."""
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
        "qwen-qwq-32b",
        "deepseek-r1-distill-llama-70b",
        "gemma2-9b-it",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768"
    ]

    ordered = [p for p in preferred_order if p in chat_models]
    for m in chat_models:
        if m not in ordered:
            ordered.append(m)

    return ordered if ordered else ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def build_story_prompts(concept, used_titles, used_dialogues):
    entropy = f"{int(time.time())}-{random.randint(10000, 99999)}"
    system_prompt = (
        "You are an elite Korean Romance Manhwa & Webtoon scriptwriter. "
        "You write complete, emotionally captivating 8-scene vertical romance Shorts (~43 seconds total) "
        "with a clear beginning, emotional turning point, and deeply satisfying resolution. "
        "You use comic bubble types ('speech', 'thought', 'whisper', 'shout') like a master webtoon artist. "
        "Output strictly valid JSON."
    )
    user_prompt = f"""Write a brand-new, complete 8-scene vertical Korean Manhwa romance Short script.
Run Seed: {entropy}
Story Concept: "{concept}"
Previously Used Titles (NEVER REPEAT): {json.dumps(used_titles[-10:])}
Previously Used Lines (NEVER REPEAT): {json.dumps(used_dialogues[-15:])}

COMPLETE 8-SCENE STORY ARC (~43 SECONDS TOTAL):
- Scenes 1 & 2 (Act I - The Setup): Establish the male and female lead, their ages, and the emotional hook.
- Scenes 3 & 4 (Act II - Heartbreak / Tension): Jealousy, unspoken feelings, or being left in the rain.
- Scenes 5 & 6 (Act III - The Turning Point): The dramatic umbrella rescue, protective confrontation, or sudden closeness.
- Scenes 7 & 8 (Act IV - Confession & Payoff): Raw emotional confession and unforgettable romantic resolution (proposal, embrace, or kiss).

COMIC WRITER BUBBLE RULES:
- Choose the exact right bubble type for each character in every scene:
  * "speech"  -> Spoken out loud (solid curved tail).
  * "thought" -> Secret inner thoughts or silent realization (cloud with detached circular thought dots).
  * "whisper" -> Shy, trembling, or soft confession (dashed border).
  * "shout"   -> Jealousy, shock, or urgent protective call (spiky burst).
- Keep "male_line" and "female_line" between 4 and 8 natural English words.

Return ONLY valid JSON matching this exact schema:
{{
  "trope": "Short catchy story theme",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "video_title": "Emotional viral English title with emojis #Shorts #manhwa #lovestory",
  "male_dna": "handsome Korean manhwa boy with jet-black tousled hair and warm amber eyes",
  "female_dna": "beautiful Korean manhwa girl with long wavy chestnut-brown hair and bright eyes",
  "scenes": [
    {{
      "male_age": "19",
      "female_age": "18",
      "male_bubble_type": "speech",
      "male_line": "Why are you standing in the rain?",
      "female_bubble_type": "thought",
      "female_line": "He actually came looking for me...",
      "lighting_and_atmosphere": "soft pastel rain reflections, warm streetlamp bokeh, romantic webtoon glow",
      "scene_setting_and_pose": "standing side-by-side under a transparent umbrella on an evening street with cherry trees above"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_complete_fallback_story(history):
    """Complete 8-scene multi-act Korean Manhwa romance fallback generator."""
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    m_hair = random.choice(["silver-white tousled", "jet-black", "ash-brown", "dark navy"])
    f_hair = random.choice(["long wavy chestnut-brown", "silky raven-black", "soft caramel", "dark cherry"])

    story_templates = [
        {
            "trope": f"Uncherished to Treasured by True Love #{run_id}",
            "video_title": f"He Left Her In The Rain… So His Brother Stepped In 💔☔ #{run_id} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "21", "female_age": "19", "male_bubble_type": "speech", "male_line": "Wait outside. I'm busy right now.", "female_bubble_type": "thought", "female_line": "He forgot my birthday again...", "lighting_and_atmosphere": "soft blue evening twilight outside a glowing cafe", "scene_setting_and_pose": "boy in dark jacket looking coldly at cute girl holding a small birthday cake box"},
                {"male_age": "23", "female_age": "19", "male_bubble_type": "thought", "male_line": "How can my brother ignore her tears?", "female_bubble_type": "whisper", "female_line": "It's fine... I'm used to waiting.", "lighting_and_atmosphere": "warm streetlamp bokeh as gentle rain begins to fall", "scene_setting_and_pose": "tall handsome older brother in a tailored coat approaching the shivering girl"},
                {"male_age": "23", "female_age": "19", "male_bubble_type": "speech", "male_line": "Take my umbrella. Come with me.", "female_bubble_type": "thought", "female_line": "Why is his gaze so warm?", "lighting_and_atmosphere": "cinematic rain droplets and soft pastel neon reflections", "scene_setting_and_pose": "standing side-by-side under a large umbrella in the rain, looking into each other's eyes"},
                {"male_age": "23", "female_age": "20", "male_bubble_type": "speech", "male_line": "I bought every cake you missed.", "female_bubble_type": "thought", "female_line": "No one ever treasured me like this...", "lighting_and_atmosphere": "warm candlelit penthouse dining room with city skyline view", "scene_setting_and_pose": "boy smiling gently over birthday candles while girl covers her blushing cheeks"},
                {"male_age": "24", "female_age": "20", "male_bubble_type": "shout", "male_line": "Don't touch her! You lost your chance!", "female_bubble_type": "thought", "female_line": "He stepped right in front of me...", "lighting_and_atmosphere": "dramatic crystal chandelier lighting in a grand hall", "scene_setting_and_pose": "protective older brother shielding the girl behind his shoulder"},
                {"male_age": "24", "female_age": "20", "male_bubble_type": "whisper", "male_line": "I've loved you in silence for years.", "female_bubble_type": "speech", "female_line": "Stay with me. Never let go.", "lighting_and_atmosphere": "starry night balcony with floating golden bokeh lights", "scene_setting_and_pose": "standing close on a night balcony, boy gently cupping the blushing girl's cheek"},
                {"male_age": "25", "female_age": "21", "male_bubble_type": "speech", "male_line": "Marry me and be my whole world.", "female_bubble_type": "speech", "female_line": "Yes! Only you, forever.", "lighting_and_atmosphere": "dreamy pink sunset garden with falling cherry blossom petals", "scene_setting_and_pose": "handsome man holding a velvet ring box under cherry blossoms, girl smiling with happy tears"},
                {"male_age": "26", "female_age": "22", "male_bubble_type": "thought", "male_line": "I'll protect her smile for life.", "female_bubble_type": "thought", "female_line": "Losing the wrong one led me to you.", "lighting_and_atmosphere": "soft pastel sunset glow and floating cherry blossom petals", "scene_setting_and_pose": "couple holding hands and embracing tenderly under blooming cherry trees"}
            ]
        },
        {
            "trope": f"Childhood Friends to Forever #{run_id}",
            "video_title": f"From Next-Door Neighbours To Forever 🥺🌸 #{run_id} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "10", "female_age": "9", "male_bubble_type": "speech", "male_line": "Stop crying! I saved you strawberries.", "female_bubble_type": "thought", "female_line": "He always knows how to make me smile...", "lighting_and_atmosphere": "bright sunny summer afternoon with soft green leaves", "scene_setting_and_pose": "two cute childhood kids smiling across adjacent bedroom balconies"},
                {"male_age": "15", "female_age": "14", "male_bubble_type": "speech", "male_line": "Walk on the inside of the street.", "female_bubble_type": "thought", "female_line": "Since when did he get so tall?", "lighting_and_atmosphere": "warm afternoon sunlight with floating cherry blossom petals", "scene_setting_and_pose": "two middle school teens in uniforms walking side-by-side under cherry trees"},
                {"male_age": "17", "female_age": "16", "male_bubble_type": "thought", "male_line": "Why is that guy talking to her?", "female_bubble_type": "speech", "female_line": "Wait, why are you holding my wrist?", "lighting_and_atmosphere": "sunlit high school hallway with pastel window light", "scene_setting_and_pose": "jealous handsome high school boy gently holding blushing girl's wrist"},
                {"male_age": "18", "female_age": "17", "male_bubble_type": "speech", "male_line": "Take my coat. Your hands are freezing.", "female_bubble_type": "thought", "female_line": "His coat feels so warm and safe...", "lighting_and_atmosphere": "soft white snow falling under glowing streetlamps", "scene_setting_and_pose": "boy draping his winter coat over the blushing girl's shoulders at a snowy bus stop"},
                {"male_age": "19", "female_age": "18", "male_bubble_type": "shout", "male_line": "Don't date anyone else! Look at me!", "female_bubble_type": "thought", "female_line": "His heart is beating so fast...", "lighting_and_atmosphere": "evening rain with glowing pastel reflections", "scene_setting_and_pose": "sheltering together under an umbrella in the rain, intense romantic eye contact"},
                {"male_age": "19", "female_age": "18", "male_bubble_type": "whisper", "male_line": "I've loved you since we were kids.", "female_bubble_type": "whisper", "female_line": "I loved you from the very start...", "lighting_and_atmosphere": "starry night rooftop with dreamy blue and pink bokeh", "scene_setting_and_pose": "standing close on a starry rooftop, boy gently resting his forehead against hers"},
                {"male_age": "22", "female_age": "21", "male_bubble_type": "speech", "male_line": "From next-door neighbours to my wife?", "female_bubble_type": "speech", "female_line": "Yes! A thousand times yes!", "lighting_and_atmosphere": "magical sunset rooftop with glowing fairy lights", "scene_setting_and_pose": "handsome man in suit proposing with a diamond ring box, girl smiling with happy tears"},
                {"male_age": "23", "female_age": "22", "male_bubble_type": "thought", "male_line": "Forever starts right now with her.", "female_bubble_type": "thought", "female_line": "My childhood friend is my whole world.", "lighting_and_atmosphere": "sparkling night fireworks and floating petals", "scene_setting_and_pose": "couple embracing happily under colorful fireworks in the night sky"}
            ]
        }
    ]

    picked = random.choice(story_templates)
    return {
        "trope": picked["trope"],
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": picked["video_title"],
        "male_dna": f"handsome Korean manhwa boy with {m_hair} hair and warm amber eyes",
        "female_dna": f"beautiful Korean manhwa girl with {f_hair} hair and bright expressive eyes",
        "scenes": picked["scenes"]
    }


def generate_fresh_story(history):
    used_concepts = history.get("used_archetypes", [])[-6:]
    used_titles = history.get("used_titles", [])
    used_dialogues = history.get("used_dialogues", [])

    avail = [c for c in STORY_CONCEPTS if c not in used_concepts] or STORY_CONCEPTS
    chosen_concept = random.choice(avail)
    sys_p, usr_p = build_story_prompts(chosen_concept, used_titles, used_dialogues)

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            candidate_models = get_valid_groq_chat_models(client)
            for model in candidate_models[:4]:
                try:
                    print(f"[STORY-ENGINE] Writing complete 8-scene script via Groq ({model})...")
                    res = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                        response_format={"type": "json_object"},
                        temperature=0.85
                    )
                    data = json.loads(res.choices[0].message.content.strip())
                    if "scenes" in data and len(data["scenes"]) >= 7:
                        data["archetype_used"] = chosen_concept
                        print(f"✅ Complete {len(data['scenes'])}-Scene Script Ready: {data.get('video_title')}")
                        return data
                except Exception as model_err:
                    print(f"⚠️ Model {model} skipped ({model_err}). Trying next chat model...")
                    continue
        except Exception as e:
            print(f"⚠️ Groq client fallback ({e})...")

    try:
        print("[STORY-ENGINE] Trying secondary Pollinations OpenAI Text LLM...")
        resp = requests.post(
            "https://text.pollinations.ai/openai",
            json={
                "model": "openai",
                "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                "response_format": {"type": "json_object"},
                "temperature": 0.85
            },
            timeout=50
        )
        if resp.status_code == 200:
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            data = json.loads(raw)
            if "scenes" in data and len(data["scenes"]) >= 7:
                data["archetype_used"] = chosen_concept
                print(f"✅ Complete {len(data['scenes'])}-Scene Script Ready via Secondary LLM!")
                return data
    except Exception as e:
        print(f"⚠️ Secondary LLM skipped ({e})...")

    return generate_complete_fallback_story(history)


def build_age_matched_manhwa_character(age_str, is_male, base_dna):
    """
    Ensures the character's visual age matches the numeric age badge while keeping
    the gorgeous Korean Manhwa / Webtoon aesthetic.
    """
    digits = "".join(c for c in str(age_str) if c.isdigit())
    age = int(digits) if digits else 19

    if age <= 11:
        role = f"cute {age}-year-old child boy with small kid proportions" if is_male else f"cute {age}-year-old child girl with small kid proportions"
        return f"{role} ({base_dna})"
    elif age <= 15:
        role = f"{age}-year-old middle-school teen boy in uniform" if is_male else f"{age}-year-old middle-school teen girl in uniform"
        return f"{role} ({base_dna})"
    elif age <= 18:
        role = f"handsome {age}-year-old high-school boy in blazer uniform" if is_male else f"cute {age}-year-old high-school girl in cardigan uniform"
        return f"{role} ({base_dna})"
    else:
        role = f"handsome {age}-year-old young man in stylish jacket" if is_male else f"beautiful {age}-year-old young woman in stylish outfit"
        return f"{role} ({base_dna})"


def fetch_pollinations_manhwa_artwork(scene, male_dna, female_dna, story_seed, idx, total_scenes, output_path):
    """
    100% Pure Pollinations Korean Manhwa / Webtoon Artwork Generator (Zero Hugging Face, Zero Filters):
    - Uses the exact vibrant Korean Manhwa / Makoto Shinkai webtoon style that made the 2nd video look beautiful.
    - Respects Pollinations' token-bucket rate limit with smart cooldowns so all 8 scenes succeed natively.
    """
    api_key = os.getenv("POLLINATIONS_API_KEY")
    m_age = scene.get("male_age", "19")
    f_age = scene.get("female_age", "18")
    atmos = scene.get("lighting_and_atmosphere", "soft pastel sunset lighting and glowing cherry blossom petals")
    pose = scene.get("scene_setting_and_pose", "standing side-by-side looking warmly into each other's eyes")

    male_desc = build_age_matched_manhwa_character(m_age, True, male_dna)
    female_desc = build_age_matched_manhwa_character(f_age, False, female_dna)

    prompt = (
        f"Masterpiece Korean romance manhwa webtoon illustration, Makoto Shinkai anime aesthetic, "
        f"vibrant luminous colors, clean detailed lineart, soft romantic lighting. "
        f"Wide composition with clean sky or ceiling headroom in the top 25 percent above their heads: "
        f"On the left is {male_desc}; on the right is {female_desc}. "
        f"Scene: {pose}, {atmos}. "
        f"Natural front-facing posture, expressive eyes, strictly no text, no speech bubbles, no numbers, no watermark."
    )
    encoded = urllib.parse.quote(prompt)

    # Pace requests between scenes so Pollinations' IP burst limiter stays green
    if idx > 0:
        time.sleep(9.0)

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
    ]

    print(f"[POLLINATIONS-ART] Generating Scene {idx + 1}/{total_scenes} (Ages {m_age} & {f_age})...")

    for attempt in range(7):
        seed = story_seed + (idx * 317) + (attempt * 43)
        # Rotate between exact 9:16 Pollinations Flux endpoints
        if attempt % 3 == 0:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1344&model=flux&seed={seed}&nologo=true"
        elif attempt % 3 == 1:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&seed={seed}&nologo=true"
        else:
            url = f"https://gen.pollinations.ai/image/{encoded}?width=768&height=1344&model=flux&seed={seed}&nologo=true"
            if api_key and attempt == 2:
                url += f"&key={api_key}"

        headers = {"User-Agent": user_agents[attempt % len(user_agents)]}

        try:
            res = requests.get(url, headers=headers, timeout=85)
            ctype = res.headers.get("Content-Type", "")
            if res.status_code == 200 and "image" in ctype and is_valid_colorful_artwork(res.content):
                clean_watermark_and_fit_9_16(res.content, output_path)
                print(f"✅ Scene {idx + 1}/{total_scenes} saved in pure Pollinations Manhwa quality: {output_path}")
                return True
            else:
                # Token-bucket refill wait (15s-24s) so the next request succeeds cleanly
                cooldown = 15 + (attempt * 3)
                print(f"   ⏳ Pollinations cooldown (status {res.status_code}). Waiting {cooldown}s for token bucket refill...")
                time.sleep(cooldown)
        except Exception as e:
            cooldown = 12 + (attempt * 3)
            print(f"   ⏳ Network retry ({e}). Waiting {cooldown}s...")
            time.sleep(cooldown)

    return False


def download_youtube_audio_multi_client(yt_url, out_raw_path):
    """
    Downloads audio from a specific YouTube URL on GitHub Actions using 3 sequential bypass layers:
    1) pytubefix with ANDROID_VR / IOS / TV / WEB_EMBED clients
    2) yt-dlp with android_vr / ios / tv_embedded player clients
    3) Invidious / Piped public stream API mirrors
    """
    video_id = yt_url.split("/")[-1].split("?")[0].replace("watch?v=", "")

    # Layer 1: pytubefix multi-client bypass
    try:
        from pytubefix import YouTube
        for client_name in ("ANDROID_VR", "IOS", "TV", "MWEB", "WEB_EMBED"):
            try:
                print(f"   [AUDIO-DL] Trying pytubefix ({client_name}) for {yt_url}...")
                yt = YouTube(yt_url, client=client_name)
                stream = yt.streams.get_audio_only()
                if stream:
                    dl_file = stream.download(output_path="workspace", filename=f"pytube_{video_id}.m4a")
                    if dl_file and os.path.exists(dl_file) and os.path.getsize(dl_file) > 60000:
                        os.replace(dl_file, out_raw_path)
                        print(f"   ✅ Downloaded {yt_url} via pytubefix ({client_name})!")
                        return True
            except Exception:
                continue
    except Exception:
        pass

    # Layer 2: yt-dlp with player_client spoofing
    for client_arg in ("youtube:player_client=android_vr", "youtube:player_client=ios,tv_embedded", "youtube:player_client=mweb"):
        try:
            print(f"   [AUDIO-DL] Trying yt-dlp ({client_arg}) for {yt_url}...")
            if os.path.exists(out_raw_path):
                os.remove(out_raw_path)
            cmd = [
                sys.executable, "-m", "yt_dlp",
                yt_url,
                "--extractor-args", client_arg,
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "--no-playlist",
                "--quiet",
                "--output", out_raw_path
            ]
            subprocess.run(cmd, timeout=60, check=False)
            if os.path.exists(out_raw_path) and os.path.getsize(out_raw_path) > 60000:
                print(f"   ✅ Downloaded {yt_url} via yt-dlp ({client_arg})!")
                return True
        except Exception:
            continue

    # Layer 3: Piped / Invidious Direct Audio Stream Mirrors
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
                        if audio_res.status_code == 200 and len(audio_res.content) > 60000:
                            with open(out_raw_path, "wb") as f:
                                f.write(audio_res.content)
                            print(f"   ✅ Downloaded {yt_url} via stream mirror!")
                            return True
        except Exception:
            continue

    return False


def get_locked_target_song(required_duration_sec):
    """
    Fetches and slices the exact requested song:
    1) Primary: https://youtu.be/e4KMz7PdAmE from 00:00 (Love Story - Indila Slowed+Reverb+Echo)
    2) Secondary: https://youtu.be/1NBnN0IAljQ from 00:20 (Love Story by Indila Ethereal Instrumental)
    3) Direct SoundCloud Mirror of the exact same Slowed+Reverb+Echo / Ethereal track if YouTube blocks datacenter IPs.
    Never uses any synthetic computer piano!
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    # Purge any old synthetic or short audio files
    for old_f in (
        "assets/indila_love_story_magical_cut.mp3",
        "assets/indila_love_story_instrumental_v2.mp3",
        "assets/indila_love_story_pure_instrumental_v3.mp3",
        "assets/indila_love_story_pure_inst_v4.mp3",
        "assets/indila_love_story_pure_inst_75s_v5.mp3"
    ):
        if os.path.exists(old_f):
            try:
                os.remove(old_f)
            except Exception:
                pass

    slice_len = max(MASTER_AUDIO_DURATION, int(required_duration_sec) + 6)

    if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 90000:
        try:
            clip = AudioFileClip(LOCKED_SONG_PATH)
            dur = clip.duration
            clip.close()
            if dur >= required_duration_sec:
                print(f"✅ Using cached real Indila soundtrack ({dur:.1f}s): {LOCKED_SONG_PATH}")
                return LOCKED_SONG_PATH
        except Exception:
            pass

    raw_audio = "workspace/raw_target_song.mp3"

    # Attempt 1: Primary YouTube URL (e4KMz7PdAmE from 00:00)
    print(f"[AUDIO] Fetching Primary Track: {PRIMARY_YT_URL} (starting from 00:00)...")
    if download_youtube_audio_multi_client(PRIMARY_YT_URL, raw_audio):
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(PRIMARY_START_SEC),
            "-t", str(slice_len),
            "-i", raw_audio,
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-b:a", "192k",
            LOCKED_SONG_PATH
        ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 80000:
            print(f"🎉 Locked Primary Track ({PRIMARY_YT_URL} from 00:00) -> {LOCKED_SONG_PATH}")
            return LOCKED_SONG_PATH

    # Attempt 2: Secondary YouTube URL (1NBnN0IAljQ from 00:20)
    print(f"[AUDIO] Fetching Secondary Track: {SECONDARY_YT_URL} (starting from 00:20)...")
    if download_youtube_audio_multi_client(SECONDARY_YT_URL, raw_audio):
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(SECONDARY_START_SEC),
            "-t", str(slice_len),
            "-i", raw_audio,
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-b:a", "192k",
            LOCKED_SONG_PATH
        ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 80000:
            print(f"🎉 Locked Secondary Track ({SECONDARY_YT_URL} from 00:20) -> {LOCKED_SONG_PATH}")
            return LOCKED_SONG_PATH

    # Attempt 3: Direct SoundCloud Mirror of the exact same tracks (Never blocked on GitHub Actions IPs!)
    sc_mirrors = [
        ("scsearch1:Love Story Indila Slowed Reverb Echo", 0),
        ("scsearch1:Indila Love Story Slowed and Reverb", 0),
        ("scsearch1:Love Story Indila Ethereal Instrumental", 20)
    ]
    for sc_query, start_offset in sc_mirrors:
        print(f"[AUDIO] Fetching exact SoundCloud mirror: {sc_query} (from 00:{start_offset:02d})...")
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
                "--quiet",
                "--output", raw_audio
            ]
            subprocess.run(cmd, timeout=60, check=False)
            if os.path.exists(raw_audio) and os.path.getsize(raw_audio) > 90000:
                subprocess.run([
                    "ffmpeg", "-y",
                    "-ss", str(start_offset),
                    "-t", str(slice_len),
                    "-i", raw_audio,
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-b:a", "192k",
                    LOCKED_SONG_PATH
                ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 80000:
                    print(f"🎉 Locked real Indila Slowed+Reverb track via SoundCloud mirror: {LOCKED_SONG_PATH}")
                    return LOCKED_SONG_PATH
        except Exception as e:
            print(f"⚠️ Mirror attempt skipped: {e}")

    raise RuntimeError("❌ Could not download the real Indila audio track.")


def build_pipeline():
    print("=== STARTING PURE POLLINATIONS MANHWA + REAL INDILA SLOWED+REVERB PIPELINE ===")
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

    male_dna = story_data.get("male_dna", "handsome Korean manhwa boy with jet-black hair and warm amber eyes")
    female_dna = story_data.get("female_dna", "beautiful Korean manhwa girl with long chestnut hair and bright eyes")
    scenes = story_data.get("scenes", [])[:8]
    total_scenes = len(scenes)
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.4  # 8 scenes * 5.4s = 43.2s complete story
    reply_pop_delay = 1.8
    clips = []

    for idx, sc in enumerate(scenes):
        bg_path = f"workspace/clean_art_{idx}.jpg"
        if not fetch_pollinations_manhwa_artwork(
            sc, male_dna, female_dna, story_seed, idx, total_scenes, bg_path
        ):
            print(f"⚠️ Scene {idx + 1} skipped after all Pollinations retries.")
            continue

        anchors = detect_character_anchors(bg_path)
        base_clip = ImageClip(bg_path).set_duration(scene_duration).resize((1080, 1920))
        layers = [base_clip]

        # Floating Age Numbers in Top Corners
        age_png = f"workspace/ages_{idx}.png"
        render_floating_manhwa_ages(sc.get("male_age", "20"), sc.get("female_age", "19"), age_png)
        age_clip = ImageClip(age_png).set_position(("center", 12)).set_duration(scene_duration)
        layers.append(age_clip)

        # Left Character Bubble (Speech = Solid Tail, Thought = Detached Circular Dot Chain)
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

        # Right Character Bubble (Pops in at 1.8s)
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

    # Attach the exact locked Indila soundtrack playing continuously forward
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
