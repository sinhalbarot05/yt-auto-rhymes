import os
import sys
import json
import time
import math
import wave
import struct
import random
import subprocess
import urllib.parse
import requests

# Auto-ensure yt-dlp is installed even if the GitHub workflow YAML wasn't updated
try:
    import yt_dlp
except ImportError:
    print("[SETUP] Installing yt-dlp automatically...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"], check=False)

from groq import Groq
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, afx

HISTORY_FILE = "story_history.json"
LOCKED_SONG_PATH = "assets/indila_love_story_magical_cut.mp3"
LOCKED_SONG_TITLE = "Love Story (Instrumental Slowed & Reverb) - Indila"

# Best 26-30s emotional climax window of Indila - Love Story (Slowed & Reverb)
GOLDEN_START_SEC = 45
GOLDEN_DURATION_SEC = 30

# Wide spectrum of high-view Manhwa sub-genres & emotional hooks (Never locked to one formula)
STORY_ARCHETYPES = [
    "Enemies to Lovers: Two hyper-competitive academy rivals who can't stop bickering until a crisis forces them to protect each other",
    "Fake Relationship to Real Obsession: A cold popular guy and a quiet girl pretend to date to stop rumours, but he falls dangerously in love first",
    "The Second Lead Rescue: She spent years chasing a guy who took her for granted, until his quiet best friend steps into the rain and treats her like a queen",
    "Reincarnation / Time-Leap Regret: He was cold to her in their past life; waking up 5 years in the past, he vows to cherish and protect her from day one",
    "Secret Identity Crush: By day they ignore each other in university lectures; by night they are anonymous rooftop confidants who don't know each other's faces",
    "CEO & The Only Person Who Defies Him: Everyone fears the ruthless young chaebol heir except the fearless new designer who accidentally spills iced coffee on his suit",
    "Childhood Promise Broken & Healed: Separated ten years ago after an airport goodbye, he recognizes her immediately when she transfers into his college",
    "Bodyguard & Heiress Forbidden Line: Hired only to guard her from afar, he breaks his own strict rules the night she cries alone at a gala",
    "Cold Ice Prince & Sunshine Transfer Student: He sits alone by the window refusing to talk to anyone until the clumsy new girl refuses to leave him in the dark",
    "Brother's Best Friend Secretly Waited: He always teased her like a kid sister, until the night another boy asks her out and his calm mask finally shatters"
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


def select_groq_chat_model(client):
    """
    Strictly filters Groq's model list so it NEVER selects audio/whisper/tts/guard models.
    """
    models_resp = client.models.list().data
    all_ids = [m.id for m in models_resp]

    # Filter out non-chat models (fixes the whisper-large-v3 crash)
    banned_substrings = ("whisper", "guard", "tts", "playai", "embed", "vision", "allam", "distil-whisper")
    chat_models = [
        m for m in all_ids
        if not any(bad in m.lower() for bad in banned_substrings)
    ]

    preferred_priority = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "deepseek-r1-distill-llama-70b",
        "qwen-qwq-32b",
        "qwen-2.5-32b",
        "gemma2-9b-it",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768"
    ]

    for pref in preferred_priority:
        if pref in chat_models:
            return pref

    # Fallback to any remaining llama/qwen/gemma chat model
    for m in chat_models:
        if any(k in m.lower() for k in ("llama", "qwen", "gemma", "mixtral", "deepseek")):
            return m

    return chat_models[0] if chat_models else "llama-3.3-70b-versatile"


def build_prompt_payload(chosen_archetype, used_titles, used_dialogues):
    entropy = f"{int(time.time())}-{random.randint(10000, 99999)}"
    system_prompt = (
        "You are an elite viral Korean Webtoon & Manhwa Shorts creator. "
        "Every single run you invent a 100% original, unpredictable, emotionally addictive 5-scene story. "
        "Never reuse old plots, ages, settings, or dialogues. Output strictly valid JSON."
    )
    user_prompt = f"""Write a completely original 5-scene vertical Korean Manhwa romance Short script.
Unique Run Seed: {entropy}
Story Concept Direction: "{chosen_archetype}"
Previously Used Titles (NEVER REPEAT): {json.dumps(used_titles[-8:])}
Previously Used Dialogues (NEVER REPEAT): {json.dumps(used_dialogues[-15:])}

PACING SYNCED TO 'INDILA - LOVE STORY (SLOWED & REVERB)' (0:45 to 1:11):
- Scene 1 (0.0s - 5.2s): Intriguing hook / unexpected first encounter or conflict.
- Scene 2 (5.2s - 10.4s): Escalating romantic tension, secret jealousy, or vulnerability.
- Scene 3 (10.4s - 15.6s): THE BEAT DROP -> Major dramatic twist, betrayal, sudden rescue, or confrontation!
- Scene 4 (15.6s - 20.8s): Raw emotional confession or heart-stopping closeness.
- Scene 5 (20.8s - 26.0s): Unforgettable payoff (twist ending, passionate embrace, or bittersweet regret).

FREEDOM & CREATIVITY RULES:
- Choose ANY fitting ages for the characters (they can stay the same age across a single night/week, or jump across years—whatever fits THIS specific plot best!).
- Vary the settings wildly (rooftop gala, subway train, convenience store at 2 AM, university art studio, snowy bus stop, fencing club, rain-soaked alley, hospital corridor, etc.).
- Keep "dialogue" between 4 and 7 punchy English words so the AI image generator renders the text cleanly inside the comic bubble.

Return ONLY a valid JSON object with this exact schema:
{{
  "trope": "Short catchy name for this specific story",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "yt_music_search_query": "Indila Love Story instrumental slowed reverb",
  "video_title": "Unique viral title with emojis #Shorts #manhwa #lovestory",
  "male_dna": "handsome Korean manhwa male lead with [distinct hair color/style], [eye color] eyes, and [signature outfit/vibe]",
  "female_dna": "beautiful Korean manhwa female lead with [distinct hair color/style], [eye color] eyes, and [signature outfit/vibe]",
  "scenes": [
    {{
      "male_age": "19",
      "female_age": "19",
      "bubble_style": "crisp white oval manga speech bubble pointing to the boy OR fluffy cloud thought bubble above the girl",
      "dialogue": "4 to 7 punchy English words",
      "visual_effect": "specific lighting, weather, and atmospheric particle effects",
      "scene_action": "Rich visual description of what both characters are doing, their facial expressions, and the background setting"
    }}
  ]
}}"""
    return system_prompt, user_prompt


def generate_dynamic_combinatorial_story(history):
    """
    Emergency combinatorial story engine (zero static scenes).
    Assembles a fresh plot from randomized character designs, settings, conflicts, twists, and endings.
    """
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    m_hair = random.choice(["silver-white", "jet-black undercut", "messy ash-brown", "dark midnight-blue", "platinum-blonde"])
    f_hair = random.choice(["long chestnut-brown", "wavy strawberry-blonde", " silky raven-black", "soft caramel", "ponytail dark-cherry"])
    m_eyes = random.choice(["amber", "crimson-grey", "deep sapphire", "emerald", "obsidian"])
    f_eyes = random.choice(["golden-hazel", "violet", "bright sky-blue", "warm jade", "soft rose"])

    age_base = random.choice([17, 18, 19, 20, 21, 22])
    m_age = str(age_base + random.choice([0, 1, 2]))
    f_age = str(age_base)

    hooks = [
        ("You spilled coffee on my shirt.", "two strangers colliding outside a rainy midnight convenience store", "neon rain reflections"),
        ("Stop pretending you don't know me.", "tense encounter in a grand university library aisle at dusk", "floating dust motes in amber sunlight"),
        ("Why did you sit next to me?", "crowded evening subway train as it suddenly brakes", "warm city lights blurring past train windows"),
        ("I'm only dating you by contract.", "luxury rooftop gala overlooking glittering city skyline", "champagne gold bokeh sparkles")
    ]
    tensions = [
        ("Why is he looking at me?", "boy secretly tying his scarf around shivering girl at snowy bus stop", "falling white snowflakes and warm breath mist"),
        ("He stayed up all night for me?", "boy asleep on art studio table beside girl's finished canvas", "soft morning sunbeams"),
        ("Who was that guy with you?", "jealous boy cornering blushing girl near locker hallway", "dramatic high-contrast manga shadows")
    ]
    drops = [
        ("Get behind me. Right now.", "boy stepping in front of girl to shield her from a splashing car in pouring rain", "cinematic water splash and streetlamp halo"),
        ("Don't ever walk away from me!", "boy catching girl's hand on a windy stone bridge at twilight", "swirling autumn leaves and dramatic wind"),
        ("I broke the contract for you.", "man tearing up paper contract in front of stunned girl on balcony", "flying paper shards and moonlight")
    ]
    confessions = [
        ("I fell for you first, dummy.", "boy gently resting his forehead against hers under a single umbrella", "glowing raindrops and soft pink aura"),
        ("Every sketch in my book is you.", "pages of portrait sketches fluttering around them on the school rooftop", "golden sunset flare and wind"),
        ("My heart only beats for you.", "man cupping girl's tearful cheek under glowing festival lanterns", "floating warm sky lanterns")
    ]
    endings = [
        ("Stay by my side forever.", "passionate embrace under night fireworks with blushing smiles", "vibrant fireworks and starry sky"),
        ("You were never a mistake to me.", "couple holding hands walking into glowing sunrise on the beach", "shimmering ocean sunrise light"),
        ("Marry me, my favourite rival.", "man kneeling with ring box in a blooming greenhouse garden", "swirling flower petals and sunbeams")
    ]

    s1, s2, s3, s4, s5 = random.choice(hooks), random.choice(tensions), random.choice(drops), random.choice(confessions), random.choice(endings)

    return {
        "trope": f"Original Webtoon Drama #{run_id}",
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "yt_music_search_query": "Indila Love Story instrumental slowed reverb",
        "video_title": f"\"{s3[0]}\" 💔🥺 #{run_id} #Shorts #manhwa #lovestory",
        "male_dna": f"handsome Korean manhwa boy with {m_hair} hair and {m_eyes} eyes",
        "female_dna": f"beautiful Korean manhwa girl with {f_hair} hair and {f_eyes} eyes",
        "scenes": [
            {"male_age": m_age, "female_age": f_age, "bubble_style": "white oval manga speech bubble pointing to the boy", "dialogue": s1[0], "visual_effect": s1[2], "scene_action": s1[1]},
            {"male_age": m_age, "female_age": f_age, "bubble_style": "fluffy white cloud thought bubble above the girl", "dialogue": s2[0], "visual_effect": s2[2], "scene_action": s2[1]},
            {"male_age": str(int(m_age)+1), "female_age": str(int(f_age)+1), "bubble_style": "dramatic manga speech bubble pointing to the boy", "dialogue": s3[0], "visual_effect": s3[2], "scene_action": s3[1]},
            {"male_age": str(int(m_age)+1), "female_age": str(int(f_age)+1), "bubble_style": "white oval manga speech bubble pointing to the boy", "dialogue": s4[0], "visual_effect": s4[2], "scene_action": s4[1]},
            {"male_age": str(int(m_age)+2), "female_age": str(int(f_age)+2), "bubble_style": "white manga speech bubble between them", "dialogue": s5[0], "visual_effect": s5[2], "scene_action": s5[1]}
        ]
    }


def generate_fresh_story(history):
    """
    Tier 1: Groq Chat LLM (with whisper/audio models strictly filtered out).
    Tier 2: Pollinations Free OpenAI-compatible LLM (if Groq is down).
    Tier 3: Combinatorial Dynamic Matrix (never repeats a static script).
    """
    used_archetypes = history.get("used_archetypes", [])[-6:]
    used_titles = history.get("used_titles", [])
    used_dialogues = history.get("used_dialogues", [])

    available_arch = [a for a in STORY_ARCHETYPES if a not in used_archetypes] or STORY_ARCHETYPES
    chosen_archetype = random.choice(available_arch)
    system_prompt, user_prompt = build_prompt_payload(chosen_archetype, used_titles, used_dialogues)

    # TIER 1: Groq LLM
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            chosen_model = select_groq_chat_model(client)
            print(f"[GROQ-AI] Selected true chat model: {chosen_model}")

            res = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.92
            )
            content = res.choices[0].message.content.strip()
            data = json.loads(content)
            if "scenes" in data and len(data["scenes"]) >= 4:
                data["recommended_yt_song"] = LOCKED_SONG_TITLE
                data["archetype_used"] = chosen_archetype
                print(f"✅ [GROQ-AI] Brand-new story generated: {data.get('video_title')}")
                return data
        except Exception as e:
            print(f"⚠️ Groq LLM error ({e}). Trying secondary Free AI LLM...")

    # TIER 2: Pollinations Free Text LLM (Zero-Key Backup Brain)
    try:
        print("[BACKUP-LLM] Calling Pollinations OpenAI Text API for fresh story...")
        resp = requests.post(
            "https://text.pollinations.ai/openai",
            json={
                "model": "openai",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.9
            },
            timeout=45
        )
        if resp.status_code == 200:
            raw_txt = resp.json()["choices"][0]["message"]["content"].strip()
            if raw_txt.startswith("```"):
                raw_txt = raw_txt.split("```")[1]
                if raw_txt.startswith("json"):
                    raw_txt = raw_txt[4:]
            data = json.loads(raw_txt.strip())
            if "scenes" in data and len(data["scenes"]) >= 4:
                data["recommended_yt_song"] = LOCKED_SONG_TITLE
                data["archetype_used"] = chosen_archetype
                print(f"✅ [BACKUP-LLM] Brand-new story generated: {data.get('video_title')}")
                return data
    except Exception as e:
        print(f"⚠️ Secondary LLM skipped ({e}). Using combinatorial generator...")

    # TIER 3: Dynamic Combinatorial Generator
    return generate_dynamic_combinatorial_story(history)


def generate_complete_manhwa_panel(scene, male_dna, female_dna, story_seed, idx, output_path):
    """Generates the complete 9:16 Manhwa panel with baked-in bubbles, age numbers, and visual effects."""
    api_key = os.getenv("POLLINATIONS_API_KEY")
    m_age = scene.get("male_age", "19")
    f_age = scene.get("female_age", "18")
    bubble_style = scene.get("bubble_style", "white manga speech bubble")
    dialogue = scene.get("dialogue", "Don't let go.")
    visual_effect = scene.get("visual_effect", "dramatic anime lighting and glowing bokeh")
    action = scene.get("scene_action", "romantic couple looking at each other")

    full_ai_prompt = (
        f"Vertical 9:16 Korean webtoon manhwa comic panel illustration. "
        f"Characters: {male_dna} (on left) and {female_dna} (on right), {action}. "
        f"Visual Effects: {visual_effect}, high-contrast cel-shaded anime masterpiece. "
        f"Built-in Comic Typography: At the top corners, floating glowing neon numbers '{m_age}' in blue and '{f_age}' in pink. "
        f"In the upper area, draw one {bubble_style} containing large bold crisp English comic text reading exactly: \"{dialogue}\". "
        f"Strictly English alphabet only, no Chinese characters, no Hanzi, no Kanji, no watermark."
    )

    encoded_prompt = urllib.parse.quote(full_ai_prompt)
    seed = story_seed + (idx * 137)
    url = (
        f"https://gen.pollinations.ai/image/{encoded_prompt}"
        f"?width=1080&height=1920&model=flux&seed={seed}&nologo=true&enhance=false"
    )
    if api_key:
        url += f"&key={api_key}"

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"[AI-PANEL] Generating Scene {idx + 1}/5: \"{dialogue}\"...")
    for attempt in range(4):
        try:
            res = requests.get(url, headers=headers, timeout=75)
            if res.status_code == 200 and "image" in res.headers.get("Content-Type", "") and len(res.content) > 15000:
                with open(output_path, "wb") as f:
                    f.write(res.content)
                print(f"✅ Scene {idx + 1} saved: {output_path}")
                return True
            time.sleep(4)
        except Exception:
            time.sleep(4)
    return False


def synthesize_indila_waltz_fallback(output_mp3, duration_sec=30):
    """
    Synthesizes the D-Minor 3/4 Waltz arpeggio & soaring melody of Indila's 'Love Story'
    with slowed cathedral reverb via FFmpeg if external audio networks are blocked.
    Fixed float boundary clamping with min(2, ...) so IndexError is impossible.
    """
    raw_wav = "workspace/waltz_raw.wav"
    sample_rate = 44100
    num_samples = int(sample_rate * duration_sec)

    waltz_bars = [
        ([146.83, 293.66, 349.23, 440.00], [587.33, 523.25, 440.00]),  # Dm
        ([116.54, 233.08, 293.66, 349.23], [523.25, 466.16, 392.00]),  # Bb
        ([98.00, 196.00, 233.08, 293.66], [466.16, 440.00, 349.23]),   # Gm
        ([110.00, 220.00, 277.18, 329.63], [440.00, 392.00, 329.63])   # A7
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
            # Clamped to [0, 2] to prevent float precision IndexError
            beat_in_bar = min(2, max(0, int((t % bar_len) / beat_len)))
            note_t = max(0.0, (t % bar_len) - (beat_in_bar * beat_len))

            arp_notes, mel_notes = waltz_bars[bar_idx]
            arp_freq = arp_notes[min(beat_in_bar + 1, 3)]
            bass_freq = arp_notes[0]
            mel_freq = mel_notes[beat_in_bar]

            env_arp = math.exp(-note_t * 3.2) * min(1.0, note_t * 40.0)
            env_bass = math.exp(-(t % bar_len) * 1.4)

            signal = 0.35 * math.sin(2 * math.pi * bass_freq * t) * env_bass
            signal += 0.35 * (
                math.sin(2 * math.pi * arp_freq * t) + 0.4 * math.sin(4 * math.pi * arp_freq * t)
            ) * env_arp

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


def get_indila_magical_cut():
    """
    Pulls 'Indila - Love Story (Instrumental Slowed & Reverb)' using python -m yt_dlp,
    slices the 0:45 - 1:15 climax window, and caches it in assets/.
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 40000:
        print(f"✅ Using cached Indila Love Story magical cut: {LOCKED_SONG_PATH}")
        return LOCKED_SONG_PATH

    raw_download = "workspace/indila_full_raw.mp3"
    search_queries = [
        "scsearch3:Indila Love Story instrumental slowed reverb",
        "scsearch3:Indila Love Story slowed reverb",
        "ytsearch3:Indila Love Story instrumental slowed and reverb"
    ]

    downloaded = False
    for query in search_queries:
        print(f"[MUSIC-HUNTER] Searching via python -m yt_dlp: {query}...")
        try:
            if os.path.exists(raw_download):
                os.remove(raw_download)
            # Invoking via sys.executable -m yt_dlp avoids PATH binary missing errors
            cmd = [
                sys.executable, "-m", "yt_dlp",
                query,
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
                print("✅ Downloaded Indila - Love Story (Slowed & Reverb) track!")
                downloaded = True
                break
        except Exception as e:
            print(f"⚠️ Search attempt skipped: {e}")

    if downloaded:
        print(f"[AUDIO-MASTERING] Slicing magical timeline ({GOLDEN_START_SEC}s to {GOLDEN_START_SEC + GOLDEN_DURATION_SEC}s)...")
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
            print(f"🎉 Cached permanent magical cut: {LOCKED_SONG_PATH}")
            return LOCKED_SONG_PATH

    print("[AUDIO-FALLBACK] Generating Indila Love Story D-Minor Waltz (Slowed & Reverb)...")
    fallback_mp3 = "workspace/indila_waltz_fallback.mp3"
    return synthesize_indila_waltz_fallback(fallback_mp3, duration_sec=30)


def build_pipeline():
    print("=== STARTING MANHWA FACTORY (UNIQUE AI STORIES + INDILA LOVE STORY CUT) ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    history = load_history()
    story_data = generate_fresh_story(history)

    # Record title, archetype, and dialogues so future runs never repeat them
    history["used_titles"].append(story_data.get("video_title", ""))
    history.setdefault("used_archetypes", []).append(story_data.get("archetype_used", ""))
    for sc in story_data.get("scenes", []):
        if sc.get("dialogue"):
            history.setdefault("used_dialogues", []).append(sc["dialogue"])
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
        panel_path = f"workspace/panel_{idx}.jpg"
        if not generate_complete_manhwa_panel(sc, male_dna, female_dna, story_seed, idx, panel_path):
            continue

        clip = ImageClip(panel_path).set_duration(scene_duration).resize((1080, 1920))
        clip = clip.resize(lambda t: 1.0 + (0.02 * t))
        clips.append(clip)

    if not clips:
        raise RuntimeError("❌ Pipeline aborted: No AI comic panels were generated.")

    final_video = concatenate_videoclips(clips, method="compose")
    total_dur = final_video.duration

    magical_audio_path = get_indila_magical_cut()
    if magical_audio_path and os.path.exists(magical_audio_path):
        print(f"[AUDIO-SYNC] Locking Indila 'Love Story' climax cut onto {total_dur:.1f}s timeline...")
        audio_clip = AudioFileClip(magical_audio_path)
        if audio_clip.duration < total_dur:
            audio_clip = afx.audio_loop(audio_clip, duration=total_dur)
        else:
            audio_clip = audio_clip.subclip(0, total_dur)

        audio_clip = audio_clip.audio_fadein(0.8).audio_fadeout(1.5).volumex(0.95)
        final_video = final_video.set_audio(audio_clip)

    output_mp4 = "videos/final_manhwa_short.mp4"
    print("[RENDER] Exporting 9:16 Short with embedded soundtrack...")
    final_video.write_videofile(
        output_mp4,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"]
    )
    print(f"🎉 MASTER SHORT COMPLETE: {output_mp4}")


if __name__ == "__main__":
    build_pipeline()
