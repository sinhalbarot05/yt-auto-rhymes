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

# Auto-install required packages if missing
for pkg in ("yt-dlp", "numpy"):
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", pkg], check=False)

import numpy as np
import yt_dlp
from groq import Groq
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips
)

HISTORY_FILE = "story_history.json"
LOCKED_SONG_PATH = "assets/indila_love_story_ethereal_inst_v7.mp3"
LOCKED_SONG_TITLE = "Love Story - Indila (Ethereal Instrumental Slowed & Reverb)"
MASTER_AUDIO_DURATION = 75

# Rich multi-year 2D Webtoon storylines inspired by 'Hidden Love' & 'Silent Blossom'
STORY_CONCEPTS = [
    "Older Brother's Best Friend Age-Gap Romance (Ages 19 & 13 -> 24 & 18 Airport Goodbye -> 3 Years Later Reunion at 27 & 21 -> 28 & 22 Wedding Embrace): He watched her grow up from a tiny middle-school girl whose backpack he carried, to the woman he kneels before to put on her silver heel and marries",
    "Childhood Next-Door Neighbours to Forever (Ages 16 & 12 -> 21 & 17 Train Commute -> 3 Years Later Reunion at 24 & 20 -> 26 & 22 Proposal): He always patted her head and called her shortie under the cherry blossoms, until they reunite years later and he confesses she was always his only one",
    "Uncherished Fiancée Rescued by the Quiet Older Brother (Ages 22 & 18 -> 24 & 20 Rain Rescue -> 2 Years Later at 26 & 22 -> 27 & 23 Wedding): Ignored by her cold crush, she is sheltered under an umbrella by his gentle older brother who cherishes every detail about her",
    "Campus Senior & Shy Freshman Across the Years (Ages 21 & 17 Elevator Meet -> 23 & 19 Night Balcony -> 3 Years Later at 26 & 22 -> 27 & 23): From sharing snacks in an apartment elevator and holding the same bus strap to an emotional airport reunion and sunlit wedding"
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
    """Loads clean bold font for crisp webtoon lettering."""
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


def enhance_bright_pastel_webtoon_look(pil_img):
    """
    Ensures every generated frame has the bright, airy, high-key 2D pastel watercolor & cel-shaded look
    of 'Hidden Love' (Silent Blossom's benchmark video)—never dark, murky, or muddy.
    """
    rgb = pil_img.convert("RGB")
    arr = np.array(rgb, dtype=np.float32) / 255.0

    mean_lum = float(np.mean(arr))
    if mean_lum < 0.55:
        gamma = max(0.74, min(0.92, mean_lum / 0.58))
        arr = np.power(np.clip(arr, 0.0, 1.0), gamma)

    arr = np.clip(arr * 1.04 + 0.02, 0.0, 1.0)
    out = Image.fromarray((arr * 255.0).astype(np.uint8), mode="RGB")
    out = ImageEnhance.Color(out).enhance(1.12)
    out = ImageEnhance.Sharpness(out).enhance(1.15)
    return out


def clean_watermark_and_fit_9_16(raw_bytes, output_path):
    """
    1. Trims 4.0% off the bottom edge to remove any 'pollinations.ai' corner watermark.
    2. Center-crops to exact 9:16 aspect ratio with ZERO vertical or horizontal stretching.
    3. Applies the High-Key Pastel Webtoon brightness guard.
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
        bright_webtoon = enhance_bright_pastel_webtoon_look(fitted)
        bright_webtoon.save(output_path, "JPEG", quality=96)

    return output_path


def is_valid_2d_webtoon_image(raw_bytes):
    """Verifies the downloaded image is valid, non-blank, and colorful."""
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
    Detects the Boy (left half) and Girl (right half) head-tops and mouth coordinates
    so age badges sit right above their heads and bubbles point directly to them.
    """
    default_anchors = {
        "boy_head_top": (300, 390),
        "boy_mouth": (335, 560),
        "girl_head_top": (760, 510),
        "girl_mouth": (725, 665)
    }
    try:
        with Image.open(img_path) as im:
            rgb = np.array(im.convert("RGB").resize((1080, 1920)), dtype=np.float32)

        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        skin_mask = (
            (r > 175) & (g > 135) & (b > 110) &
            ((r - g) > 8) & ((r - b) > 18) & ((r - b) < 105) &
            (g > b)
        )
        y_min, y_max = 220, 1250

        def find_side_face(x_start, x_end, is_left):
            sub_mask = skin_mask[y_min:y_max, x_start:x_end]
            ys, xs = np.where(sub_mask)
            if len(ys) < 300:
                return None

            face_cx = int(x_start + np.median(xs))
            face_top_y = int(y_min + np.percentile(ys, 10))
            face_bot_y = int(y_min + np.percentile(ys, 85))
            face_h = max(110, min(280, face_bot_y - face_top_y))

            head_top_y = max(220, face_top_y - int(face_h * 0.52))
            inward_shift = int(face_h * 0.15) if is_left else -int(face_h * 0.15)
            mouth_x = max(120, min(960, face_cx + inward_shift))
            mouth_y = min(1180, face_top_y + int(face_h * 0.65))
            return (face_cx, head_top_y), (mouth_x, mouth_y)

        left_res = find_side_face(45, 535, is_left=True)
        right_res = find_side_face(545, 1035, is_left=False)

        if left_res:
            default_anchors["boy_head_top"], default_anchors["boy_mouth"] = left_res
        if right_res:
            default_anchors["girl_head_top"], default_anchors["girl_mouth"] = right_res
    except Exception:
        pass

    return default_anchors


def render_head_tracked_ages_layer(male_age, female_age, boy_head_top, girl_head_top, output_path):
    """
    Renders the character ages directly above each character's head:
    - Boy's Age in Glowing Aqua-Cyan (#28F0E8) with crisp black comic stroke.
    - Girl's Age in Glowing Rose-Pink (#FF6888) with crisp black comic stroke.
    """
    scale = 2
    W, H = 1080 * scale, 1920 * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_age = get_comic_font(56 * scale)

    def draw_age_on_head(hx, hy, age_val, fill_rgb):
        txt = "".join(c for c in str(age_val) if c.isdigit())[:2]
        if not txt:
            return
        cx = max(110 * scale, min(W - 110 * scale, hx * scale))
        cy = max(85 * scale, min(H - 300 * scale, (hy - 32) * scale))

        draw.text(
            (cx, cy),
            txt,
            font=font_age,
            fill=fill_rgb + (255,),
            anchor="mm",
            stroke_width=6 * scale,
            stroke_fill=(12, 14, 18, 255)
        )

    if male_age:
        draw_age_on_head(boy_head_top[0], boy_head_top[1], male_age, (40, 240, 232))
    if female_age:
        draw_age_on_head(girl_head_top[0], girl_head_top[1], female_age, (255, 104, 136))

    img.resize((1080, 1920), Image.LANCZOS).save(output_path, "PNG")
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
    Renders sleek comic bubbles at 2x supersampled resolution (2160x3840):
    - 'speech'  -> Compact horizontal oval + solid curved Bezier tail pointing to speaker.
    - 'thought' -> Soft scalloped cloud + 4 detached shrinking circular thought bubbles (Garfield style).
    - 'whisper' -> Dashed-border oval for shy/soft lines.
    - 'shout'   -> Starburst oval for urgent calling out.
    """
    scale = 2
    W, H = 1080 * scale, 1920 * scale
    clean_txt = clean_english_text(text)

    b_type = str(bubble_type or "speech").lower().strip()
    if b_type not in ("speech", "thought", "whisper", "shout"):
        b_type = "speech"

    wrapped_lines = textwrap.wrap(clean_txt, width=18)[:3]
    multiline_str = "\n".join(wrapped_lines)

    font = get_comic_font(31 * scale)
    dummy = Image.new("L", (10, 10))
    d_draw = ImageDraw.Draw(dummy)
    bbox = d_draw.multiline_textbbox((0, 0), multiline_str, font=font, align="center", spacing=7 * scale)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    rx = max(136 * scale, int(tw * 0.5 + 46 * scale))
    ry = max(70 * scale, int(th * 0.5 + 36 * scale))

    hx, hy = head_top[0] * scale, head_top[1] * scale
    mx, my = mouth_pt[0] * scale, mouth_pt[1] * scale

    if side == "left":
        cx = max(rx + 24 * scale, min(520 * scale - rx, hx - 8 * scale))
        cy = max(ry + 95 * scale, min((hy - 78 * scale) - ry, 195 * scale))
    else:
        cx = max(560 * scale + rx, min(W - rx - 24 * scale, hx + 8 * scale))
        cy = max(ry + 125 * scale, min((hy - 78 * scale) - ry, 235 * scale))

    raw_tx = mx + (-18 * scale if side == "left" else 18 * scale)
    tx = max(cx - rx + 20 * scale, min(cx + rx - 20 * scale, raw_tx))
    if side == "left":
        tx = max(tx, cx + int(rx * 0.16))
    else:
        tx = min(tx, cx - int(rx * 0.16))

    tail_bottom_limit = cy + ry + 110 * scale
    ty = max(cy + ry + 58 * scale, min(tail_bottom_limit, my - 65 * scale))

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
            pr = (26 if i % 2 == 0 else 22) * scale
            m_draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=255)

        start_x = cx + (int(rx * 0.14) if side == "left" else -int(rx * 0.14))
        start_y = cy + ry + 22 * scale
        ctrl_x = (start_x + tx) * 0.5 + (-12 * scale if side == "left" else 12 * scale)
        ctrl_y = start_y + (ty - start_y) * 0.52

        dot_specs = [
            (0.08, 13.0 * scale),
            (0.40, 9.5 * scale),
            (0.70, 6.5 * scale),
            (0.96, 4.5 * scale)
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
            (base_x - 18 * scale, base_y),
            (tx, ty),
            (base_x + 18 * scale, base_y)
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
        half_base = (13 if b_type == "whisper" else 18) * scale

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
    shadow_mask = outer_mask.filter(ImageFilter.GaussianBlur(6 * scale))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    shadow_layer = Image.new("RGBA", (W, H), (12, 15, 24, 50))
    canvas.paste(shadow_layer, (0, 5 * scale), mask=shadow_mask)

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
        spacing=7 * scale
    )

    canvas.resize((1080, 1920), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def render_timeskip_card(text, output_path):
    """Renders the dramatic black time-skip card ('3 yrs later..')."""
    img = Image.new("RGB", (1080, 1920), (8, 8, 10))
    draw = ImageDraw.Draw(img)
    font = get_comic_font(54)
    draw.text((540, 960), clean_english_text(text), font=font, fill=(245, 245, 250), anchor="mm")
    img.save(output_path, "JPEG", quality=95)
    return output_path


def get_valid_groq_chat_models(client):
    """
    Prioritizes high-TPM Llama models first and places low-OTPM preview models (like qwen3.8)
    at the very back so 1000-OTPM rate limits are never triggered.
    """
    models_resp = client.models.list().data
    all_ids = [m.id for m in models_resp]

    banned = (
        "orpheus", "canopylabs", "whisper", "guard", "tts", "playai",
        "embed", "vision", "allam", "distil", "audio", "speech", "safeguard"
    )
    allowed_families = ("llama", "gemma", "mixtral", "deepseek", "qwen")

    chat_models = [
        m for m in all_ids
        if not any(b in m.lower() for b in banned)
        and any(f in m.lower() for f in allowed_families)
    ]

    # High output-token-per-minute models strictly prioritized first
    preferred_order = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "gemma2-9b-it",
        "mixtral-8x7b-32768"
    ]

    ordered = [p for p in preferred_order if p in chat_models]
    for m in chat_models:
        if m not in ordered and "qwen3.8" not in m.lower():
            ordered.append(m)
    for m in chat_models:
        if m not in ordered:
            ordered.append(m)

    return ordered if ordered else ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def build_story_prompts(concept, used_titles, used_dialogues):
    """
    Uses a compact, token-efficient prompt and schema (~550 output tokens) so even models
    with a strict 1,000 OTPM ceiling on Groq never throw a 429 Request Too Large error.
    """
    entropy = f"{int(time.time())}-{random.randint(1000, 9999)}"
    system_prompt = (
        "You are an elite 2D Romance Webtoon Director ('Hidden Love' / 'Silent Blossom' style). "
        "Output strictly valid, compact JSON."
    )
    user_prompt = f"""Write a 9-scene vertical 2D Webtoon romance Short script.
Seed: {entropy} | Concept: "{concept}"
Avoid titles: {json.dumps(used_titles[-5:])}

Each scene needs rich real-world scenery & physical actions (e.g., S1 street carrying schoolbag, S2 cherry blossoms head-pat, S3 apartment elevator snack, S4 sunlit bus handrail, S5 station bench kneeling goodbye, S6 airport terminal calling out, S7 tight reunion hug after 3-yr skip, S8 night park bench putting silver heel on her foot, S9 sunlit wedding embrace).
Keep male_line and female_line to 3-7 English words.

Return ONLY compact JSON matching this exact schema:
{{
  "trope": "Short theme",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "video_title": "Viral title with emojis #Shorts #manhwa #lovestory",
  "male_traits": "tall slender 2D anime boy with messy jet-black hair and warm dark eyes",
  "female_traits": "petite cute 2D anime girl with long honey-brown hair and bright eyes",
  "timeskip_after_scene_index": 5,
  "timeskip_text": "3 yrs later..",
  "scenes": [
    {{
      "male_age": "19",
      "female_age": "13",
      "male_bubble_type": "speech",
      "male_line": "Give me that, I'll hold it!",
      "female_bubble_type": "whisper",
      "female_line": "Thank you...",
      "camera_framing": "full-body vertical 2D webtoon shot",
      "scenery_background": "sunlit street sidewalk with pastel walls and green trees",
      "character_pose_and_action": "tall 19yo boy reaching down to hold the light-blue schoolbag of a petite 13yo girl"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_complete_fallback_story(history):
    """Complete 9-scene multi-year 'Hidden Love / Silent Blossom' visual story arc."""
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    return {
        "trope": f"Between Goodbye and Forever #{run_id}",
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": f"Somewhere Between Goodbye and Forever.. 👉🏻👈🏻💗🦋 #{run_id} #Shorts #manhwa #lovestory",
        "male_traits": "tall slender 2D anime boy with messy jet-black hair and warm dark eyes",
        "female_traits": "petite cute 2D anime girl with long soft honey-brown hair and big bright eyes",
        "timeskip_after_scene_index": 5,
        "timeskip_text": "3 yrs later..",
        "scenes": [
            {
                "male_age": "19", "female_age": "13",
                "male_bubble_type": "speech", "male_line": "Give me that, I'll hold it!",
                "female_bubble_type": "whisper", "female_line": "Hmm.. thank you.",
                "camera_framing": "full-body vertical 2D webtoon illustration",
                "scenery_background": "bright sunlit neighborhood street sidewalk with warm cream walls and soft green trees",
                "character_pose_and_action": "tall 19yo boy in white collared shirt and black trousers reaching down to hold the light-blue school backpack of a petite 13yo girl in school blouse and pleated skirt, cute height difference"
            },
            {
                "male_age": "20", "female_age": "14",
                "male_bubble_type": "speech", "male_line": "Okay, shortie! Walk faster.",
                "female_bubble_type": "speech", "female_line": "Stop calling me shortie!",
                "camera_framing": "medium-full vertical 2D webtoon illustration",
                "scenery_background": "dreamy pastel blue and pink sky with floating cherry blossom petals",
                "character_pose_and_action": "tall 20yo boy affectionately patting the top of the shorter 14yo girl's head as they walk side-by-side"
            },
            {
                "male_age": "21", "female_age": "15",
                "male_bubble_type": "speech", "male_line": "What are you eating? Save me some?",
                "female_bubble_type": "speech", "female_line": "Do you want a bite?",
                "camera_framing": "three-quarter vertical 2D webtoon illustration",
                "scenery_background": "bright clean modern silver apartment elevator interior with soft overhead lighting",
                "character_pose_and_action": "tall 21yo boy in a casual black t-shirt looking down fondly at the petite 15yo girl in a light-blue pinafore dress holding a snack"
            },
            {
                "male_age": "22", "female_age": "16",
                "male_bubble_type": "speech", "male_line": "Hold onto my sleeve so you don't fall.",
                "female_bubble_type": "thought", "female_line": "He is always so gentle with me...",
                "camera_framing": "medium vertical 2D webtoon illustration",
                "scenery_background": "bright sunlit commuter bus interior with large windows and soft blue sky outside",
                "character_pose_and_action": "tall 22yo boy in a light-blue plaid shirt over white tee and petite 16yo girl in a pastel ribbon blouse both holding the white overhead bus strap, hands touching"
            },
            {
                "male_age": "24", "female_age": "18",
                "male_bubble_type": "speech", "male_line": "Hey... are you crying?",
                "female_bubble_type": "speech", "female_line": "Are you really leaving next month?",
                "camera_framing": "full-body wide vertical 2D webtoon illustration",
                "scenery_background": "bright glass-walled airport waiting lounge with blue sky outside and blooming pink flowers in foreground",
                "character_pose_and_action": "18yo girl sitting on a bench looking sad while the tall 24yo man in a long grey coat kneels on one knee in front of her looking up at her face"
            },
            {
                "male_age": "24", "female_age": "18",
                "male_bubble_type": "thought", "male_line": "Wait for me until I return.",
                "female_bubble_type": "shout", "female_line": "Wait! Don't dare forget me!",
                "camera_framing": "full-body dynamic vertical 2D webtoon illustration",
                "scenery_background": "grand sunlit airport terminal hall with warm geometric skylight ceiling panels",
                "character_pose_and_action": "18yo girl in blue cardigan and white dress running forward calling out toward the tall 24yo man in a dark coat"
            },
            {
                "male_age": "27", "female_age": "21",
                "male_bubble_type": "thought", "male_line": "She has no idea how much I missed her.",
                "female_bubble_type": "speech", "female_line": "You're finally back in my arms!",
                "camera_framing": "close medium vertical 2D webtoon illustration",
                "scenery_background": "soft bright sunlit station concourse with warm pastel bokeh",
                "character_pose_and_action": "emotional reunion hug, 21yo woman wrapping both arms tightly around the neck of the tall 27yo man in a beige trench coat, burying her blushing face in his shoulder"
            },
            {
                "male_age": "27", "female_age": "21",
                "male_bubble_type": "speech", "male_line": "Hold still. Let me put it on for you.",
                "female_bubble_type": "thought", "female_line": "He still treats me like a princess...",
                "camera_framing": "full-body vertical 2D webtoon illustration",
                "scenery_background": "romantic night park garden bench under a deep blue starry sky and soft greenery",
                "character_pose_and_action": "21yo woman in an emerald evening dress sitting on a wrought-iron park bench while the 27yo man in a crisp white shirt kneels on one knee putting a silver high-heel shoe onto her foot"
            },
            {
                "male_age": "28", "female_age": "22",
                "male_bubble_type": "speech", "male_line": "I love you. Forever starts today.",
                "female_bubble_type": "speech", "female_line": "I love you too, my forever.",
                "camera_framing": "medium vertical 2D webtoon illustration",
                "scenery_background": "magical glowing golden-white wedding sunlight with soft floating sparkles and floral lace",
                "character_pose_and_action": "passionate wedding embrace, 22yo bride in a white wedding dress, floral hairpiece, and flowing veil wrapping her arms around the neck of the 28yo groom in a black tuxedo"
            }
        ]
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
            for model in candidate_models[:5]:
                try:
                    print(f"[STORY-ENGINE] Writing 9-scene 'Hidden Love' webtoon script via Groq ({model})...")
                    # max_tokens=850 strictly satisfies the 1000-OTPM limit on Groq's free on_demand tier!
                    res = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                        response_format={"type": "json_object"},
                        max_tokens=850,
                        temperature=0.80
                    )
                    data = json.loads(res.choices[0].message.content.strip())
                    if "scenes" in data and len(data["scenes"]) >= 7:
                        data["archetype_used"] = chosen_concept
                        print(f"✅ Complete {len(data['scenes'])}-Scene Webtoon Script Ready: {data.get('video_title')}")
                        return data
                except Exception as model_err:
                    print(f"⚠️ Model {model} skipped ({model_err}). Trying next chat model...")
                    time.sleep(2)
                    continue
        except Exception as e:
            print(f"⚠️ Groq client fallback ({e})...")

    return generate_complete_fallback_story(history)


# Track globally if POLLINATIONS_API_KEY is out of credits (402/401) so we never waste retries on it
POLLINATIONS_KEY_EXHAUSTED = False


def fetch_2d_hidden_love_webtoon_scene(scene, male_traits, female_traits, story_seed, idx, total_scenes, output_path):
    """
    Fast, Zero-402-Loop Pollinations 2D Webtoon Image Fetcher:
    - Uses ONLY 'image.pollinations.ai' (which succeeded for all 9 of your scenes) and skips 'gen.pollinations.ai'
      when POLLINATIONS_API_KEY is exhausted, eliminating the 401/402 retry loop!
    """
    global POLLINATIONS_KEY_EXHAUSTED
    api_key = os.getenv("POLLINATIONS_API_KEY")

    m_age = scene.get("male_age", "21")
    f_age = scene.get("female_age", "15")
    framing = scene.get("camera_framing", "full-body vertical 2D webtoon illustration")
    scenery = scene.get("scenery_background", "bright sunlit street with pastel buildings and cherry blossom trees")
    action = scene.get("character_pose_and_action", "tall anime boy looking fondly at shorter anime girl")

    f_age_num = int("".join(c for c in str(f_age) if c.isdigit()) or "16")
    if f_age_num <= 14:
        girl_desc = f"petite {f_age_num}yo 2D anime middle-school girl ({female_traits})"
    elif f_age_num <= 18:
        girl_desc = f"petite shorter {f_age_num}yo 2D anime high-school girl ({female_traits})"
    else:
        girl_desc = f"slender {f_age_num}yo 2D anime young woman ({female_traits})"

    boy_desc = f"tall slender {m_age}yo 2D anime boy ({male_traits})"

    prompt = (
        f"2D romance manhua webtoon illustration in the exact art style of Hidden Love (Toutou Cang Buzhu), "
        f"clean delicate 2D hand-drawn ink lineart, bright airy high-key pastel watercolor and cel-shading, "
        f"soft luminous lighting, flat 2D anime art, NOT 3D. "
        f"{framing} with generous sky or ceiling headroom at top. "
        f"Scenery: {scenery}. Left: {boy_desc}; Right: {girl_desc}. Action: {action}. "
        f"Strictly 2 characters only, no text, no speech bubbles, no watermark."
    )
    encoded = urllib.parse.quote(prompt)

    # Clean 12s pacing between scenes so image.pollinations.ai's rate limiter stays clear
    if idx > 0:
        time.sleep(12.0)

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
    ]

    print(f"[2D-WEBTOON-ART] Generating Scene {idx + 1}/{total_scenes} (Ages {m_age} & {f_age}): {scenery[:55]}...")

    for attempt in range(6):
        seed = story_seed + (idx * 347) + (attempt * 53)
        # Use image.pollinations.ai directly (no dead gen.pollinations.ai 401/402 loops)
        if attempt % 2 == 0:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1344&model=flux&seed={seed}&nologo=true&enhance=false"
        else:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&seed={seed}&nologo=true&enhance=false"

        headers = {"User-Agent": user_agents[attempt % len(user_agents)]}
        if api_key and not POLLINATIONS_KEY_EXHAUSTED and attempt == 0:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            res = requests.get(url, headers=headers, timeout=85)
            ctype = res.headers.get("Content-Type", "")
            if res.status_code == 200 and "image" in ctype and is_valid_2d_webtoon_image(res.content):
                clean_watermark_and_fit_9_16(res.content, output_path)
                print(f"✅ Scene {idx + 1}/{total_scenes} saved in bright 2D 'Hidden Love' webtoon style: {output_path}")
                return True

            if res.status_code in (401, 402):
                POLLINATIONS_KEY_EXHAUSTED = True

            # Wait 25s in a single clean sleep so the anonymous IP bucket refills immediately on the next try
            cooldown = 25 + (attempt * 5)
            print(f"   ⏳ Pollinations rate-limit refill (status {res.status_code}). Waiting {cooldown}s...")
            time.sleep(cooldown)
        except Exception as e:
            cooldown = 15 + (attempt * 5)
            print(f"   ⏳ Network retry ({e}). Waiting {cooldown}s...")
            time.sleep(cooldown)

    return False


def probe_audio_duration_ffprobe(file_path):
    """Uses ffprobe (fast, zero-crash) to check the exact duration of a cached audio file."""
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 80000:
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


def get_locked_target_song(required_duration_sec):
    """
    Zero-Cookie, Zero-Bot-Wall Indila Instrumental Fetcher:
    1) Checks cached 'assets/indila_love_story_ethereal_inst_v7.mp3' via ffprobe first (0 network calls if cached!).
    2) Queries SoundCloud ('scsearch:') FIRST because SoundCloud NEVER triggers YouTube's datacenter bot wall!
    3) Queries Piped/Invidious stream APIs for 1NBnN0IAljQ (from 00:20) as a quiet backup without printing yt-dlp errors.
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    # Purge old v1-v6 cached audio files
    for old_f in (
        "assets/indila_love_story_magical_cut.mp3",
        "assets/indila_love_story_instrumental_v2.mp3",
        "assets/indila_love_story_pure_instrumental_v3.mp3",
        "assets/indila_love_story_pure_inst_v4.mp3",
        "assets/indila_love_story_pure_inst_75s_v5.mp3",
        "assets/indila_love_story_real_v6.mp3"
    ):
        if os.path.exists(old_f):
            try:
                os.remove(old_f)
            except Exception:
                pass

    # 1. Instant Cache Check via ffprobe
    cached_dur = probe_audio_duration_ffprobe(LOCKED_SONG_PATH)
    if cached_dur >= required_duration_sec:
        print(f"✅ Using cached vocal-free Ethereal Instrumental ({cached_dur:.1f}s): {LOCKED_SONG_PATH}")
        return LOCKED_SONG_PATH

    slice_len = max(MASTER_AUDIO_DURATION, int(required_duration_sec) + 6)
    raw_audio = "workspace/raw_target_song.mp3"

    # 2. Primary Bot-Wall-Free Source: SoundCloud Mirrors of Indila - Love Story (Ethereal / Slowed+Reverb Instrumental)
    sc_queries = [
        ("scsearch1:Love Story by Indila Ethereal Instrumental Full Version", 20),
        ("scsearch1:Indila Love Story Extended Instrumental Slowed Reverb", 20),
        ("scsearch1:Indila Love Story Piano Instrumental Slowed Reverb", 0),
        ("scsearch1:Love Story Indila Slowed Reverb Instrumental", 20)
    ]
    for sc_query, start_offset in sc_queries:
        print(f"[AUDIO] Fetching Indila Instrumental via SoundCloud (zero bot wall): '{sc_query}' (from 00:{start_offset:02d})...")
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

    # 3. Secondary Source: Piped / Invidious Direct Audio Stream Mirrors for 1NBnN0IAljQ (from 00:20)
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

    raise RuntimeError("❌ Could not download the Indila instrumental audio track.")


def build_pipeline():
    print("=== STARTING 2D 'HIDDEN LOVE' PASTEL WEBTOON SCENERY + HEAD-TRACKED AGES PIPELINE ===")
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

    male_traits = story_data.get("male_traits", "tall slender 2D anime boy with messy jet-black hair and warm dark eyes")
    female_traits = story_data.get("female_traits", "petite cute 2D anime girl with long soft honey-brown hair and big bright eyes")
    timeskip_idx = int(story_data.get("timeskip_after_scene_index", 5))
    timeskip_txt = story_data.get("timeskip_text", "3 yrs later..")

    scenes = story_data.get("scenes", [])[:9]
    total_scenes = len(scenes)
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.0
    reply_pop_delay = 1.7
    clips = []

    for idx, sc in enumerate(scenes):
        bg_path = f"workspace/clean_art_{idx}.jpg"
        if not fetch_2d_hidden_love_webtoon_scene(
            sc, male_traits, female_traits, story_seed, idx, total_scenes, bg_path
        ):
            print(f"⚠️ Scene {idx + 1} skipped after retries.")
            continue

        anchors = detect_character_anchors(bg_path)
        base_clip = ImageClip(bg_path).set_duration(scene_duration).resize((1080, 1920))
        layers = [base_clip]

        # 1. Head-Tracked Ages (Cyan #28F0E8 right above Boy's head, Pink #FF6888 right above Girl's head)
        age_png = f"workspace/ages_{idx}.png"
        render_head_tracked_ages_layer(
            sc.get("male_age", "21"),
            sc.get("female_age", "15"),
            anchors["boy_head_top"],
            anchors["girl_head_top"],
            age_png
        )
        age_clip = ImageClip(age_png).set_position((0, 0)).set_duration(scene_duration)
        layers.append(age_clip)

        # 2. Left Character Bubble (Speech = Solid Tail, Thought = Detached Circular Dot Chain)
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

        # 3. Right Character Bubble (Pops in at 1.7s)
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
        scene_comp = scene_comp.resize(lambda t: 1.0 + (0.016 * t))
        clips.append(scene_comp)

        # Insert the dramatic black "3 yrs later.." time-skip card after the departure scene
        if idx == timeskip_idx:
            ts_path = "workspace/timeskip_card.jpg"
            render_timeskip_card(timeskip_txt, ts_path)
            ts_clip = ImageClip(ts_path).set_duration(2.2).resize((1080, 1920))
            clips.append(ts_clip)

    if len(clips) < 6:
        raise RuntimeError(f"❌ Pipeline aborted: Only {len(clips)} clips rendered.")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration
    print(f"[TIMELINE] Assembled complete {len(clips)}-clip story ({total_dur:.1f} seconds total).")

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
    print(f"🎉 COMPLETE {total_dur:.1f}s 2D WEBTOON SHORT READY: {output_mp4}")


if __name__ == "__main__":
    build_pipeline()
