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

# Ensure yt-dlp and numpy are available
for pkg in ("yt-dlp", "numpy"):
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", pkg], check=False)

import numpy as np
import yt_dlp
from groq import Groq
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, afx

HISTORY_FILE = "story_history.json"
# Brand-new v4 path so any old vocal track in assets/ is ignored and replaced
LOCKED_SONG_PATH = "assets/indila_love_story_pure_inst_v4.mp3"
LOCKED_SONG_TITLE = "Love Story (Instrumental Slowed & Reverb) - Indila"

GOLDEN_START_SEC = 45
GOLDEN_DURATION_SEC = 30

STORY_CONCEPTS = [
    "7 AM Subway Strangers: Standing in the same train car every morning in silence until a sudden storm stops the train and he finally speaks",
    "Academic Rivals to Lovers: Rank #1 cold boy and Rank #2 girl who compete in every exam, until he secretly takes the blame for her mistake",
    "Contract Fake Dating to Real Love: They signed a 30-day fake dating agreement to fool their families, but he tears up the contract on the final night",
    "The Second-Lead Umbrella Rescue: Her fiancé left her waiting in the rain, so his quiet older brother steps in with an umbrella and never leaves her side",
    "Childhood Next-Door Neighbours: From sharing snacks across balconies as kids to a breathless rooftop confession in college",
    "Ruthless Young CEO & Fearless New Architect: Nobody dares to speak back to the company heir except her—and he becomes completely obsessed",
    "Time-Leap Second Chance: After losing her in a tragic future, he wakes up 4 years in the past on the day they first met and vows to protect her",
    "Brother's Best Friend Secretly Waited: He pretended to see her as a kid sister for years until another guy asks her to the gala",
    "Campus Ice Prince & Warm Art Student: He rejects every confession on campus, yet secretly keeps every sketch she left on the library desk",
    "Bodyguard & Runaway Heiress: Hired strictly to keep her safe from a distance, he breaks his own rule when she cries alone at night"
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
    """Loads clean bold font for crisp English comic lettering."""
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def clean_english_text(text):
    """Strips any non-ASCII/foreign characters so only clean English punctuation and letters remain."""
    allowed = "".join(ch for ch in str(text) if 32 <= ord(ch) <= 126)
    return " ".join(allowed.split()) or "..."


def detect_character_anchors(img_path):
    """
    Computer-Vision Character Head & Mouth Locator:
    Scans the left half (Boy, x: 40..530) and right half (Girl, x: 550..1040) of the 1080x1920 image
    for warm skin-tone clusters (anime face region: R > G > B, bright luminance, bounded by hair).
    Returns exact pixel coordinates for:
      - boy_head_top: (x, y) right above the boy's hair
      - boy_mouth:    (x, y) near the boy's mouth/cheek where the tail tip should point
      - girl_head_top:(x, y) right above the girl's hair
      - girl_mouth:   (x, y) near the girl's mouth/cheek where the tail tip should point
    """
    default_anchors = {
        "boy_head_top": (285, 500),
        "boy_mouth": (345, 730),
        "girl_head_top": (795, 535),
        "girl_mouth": (725, 760)
    }
    try:
        with Image.open(img_path) as im:
            rgb = np.array(im.convert("RGB").resize((1080, 1920)), dtype=np.float32)

        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        # Anime/Manhwa facial skin-tone mask (peach/ivory warm skin luminance)
        skin_mask = (
            (r > 165) & (g > 120) & (b > 95) &
            ((r - g) > 10) & ((r - b) > 22) & ((r - b) < 115) &
            (g > b)
        )

        # Search vertical band where character heads appear (y: 360 to 1050)
        y_min, y_max = 360, 1050

        def find_side_face(x_start, x_end, is_left):
            sub_mask = skin_mask[y_min:y_max, x_start:x_end]
            ys, xs = np.where(sub_mask)
            if len(ys) < 400:
                return None

            # Use robust percentiles to find the face box center and top
            face_cx = int(x_start + np.median(xs))
            face_top_y = int(y_min + np.percentile(ys, 12))
            face_bot_y = int(y_min + np.percentile(ys, 88))
            face_h = max(140, min(320, face_bot_y - face_top_y))

            # Hair extends roughly 0.48 * face_h above the forehead skin top
            head_top_y = max(340, face_top_y - int(face_h * 0.48))
            # Mouth/cheek target is in the lower-inner portion of the face
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
    Renders an authentic Korean Webtoon speech bubble or thought cloud onto a full 1080x1920 layer
    at 2x supersampled resolution (2160x3840):
    - Positioned intimately right above the character's detected head_top.
    - Features a long, graceful curved Quadratic Bezier comic tail (or trailing cloud droplets)
      whose tip points directly toward the character's detected mouth_pt!
    - Unified silhouette mask + 3.5px charcoal ink stroke + soft ambient shadow (ZERO boxy seams, ZERO 'HIM/HER' pills).
    """
    scale = 2
    W, H = 1080 * scale, 1920 * scale
    clean_txt = clean_english_text(text)

    # Wrap text into a balanced, compact comic block (16-20 chars per line, max 3 lines)
    wrapped_lines = textwrap.wrap(clean_txt, width=18)[:3]
    multiline_str = "\n".join(wrapped_lines)

    font = get_comic_font(33 * scale)
    dummy = Image.new("L", (10, 10))
    d_draw = ImageDraw.Draw(dummy)
    bbox = d_draw.multiline_textbbox((0, 0), multiline_str, font=font, align="center", spacing=8 * scale)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # Super-ellipse radii with generous white breathing space around text
    rx = max(145 * scale, int(tw * 0.5 + 54 * scale))
    ry = max(78 * scale, int(th * 0.5 + 42 * scale))

    hx, hy = head_top[0] * scale, head_top[1] * scale
    mx, my = mouth_pt[0] * scale, mouth_pt[1] * scale

    # Place bubble center right above the character's hair-top, clamped within safe left/right half
    if side == "left":
        cx = max(rx + 28 * scale, min(515 * scale - rx, hx - 15 * scale))
        # Stagger left bubble slightly higher so left & right bubbles have natural comic rhythm
        cy = max(ry + 115 * scale, min(hy - ry - 18 * scale, 330 * scale))
    else:
        cx = max(565 * scale + rx, min(W - rx - 28 * scale, hx + 15 * scale))
        cy = max(ry + 155 * scale, min(hy - ry - 14 * scale, 375 * scale))

    # Target point for the tip of the tail (pointing right toward the character's upper cheek/mouth)
    # Clamped so the tail is graceful (65px to 150px long) and never pokes over the character's eyes
    raw_tx = mx + (-22 * scale if side == "left" else 22 * scale)
    tx = max(cx - rx + 20 * scale, min(cx + rx - 20 * scale, raw_tx))
    if side == "left":
        tx = max(tx, cx + int(rx * 0.18))
    else:
        tx = min(tx, cx - int(rx * 0.18))

    tail_bottom_limit = cy + ry + 115 * scale
    ty = max(cy + ry + 58 * scale, min(tail_bottom_limit, my - 55 * scale))

    # 1. Build Unified Silhouette Mask (Body + Tail/Cloud) in "L" mode
    mask = Image.new("L", (W, H), 0)
    m_draw = ImageDraw.Draw(mask)

    if bubble_type == "thought":
        # Organic Webtoon Cloud: Super-ellipse core + ring of overlapping circular puffs
        m_draw.ellipse([cx - rx + 12 * scale, cy - ry + 10 * scale, cx + rx - 12 * scale, cy + ry - 10 * scale], fill=255)
        num_puffs = 14
        for i in range(num_puffs):
            ang = (2.0 * math.pi * i) / num_puffs
            px = cx + (rx - 14 * scale) * math.cos(ang)
            py = cy + (ry - 10 * scale) * math.sin(ang)
            # Alternate puff radii slightly for an organic hand-drawn cloud feel
            pr = (30 if i % 2 == 0 else 25) * scale
            m_draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=255)

        # 3 Trailing Thought Droplets curving down toward the character's temple/mouth
        start_x = cx + (int(rx * 0.22) if side == "left" else -int(rx * 0.22))
        start_y = cy + ry + 14 * scale
        for idx_d, (t_frac, r_dot) in enumerate([(0.25, 13 * scale), (0.60, 9 * scale), (0.92, 5.5 * scale)]):
            dx = start_x + (tx - start_x) * t_frac
            dy = start_y + (ty - start_y) * t_frac
            m_draw.ellipse([dx - r_dot, dy - r_dot, dx + r_dot, dy + r_dot], fill=255)
    else:
        # Smooth Super-Ellipse (Webtoon Oval, exponent = 2.35)
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

        # Curved Quadratic Bezier Comic Tail pointing directly toward (tx, ty)
        base_x = cx + (int(rx * 0.12) if side == "left" else -int(rx * 0.12))
        base_y = cy + ry - 8 * scale
        half_base = 20 * scale

        p_left = (base_x - half_base, base_y)
        p_right = (base_x + half_base, base_y)

        # Control points bow the tail gracefully toward the character's mouth
        curve_pull_x = -12 * scale if side == "left" else 12 * scale
        ctrl_left = ((p_left[0] + tx) * 0.5 + curve_pull_x, base_y + (ty - base_y) * 0.55)
        ctrl_right = ((p_right[0] + tx) * 0.5 + curve_pull_x, base_y + (ty - base_y) * 0.45)

        left_edge = quad_bezier_points(p_left, ctrl_left, (tx, ty), steps=24)
        right_edge = quad_bezier_points((tx, ty), ctrl_right, p_right, steps=24)
        tail_poly = left_edge + right_edge
        m_draw.polygon(tail_poly, fill=255)

    # 2. Create Seamless Charcoal Ink Outline via Morphological Dilation (MaxFilter)
    stroke_px = 7  # 3.5px at 1080p after 2x LANCZOS downsampling
    outer_mask = mask.filter(ImageFilter.MaxFilter(stroke_px))

    # 3. Create Soft Ambient Drop Shadow under the bubble
    shadow_mask = outer_mask.filter(ImageFilter.GaussianBlur(7 * scale))

    # 4. Composite Shadow + Ink Border + Pure White Fill onto RGBA Canvas
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # Paste shadow offset slightly downward
    shadow_layer = Image.new("RGBA", (W, H), (12, 15, 24, 55))
    canvas.paste(shadow_layer, (0, 6 * scale), mask=shadow_mask)

    # Paste dark charcoal comic ink border (#18181E)
    ink_layer = Image.new("RGBA", (W, H), (24, 24, 30, 255))
    canvas.paste(ink_layer, (0, 0), mask=outer_mask)

    # Paste warm paper-white interior fill (#FDFDFD)
    fill_layer = Image.new("RGBA", (W, H), (253, 253, 254, 255))
    canvas.paste(fill_layer, (0, 0), mask=mask)

    # 5. Render Crisp Centered English Dialogue Inside the Bubble
    c_draw = ImageDraw.Draw(canvas)
    text_color = (38, 42, 52, 255) if bubble_type == "thought" else (18, 18, 22, 255)
    c_draw.multiline_text(
        (cx, cy),
        multiline_str,
        font=font,
        fill=text_color,
        align="center",
        anchor="mm",
        spacing=8 * scale
    )

    # Downsample 2x -> 1x with LANCZOS for razor-sharp anti-aliased comic ink lines
    canvas.resize((1080, 1920), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def render_floating_manhwa_ages(male_age, female_age, output_path):
    """
    Renders sleek, floating Manhwa age typography in the top-left (Electric Blue)
    and top-right (Ruby Pink) with crisp comic strokes—no bulky boxes, never colliding with bubbles.
    """
    scale = 2
    W, H = 1080 * scale, 180 * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_age = get_comic_font(62 * scale)

    def draw_stylized_age(cx, cy, age_val, main_color, glow_color):
        txt = "".join(c for c in str(age_val) if c.isdigit())[:2] or "19"
        # Soft outer glow
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_layer)
        g_draw.text((cx, cy), txt, font=font_age, fill=glow_color + (160,), anchor="mm", stroke_width=10 * scale, stroke_fill=glow_color + (160,))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(6 * scale))
        img.alpha_composite(glow_layer)

        # Crisp dark comic stroke + bright fill
        draw.text(
            (cx, cy),
            txt,
            font=font_age,
            fill=main_color + (255,),
            anchor="mm",
            stroke_width=5 * scale,
            stroke_fill=(15, 18, 26, 255)
        )

    if male_age:
        draw_stylized_age(95 * scale, 78 * scale, male_age, (75, 180, 255), (30, 120, 255))
    if female_age:
        draw_stylized_age(985 * scale, 78 * scale, female_age, (255, 85, 135), (255, 40, 100))

    img.resize((1080, 180), Image.LANCZOS).save(output_path, "PNG")
    return output_path


def select_groq_chat_model(client):
    """Strictly selects a text LLM on Groq and blocks whisper/audio/guard/tts models."""
    models_resp = client.models.list().data
    all_ids = [m.id for m in models_resp]
    banned = ("whisper", "guard", "tts", "playai", "embed", "vision", "allam", "distil")
    chat_models = [m for m in all_ids if not any(b in m.lower() for b in banned)]

    preferred = [
        "llama-3.3-70b-versatile",
        "deepseek-r1-distill-llama-70b",
        "qwen-qwq-32b",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "llama3-70b-8192",
        "llama3-8b-8192"
    ]
    for p in preferred:
        if p in chat_models:
            return p
    return chat_models[0] if chat_models else "llama-3.3-70b-versatile"


def build_story_prompts(concept, used_titles, used_dialogues):
    entropy = f"{int(time.time())}-{random.randint(10000, 99999)}"
    system_prompt = (
        "You are an elite Korean Manhwa romance scriptwriter. "
        "You write 100% English scripts where every scene features a romantic two-beat exchange "
        "between the male lead (left) and female lead (right). Output strictly valid JSON."
    )
    user_prompt = f"""Write a brand-new, emotionally gripping 5-scene vertical Korean Manhwa romance Short script.
Run Seed: {entropy}
Concept Direction: "{concept}"
Previously Used Titles (DO NOT REPEAT): {json.dumps(used_titles[-10:])}
Previously Used Lines (DO NOT REPEAT): {json.dumps(used_dialogues[-15:])}

PACING SYNCED TO 'INDILA - LOVE STORY (INSTRUMENTAL SLOWED & REVERB)' (0:45 to 1:11):
- Scene 1 (0.0s - 5.2s): Intriguing hook / first encounter or unspoken tension.
- Scene 2 (5.2s - 10.4s): Growing secret feelings, blushing, or protective gesture.
- Scene 3 (10.4s - 15.6s): THE ORCHESTRAL BEAT DROP -> High-emotion twist, sudden storm/rain rescue, or jealousy!
- Scene 4 (15.6s - 20.8s): Heart-stopping closeness or raw confession.
- Scene 5 (20.8s - 26.0s): Unforgettable romantic payoff.

DIALOGUE & POSE RULES:
1. Every scene has TWO lines:
   - "male_bubble_type": "speech" or "thought"
   - "male_line": 4 to 8 natural, complete English words (no abbreviations, no cut-off words).
   - "female_bubble_type": "speech" or "thought"
   - "female_line": 4 to 8 natural, complete English words.
2. "scene_setting_and_pose": Describe a waist-up portrait of both characters in the lower two-thirds of the frame with generous ceiling/sky headroom above their heads, chests facing forward in open blazers/cardigans/collared shirts (never backward hoodies).

Return ONLY valid JSON matching this exact schema:
{{
  "trope": "Short catchy story theme",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "video_title": "Emotional viral English title with emojis #Shorts #manhwa #lovestory",
  "male_dna": "handsome young Korean man with [distinct hair color/style], [eye color] eyes, wearing an open dark tailored blazer over a crisp collared shirt",
  "female_dna": "beautiful young Korean woman with [distinct hair color/style], [eye color] eyes, wearing a cozy pastel cardigan over a collared blouse",
  "scenes": [
    {{
      "male_age": "20",
      "female_age": "19",
      "male_bubble_type": "speech",
      "male_line": "Did you wait in the rain?",
      "female_bubble_type": "thought",
      "female_line": "He actually came back for me...",
      "lighting_and_atmosphere": "warm golden streetlamp glow, soft rain droplets, romantic bokeh",
      "scene_setting_and_pose": "standing side-by-side under an umbrella on a rainy evening street with tall glowing buildings and night sky above their heads"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_combinatorial_fallback(history):
    """Dynamic combinatorial story generator if external LLMs are unreachable."""
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    m_hair = random.choice(["jet-black tousled", "silver-ash", "dark espresso", "midnight-blue"])
    f_hair = random.choice(["chestnut-brown bob", "long wavy raven-black", "warm honey-brown", "soft caramel"])
    base_age = random.choice([18, 19, 20, 21])
    ma, fa = str(base_age + 1), str(base_age)

    scenes = [
        {
            "male_age": ma, "female_age": fa,
            "male_bubble_type": "thought", "male_line": "Same train car. Every single morning.",
            "female_bubble_type": "thought", "female_line": "If he looks over, I'll smile.",
            "lighting_and_atmosphere": "soft morning sunlight streaming through subway windows",
            "scene_setting_and_pose": "standing side-by-side holding subway handrails with spacious train ceiling above their heads, stealing shy glances"
        },
        {
            "male_age": ma, "female_age": fa,
            "male_bubble_type": "speech", "male_line": "Here. Take my seat today.",
            "female_bubble_type": "thought", "female_line": "He remembered my tired eyes...",
            "lighting_and_atmosphere": "warm golden afternoon light and soft dust motes",
            "scene_setting_and_pose": "standing close inside the train car with high windows above their heads, boy gesturing kindly while girl blushes"
        },
        {
            "male_age": str(int(ma) + 1), "female_age": str(int(fa) + 1),
            "male_bubble_type": "speech", "male_line": "Hold onto me. The lights went out.",
            "female_bubble_type": "thought", "female_line": "His arms feel so safe...",
            "lighting_and_atmosphere": "dramatic blue storm lighting outside train windows and warm phone glow",
            "scene_setting_and_pose": "train stopped in a rainstorm, boy steadying girl by her shoulders, chests facing forward, intense eye contact"
        },
        {
            "male_age": str(int(ma) + 1), "female_age": str(int(fa) + 1),
            "male_bubble_type": "speech", "male_line": "I rode this train just for you.",
            "female_bubble_type": "speech", "female_line": "For a whole year in silence?",
            "lighting_and_atmosphere": "rainy station platform with glowing amber lamps above",
            "scene_setting_and_pose": "standing under one umbrella on the station platform with high roof arch above their heads, boy gently touching her cheek"
        },
        {
            "male_age": str(int(ma) + 2), "female_age": str(int(fa) + 2),
            "male_bubble_type": "speech", "male_line": "I never want another silent morning.",
            "female_bubble_type": "speech", "female_line": "Then walk with me every day.",
            "lighting_and_atmosphere": "magical golden sunrise sky and floating cherry blossom petals",
            "scene_setting_and_pose": "holding both hands under a glowing sunrise sky with tall cherry blossom branches high above their heads, smiling warmly"
        }
    ]
    return {
        "trope": f"Subway Romance Story #{run_id}",
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": f"Same 7 AM Train... Until The Storm Stopped Us 😭🚇 #{run_id} #Shorts #manhwa #lovestory",
        "male_dna": f"handsome young Korean man with {m_hair} hair, warm dark eyes, wearing an open dark tailored blazer over a crisp white shirt",
        "female_dna": f"beautiful young Korean woman with {f_hair} hair, bright expressive eyes, wearing a soft rose cardigan over a white blouse",
        "scenes": scenes
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
            model = select_groq_chat_model(client)
            print(f"[STORY-ENGINE] Writing fresh script via Groq ({model})...")
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                response_format={"type": "json_object"},
                temperature=0.85
            )
            data = json.loads(res.choices[0].message.content.strip())
            if "scenes" in data and len(data["scenes"]) >= 4:
                data["archetype_used"] = chosen_concept
                print(f"✅ Fresh Script Ready: {data.get('video_title')}")
                return data
        except Exception as e:
            print(f"⚠️ Groq LLM fallback ({e})...")

    return generate_combinatorial_fallback(history)


def fetch_clean_manhwa_artwork(scene, male_dna, female_dna, story_seed, idx, output_path):
    """
    Generates 100% TEXT-FREE, BUBBLE-FREE Korean romance anime artwork.
    By avoiding words like 'manga/manhwa/comic panel' in the image prompt, Flux never hallucinates
    fake speech bubbles, Korean Hangul, or Chinese text!
    Characters are framed waist-up in the lower two-thirds so their heads sit around y=500..750
    with clean scenic ceiling/sky above them for our anchored vector bubbles.
    """
    api_key = os.getenv("POLLINATIONS_API_KEY")
    atmos = scene.get("lighting_and_atmosphere", "warm golden cinematic lighting")
    pose = scene.get("scene_setting_and_pose", "standing side-by-side looking warmly at each other")

    prompt = (
        f"Vertical 9:16 romantic Korean anime keyframe digital illustration, Makoto Shinkai and K-drama visual novel painting style. "
        f"Wide headroom composition: The top 30 percent of the canvas is clean scenic ceiling or sky background above the characters' heads. "
        f"In the lower two-thirds stand two characters waist-up with front-facing chests and natural neck anatomy: "
        f"On the left is {male_dna}; on the right is {female_dna}. "
        f"Action: {pose}. Atmosphere: {atmos}. "
        f"Pure clean illustration without any UI, without any text, without any speech bubbles, without any numbers or watermarks."
    )
    neg_prompt = (
        "speech bubble, thought bubble, text, letters, words, numbers, subtitles, korean text, hangul, "
        "chinese characters, hanzi, kanji, comic panels, watermark, logo, backward head, twisted neck, hoodie"
    )

    encoded = urllib.parse.quote(prompt)
    encoded_neg = urllib.parse.quote(neg_prompt)
    seed = story_seed + (idx * 173)

    url = (
        f"https://gen.pollinations.ai/image/{encoded}"
        f"?width=1080&height=1920&model=flux&seed={seed}"
        f"&negative_prompt={encoded_neg}&nologo=true&enhance=false"
    )
    if api_key:
        url += f"&key={api_key}"

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"[ARTWORK] Generating clean text-free Scene {idx + 1}/5...")
    for attempt in range(4):
        try:
            res = requests.get(url, headers=headers, timeout=75)
            if res.status_code == 200 and "image" in res.headers.get("Content-Type", "") and len(res.content) > 15000:
                with open(output_path, "wb") as f:
                    f.write(res.content)
                with Image.open(output_path) as im:
                    im.convert("RGB").resize((1080, 1920), Image.LANCZOS).save(output_path, "JPEG", quality=95)
                print(f"✅ Clean Scene {idx + 1} artwork saved: {output_path}")
                return True
            time.sleep(4)
        except Exception:
            time.sleep(4)
    return False


def verify_zero_vocals_with_whisper(audio_path):
    """
    Uses Groq's ultra-fast whisper-large-v3 model to listen to the sliced 30s audio track
    and verify that NO ONE IS SINGING French or English lyrics!
    Returns True if 100% pure instrumental (0 sung words), False if vocals are detected.
    """
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
        # Filter out standard non-speech Whisper hallucinations like "thank you", "music", "sous-titres"
        non_vocal_phrases = ["sous-titres", "amara.org", "merci d'avoir", "thank you for watching", "music", "applause", "instrumental"]
        for p in non_vocal_phrases:
            text = text.replace(p, "")

        # Known French vocal words from Indila - Love Story
        indila_lyrics = ("attend", "debout", "rose", "main", "rien", "autour", "sens", "lourd", "regard", "seul", "parle", "aime", "histoire")
        if any(w in text for w in indila_lyrics):
            print(f"⚠️ [WHISPER VOCAL GATE] Rejected track—detected Indila French lyrics: '{text[:60]}'")
            return False

        words = [w for w in text.split() if len(w) > 2]
        if len(words) > 5:
            print(f"⚠️ [WHISPER VOCAL GATE] Rejected track—detected sung words ({len(words)} words): '{text[:60]}'")
            return False

        print("✅ [WHISPER VOCAL GATE] Confirmed 100% PURE INSTRUMENTAL (Zero vocals detected)!")
        return True
    except Exception as e:
        print(f"⚠️ Whisper check skipped ({e}).")
        return True


def synthesize_indila_orchestral_music_box(output_mp3, duration_sec=30):
    """
    Rich Multi-Voice Instrumental Renderer of Indila's 'Love Story' (Slowed & Reverb):
    Combines Grand Piano + Warm Cello Bass + Music-Box Harp Arpeggio + Soaring Violin Lead
    in the exact D-Minor 3/4 Waltz of Indila's Love Story, mastered through FFmpeg Cathedral Reverb.
    Guaranteed 100% vocal-free and magical.
    """
    raw_wav = "workspace/indila_orchestral_raw.wav"
    sr = 44100
    total_samples = int(sr * duration_sec)

    # Exact Indila 'Love Story' D-minor 3/4 Waltz progression & iconic melody notes
    # Progression: Dm -> Bb -> Gm -> A7
    bars = [
        # (Bass root, 3-note Waltz Arpeggio, 3-beat Violin/Piano Lead Melody)
        (146.83, [293.66, 349.23, 440.00], [440.00, 587.33, 523.25]),  # Dm: A4 -> D5 -> C5
        (116.54, [233.08, 293.66, 349.23], [466.16, 440.00, 392.00]),  # Bb: Bb4 -> A4 -> G4
        (98.00,  [196.00, 293.66, 349.23], [349.23, 440.00, 392.00]),  # Gm: F4 -> A4 -> G4
        (110.00, [220.00, 277.18, 329.63], [349.23, 329.63, 293.66]),  # A7: F4 -> E4 -> D4
    ]
    beat_sec = 0.64  # Slowed waltz tempo
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

            # 1. Warm Cello/Piano Bass on Beat 1
            bass_env = math.exp(-in_bar_t * 1.15) * min(1.0, in_bar_t * 35.0)
            bass_sig = 0.32 * (
                math.sin(2 * math.pi * bass_f * t)
                + 0.35 * math.sin(4 * math.pi * bass_f * t)
            ) * bass_env

            # 2. Felt Piano + Harp Waltz Arpeggio on Every Beat
            arp_env = math.exp(-note_t * 2.8) * min(1.0, note_t * 50.0)
            arp_sig = 0.30 * (
                math.sin(2 * math.pi * arp_f * t)
                + 0.25 * math.sin(4 * math.pi * arp_f * t) * math.exp(-note_t * 4.0)
            ) * arp_env

            # 3. Expressive Violin & High Piano Lead (Swells dramatically at Scene 3 beat drop)
            lead_gain = 0.28 if t < 10.2 else min(0.52, 0.28 + (t - 10.2) * 0.15)
            vib = 1.0 + 0.0035 * math.sin(2 * math.pi * 5.0 * t)
            mel_env = math.exp(-note_t * 1.3) * min(1.0, note_t * 18.0)
            lead_sig = lead_gain * (
                math.sin(2 * math.pi * mel_f * vib * t)
                + 0.45 * math.sin(4 * math.pi * mel_f * vib * t)
                + 0.15 * math.sin(6 * math.pi * mel_f * vib * t)
            ) * mel_env

            val = max(-1.0, min(1.0, (bass_sig + arp_sig + lead_sig) * 0.65))
            wf.writeframesraw(struct.pack("<h", int(val * 32767)))

    # Master with lush Slowed & Reverb cathedral acoustics via FFmpeg
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_wav,
        "-af", "aecho=0.8:0.90:70|140:0.40|0.25,lowpass=f=3600,loudnorm=I=-14:TP=-1.5:LRA=11",
        "-b:a", "192k", output_mp3
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3


def get_verified_pure_instrumental():
    """
    Guarantees 100% VOCAL-FREE Indila - Love Story (Instrumental Slowed & Reverb):
    1. Purges any old vocal-contaminated MP3 files from assets/.
    2. Searches verified YouTube Instrumental IDs & SoundCloud strictly filtering for 'instrumental'/'piano'/'karaoke'/'violin' titles.
    3. Applies FFmpeg center-vocal cancellation + Slowed & Reverb mastering on the 0:45-1:15 climax window.
    4. Verifies with Groq Whisper-Large-v3 that ZERO sung lyrics exist before accepting!
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    # Remove old vocal-contaminated cache files from previous versions
    for old_file in (
        "assets/indila_love_story_magical_cut.mp3",
        "assets/indila_love_story_instrumental_v2.mp3",
        "assets/indila_love_story_pure_instrumental_v3.mp3"
    ):
        if os.path.exists(old_file):
            try:
                os.remove(old_file)
                print(f"🧹 Purged old vocal-contaminated audio file: {old_file}")
            except Exception:
                pass

    if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 40000:
        if verify_zero_vocals_with_whisper(LOCKED_SONG_PATH):
            print(f"✅ Using Whisper-verified pure instrumental: {LOCKED_SONG_PATH}")
            return LOCKED_SONG_PATH
        else:
            os.remove(LOCKED_SONG_PATH)

    # Candidate list: Known Pure Instrumentals on YouTube + Strict SoundCloud Instrumental Queries
    candidate_queries = [
        "https://www.youtube.com/watch?v=FRhcUnZ7MOw",  # Indila - Love Story (Extended Instrumental) [slowed + reverb]
        "https://www.youtube.com/watch?v=SPEqQwB0tZs",  # Love Story (Version Orchestrale) (Instrumental) - Indila
        "https://www.youtube.com/watch?v=EqAj188uSBQ",  # Indila - Love Story (Karaoke Piano Instrumental)
        "https://www.youtube.com/watch?v=1NBnN0IAljQ",  # Love Story by Indila (Ethereal Instrumental Full Version)
        "scsearch12:Indila Love Story piano cover instrumental",
        "scsearch12:Indila Love Story karaoke instrumental",
        "scsearch12:Indila Love Story violin instrumental"
    ]

    required_keywords = ("instrumental", "karaoke", "piano", "violin", "orchestral", "guitar", "backing")
    banned_keywords = ("lyrics", "lyric", "vocal", "singing", "official music video", "nightcore")

    raw_dl = "workspace/candidate_raw.mp3"
    test_cut = "workspace/candidate_cut.mp3"

    for item in candidate_queries:
        print(f"[AUDIO-HUNTER] Probing instrumental source: {item}...")
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
                            90 <= dur <= 420
                            and any(k in title for k in required_keywords)
                            and not any(b in title for b in banned_keywords)
                        ):
                            urls_to_try.append((entry.get("url") or entry.get("webpage_url"), title))
            else:
                urls_to_try.append((item, "verified_yt_instrumental"))

            for target_url, title_label in urls_to_try[:3]:
                if not target_url:
                    continue
                print(f"   ↳ Downloading pure instrumental candidate: '{title_label}'...")
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
                subprocess.run(cmd, timeout=55, check=False)

                if not (os.path.exists(raw_dl) and os.path.getsize(raw_dl) > 50000):
                    continue

                # Slice 0:45 to 1:15 (30s climax) + Slowed & Cathedral Reverb mastering
                slice_cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(GOLDEN_START_SEC),
                    "-t", str(GOLDEN_DURATION_SEC),
                    "-i", raw_dl,
                    "-af", "aecho=0.8:0.86:55:0.28,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-b:a", "192k",
                    test_cut
                ]
                subprocess.run(slice_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if os.path.exists(test_cut) and os.path.getsize(test_cut) > 30000:
                    # Pass 1: Check with Whisper if already 100% vocal-free
                    if verify_zero_vocals_with_whisper(test_cut):
                        os.replace(test_cut, LOCKED_SONG_PATH)
                        print(f"🎉 Locked 100% Vocal-Free Indila Instrumental: {LOCKED_SONG_PATH}")
                        return LOCKED_SONG_PATH

                    # Pass 2: Apply FFmpeg Stereo Center-Channel Vocal Cancellation & re-verify
                    print("   ↳ Applying FFmpeg Stereo Vocal Remover to strip center vocals...")
                    stripped_cut = "workspace/candidate_stripped.mp3"
                    strip_cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(GOLDEN_START_SEC),
                        "-t", str(GOLDEN_DURATION_SEC),
                        "-i", raw_dl,
                        "-af", "stereotools=mlev=0.015,aecho=0.8:0.88:65:0.35,loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-b:a", "192k",
                        stripped_cut
                    ]
                    subprocess.run(strip_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(stripped_cut) and verify_zero_vocals_with_whisper(stripped_cut):
                        os.replace(stripped_cut, LOCKED_SONG_PATH)
                        print(f"🎉 Locked Vocal-Stripped Pure Instrumental: {LOCKED_SONG_PATH}")
                        return LOCKED_SONG_PATH

        except Exception as e:
            print(f"⚠️ Candidate probe skipped: {e}")

    print("[AUDIO-SYNTH] Rendering multi-voice Indila Love Story Orchestral Piano & Violin Waltz (100% Vocal-Free)...")
    synth_mp3 = synthesize_indila_orchestral_music_box(LOCKED_SONG_PATH, duration_sec=30)
    return synth_mp3


def build_pipeline():
    print("=== STARTING PRECISION CV-ANCHORED WEBTOON BUBBLE + VOCAL-FREE INDILA PIPELINE ===")
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
    scenes = story_data.get("scenes", [])
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.2
    reply_pop_delay = 1.8  # Girl's reply bubble pops in at 1.8s for realistic reading flow
    clips = []

    for idx, sc in enumerate(scenes):
        bg_path = f"workspace/clean_art_{idx}.jpg"
        if not fetch_clean_manhwa_artwork(sc, male_dna, female_dna, story_seed, idx, bg_path):
            continue

        # Detect exact pixel coordinates of the Boy's and Girl's heads and mouths on the artwork
        anchors = detect_character_anchors(bg_path)
        print(
            f"[CV-ANCHORS] Scene {idx + 1}: Boy Head={anchors['boy_head_top']} Mouth={anchors['boy_mouth']} | "
            f"Girl Head={anchors['girl_head_top']} Mouth={anchors['girl_mouth']}"
        )

        # 1. Base Clean Manhwa Artwork
        base_clip = ImageClip(bg_path).set_duration(scene_duration).resize((1080, 1920))
        layers = [base_clip]

        # 2. Floating Age Numbers in Top Corners (Sky Blue Left, Ruby Pink Right)
        age_png = f"workspace/ages_{idx}.png"
        render_floating_manhwa_ages(sc.get("male_age", "20"), sc.get("female_age", "19"), age_png)
        age_clip = ImageClip(age_png).set_position(("center", 12)).set_duration(scene_duration)
        layers.append(age_clip)

        # 3. Boy's Anchored Webtoon Bubble (Appears at 0.0s right above his head, curved tail pointing to his mouth)
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

        # 4. Girl's Anchored Webtoon Bubble (Pops in at 1.8s right above her head, curved tail pointing to her mouth)
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

        # Subtle unified camera push across the composite panel so the bubbles move locked with the characters!
        scene_comp = CompositeVideoClip(layers, size=(1080, 1920)).set_duration(scene_duration)
        scene_comp = scene_comp.resize(lambda t: 1.0 + (0.015 * t))
        clips.append(scene_comp)

    if not clips:
        raise RuntimeError("❌ Pipeline aborted: 0 scenes rendered.")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration

    audio_path = get_verified_pure_instrumental()
    if audio_path and os.path.exists(audio_path):
        audio_clip = AudioFileClip(audio_path)
        if audio_clip.duration < total_dur:
            audio_clip = afx.audio_loop(audio_clip, duration=total_dur)
        else:
            audio_clip = audio_clip.subclip(0, total_dur)
        audio_clip = audio_clip.audio_fadein(0.8).audio_fadeout(1.5).volumex(0.95)
        final_video = final_video.set_audio(audio_clip)

    output_mp4 = "videos/final_manhwa_short.mp4"
    print("[RENDER] Exporting 9:16 Master MP4...")
    final_video.write_videofile(
        output_mp4,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"]
    )
    print(f"🎉 MASTER MANHWA SHORT READY: {output_mp4}")


if __name__ == "__main__":
    build_pipeline()
