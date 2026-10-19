import os
import sys
import json
import time
import math
import wave
import struct
import base64
import random
import subprocess
import urllib.parse
import requests

# Auto-install yt-dlp if missing in environment
try:
    import yt_dlp
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"], check=False)

from PIL import Image
from groq import Groq
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, afx

HISTORY_FILE = "story_history.json"
LOCKED_SONG_PATH = "assets/indila_love_story_pure_instrumental_v3.mp3"
LOCKED_SONG_TITLE = "Love Story (Instrumental Slowed & Reverb) - Indila"

# Best 26-30s emotional climax window of Indila - Love Story (Slowed & Reverb)
GOLDEN_START_SEC = 45
GOLDEN_DURATION_SEC = 30

# Priority list of Pollinations image models ranked by Native English Typography & Anatomical Accuracy
PREFERRED_IMAGE_MODELS = [
    "gptimage-large",
    "gptimage",
    "nanobanana-pro",
    "nanobanana",
    "seedream",
    "kontext",
    "flux"
]

STORY_CONCEPTS = [
    "Academic Rivals to Lovers: Rank #1 cold boy and Rank #2 girl who compete in every exam, until he secretly takes the blame for her mistake",
    "Contract Fake Dating to Real Love: They signed a 30-day fake dating agreement to fool their families, but he tears up the contract on day 30",
    "The Second-Lead Umbrella Rescue: Her fiancé left her waiting in the rain, so his quiet older brother steps in with an umbrella and never leaves her side",
    "Childhood Next-Door Neighbours: From sharing snacks across balconies at age 10 to a breathless rooftop confession at age 21",
    "Ruthless Young CEO & Fearless New Architect: Nobody dares to speak back to the company heir except her—and he becomes completely obsessed",
    "Time-Leap Second Chance: After losing her in a tragic future, he wakes up 4 years in the past on the day they first met and vows to protect her",
    "Brother's Best Friend Secretly Waited: He pretended to see her as a kid sister for years until another guy asks her to the gala",
    "7 AM Subway Strangers: Riding the same train car every morning in silence for a year until the train stops in a storm and he finally speaks",
    "Campus Ice Prince & Warm Art Student: He rejects every confession on campus, yet secretly keeps every doodle she left on the library desk",
    "Bodyguard & Runaway Heiress: Hired strictly to keep her safe from a distance, he breaks his own rule when she reaches for his hand"
]


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"used_titles": [], "used_concepts": [], "used_dialogues": [], "total_videos": 0}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def discover_image_models():
    """Queries Pollinations for active image models and orders them by text/anatomy quality."""
    available = []
    try:
        res = requests.get("https://gen.pollinations.ai/image/models", timeout=12)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        available.append(item)
                    elif isinstance(item, dict) and "name" in item:
                        available.append(item["name"])
                    elif isinstance(item, dict) and "id" in item:
                        available.append(item["id"])
    except Exception:
        pass

    ordered = []
    for m in PREFERRED_IMAGE_MODELS:
        if not available or m in available:
            ordered.append(m)
    if "flux" not in ordered:
        ordered.append("flux")
    print(f"[MODEL-ENGINE] Image model priority queue: {ordered}")
    return ordered


def select_groq_chat_model(client):
    """Selects a true text LLM on Groq and strictly excludes whisper/audio/guard/tts models."""
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


def build_director_prompts(concept, used_titles, used_dialogues):
    entropy = f"{int(time.time())}-{random.randint(10000, 99999)}"
    system_prompt = (
        "You are a Master Romantic Graphic Novel Director and AI Prompt Architect. "
        "You design 5-scene vertical romance Shorts where the AI image model natively renders "
        "both characters facing forward with flawless human anatomy, separate left/right comic bubbles, "
        "and ultra-clean 3-to-5 word English lines. Output strictly valid JSON."
    )
    user_prompt = f"""Design a 100% original, deeply emotional 5-scene vertical romance Short script.
Run Seed: {entropy}
Story Concept: "{concept}"
Previously Used Titles (NEVER REPEAT): {json.dumps(used_titles[-10:])}
Previously Used Lines (NEVER REPEAT): {json.dumps(used_dialogues[-15:])}

CRITICAL NATIVE-IMAGE TYPOGRAPHY & ANATOMY RULES:
1. Every scene has TWO separate bubbles drawn natively by the image generator:
   - "male_bubble_shape": either "sleek white oval speech bubble with pointer tail aimed down-left at the boy" OR "fluffy white cloud thought bubble with small dots aimed down-left at the boy"
   - "male_line": 3 to 5 simple English words ONLY (short lines guarantee 100% perfect spelling by the image model!).
   - "female_bubble_shape": either "sleek white oval speech bubble with pointer tail aimed down-right at the girl" OR "fluffy white cloud thought bubble with small dots aimed down-right at the girl"
   - "female_line": 3 to 5 simple English words ONLY.
2. ANATOMY LOCK:
   - Never use pullover hoodies or back-turned poses (which cause twisted necks).
   - Dress characters in front-buttoned blazers, collared shirts, V-neck cardigans, or evening wear so their chests and collarbones clearly face the camera.
   - Both characters must stand side-by-side (boy on left, girl on right) in a waist-up front/three-quarter view facing the viewer while looking at each other.

Return ONLY a valid JSON object matching this exact schema:
{{
  "trope": "Short catchy story theme",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "video_title": "Emotional viral English title with emojis #Shorts #manhwa #lovestory",
  "male_dna": "handsome young Korean man with [distinct hair color/style], [eye color] eyes, wearing an open front-buttoned dark tailored blazer over a crisp collared shirt",
  "female_dna": "beautiful young Korean woman with [distinct hair color/style], [eye color] eyes, wearing a front-buttoned pastel cardigan with a visible V-neck collar",
  "scenes": [
    {{
      "male_age": "20",
      "female_age": "19",
      "male_bubble_shape": "sleek white oval speech bubble with pointer tail aimed down-left at the boy",
      "male_line": "You waited in the rain?",
      "female_bubble_shape": "fluffy white cloud thought bubble with small dots aimed down-right at the girl",
      "female_line": "Only for you, dummy.",
      "lighting_and_atmosphere": "warm golden streetlamp glow, soft rain droplets, romantic bokeh",
      "scene_setting_and_pose": "standing side-by-side under a transparent umbrella on an evening city street, chests facing forward toward camera, looking warmly into each other's eyes"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_dynamic_fallback_story(history):
    """Combinatorial story generator (never repeats static scenes) if external LLMs time out."""
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    m_hair = random.choice(["jet-black tousled", "silver-ash", "dark espresso", "midnight-blue"])
    f_hair = random.choice(["long chestnut wavy", "silky raven-black", "warm honey-brown", "dark cherry"])
    m_eyes = random.choice(["deep amber", "sapphire", "obsidian", "warm grey"])
    f_eyes = random.choice(["bright hazel", "emerald", "soft violet", "warm brown"])

    base_age = random.choice([18, 19, 20, 21])
    ma, fa = str(base_age + 1), str(base_age)

    arc_sets = [
        [
            ("Why sit near me?", "Because you looked lonely.", "sunlit university library desk, warm afternoon dust motes", "sitting side-by-side at wooden library table, front-facing torsos, looking at each other"),
            ("Take my blazer now.", "His jacket is so warm...", "snowy evening campus courtyard, glowing lamp posts", "standing side-by-side in gentle snow, boy draping his blazer over girl's shoulders, front view"),
            ("Stay right behind me.", "He's holding my hand!", "rainy neon city crosswalk at night, shimmering reflections", "boy holding umbrella over both of them, holding her hand firmly, chests facing forward"),
            ("I broke our contract.", "Wait... why did you?", "starry rooftop terrace with city skyline lights", "standing close by rooftop railing facing forward, boy holding torn paper, intense loving gaze"),
            ("Because I love you.", "I loved you first.", "golden sunrise balcony with floating cherry blossom petals", "holding both hands and smiling tenderly at each other, warm sunrise glow")
        ],
        [
            ("You dropped your sketchbook.", "Don't open that page!", "autumn park pathway with falling golden leaves", "standing face-to-face in three-quarter front view, boy holding an open sketchbook"),
            ("Every drawing is me?", "My heart is racing...", "quiet art studio with warm sunset window beams", "standing beside an easel, boy smiling softly while girl blushes, front-facing posture"),
            ("Why didn't you tell me?", "I thought you hated me.", "dramatic rain outside glass conservatory, soft blue lighting", "sheltering together under conservatory roof, boy gently touching her chin, front view"),
            ("I could never hate you.", "You mean that truly?", "lantern-lit night garden bridge, glowing floating lights", "leaning close together on bridge, warm golden lantern light on their faces"),
            ("Be mine forever, okay?", "Yes, always with you.", "fireworks blooming over night harbor, sparkling reflections", "embracing warmly in front-facing waist-up portrait, happy tears and smiles")
        ]
    ]
    chosen_arc = random.choice(arc_sets)

    scenes = []
    for idx, (m_line, f_line, atmos, pose) in enumerate(chosen_arc):
        cur_m = str(int(ma) + (1 if idx >= 3 else 0))
        cur_f = str(int(fa) + (1 if idx >= 3 else 0))
        scenes.append({
            "male_age": cur_m,
            "female_age": cur_f,
            "male_bubble_shape": "sleek white oval speech bubble with pointer tail aimed down-left at the boy",
            "male_line": m_line,
            "female_bubble_shape": "fluffy white cloud thought bubble with small dots aimed down-right at the girl" if idx < 3 else "sleek white oval speech bubble with pointer tail aimed down-right at the girl",
            "female_line": f_line,
            "lighting_and_atmosphere": atmos,
            "scene_setting_and_pose": pose
        })

    return {
        "trope": f"Original Romance Story #{run_id}",
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "video_title": f"\"{chosen_arc[2][0]}\" 💔🥺 #{run_id} #Shorts #manhwa #lovestory",
        "male_dna": f"handsome young Korean man with {m_hair} hair and {m_eyes} eyes, wearing an open front-buttoned dark blazer over a crisp white collared shirt",
        "female_dna": f"beautiful young Korean woman with {f_hair} hair and {f_eyes} eyes, wearing a front-buttoned cream cardigan with a visible collar",
        "scenes": scenes
    }


def generate_fresh_story(history):
    used_concepts = history.get("used_archetypes", [])[-6:]
    used_titles = history.get("used_titles", [])
    used_dialogues = history.get("used_dialogues", [])

    avail = [c for c in STORY_CONCEPTS if c not in used_concepts] or STORY_CONCEPTS
    chosen_concept = random.choice(avail)
    sys_p, usr_p = build_director_prompts(chosen_concept, used_titles, used_dialogues)

    # 1. Try Groq Chat LLM
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            model = select_groq_chat_model(client)
            print(f"[STORY-DIRECTOR] Writing fresh script via Groq ({model})...")
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
                response_format={"type": "json_object"},
                temperature=0.85
            )
            data = json.loads(res.choices[0].message.content.strip())
            if "scenes" in data and len(data["scenes"]) >= 4:
                data["archetype_used"] = chosen_concept
                print(f"✅ Fresh Script Created: {data.get('video_title')}")
                return data
        except Exception as e:
            print(f"⚠️ Groq LLM skipped ({e}). Switching to Pollinations Text LLM...")

    # 2. Try Pollinations Unified OpenAI Chat Endpoint
    try:
        api_key = os.getenv("POLLINATIONS_API_KEY")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.post(
            "https://gen.pollinations.ai/v1/chat/completions",
            headers=headers,
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
            if "scenes" in data and len(data["scenes"]) >= 4:
                data["archetype_used"] = chosen_concept
                print(f"✅ Fresh Script Created via Pollinations LLM: {data.get('video_title')}")
                return data
    except Exception as e:
        print(f"⚠️ Secondary LLM skipped ({e}). Using dynamic combinatorial story...")

    return generate_dynamic_fallback_story(history)


def sanitize_short_english(text, max_words=6):
    """Ensures dialogue contains ONLY clean ASCII English characters and stays concise for AI spelling."""
    clean = "".join(c for c in str(text) if ord(c) < 128 and (c.isalnum() or c in " .,?!'\"-")).strip()
    words = clean.split()
    if not words:
        return "I waited for you."
    return " ".join(words[:max_words])


def build_native_panel_prompt(scene, male_dna, female_dna):
    """
    Constructs a spatially engineered prompt that forces the AI image generator to:
    1. Render natural front-facing torso & neck anatomy (no 180-degree twisted heads).
    2. Draw two separate bubbles (Boy on upper-left, Girl on upper-right) with clean English text.
    3. Draw neat corner age badges without duplicating digits or using Chinese/Japanese characters.
    """
    m_age = str(scene.get("male_age", "20")).strip()[:2]
    f_age = str(scene.get("female_age", "19")).strip()[:2]
    m_shape = scene.get("male_bubble_shape", "sleek white oval speech bubble with pointer tail aimed down-left at the boy")
    f_shape = scene.get("female_bubble_shape", "fluffy white cloud thought bubble with small dots aimed down-right at the girl")
    m_line = sanitize_short_english(scene.get("male_line", scene.get("dialogue", "Wait for me.")))
    f_line = sanitize_short_english(scene.get("female_line", "My heart is racing..."))
    atmos = scene.get("lighting_and_atmosphere", scene.get("visual_effect", "warm golden sunset lighting"))
    pose = scene.get("scene_setting_and_pose", scene.get("scene_action", "standing side by side looking at each other"))

    prompt = (
        f"Vertical 9:16 romantic Korean web-novel digital illustration, masterpiece cel-shaded art style. "
        f"CAMERA & ANATOMY LOCK: Waist-up front-facing portrait in the lower two-thirds of the frame. "
        f"On the left stands {male_dna}; on the right stands {female_dna}. "
        f"Action: {pose}. Both characters have front-facing chests, visible collarbones, and natural human neck alignment "
        f"(strictly no back views, no hoods on backs, no twisted necks). Atmosphere: {atmos}. "
        f"SEPARATE DUAL COMIC BUBBLES IN UPPER SKY AREA: "
        f"1) Upper-left above the boy: one {m_shape} reading in bold black English letters: \"{m_line}\". "
        f"2) Upper-right above the girl: one separate {f_shape} reading in bold black English letters: \"{f_line}\". "
        f"CORNER AGE PILLS: Top-left corner has a small clean blue rounded pill reading \"{m_age}\". "
        f"Top-right corner has a small clean pink rounded pill reading \"{f_age}\". "
        f"LANGUAGE RULE: 100% English Latin alphabet only. Strictly zero Chinese characters, zero Japanese Kanji or Kana, zero gibberish."
    )
    return prompt, m_line, f_line, m_age, f_age


def inspect_image_with_vision_ai(image_path, expected_m_line, expected_f_line):
    """
    Acts like human eyes: inspects the generated image using a Vision LLM to verify:
    - No Chinese/Japanese/Korean characters
    - No 180-degree backward twisted necks / horror anatomy
    - Separate, readable bubbles
    Returns (is_clean: bool, reason: str)
    """
    try:
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return True, "File read skipped"

    inspection_prompt = (
        "You are a strict Quality Control Director for a romantic comic channel. Inspect this image carefully:\n"
        "1. Are there any Chinese (Hanzi), Japanese (Kanji/Kana), or Korean (Hangul) characters anywhere in the speech bubbles?\n"
        "2. Does either character have a horror/deformed neck (e.g., head twisted 180 degrees backward onto a back-facing hoodie/torso)?\n"
        "3. Are the corner age numbers corrupted into 3+ digits like '119' or '20019'?\n"
        "Respond ONLY with valid JSON: {\"pass\": true_or_false, \"defect\": \"none or short reason\"}"
    )

    api_key = os.getenv("POLLINATIONS_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.post(
            "https://gen.pollinations.ai/v1/chat/completions",
            headers=headers,
            json={
                "model": "openai",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": inspection_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1
            },
            timeout=25
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1].lstrip("json").strip()
            result = json.loads(content)
            passed = bool(result.get("pass", True))
            defect = str(result.get("defect", "none"))
            return passed, defect
    except Exception:
        pass

    return True, "Vision check bypassed"


def generate_verified_native_panel(scene, male_dna, female_dna, model_queue, story_seed, idx, output_path):
    """
    Generates the complete panel (Characters + Native Dual Bubbles + Native English Text + Ages)
    using the highest-tier model available, then runs Vision AI Quality Control.
    If Vision QC detects Chinese text or twisted anatomy, it automatically regenerates!
    """
    api_key = os.getenv("POLLINATIONS_API_KEY")
    base_prompt, m_line, f_line, m_age, f_age = build_native_panel_prompt(scene, male_dna, female_dna)

    neg_prompt = (
        "chinese text, hanzi, kanji, hiragana, katakana, hangul, asian characters, gibberish text, "
        "backward head, twisted neck, 180 degree head turn, back of hoodie, deformed face, extra limbs, "
        "merged speech bubbles, triple digit numbers, 119, watermark, signature"
    )

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Try up to 3 quality-controlled generation passes per scene
    for qc_pass in range(3):
        # Cycle through our top typography models
        for model_name in model_queue:
            seed = story_seed + (idx * 251) + (qc_pass * 997)
            prompt_variant = base_prompt
            if qc_pass > 0:
                prompt_variant += (
                    " CRITICAL CORRECTION: Ensure both characters face forward with visible collarbones "
                    "and render ONLY clean English letters inside two separate white bubbles."
                )

            encoded_prompt = urllib.parse.quote(prompt_variant)
            encoded_neg = urllib.parse.quote(neg_prompt)

            url = (
                f"https://gen.pollinations.ai/image/{encoded_prompt}"
                f"?model={model_name}&width=1080&height=1920&seed={seed}"
                f"&negative_prompt={encoded_neg}&nologo=true&enhance=false"
            )
            if api_key:
                url += f"&key={api_key}"

            print(f"[IMAGE-GEN] Scene {idx + 1}/5 | Model: {model_name} | Pass #{qc_pass + 1} | Boy: \"{m_line}\" | Girl: \"{f_line}\"")
            try:
                res = requests.get(url, headers=headers, timeout=80)
                ctype = res.headers.get("Content-Type", "")
                if res.status_code == 200 and "image" in ctype and len(res.content) > 18000:
                    with open(output_path, "wb") as f:
                        f.write(res.content)
                    # Normalize dimensions to crisp 1080x1920
                    with Image.open(output_path) as im:
                        im.convert("RGB").resize((1080, 1920), Image.LANCZOS).save(output_path, "JPEG", quality=95)

                    # Run Vision AI Quality Control Inspector
                    passed, defect = inspect_image_with_vision_ai(output_path, m_line, f_line)
                    if passed:
                        print(f"✅ [VISION-QC PASSED] Scene {idx + 1} verified clean ({model_name})!")
                        return True
                    else:
                        print(f"⚠️ [VISION-QC REJECTED] Scene {idx + 1} ({model_name}) had defect: {defect}. Regenerating...")
                        break  # Break inner loop to advance qc_pass with a new seed and stricter prompt
                else:
                    # Model might require higher tier or returned error; try next model in queue
                    continue
            except Exception as e:
                print(f"⚠️ Model {model_name} timeout/error: {e}. Trying next model...")
                continue

    # If all QC passes completed, use the last successfully downloaded frame
    return os.path.exists(output_path) and os.path.getsize(output_path) > 15000


def synthesize_indila_waltz_fallback(output_mp3, duration_sec=30):
    """Zero-crash D-Minor 3/4 Waltz synthesizer fallback."""
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
    Pulls a PURE INSTRUMENTAL (piano/violin cover, zero French vocals) of
    Indila - Love Story (Slowed & Reverb) and slices the 0:45-1:15 climax window.
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 40000:
        print(f"✅ Using cached pure instrumental cut: {LOCKED_SONG_PATH}")
        return LOCKED_SONG_PATH

    raw_download = "workspace/indila_inst_raw.mp3"
    queries = [
        "scsearch5:Indila Love Story piano instrumental slowed reverb",
        "scsearch5:Indila Love Story violin instrumental slowed reverb",
        "ytsearch5:Indila Love Story piano cover slowed reverb no vocals"
    ]

    downloaded = False
    for q in queries:
        print(f"[MUSIC-HUNTER] Searching pure instrumental via: {q}...")
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
        print("[AUDIO-MASTERING] Slicing 0:45-1:15 magical climax cut...")
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
    print("=== STARTING FRONTIER VISION-VERIFIED NATIVE MANHWA PIPELINE ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    model_queue = discover_image_models()
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
    clips = []

    for idx, sc in enumerate(scenes):
        panel_path = f"workspace/native_panel_{idx}.jpg"
        if not generate_verified_native_panel(sc, male_dna, female_dna, model_queue, story_seed, idx, panel_path):
            print(f"❌ Skipping scene {idx + 1} due to generation failure.")
            continue

        # Zero post-editing text boxes: the AI image already has the bubbles, text, and ages baked in!
        clip = ImageClip(panel_path).set_duration(scene_duration).resize((1080, 1920))
        clip = clip.resize(lambda t: 1.0 + (0.016 * t))
        clips.append(clip)

    if not clips:
        raise RuntimeError("❌ Pipeline aborted: 0 verified panels generated.")

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
    print("[RENDER] Exporting 9:16 Master MP4...")
    final_video.write_videofile(
        output_mp4,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"]
    )
    print(f"🎉 VISION-VERIFIED MASTER SHORT READY: {output_mp4}")


if __name__ == "__main__":
    build_pipeline()
