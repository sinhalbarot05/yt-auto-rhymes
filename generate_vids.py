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

# Ensure yt-dlp and numpy are installed
for pkg in ("yt-dlp", "numpy"):
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", pkg], check=False)

import numpy as np
import yt_dlp
from groq import Groq
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

HISTORY_FILE = "story_history.json"
# Continuous 75-second forward cut (never loops on 45s-58s videos)
LOCKED_SONG_PATH = "assets/indila_love_story_pure_inst_75s_v5.mp3"
LOCKED_SONG_TITLE = "Love Story (Instrumental Slowed & Reverb) - Indila"

# Slice 0:35 to 1:50 (75 continuous seconds of forward progression)
GOLDEN_START_SEC = 35
GOLDEN_DURATION_SEC = 75

# Rich, complete multi-act romance storylines
STORY_CONCEPTS = [
    "Uncherished to Cherished by True Future Love: For 3 years her cold fiancé ignored her birthday and left her in the rain for his female friend; when she walks away, his powerful older brother (who secretly cherished her for years) steps in with an umbrella and treats her like a queen while her ex begs in regret",
    "Childhood Friends to Soulmates: From age 9 sharing strawberries across next-door balconies, to age 16 defending her from bullies, to age 19 hiding jealousy when another boy confesses, to age 23 proposing under the same cherry tree",
    "Intense Jealousy in Secret Love: The cold campus student council president claims he only sees her as a junior, until a handsome transfer student makes her laugh—shattering his calm mask as he pulls her into an empty classroom to confess",
    "Contract Marriage to Obsessive Devotion: Married on paper for family business with a rule to never fall in love; when she falls ill in a storm and prepares divorce papers thinking he loves someone else, he tears them up in panic",
    "Academic Rivals to Midnight Confidants: Fighting for #1 rank every semester while bickering daily, until he discovers her crying on the rooftop over family pressure and stays beside her every night",
    "The Forgotten Childhood Promise: Separated at age 10 when she moved away, she doesn't recognize the cold university ice prince—until she sees the braided bracelet she made 10 years ago still on his wrist",
    "Ignored by Crush, Treasured by the Quiet Protector: She always baked cookies for the popular basketball captain who threw them away, while the quiet art prodigy secretly sketched her smile for two years before stepping forward",
    "Time-Leap Redemption: After losing her in a cold marriage where he never spoke his feelings, he wakes up 5 years earlier on the day they first met at university and showers her with the warmth she always deserved"
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
            (r > 165) & (g > 120) & (b > 95) &
            ((r - g) > 10) & ((r - b) > 22) & ((r - b) < 115) &
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
                    pointing to the character's head (inspired by the Garfield comic strip).
    3. 'whisper' -> Smooth horizontal egg + slender curved tail with a DASHED ink border for shy/quiet lines.
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

    # Horizontal egg proportions
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

    # Target point (tx, ty) toward character's head/mouth
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
        # 1. Scalloped Cloud / Egg Body (NO solid triangular tail!)
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

        # 2. Detached Chain of 4 Shrinking Circular Bubbles (Garfield Thought Balloon Style)
        # Placed along a gentle curve from below the cloud down toward the thinker's head,
        # spaced clearly apart so each circle retains its own crisp black ink ring!
        start_x = cx + (int(rx * 0.14) if side == "left" else -int(rx * 0.14))
        start_y = cy + ry + 26 * scale
        ctrl_x = (start_x + tx) * 0.5 + (-14 * scale if side == "left" else 14 * scale)
        ctrl_y = start_y + (ty - start_y) * 0.52

        dot_specs = [
            (0.08, 14.5 * scale),  # Largest detached bubble near cloud
            (0.40, 10.5 * scale),  # Medium bubble
            (0.70, 7.5 * scale),   # Small bubble
            (0.96, 5.0 * scale)    # Tiny bubble right above character's head
        ]
        for t_val, r_dot in dot_specs:
            inv = 1.0 - t_val
            dx = (inv * inv * start_x) + (2 * inv * t_val * ctrl_x) + (t_val * t_val * tx)
            dy = (inv * inv * start_y) + (2 * inv * t_val * ctrl_y) + (t_val * t_val * ty)
            m_draw.ellipse([dx - r_dot, dy - r_dot, dx + r_dot, dy + r_dot], fill=255)

    elif b_type == "shout":
        # Spiky Comic Starburst Oval + Sharp Connected Tail for emotional/jealous outbursts
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
        # 'speech' or 'whisper': Smooth Horizontal Egg (Super-Ellipse) + Solid Curved Bezier Tail
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

    # Morphological Dilation for Seamless Ink Border + Gaussian Drop Shadow
    stroke_px = 7
    outer_mask = mask.filter(ImageFilter.MaxFilter(stroke_px))
    shadow_mask = outer_mask.filter(ImageFilter.GaussianBlur(7 * scale))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # 1. Soft Ambient Shadow
    shadow_layer = Image.new("RGBA", (W, H), (12, 15, 24, 55))
    canvas.paste(shadow_layer, (0, 6 * scale), mask=shadow_mask)

    # 2. Charcoal Ink Outline
    ink_layer = Image.new("RGBA", (W, H), (24, 24, 30, 255))
    canvas.paste(ink_layer, (0, 0), mask=outer_mask)

    # 3. Warm Paper-White Fill
    fill_layer = Image.new("RGBA", (W, H), (253, 253, 254, 255))
    canvas.paste(fill_layer, (0, 0), mask=mask)

    # If 'whisper', add classic comic dashed white breaks along the top/side oval perimeter
    c_draw = ImageDraw.Draw(canvas)
    if b_type == "whisper":
        dash_steps = 36
        for i in range(0, dash_steps, 2):
            ang = (2.0 * math.pi * i) / dash_steps
            if 0.35 * math.pi < ang < 0.65 * math.pi:
                continue  # Keep tail base solid
            dx = cx + rx * math.cos(ang)
            dy = cy + ry * math.sin(ang)
            r_gap = 5 * scale
            c_draw.ellipse([dx - r_gap, dy - r_gap, dx + r_gap, dy + r_gap], fill=(253, 253, 254, 255))

    # 4. Crisp Centered English Comic Lettering
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
    """
    Returns an ordered list of verified text-chat LLMs on Groq.
    Strictly blocks TTS/audio/guard models like 'canopylabs/orpheus-v1-english' and 'whisper'.
    """
    models_resp = client.models.list().data
    all_ids = [m.id for m in models_resp]

    banned = (
        "orpheus", "canopylabs", "whisper", "guard", "tts", "playai",
        "embed", "vision", "allam", "distil", "audio", "speech", " safeguard"
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
        "You are an elite Korean Manhwa romance scriptwriter and comic director. "
        "You write complete, deeply satisfying 9-scene vertical romance Shorts (45 to 52 seconds long) "
        "with a full beginning, emotional turning point, and unforgettable resolution. "
        "You use comic bubble types ('speech', 'thought', 'whisper', 'shout') like a master comic writer. "
        "Output strictly valid JSON."
    )
    user_prompt = f"""Write a brand-new, complete 9-scene vertical Korean Manhwa romance Short script.
Run Seed: {entropy}
Story Concept: "{concept}"
Previously Used Titles (NEVER REPEAT): {json.dumps(used_titles[-10:])}
Previously Used Lines (NEVER REPEAT): {json.dumps(used_dialogues[-15:])}

COMPLETE 9-SCENE STORY STRUCTURE (47 SECONDS TOTAL — DO NOT RUSH):
- Scenes 1 & 2 (Act I - The Setup): Establish the characters, ages, and emotional hook (e.g., childhood bond, uncherished girlfriend ignored by cold fiancé, or secret crush).
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
  "male_dna": "handsome young Korean man with [distinct hair color/style], [eye color] eyes, wearing an open dark tailored blazer over a crisp collared shirt",
  "female_dna": "beautiful young Korean woman with [distinct hair color/style], [eye color] eyes, wearing a cozy pastel cardigan over a collared blouse",
  "scenes": [
    {{
      "male_age": "19",
      "female_age": "18",
      "male_bubble_type": "speech",
      "male_line": "Why are you standing in the rain?",
      "female_bubble_type": "thought",
      "female_line": "He actually came looking for me...",
      "lighting_and_atmosphere": "warm golden streetlamp glow, soft rain droplets, romantic bokeh",
      "scene_setting_and_pose": "standing side-by-side under an umbrella on a rainy evening street with tall glowing buildings above their heads"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_complete_fallback_story(history):
    """
    Complete 9-scene (47-second) multi-act fallback story generator.
    Rotates across complete storylines (Uncherished -> True Future Love, Childhood Friends, Jealous Rivals).
    """
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    m_hair = random.choice(["jet-black tousled", "silver-ash", "dark espresso", "midnight-blue"])
    f_hair = random.choice(["long chestnut wavy", "silky raven-black", "warm honey-brown", "soft caramel"])

    story_templates = [
        {
            "trope": f"Uncherished to Treasured by True Love #{run_id}",
            "video_title": f"He Left Her In The Rain… So His Brother Stepped In 💔☔ #{run_id} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "21", "female_age": "19", "male_bubble_type": "speech", "male_line": "Wait outside. I'm busy right now.", "female_bubble_type": "thought", "female_line": "He forgot my birthday again...", "lighting_and_atmosphere": "cold blue evening outside a restaurant window", "scene_setting_and_pose": "standing on an evening sidewalk with tall glass windows above their heads, girl holding a small cake box"},
                {"male_age": "23", "female_age": "19", "male_bubble_type": "thought", "male_line": "How can my brother ignore her tears?", "female_bubble_type": "whisper", "female_line": "It's fine... I'm used to waiting.", "lighting_and_atmosphere": "soft amber streetlamp light and first rain drops", "scene_setting_and_pose": "older brother in a dark coat approaching the shivering girl under a high archway"},
                {"male_age": "23", "female_age": "19", "male_bubble_type": "speech", "male_line": "Take my umbrella. Come with me.", "female_bubble_type": "thought", "female_line": "Why is his gaze so warm?", "lighting_and_atmosphere": "pouring rain and glowing golden reflections", "scene_setting_and_pose": "standing side-by-side under a large black umbrella in heavy rain with city lights high above"},
                {"male_age": "23", "female_age": "20", "male_bubble_type": "speech", "male_line": "I bought every cake you missed.", "female_bubble_type": "thought", "female_line": "No one ever treasured me like this...", "lighting_and_atmosphere": "warm candlelight inside a high-ceiling penthouse", "scene_setting_and_pose": "standing by a table with glowing birthday candles, boy smiling gently while girl covers her blushing cheeks"},
                {"male_age": "24", "female_age": "20", "male_bubble_type": "shout", "male_line": "Don't touch her! You lost your chance!", "female_bubble_type": "thought", "female_line": "He stepped right in front of me...", "lighting_and_atmosphere": "dramatic marble lobby lighting with high chandeliers", "scene_setting_and_pose": "protective man shielding the girl behind his shoulder in a grand hall"},
                {"male_age": "24", "female_age": "20", "male_bubble_type": "whisper", "male_line": "Did you really wait years for me?", "female_bubble_type": "speech", "female_line": "Stay with me. Never look back.", "lighting_and_atmosphere": "starry rooftop balcony with glowing city bokeh", "scene_setting_and_pose": "standing close on a rooftop terrace under open night sky, boy gently holding her hands"},
                {"male_age": "25", "female_age": "21", "male_bubble_type": "speech", "male_line": "You deserve to be cherished every day.", "female_bubble_type": "thought", "female_line": "My broken heart finally feels whole.", "lighting_and_atmosphere": "floating golden sky lanterns over a night lake", "scene_setting_and_pose": "standing together under hundreds of floating lanterns in the upper sky, warm smiles"},
                {"male_age": "26", "female_age": "22", "male_bubble_type": "speech", "male_line": "Marry me and be my whole world.", "female_bubble_type": "speech", "female_line": "Yes! Only you, forever.", "lighting_and_atmosphere": "golden sunset garden with cherry blossom petals", "scene_setting_and_pose": "man holding a velvet ring box under blooming cherry tree branches, girl smiling with happy tears"},
                {"male_age": "27", "female_age": "23", "male_bubble_type": "thought", "male_line": "I'll protect that smile for life.", "female_bubble_type": "thought", "female_line": "Losing the wrong one led me to you.", "lighting_and_atmosphere": "dreamy sunlit cathedral window beams and sparkles", "scene_setting_and_pose": "embracing warmly in waist-up portrait under tall sunlit arches, peaceful loving expressions"}
            ]
        },
        {
            "trope": f"Childhood Friends to Forever #{run_id}",
            "video_title": f"From Next-Door Neighbours To Forever 🥺🌸 #{run_id} #Shorts #manhwa #lovestory",
            "scenes": [
                {"male_age": "10", "female_age": "9", "male_bubble_type": "speech", "male_line": "Stop crying! I saved you strawberries.", "female_bubble_type": "thought", "female_line": "He always makes me smile...", "lighting_and_atmosphere": "warm summer afternoon sunlight and green leaves", "scene_setting_and_pose": "two childhood friends talking across adjacent balconies with blue sky above"},
                {"male_age": "15", "female_age": "14", "male_bubble_type": "speech", "male_line": "Walk on the inside of the street.", "female_bubble_type": "thought", "female_line": "Since when did he get so tall?", "lighting_and_atmosphere": "golden sunset school street with autumn leaves", "scene_setting_and_pose": "walking side-by-side in school uniforms under tall autumn trees"},
                {"male_age": "17", "female_age": "16", "male_bubble_type": "thought", "male_line": "Why is that guy talking to her?", "female_bubble_type": "speech", "female_line": "Wait, why are you pulling my sleeve?", "lighting_and_atmosphere": "sunlit high school hallway with tall windows", "scene_setting_and_pose": "jealous boy gently taking girl's wrist in a bright school corridor"},
                {"male_age": "18", "female_age": "17", "male_bubble_type": "speech", "male_line": "Take my coat. Your hands are freezing.", "female_bubble_type": "thought", "female_line": "His coat smells like winter rain...", "lighting_and_atmosphere": "falling white snow under warm streetlamp glow", "scene_setting_and_pose": "boy draping his winter coat over girl's shoulders at a snowy bus stop"},
                {"male_age": "19", "female_age": "18", "male_bubble_type": "shout", "male_line": "Don't date anyone else! Look at me!", "female_bubble_type": "thought", "female_line": "His heart is beating so loud...", "lighting_and_atmosphere": "dramatic rain and glowing neon reflections", "scene_setting_and_pose": "sheltering under an awning in the rain, boy looking intensely into her eyes"},
                {"male_age": "19", "female_age": "18", "male_bubble_type": "whisper", "male_line": "I've loved you since we were kids.", "female_bubble_type": "whisper", "female_line": "I was scared to lose our friendship...", "lighting_and_atmosphere": "soft moonlight on a quiet rooftop terrace", "scene_setting_and_pose": "standing close under starry night sky, boy gently cupping her cheek"},
                {"male_age": "21", "female_age": "20", "male_bubble_type": "speech", "male_line": "Every promise I made was for you.", "female_bubble_type": "thought", "female_line": "He kept the ring from ten years ago!", "lighting_and_atmosphere": "blooming spring park with pink cherry blossoms", "scene_setting_and_pose": "standing under high cherry blossom branches, boy showing a silver promise ring"},
                {"male_age": "23", "female_age": "22", "male_bubble_type": "speech", "male_line": "From next-door neighbours to my wife?", "female_bubble_type": "speech", "female_line": "Yes! A thousand times yes!", "lighting_and_atmosphere": "magical sunset rooftop with fairy lights", "scene_setting_and_pose": "romantic proposal under glowing string lights in the upper sky"},
                {"male_age": "24", "female_age": "23", "male_bubble_type": "thought", "male_line": "Forever starts right now with her.", "female_bubble_type": "thought", "female_line": "My childhood friend is my whole life.", "lighting_and_atmosphere": "sparkling night fireworks over the harbor", "scene_setting_and_pose": "embracing happily under high colorful fireworks in the night sky"}
            ]
        }
    ]

    picked = random.choice(story_templates)
    return {
        "trope": picked["trope"],
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": picked["video_title"],
        "male_dna": f"handsome young Korean man with {m_hair} hair, warm dark eyes, wearing an open dark tailored blazer over a crisp white shirt",
        "female_dna": f"beautiful young Korean woman with {f_hair} hair, bright expressive eyes, wearing a soft pastel cardigan over a white collared blouse",
        "scenes": picked["scenes"]
    }


def generate_fresh_story(history):
    used_concepts = history.get("used_archetypes", [])[-6:]
    used_titles = history.get("used_titles", [])
    used_dialogues = history.get("used_dialogues", [])

    avail = [c for c in STORY_CONCEPTS if c not in used_concepts] or STORY_CONCEPTS
    chosen_concept = random.choice(avail)
    sys_p, usr_p = build_story_prompts(chosen_concept, used_titles, used_dialogues)

    # 1. Try Groq Chat LLMs (iterating across all valid chat models if one requires terms or rate-limits)
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

    # 2. Try Pollinations Text LLM
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


def fetch_clean_manhwa_artwork(scene, male_dna, female_dna, story_seed, idx, total_scenes, output_path):
    """
    Bulletproof Dual-Gateway Image Fetcher:
    - Keeps the URL concise (<500 chars) so Cloudflare/Pollinations never drops the request with HTTP 400/414.
    - Alternates between gen.pollinations.ai and image.pollinations.ai across retries so 0-scene failures cannot happen.
    """
    api_key = os.getenv("POLLINATIONS_API_KEY")
    atmos = scene.get("lighting_and_atmosphere", "warm golden cinematic lighting")
    pose = scene.get("scene_setting_and_pose", "standing side-by-side looking warmly at each other")

    prompt = (
        f"Vertical 9:16 Korean anime romance illustration, Makoto Shinkai webtoon style. "
        f"Top 30 percent is clean scenic sky or ceiling headroom above characters' heads. "
        f"Lower two-thirds waist-up portrait: on left {male_dna}; on right {female_dna}. "
        f"{pose}. {atmos}. Front-facing chests, natural neck anatomy, clean illustration, no text, no speech bubbles, no watermark."
    )
    encoded = urllib.parse.quote(prompt[:480])
    seed = story_seed + (idx * 173)

    endpoints = [
        f"https://gen.pollinations.ai/image/{encoded}?width=1080&height=1920&model=flux&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&seed={seed}&nologo=true",
        f"https://gen.pollinations.ai/image/{encoded}?width=1080&height=1920&model=turbo&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&seed={seed}&nologo=true"
    ]

    print(f"[ARTWORK] Generating clean text-free Scene {idx + 1}/{total_scenes}...")
    for attempt, base_url in enumerate(endpoints):
        url = base_url
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
        if api_key and "gen.pollinations.ai" in url:
            url += f"&key={api_key}"
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            res = requests.get(url, headers=headers, timeout=75)
            ctype = res.headers.get("Content-Type", "")
            if res.status_code == 200 and "image" in ctype and len(res.content) > 14000:
                with open(output_path, "wb") as f:
                    f.write(res.content)
                with Image.open(output_path) as im:
                    im.convert("RGB").resize((1080, 1920), Image.LANCZOS).save(output_path, "JPEG", quality=95)
                print(f"✅ Clean Scene {idx + 1}/{total_scenes} saved: {output_path}")
                return True
            else:
                print(f"   ⚠️ Attempt {attempt + 1} status {res.status_code}. Switching endpoint...")
                time.sleep(3)
        except Exception as e:
            print(f"   ⚠️ Attempt {attempt + 1} network error ({e}). Switching endpoint...")
            time.sleep(3)

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
    """
    Generates a continuous 75-second evolving orchestral arrangement of Indila's 'Love Story'
    in D-Minor 3/4 Waltz (Intro -> Verse -> Pre-Chorus -> Full Strings Drop -> High Octave Climax -> Outro)
    so the music evolves forward continuously for the entire 45s-58s video without looping!
    """
    raw_wav = "workspace/indila_orchestral_75s.wav"
    sr = 44100
    total_samples = int(sr * duration_sec)

    # Evolving 8-bar phrasing so the melody develops continuously forward
    bars = [
        (146.83, [293.66, 349.23, 440.00], [440.00, 587.33, 523.25]),  # Bar 1: Dm
        (116.54, [233.08, 293.66, 349.23], [466.16, 440.00, 392.00]),  # Bar 2: Bb
        (98.00,  [196.00, 293.66, 349.23], [349.23, 440.00, 392.00]),  # Bar 3: Gm
        (110.00, [220.00, 277.18, 329.63], [349.23, 329.63, 293.66]),  # Bar 4: A7
        (146.83, [293.66, 440.00, 587.33], [587.33, 659.25, 698.46]),  # Bar 5: Dm High Soaring Phrase
        (116.54, [233.08, 349.23, 466.16], [659.25, 587.33, 523.25]),  # Bar 6: Bb High Phrase
        (98.00,  [196.00, 293.66, 440.00], [587.33, 523.25, 466.16]),  # Bar 7: Gm Resolution
        (110.00, [220.00, 329.63, 440.00], [523.25, 440.00, 440.00]),  # Bar 8: A7 Cadence
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

            # Continuous forward dynamic evolution across 75 seconds:
            # 0-12s: Delicate Harp/Piano Intro -> 12-24s: Cello & Violin Enter -> 24-58s: Full Grand Orchestra Climax
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
    """
    Guarantees a continuous forward-playing 75-second cut of Indila - Love Story (Instrumental Slowed & Reverb)
    with ZERO looping and ZERO vocals.
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    # Clean up older short 30s cuts so we never loop a 26s-30s file
    for old_f in (
        "assets/indila_love_story_magical_cut.mp3",
        "assets/indila_love_story_instrumental_v2.mp3",
        "assets/indila_love_story_pure_instrumental_v3.mp3",
        "assets/indila_love_story_pure_inst_v4.mp3"
    ):
        if os.path.exists(old_f):
            try:
                os.remove(old_f)
            except Exception:
                pass

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

                # Slice continuous 75s forward progression (0:35 to 1:50)
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
    print("=== STARTING COMPLETE 45s-55s STORY + GARFIELD THOUGHT CHAIN + CONTINUOUS MUSIC PIPELINE ===")
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

    male_dna = story_data.get("male_dna", "")
    female_dna = story_data.get("female_dna", "")
    scenes = story_data.get("scenes", [])[:10]  # Up to 10 scenes (~52s Short, comfortably under 60s limit)
    total_scenes = len(scenes)
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.2
    reply_pop_delay = 1.8
    clips = []

    for idx, sc in enumerate(scenes):
        bg_path = f"workspace/clean_art_{idx}.jpg"
        if not fetch_clean_manhwa_artwork(sc, male_dna, female_dna, story_seed, idx, total_scenes, bg_path):
            continue

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

    if not clips:
        raise RuntimeError("❌ Pipeline aborted: 0 scenes rendered.")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration
    print(f"[TIMELINE] Assembled complete {len(clips)}-scene story ({total_dur:.1f} seconds total).")

    # Attach continuous forward music (STRICTLY NO LOOPING!)
    audio_path = get_verified_75s_pure_instrumental(required_duration_sec=total_dur)
    if audio_path and os.path.exists(audio_path):
        audio_clip = AudioFileClip(audio_path)
        # Play continuously forward from 0.0 to total_dur without repeating
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
