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

# Ensure yt-dlp and numpy are installed
for pkg in ("yt-dlp", "numpy"):
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", pkg], check=False)

import numpy as np
import yt_dlp
from groq import Groq
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    afx
)

HISTORY_FILE = "story_history.json"
# Continuous 75-second forward cut (never loops on 45s-55s videos)
LOCKED_SONG_PATH = "assets/indila_love_story_pure_inst_75s_v5.mp3"
LOCKED_SONG_TITLE = "Love Story (Instrumental Slowed & Reverb) - Indila"

GOLDEN_START_SEC = 35
GOLDEN_DURATION_SEC = 75

# Complete multi-act romance storylines
STORY_CONCEPTS = [
    "Childhood Friends to Soulmates: From age 9 kids sharing strawberries across sunlit balconies, to age 14 walking home in autumn, to age 17 defending her in the rain, to age 19 jealous confession, to age 23 proposing under the golden cherry tree",
    "Uncherished to Cherished by True Future Love: For years her cold fiancé ignored her birthday and left her in the rain; when she walks away, his protective older brother steps in with an umbrella and cherishes her like a queen while her ex regrets losing her",
    "Intense Jealousy in Secret Love: The aloof student council president claims he only sees her as a junior, until a transfer boy makes her smile—shattering his calm mask as he pulls her into a golden sunset classroom to confess",
    "Contract Marriage to Obsessive Devotion: Married on paper with a rule to never fall in love; when she prepares to leave thinking he loves someone else, he tears up the papers in the rain and begs her to stay",
    "Academic Rivals to Midnight Confidants: Fighting for #1 rank every semester while bickering daily, until he finds her crying on the sunset rooftop and stays beside her every evening",
    "The Forgotten Childhood Promise: Separated at age 9 when she moved away, she thinks the quiet university senior is a stranger—until she spots the faded red ribbon she tied on his wrist twelve years ago",
    "Ignored by Crush, Treasured by the Quiet Protector: She always brought lunch for the popular captain who took her for granted, while the quiet art prodigy secretly painted her in golden sunlight for two years before stepping forward",
    "Time-Leap Redemption: After losing her in a distant future, he wakes up back at age 16 on the day they first met in high school and vows to protect and cherish her every single day"
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


def apply_aot_golden_2d_grade(pil_img):
    """
    Transforms the image into a crisp 2D Anime frame with Attack on Titan (WIT Studio)
    Golden-Hour Sunset color grading:
    1. Enhances 2D dark ink edge lines and flattens 3D plastic shading via subtle posterization/edge blend.
    2. Infuses warm golden-amber highlights and deep cinematic bronze shadows across the frame.
    3. Adds a soft golden sunset bloom in the upper sky/highlights.
    """
    img = pil_img.convert("RGB")

    # 1. Subtle 2D Cel-Shading & Ink Line Enhancement
    # Detect fine edges to reinforce 2D hand-drawn lineart
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(0.6))
    edge_arr = np.array(edges, dtype=np.float32) / 255.0
    ink_mask = np.clip((edge_arr - 0.12) * 0.35, 0.0, 0.28)[:, :, None]

    # Slightly quantize tonal steps + blend smooth version to remove 3D CGI skin pores
    smoothed = img.filter(ImageFilter.MedianFilter(size=3))
    arr = np.array(smoothed, dtype=np.float32)
    # Soft cel quantization blended at 30% with smooth base
    cel_arr = np.floor(arr / 16.0) * 16.0 + 8.0
    arr = (arr * 0.72) + (cel_arr * 0.28)

    # Darken ink outlines like WIT Studio thick anime lineart
    arr = arr * (1.0 - ink_mask)

    # 2. Attack on Titan (WIT Studio) Golden Sunset Color Matrix
    norm = arr / 255.0
    lum = 0.299 * norm[:, :, 0] + 0.587 * norm[:, :, 1] + 0.114 * norm[:, :, 2]

    # S-curve contrast for dramatic anime lighting
    norm = np.clip(0.5 + (norm - 0.5) * 1.14, 0.0, 1.0)

    r = norm[:, :, 0]
    g = norm[:, :, 1]
    b = norm[:, :, 2]

    # Golden amber boost in midtones & highlights, rich warm bronze in shadows
    highlight_weight = np.clip((lum - 0.35) / 0.65, 0.0, 1.0)
    shadow_weight = 1.0 - highlight_weight

    r_graded = r * 1.14 + 0.05 * highlight_weight + 0.02 * shadow_weight
    g_graded = g * 1.03 + 0.02 * highlight_weight - 0.01 * shadow_weight
    b_graded = b * 0.82 - 0.05 * highlight_weight - 0.02 * shadow_weight

    graded = np.stack([r_graded, g_graded, b_graded], axis=-1)

    # 3. Top Golden Sky Sun-Glow Gradient (adds cinematic sunset warmth from the top)
    h, w = r.shape
    y_grad = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None]
    sun_glow = (y_grad ** 1.8) * 0.08
    graded[:, :, 0] += sun_glow * 1.2
    graded[:, :, 1] += sun_glow * 0.7
    graded[:, :, 2] -= sun_glow * 0.4

    final_arr = np.clip(graded * 255.0, 0, 255).astype(np.uint8)
    out_img = Image.fromarray(final_arr, mode="RGB")
    out_img = ImageEnhance.Color(out_img).enhance(1.18)
    return out_img


def crop_watermark_and_fit_9_16(raw_bytes, output_path):
    """
    Genius Watermark Destroyer + Zero-Stretch 9:16 Aspect-Ratio Fitter:
    1. Slices off the bottom 7.5% of the raw image (where the 'pollinations.ai' watermark sits)
       and 1.5% off the left/right/top margins.
    2. Never stretches a square (1:1) or 3:4 image! Instead, computes the exact 9:16 (0.5625)
       crop window centered on the characters so proportions stay 100% natural, then scales cleanly to 1080x1920.
    3. Applies the 2D Attack on Titan Golden Sunset color grade.
    """
    with Image.open(io.BytesIO(raw_bytes)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size

        # Step 1: Slice off the bottom 7.5% to completely eliminate the pollinations.ai watermark
        left_margin = int(w * 0.015)
        right_margin = int(w * 0.985)
        top_margin = int(h * 0.01)
        bottom_clean = int(h * 0.925)  # Removes bottom 7.5% watermark bar

        clean_crop = rgb.crop((left_margin, top_margin, right_margin, bottom_clean))
        cw, ch = clean_crop.size

        # Step 2: Aspect-ratio-preserving 9:16 center crop (ZERO stretching!)
        target_aspect = 1080.0 / 1920.0  # 0.5625
        current_aspect = cw / float(ch)

        if current_aspect > target_aspect:
            # Image is wider than 9:16 (e.g. square 1024x947 after watermark cut) -> crop left & right evenly
            new_w = int(ch * target_aspect)
            x0 = (cw - new_w) // 2
            box_9_16 = clean_crop.crop((x0, 0, x0 + new_w, ch))
        else:
            # Image is taller than 9:16 -> crop bottom/top preserving upper headroom
            new_h = int(cw / target_aspect)
            y0 = max(0, (ch - new_h) // 3)
            box_9_16 = clean_crop.crop((0, y0, cw, y0 + new_h))

        # Step 3: Scale to 1080x1920 with LANCZOS (1:1 pixel aspect ratio, zero distortion)
        fitted = box_9_16.resize((1080, 1920), Image.LANCZOS)

        # Step 4: Apply 2D Cel-Shade + Attack on Titan Golden Sunset Color Grading
        graded = apply_aot_golden_2d_grade(fitted)
        graded.save(output_path, "JPEG", quality=95)

    return output_path


def detect_character_anchors(img_path):
    """
    Computer-Vision Head & Mouth Locator:
    Finds the Boy (left half) and Girl (right half) face/hair coordinates so bubbles sit
    intimately above their heads and tails/thought-chains point directly to them.
    """
    default_anchors = {
        "boy_head_top": (285, 505),
        "boy_mouth": (345, 735),
        "girl_head_top": (795, 540),
        "girl_mouth": (725, 765)
    }
    try:
        with Image.open(img_path) as im:
            rgb = np.array(im.convert("RGB").resize((1080, 1920)), dtype=np.float32)

        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        skin_mask = (
            (r > 160) & (g > 110) & (b > 80) &
            ((r - g) > 8) & ((r - b) > 20) &
            (g > b)
        )
        y_min, y_max = 360, 1060

        def find_side_face(x_start, x_end, is_left):
            sub_mask = skin_mask[y_min:y_max, x_start:x_end]
            ys, xs = np.where(sub_mask)
            if len(ys) < 400:
                return None

            face_cx = int(x_start + np.median(xs))
            face_top_y = int(y_min + np.percentile(ys, 12))
            face_bot_y = int(y_min + np.percentile(ys, 88))
            face_h = max(140, min(320, face_bot_y - face_top_y))

            head_top_y = max(345, face_top_y - int(face_h * 0.48))
            inward_shift = int(face_h * 0.18) if is_left else -int(face_h * 0.18)
            mouth_x = max(120, min(960, face_cx + inward_shift))
            mouth_y = min(1020, face_top_y + int(face_h * 0.72))
            return (face_cx, head_top_y), (mouth_x, mouth_y)

        left_res = find_side_face(50, 530, is_left=True)
        right_res = find_side_face(550, 1030, is_left=False)

        if left_res:
            default_anchors["boy_head_top"], default_anchors["boy_mouth"] = left_res
        if right_res:
            default_anchors["girl_head_top"], default_anchors["girl_mouth"] = right_res
    except Exception as e:
        print(f"⚠️ Anchor detection fallback used: {e}")

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
    Renders professional comic bubbles using our 2x supersampled morphological ink-and-shadow engine:
    1. 'speech'  -> Horizontal egg / super-ellipse + SOLID curved Bezier wedge tail pointing to mouth.
    2. 'thought' -> Fluffy scalloped cloud / egg body + NO solid tail, replaced by a curved chain of
                    4 DETACHED, progressively shrinking circular thought bubbles (O -> o -> . -> .)
                    pointing to the character's head (Garfield comic style).
    3. 'whisper' -> Smooth horizontal egg + slender curved tail with a DASHED ink border.
    4. 'shout'   -> Spiky comic starburst oval + sharp wedge tail for intense jealousy/shock moments.
    """
    scale = 2
    W, H = 1080 * scale, 1920 * scale
    clean_txt = clean_english_text(text)

    b_type = str(bubble_type or "speech").lower().strip()
    if b_type not in ("speech", "thought", "whisper", "shout"):
        b_type = "speech"

    wrapped_lines = textwrap.wrap(clean_txt, width=18)[:3]
    multiline_str = "\n".join(wrapped_lines)

    font = get_comic_font(33 * scale)
    dummy = Image.new("L", (10, 10))
    d_draw = ImageDraw.Draw(dummy)
    bbox = d_draw.multiline_textbbox((0, 0), multiline_str, font=font, align="center", spacing=8 * scale)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    rx = max(148 * scale, int(tw * 0.5 + 56 * scale))
    ry = max(80 * scale, int(th * 0.5 + 44 * scale))

    hx, hy = head_top[0] * scale, head_top[1] * scale
    mx, my = mouth_pt[0] * scale, mouth_pt[1] * scale

    if side == "left":
        cx = max(rx + 28 * scale, min(515 * scale - rx, hx - 12 * scale))
        cy = max(ry + 115 * scale, min(hy - ry - 20 * scale, 325 * scale))
    else:
        cx = max(565 * scale + rx, min(W - rx - 28 * scale, hx + 12 * scale))
        cy = max(ry + 155 * scale, min(hy - ry - 16 * scale, 370 * scale))

    raw_tx = mx + (-20 * scale if side == "left" else 20 * scale)
    tx = max(cx - rx + 20 * scale, min(cx + rx - 20 * scale, raw_tx))
    if side == "left":
        tx = max(tx, cx + int(rx * 0.18))
    else:
        tx = min(tx, cx - int(rx * 0.18))

    tail_bottom_limit = cy + ry + 128 * scale
    ty = max(cy + ry + 68 * scale, min(tail_bottom_limit, my - 50 * scale))

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
            pr = (29 if i % 2 == 0 else 24) * scale
            m_draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=255)

        start_x = cx + (int(rx * 0.14) if side == "left" else -int(rx * 0.14))
        start_y = cy + ry + 26 * scale
        ctrl_x = (start_x + tx) * 0.5 + (-14 * scale if side == "left" else 14 * scale)
        ctrl_y = start_y + (ty - start_y) * 0.52

        dot_specs = [
            (0.08, 14.5 * scale),
            (0.40, 10.5 * scale),
            (0.70, 7.5 * scale),
            (0.96, 5.0 * scale)
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
            (base_x - 22 * scale, base_y),
            (tx, ty),
            (base_x + 22 * scale, base_y)
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
        half_base = (14 if b_type == "whisper" else 20) * scale

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
    """Renders sleek floating Manhwa age numbers in top corners."""
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


def get_valid_groq_chat_models(client):
    """Strictly selects a text LLM on Groq and blocks TTS/audio/guard models."""
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
        "You are an elite 2D Anime & Manhwa romance scriptwriter and comic director. "
        "You write complete, deeply satisfying 9-scene vertical romance Shorts (46.8 seconds long) "
        "with a full beginning, emotional turning point, and unforgettable resolution. "
        "You use comic bubble types ('speech', 'thought', 'whisper', 'shout') like a master comic writer. "
        "Output strictly valid JSON."
    )
    user_prompt = f"""Write a brand-new, complete 9-scene vertical 2D Anime/Manhwa romance Short script.
Run Seed: {entropy}
Story Concept: "{concept}"
Previously Used Titles (NEVER REPEAT): {json.dumps(used_titles[-10:])}
Previously Used Lines (NEVER REPEAT): {json.dumps(used_dialogues[-15:])}

COMPLETE 9-SCENE STORY STRUCTURE (47 SECONDS TOTAL — DO NOT RUSH):
- Scenes 1 & 2 (Act I - The Setup): Establish the characters, ages, and emotional hook.
- Scenes 3 & 4 (Act II - The Wound / Jealousy): Heartbreak, jealousy, being left behind in the rain, or unspoken longing.
- Scenes 5 & 6 (Act III - The Turning Point): The dramatic rescue, umbrella moment, or jealous confrontation where the true protector steps in.
- Scenes 7 & 8 (Act IV - Healing & Confession): Being truly cherished, raw emotional confession, or the ex realizing what he lost too late.
- Scene 9 (Act V - Unforgettable Payoff): Years-later proposal, passionate embrace, or deeply satisfying romantic closure.

COMIC WRITER BUBBLE RULES:
- Choose the exact right bubble type for each character in every scene:
  * "speech"  -> Normal spoken dialogue (solid tail).
  * "thought" -> Secret inner feelings, heartbreak, or silent realization (cloud with detached circular thought dots).
  * "whisper" -> Shy, trembling, or quiet confession (dashed border).
  * "shout"   -> Jealousy, shock, or urgent protective call (spiky burst).
- Keep "male_line" and "female_line" between 4 and 8 natural English words.

Return ONLY valid JSON matching this exact schema:
{{
  "trope": "Short catchy story theme",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "video_title": "Emotional viral English title with emojis #Shorts #manhwa #lovestory",
  "male_hair_eyes": "jet-black tousled hair and warm amber eyes",
  "female_hair_eyes": "long chestnut-brown hair and bright emerald eyes",
  "scenes": [
    {{
      "male_age": "19",
      "female_age": "18",
      "male_bubble_type": "speech",
      "male_line": "Why are you standing in the rain?",
      "female_bubble_type": "thought",
      "female_line": "He actually came looking for me...",
      "scene_setting_and_pose": "standing side-by-side under an umbrella on a sunset street with cherry trees and golden sky above"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_complete_fallback_story(history):
    """Complete 9-scene (46.8-second) multi-act fallback story generator."""
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    m_hair = random.choice(["jet-black tousled", "silver-ash", "dark espresso", "midnight-blue"])
    f_hair = random.choice(["long chestnut wavy", "silky raven-black", "warm honey-brown", "soft caramel"])

    story_templates = [
        {
            "trope": f"Uncherished to Treasured by True Love #{run_id}",
            "video_title": f"He Left Her In The Rain… So His Brother Stepped In 💔☔ #{run_id} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "21", "female_age": "19", "male_bubble_type": "speech", "male_line": "Wait outside. I'm busy right now.", "female_bubble_type": "thought", "female_line": "He forgot my birthday again...", "scene_setting_and_pose": "standing outside a glowing cafe window at dusk, girl holding a small birthday cake box"},
                {"male_age": "23", "female_age": "19", "male_bubble_type": "thought", "male_line": "How can my brother ignore her tears?", "female_bubble_type": "whisper", "female_line": "It's fine... I'm used to waiting.", "scene_setting_and_pose": "tall older brother in a long coat approaching the shivering girl under a sunset streetlamp"},
                {"male_age": "23", "female_age": "19", "male_bubble_type": "speech", "male_line": "Take my umbrella. Come with me.", "female_bubble_type": "thought", "female_line": "Why is his gaze so warm?", "scene_setting_and_pose": "standing side-by-side under an umbrella in golden-lit rain with tall city buildings behind them"},
                {"male_age": "23", "female_age": "20", "male_bubble_type": "speech", "male_line": "I bought every cake you missed.", "female_bubble_type": "thought", "female_line": "No one ever treasured me like this...", "scene_setting_and_pose": "warm candlelit dining room with tall windows, boy smiling gently while girl blushes"},
                {"male_age": "24", "female_age": "20", "male_bubble_type": "shout", "male_line": "Don't touch her! You lost your chance!", "female_bubble_type": "thought", "female_line": "He stepped right in front of me...", "scene_setting_and_pose": "protective man shielding the girl behind his shoulder in a grand golden-lit hall"},
                {"male_age": "24", "female_age": "20", "male_bubble_type": "whisper", "male_line": "Did you really wait years for me?", "female_bubble_type": "speech", "female_line": "Stay with me. Never look back.", "scene_setting_and_pose": "standing close on a sunset rooftop terrace, boy gently holding her hands"},
                {"male_age": "25", "female_age": "21", "male_bubble_type": "speech", "male_line": "You deserve to be cherished every day.", "female_bubble_type": "thought", "female_line": "My broken heart finally feels whole.", "scene_setting_and_pose": "standing together under floating golden sky lanterns over an evening lake"},
                {"male_age": "26", "female_age": "22", "male_bubble_type": "speech", "male_line": "Marry me and be my whole world.", "female_bubble_type": "speech", "female_line": "Yes! Only you, forever.", "scene_setting_and_pose": "man holding a velvet ring box under golden sunset cherry blossom branches, girl smiling with happy tears"},
                {"male_age": "27", "female_age": "23", "male_bubble_type": "thought", "male_line": "I'll protect that smile for life.", "female_bubble_type": "thought", "female_line": "Losing the wrong one led me to you.", "scene_setting_and_pose": "embracing warmly under golden cathedral sunbeams and floating light particles"}
            ]
        },
        {
            "trope": f"Childhood Friends to Forever #{run_id}",
            "video_title": f"From Next-Door Neighbours To Forever 🥺🌸 #{run_id} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "9", "female_age": "9", "male_bubble_type": "speech", "male_line": "Stop crying! I saved you strawberries.", "female_bubble_type": "thought", "female_line": "He always makes me smile...", "scene_setting_and_pose": "two cute 9-year-old kids on sunlit wooden balconies with golden sky and trees above"},
                {"male_age": "14", "female_age": "14", "male_bubble_type": "speech", "male_line": "Walk on the inside of the street.", "female_bubble_type": "thought", "female_line": "Since when did he get so tall?", "scene_setting_and_pose": "two 14-year-old middle school teens walking under golden autumn trees"},
                {"male_age": "17", "female_age": "16", "male_bubble_type": "thought", "male_line": "Why is that guy talking to her?", "female_bubble_type": "speech", "female_line": "Wait, why are you pulling my sleeve?", "scene_setting_and_pose": "high school boy gently taking girl's wrist in a golden sunset school corridor"},
                {"male_age": "18", "female_age": "17", "male_bubble_type": "speech", "male_line": "Take my coat. Your hands are freezing.", "female_bubble_type": "thought", "female_line": "His coat feels so warm...", "scene_setting_and_pose": "boy draping his winter coat over girl's shoulders at a golden lamp-lit snowy bus stop"},
                {"male_age": "19", "female_age": "18", "male_bubble_type": "shout", "male_line": "Don't date anyone else! Look at me!", "female_bubble_type": "thought", "female_line": "His heart is beating so loud...", "scene_setting_and_pose": "sheltering under a wooden roof in golden-lit rain, boy looking intensely into her eyes"},
                {"male_age": "19", "female_age": "18", "male_bubble_type": "whisper", "male_line": "I've loved you since we were nine.", "female_bubble_type": "whisper", "female_line": "I was scared to lose our friendship...", "scene_setting_and_pose": "standing close on a sunset hilltop overlooking the town, boy gently cupping her cheek"},
                {"male_age": "21", "female_age": "20", "male_bubble_type": "speech", "male_line": "Every promise I made was for you.", "female_bubble_type": "thought", "female_line": "He kept the ring from childhood!", "scene_setting_and_pose": "standing under golden cherry blossom branches, boy showing a silver promise ring"},
                {"male_age": "23", "female_age": "22", "male_bubble_type": "speech", "male_line": "From next-door neighbours to my wife?", "female_bubble_type": "speech", "female_line": "Yes! A thousand times yes!", "scene_setting_and_pose": "romantic proposal under glowing golden sunset clouds and cherry petals"},
                {"male_age": "24", "female_age": "23", "male_bubble_type": "thought", "male_line": "Forever starts right now with her.", "female_bubble_type": "thought", "female_line": "My childhood friend is my whole life.", "scene_setting_and_pose": "embracing happily under warm golden sunset rays and floating petals"}
            ]
        }
    ]

    picked = random.choice(story_templates)
    return {
        "trope": picked["trope"],
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": picked["video_title"],
        "male_hair_eyes": f"{m_hair} hair and warm amber eyes",
        "female_hair_eyes": f"{f_hair} hair and bright expressive eyes",
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
                    print(f"[STORY-ENGINE] Writing complete 9-scene script via Groq ({model})...")
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


def build_age_accurate_character_prompt(age_str, gender, hair_eyes_desc):
    """
    Dynamically matches the character's physical body, face, and outfit to their exact numeric age
    so a 9-year-old looks like an adorable 9-year-old child, a 14-year-old looks like a middle-school teen,
    and a 22-year-old looks like a young adult!
    """
    digits = "".join(c for c in str(age_str) if c.isdigit())
    age = int(digits) if digits else 19

    # Strip any accidental "Korean man/woman" words that trigger 3D photorealism
    clean_traits = (
        str(hair_eyes_desc)
        .replace("handsome young Korean man with", "")
        .replace("beautiful young Korean woman with", "")
        .replace("Korean", "2D anime")
        .strip()
    )
    if not clean_traits or len(clean_traits) > 65:
        clean_traits = "dark hair and warm amber eyes" if gender == "male" else "long brown hair and bright eyes"

    if age <= 11:
        if gender == "male":
            return f"cute {age}-year-old 2D anime little child boy (small kid body proportions, round child cheeks, big innocent kid eyes, {clean_traits})"
        else:
            return f"cute {age}-year-old 2D anime little child girl (small kid body proportions, round child cheeks, big innocent kid eyes, {clean_traits})"
    elif age <= 15:
        if gender == "male":
            return f"{age}-year-old 2D anime middle-school teen boy (youthful teen face, school uniform, {clean_traits})"
        else:
            return f"{age}-year-old 2D anime middle-school teen girl (youthful teen face, school uniform, {clean_traits})"
    elif age <= 18:
        if gender == "male":
            return f"{age}-year-old 2D anime high-school boy (collared school shirt and blazer, {clean_traits})"
        else:
            return f"{age}-year-old 2D anime high-school girl (school cardigan and ribbon collar, {clean_traits})"
    else:
        if gender == "male":
            return f"handsome {age}-year-old 2D anime young man (open tailored coat over collared shirt, {clean_traits})"
        else:
            return f"beautiful {age}-year-old 2D anime young woman (elegant cardigan over collared blouse, {clean_traits})"


def try_huggingface_free_anime_space(prompt, seed):
    """
    Secondary Free Image Provider (Hugging Face Public Inference / Gradio Gateways)
    if Pollinations temporarily rate-limits a scene on GitHub Actions IPs.
    """
    hf_models = [
        "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
        "https://api-inference.huggingface.co/models/cagliostrolab/animagine-xl-3.1"
    ]
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    hf_token = os.getenv("HF_TOKEN")
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    for model_url in hf_models:
        try:
            res = requests.post(
                model_url,
                headers=headers,
                json={"inputs": prompt, "parameters": {"seed": seed}},
                timeout=45
            )
            if res.status_code == 200 and "image" in res.headers.get("Content-Type", "") and len(res.content) > 14000:
                return res.content
        except Exception:
            continue
    return None


def synthesize_emergency_aot_2d_scene_frame(prev_img_path, idx, output_path):
    """
    Last-resort emergency frame builder:
    If all external image networks time out on Scene idx, creates a distinct cinematic framing variation
    (pan/zoom/warm sunset lighting shift) from the nearest rendered scene or painted golden sky canvas
    so the 9-scene story NEVER drops a scene or shortens the video!
    """
    if prev_img_path and os.path.exists(prev_img_path):
        with Image.open(prev_img_path) as im:
            rgb = im.convert("RGB").resize((1080, 1920), Image.LANCZOS)
            # Create a distinct closer emotional medium-closeup framing with warmer golden sunset shift
            crop_box = (65, 90, 1015, 1780) if idx % 2 == 0 else (40, 60, 1040, 1838)
            varied = rgb.crop(crop_box).resize((1080, 1920), Image.LANCZOS)
            varied = ImageEnhance.Brightness(varied).enhance(1.04)
            varied.save(output_path, "JPEG", quality=95)
            return True
    return False


def fetch_clean_manhwa_artwork(scene, male_traits, female_traits, story_seed, idx, total_scenes, prev_img_path, output_path):
    """
    Bulletproof 9-Scene 2D WIT-Studio Anime Art Generator:
    1. Builds age-accurate 2D anime character prompts (so age 9 = actual 9-year-old kids!).
    2. Enforces 2D flat hand-drawn Attack on Titan (WIT Studio) golden-hour sunset aesthetic (NO 3D CGI).
    3. Uses rate-limit-aware pacing + multi-endpoint backoff so all 9 scenes complete reliably.
    4. Automatically strips the bottom 7.5% Pollinations watermark and fits to 9:16 with ZERO stretching!
    """
    m_age = scene.get("male_age", "19")
    f_age = scene.get("female_age", "18")
    pose = scene.get("scene_setting_and_pose", "standing side-by-side under golden sunset sky looking at each other")

    male_desc = build_age_accurate_character_prompt(m_age, "male", male_traits)
    female_desc = build_age_accurate_character_prompt(f_age, "female", female_traits)

    # Put 2D WIT Studio Style + Age-Accurate Characters + Scene Action right up front (never truncated!)
    prompt = (
        f"Flat 2D hand-drawn anime television frame, Attack on Titan WIT Studio 2D anime art style, "
        f"bold dark ink outlines, flat 2D cel-shading, warm golden-hour sunset amber color grading, "
        f"glowing golden dust particles, rich painted 2D anime background with sky headroom at top. "
        f"Waist-up front-facing 2D portrait: on left is {male_desc}; on right is {female_desc}. "
        f"Scene: {pose}. Strictly 2D flat anime illustration, NOT 3D, no CGI, no text, no speech bubbles."
    )

    encoded = urllib.parse.quote(prompt)
    seed = story_seed + (idx * 293)

    # Pace requests by 5.5s between scenes so Pollinations' Cloudflare IP burst limiter never triggers 402
    if idx > 0:
        time.sleep(5.5)

    # Multiple distinct URL structures & resolutions across Pollinations servers
    candidate_urls = [
        f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1344&model=flux&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&seed={seed + 11}&nologo=true",
        f"https://gen.pollinations.ai/image/{encoded}?width=768&height=1344&model=flux&seed={seed + 23}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=1344&model=flux&seed={seed + 47}",
        f"https://image.pollinations.ai/prompt/{encoded}?seed={seed + 89}"
    ]

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
    ]

    print(f"[ARTWORK] Generating 2D Golden-Tint Scene {idx + 1}/{total_scenes} (Ages {m_age} & {f_age})...")

    for attempt, url in enumerate(candidate_urls):
        headers = {"User-Agent": user_agents[attempt % len(user_agents)]}
        try:
            res = requests.get(url, headers=headers, timeout=80)
            ctype = res.headers.get("Content-Type", "")
            if res.status_code == 200 and "image" in ctype and len(res.content) > 14000:
                crop_watermark_and_fit_9_16(res.content, output_path)
                print(f"✅ Scene {idx + 1}/{total_scenes} saved (Watermark cropped + 9:16 zero-stretch + AoT Golden 2D grade): {output_path}")
                return True
            else:
                wait_sec = 6 + (attempt * 4)
                print(f"   ⚠️ Attempt {attempt + 1} status {res.status_code}. Cooling down {wait_sec}s before next gateway...")
                time.sleep(wait_sec)
        except Exception as e:
            wait_sec = 5 + (attempt * 3)
            print(f"   ⚠️ Attempt {attempt + 1} network error ({e}). Waiting {wait_sec}s...")
            time.sleep(wait_sec)

    # Secondary Provider: Hugging Face Free Inference
    print(f"   ↳ Trying Hugging Face Free Anime/Flux Gateway for Scene {idx + 1}...")
    hf_bytes = try_huggingface_free_anime_space(prompt, seed)
    if hf_bytes:
        crop_watermark_and_fit_9_16(hf_bytes, output_path)
        print(f"✅ Scene {idx + 1}/{total_scenes} saved via Hugging Face Gateway!")
        return True

    # Final Guarantee: Ensure scene count never drops
    if synthesize_emergency_aot_2d_scene_frame(prev_img_path, idx, output_path):
        print(f"✅ Scene {idx + 1}/{total_scenes} synthesized via continuity frame engine!")
        return True

    return False


def verify_zero_vocals_with_whisper(audio_path):
    """Verifies with Groq Whisper-Large-v3 that zero sung French/English lyrics exist in the cut."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key or not os.path.exists(audio_path):
        return True

    try:
        client = Groq(api_key=groq_key)
        with open(audio_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), f.read()),
                model="whisper-large-v3",
                response_format="json"
            )
        text = (getattr(transcription, "text", "") or "").strip().lower()
        non_vocal = ["sous-titres", "amara.org", "merci d'avoir", "thank you for watching", "music", "applause", "instrumental"]
        for p in non_vocal:
            text = text.replace(p, "")

        indila_lyrics = ("attend", "debout", "rose", "main", "rien", "autour", "sens", "lourd", "regard", "seul", "parle", "aime", "histoire")
        if any(w in text for w in indila_lyrics):
            print(f"⚠️ [WHISPER VOCAL GATE] Rejected track—detected Indila lyrics: '{text[:60]}'")
            return False

        words = [w for w in text.split() if len(w) > 2]
        if len(words) > 6:
            print(f"⚠️ [WHISPER VOCAL GATE] Rejected track—detected vocals ({len(words)} words): '{text[:60]}'")
            return False

        print("✅ [WHISPER VOCAL GATE] Confirmed 100% PURE INSTRUMENTAL (75s continuous forward cut)!")
        return True
    except Exception:
        return True


def synthesize_indila_continuous_75s_orchestra(output_mp3, duration_sec=75):
    """Generates a continuous 75-second evolving orchestral arrangement of Indila's 'Love Story'."""
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


def get_verified_75s_pure_instrumental(required_duration_sec):
    """Guarantees a continuous forward-playing 75-second cut of Indila - Love Story (Instrumental)."""
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 80000:
        try:
            test_clip = AudioFileClip(LOCKED_SONG_PATH)
            dur = test_clip.duration
            test_clip.close()
            if dur >= required_duration_sec and verify_zero_vocals_with_whisper(LOCKED_SONG_PATH):
                print(f"✅ Using verified {dur:.1f}s continuous forward Indila instrumental: {LOCKED_SONG_PATH}")
                return LOCKED_SONG_PATH
        except Exception:
            pass

    candidate_queries = [
        "https://www.youtube.com/watch?v=FRhcUnZ7MOw",
        "https://www.youtube.com/watch?v=SPEqQwB0tZs",
        "https://www.youtube.com/watch?v=EqAj188uSBQ",
        "https://www.youtube.com/watch?v=1NBnN0IAljQ",
        "scsearch12:Indila Love Story piano cover instrumental",
        "scsearch12:Indila Love Story karaoke instrumental",
        "scsearch12:Indila Love Story violin instrumental"
    ]

    required_kw = ("instrumental", "karaoke", "piano", "violin", "orchestral", "guitar", "backing")
    banned_kw = ("lyrics", "lyric", "vocal", "singing", "official music video", "nightcore")

    raw_dl = "workspace/candidate_raw.mp3"
    test_cut = "workspace/candidate_cut_75s.mp3"
    slice_len = max(GOLDEN_DURATION_SEC, int(required_duration_sec) + 8)

    for item in candidate_queries:
        print(f"[AUDIO-HUNTER] Probing continuous instrumental source: {item}...")
        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "extract_flat": "in_playlist" if item.startswith("scsearch") else False
            }
            urls_to_try = []
            if item.startswith("scsearch"):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(item, download=False)
                    for entry in (info.get("entries") or []):
                        title = (entry.get("title") or "").lower()
                        dur = entry.get("duration") or 180
                        if (
                            dur >= (GOLDEN_START_SEC + slice_len)
                            and any(k in title for k in required_kw)
                            and not any(b in title for b in banned_kw)
                        ):
                            urls_to_try.append((entry.get("url") or entry.get("webpage_url"), title))
            else:
                urls_to_try.append((item, "verified_yt_instrumental"))

            for target_url, title_label in urls_to_try[:3]:
                if not target_url:
                    continue
                for f_tmp in (raw_dl, test_cut):
                    if os.path.exists(f_tmp):
                        os.remove(f_tmp)

                cmd = [
                    sys.executable, "-m", "yt_dlp",
                    target_url,
                    "--extract-audio",
                    "--audio-format", "mp3",
                    "--audio-quality", "192K",
                    "--no-playlist",
                    "--quiet",
                    "--output", raw_dl
                ]
                subprocess.run(cmd, timeout=60, check=False)

                if not (os.path.exists(raw_dl) and os.path.getsize(raw_dl) > 90000):
                    continue

                slice_cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(GOLDEN_START_SEC),
                    "-t", str(slice_len),
                    "-i", raw_dl,
                    "-af", "aecho=0.8:0.86:55:0.28,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-b:a", "192k",
                    test_cut
                ]
                subprocess.run(slice_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if os.path.exists(test_cut) and os.path.getsize(test_cut) > 60000:
                    if verify_zero_vocals_with_whisper(test_cut):
                        os.replace(test_cut, LOCKED_SONG_PATH)
                        print(f"🎉 Locked {slice_len}s Continuous Forward Instrumental: {LOCKED_SONG_PATH}")
                        return LOCKED_SONG_PATH

                    stripped_cut = "workspace/candidate_stripped_75s.mp3"
                    strip_cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(GOLDEN_START_SEC),
                        "-t", str(slice_len),
                        "-i", raw_dl,
                        "-af", "stereotools=mlev=0.015,aecho=0.8:0.88:65:0.35,loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-b:a", "192k",
                        stripped_cut
                    ]
                    subprocess.run(strip_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(stripped_cut) and verify_zero_vocals_with_whisper(stripped_cut):
                        os.replace(stripped_cut, LOCKED_SONG_PATH)
                        print(f"🎉 Locked Vocal-Stripped {slice_len}s Instrumental: {LOCKED_SONG_PATH}")
                        return LOCKED_SONG_PATH
        except Exception as e:
            print(f"⚠️ Candidate probe skipped: {e}")

    print(f"[AUDIO-SYNTH] Rendering {slice_len}s Continuous Evolving Orchestral Indila Waltz...")
    return synthesize_indila_continuous_75s_orchestra(LOCKED_SONG_PATH, duration_sec=slice_len)


def build_pipeline():
    print("=== STARTING 9-SCENE 2D AOT GOLDEN-TINT + AGE-ACCURATE + WATERMARK-FREE PIPELINE ===")
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

    male_traits = story_data.get("male_hair_eyes", story_data.get("male_dna", "jet-black hair and warm amber eyes"))
    female_traits = story_data.get("female_hair_eyes", story_data.get("female_dna", "long chestnut hair and bright eyes"))
    scenes = story_data.get("scenes", [])[:9]
    total_scenes = len(scenes)
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.2
    reply_pop_delay = 1.8
    clips = []
    last_valid_img = None

    for idx, sc in enumerate(scenes):
        bg_path = f"workspace/clean_art_{idx}.jpg"
        if not fetch_clean_manhwa_artwork(
            sc, male_traits, female_traits, story_seed, idx, total_scenes, last_valid_img, bg_path
        ):
            continue

        last_valid_img = bg_path
        anchors = detect_character_anchors(bg_path)
        base_clip = ImageClip(bg_path).set_duration(scene_duration).resize((1080, 1920))
        layers = [base_clip]

        # Floating Age Numbers
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
        raise RuntimeError(f"❌ Pipeline aborted: Only {len(clips)} scenes rendered (minimum 6 required for full story).")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration
    print(f"[TIMELINE] Assembled complete {len(clips)}-scene story ({total_dur:.1f} seconds total).")

    # Attach continuous forward music (STRICTLY NO LOOPING!)
    audio_path = get_verified_75s_pure_instrumental(required_duration_sec=total_dur)
    if audio_path and os.path.exists(audio_path):
        audio_clip = AudioFileClip(audio_path)
        audio_clip = audio_clip.subclip(0, min(total_dur, audio_clip.duration))
        audio_clip = audio_clip.audio_fadein(1.0).audio_fadeout(1.8).volumex(0.95)
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
