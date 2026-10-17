import os
import json
import time
import math
import wave
import struct
import random
import subprocess
import urllib.parse
import requests
from groq import Groq
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, afx

HISTORY_FILE = "story_history.json"
LOCKED_SONG_PATH = "assets/indila_love_story_magical_cut.mp3"
LOCKED_SONG_TITLE = "Love Story (Instrumental Slowed & Reverb) - Indila"

# Golden timestamp window (0:45 to 1:15) where pre-chorus swells into the main orchestral drop at ~10.4s
GOLDEN_START_SEC = 45
GOLDEN_DURATION_SEC = 30

TROPE_CATALOG = [
    "Childhood Next-Door Neighbours to Lovers (Ages 8 & 9 -> 15 & 16 -> 18 & 19 -> 22 & 23 Marriage Proposal)",
    "Academic Rivals to Secret Lovers (Rank #1 Cold Boy & Rank #2 Stubborn Girl -> Library Rain Confession -> Couple)",
    "One-Sided Crush to Second-Lead Rescue (Girl rejected by cold senior -> Kind umbrella boy comforts her in rain -> Senior regrets)",
    "Fake Dating to Real Feelings (Contract couple to make ex jealous -> Rooftop moment -> Falling madly in love)",
    "Brother's Best Friend Forbidden Crush (Little sister's friend at 15 -> Reunion at 20 -> He confesses he waited for her)",
    "Cold CEO & Clumsy Intern (Strict boss secretly leaves warm coffee -> Protects her at gala -> Rooftop confession)",
    "Bus Stop Strangers to Soulmates (Sharing earphones every rainy morning -> Separation -> Miracle reunion at station)",
    "Basketball Captain & Quiet Art Girl (He finds her sketchbook full of his portraits -> Rain confession -> Kiss)",
    "Rich Heir & Scholarship Student (He hides his wealth to tutor her -> Family tries to separate them -> He chooses her)",
    "Childhood Promise Under the Cherry Tree (Separated at age 10 with matching rings -> Reunited at age 20 -> Ring reveal)"
]


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"used_titles": [], "used_tropes": [], "total_videos": 0}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def build_procedural_unique_story(history):
    """Fallback generator that creates a fresh story synced to the Love Story beat drop."""
    run_id = history.get("total_videos", 0) + random.randint(100, 999)
    male_hairs = ["jet-black", "silver-white", "ash-brown", "dark navy", "golden-blonde"]
    female_hairs = ["chestnut-brown", "strawberry-blonde", "long raven-black", "soft caramel", "dark cherry"]
    m_hair = random.choice(male_hairs)
    f_hair = random.choice(female_hairs)

    return {
        "trope": f"Eternal Waltz Romance #{run_id}",
        "recommended_yt_song": LOCKED_SONG_TITLE,
        "yt_music_search_query": "Indila Love Story instrumental slowed reverb",
        "video_title": f"He loved her in silence for 10 years... 💔🥀 #{run_id} #Shorts #manhwa #lovestory",
        "male_dna": f"handsome Korean manhwa boy with {m_hair} hair and deep expressive eyes",
        "female_dna": f"beautiful Korean manhwa girl with {f_hair} hair and glowing eyes",
        "scenes": [
            {
                "male_age": "12",
                "female_age": "11",
                "bubble_style": "white oval manga speech bubble pointing to the boy",
                "dialogue": "Hold my hand so you don't get lost.",
                "visual_effect": "soft golden sunset particles and nostalgic warm lighting",
                "scene_action": "two cute childhood friends walking home under autumn trees"
            },
            {
                "male_age": "16",
                "female_age": "15",
                "bubble_style": "fluffy white cloud thought bubble above the girl",
                "dialogue": "Since when did his smile make me blush?",
                "visual_effect": "dreamy pink cherry blossom petals floating through classroom window light",
                "scene_action": "handsome high school boy leaning over girl's desk smiling softly"
            },
            {
                "male_age": "18",
                "female_age": "17",
                "bubble_style": "dramatic manga speech bubble pointing to the boy",
                "dialogue": "Take my coat. I'm right here with you.",
                "visual_effect": "heavy cinematic rain droplets, glowing streetlamp halo, emotional blue-gold contrast",
                "scene_action": "dramatic rain climax, tall boy wrapping his uniform jacket around shivering girl under streetlamp"
            },
            {
                "male_age": "20",
                "female_age": "19",
                "bubble_style": "white oval manga speech bubble pointing to the boy",
                "dialogue": "It was always you. Every single day.",
                "visual_effect": "magical floating golden light orbs and starry night sky",
                "scene_action": "handsome young man gently cupping blushing girl's cheek on a starry balcony, intense gaze"
            },
            {
                "male_age": "24",
                "female_age": "23",
                "bubble_style": "white manga speech bubble between them",
                "dialogue": "Spend the rest of your life with me.",
                "visual_effect": "warm fairy lights, glowing sparkles, cinematic wedding sunset flare",
                "scene_action": "handsome man in suit embracing tearful smiling woman with a diamond ring on her finger"
            }
        ]
    }


def generate_fresh_story_via_groq(history):
    """Generates a brand-new 5-scene story paced specifically to Indila's Love Story beat drop."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return build_procedural_unique_story(history)

    used_tropes = history.get("used_tropes", [])[-6:]
    used_titles = history.get("used_titles", [])[-10:]
    available_tropes = [t for t in TROPE_CATALOG if t not in used_tropes] or TROPE_CATALOG
    chosen_trope = random.choice(available_tropes)
    entropy = f"{int(time.time())}-{random.randint(1000, 9999)}"

    client = Groq(api_key=groq_key)
    system_prompt = (
        "You are an elite Korean Manhwa director creating vertical Shorts synced to the magical climax of "
        "'Indila - Love Story (Instrumental Slowed & Reverb)'. Output strictly valid JSON."
    )
    user_prompt = f"""Create a brand-new 5-scene Korean Manhwa romance Short script.
Entropy Seed: {entropy}
Selected Trope: "{chosen_trope}"
Previously Used Titles (DO NOT REPEAT): {json.dumps(used_titles)}

MUSICAL SYNC PACING (CRITICAL):
- Scene 1 (0.0s - 5.2s): Soft acoustic intro -> Innocent meeting or childhood memory.
- Scene 2 (5.2s - 10.4s): Rising string pre-chorus -> Growing secret feelings, jealousy, or tension.
- Scene 3 (10.4s - 15.6s): THE ORCHESTRAL BEAT DROP -> High-drama emotional turning point (rain rescue, heartbreak twist, or sudden protection).
- Scene 4 (15.6s - 20.8s): Soaring violin chorus -> Intense romantic confession or embrace.
- Scene 5 (20.8s - 26.0s): Emotional peak & warm echo -> Unforgettable climax (proposal, kiss, or bittersweet regret).

VISUAL & TEXT RULES:
1. All speech bubbles, thought clouds, age numbers, and visual effects are generated directly inside the AI artwork by Flux.
2. Keep "dialogue" between 4 to 7 punchy English words so Flux renders every letter cleanly.
3. Specify "bubble_style" clearly (e.g., "fluffy white cloud thought bubble above the girl" or "crisp white oval manga speech bubble pointing to the boy").

Return ONLY valid JSON with this structure:
{{
  "trope": "{chosen_trope}",
  "recommended_yt_song": "{LOCKED_SONG_TITLE}",
  "yt_music_search_query": "Indila Love Story instrumental slowed reverb",
  "video_title": "Viral emotional title with emojis #Shorts #manhwa #lovestory",
  "male_dna": "handsome Korean manhwa boy with [unique hair color/style] and [eye color] eyes",
  "female_dna": "beautiful Korean manhwa girl with [unique hair color/style] and [eye color] eyes",
  "scenes": [
    {{
      "male_age": "16",
      "female_age": "15",
      "bubble_style": "crisp white oval manga speech bubble pointing to the boy",
      "dialogue": "4 to 7 punchy English words",
      "visual_effect": "floating cherry blossom petals and golden sunset glow",
      "scene_action": "Detailed visual action of both characters, expressions, setting"
    }}
  ]
}}"""

    try:
        models_resp = client.models.list().data
        available_ids = [m.id for m in models_resp]
        preferred = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192", "gemma2-9b-it"]
        chosen_model = next((m for m in preferred if m in available_ids), available_ids[0])

        res = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.88
        )
        data = json.loads(res.choices[0].message.content.strip())
        data["recommended_yt_song"] = LOCKED_SONG_TITLE
        if "scenes" in data and len(data["scenes"]) >= 4:
            print(f"✅ Fresh Story Synced to Indila Love Story: {data.get('video_title')}")
            return data
    except Exception as e:
        print(f"⚠️ Groq call fallback ({e}). Using procedural story generator.")

    return build_procedural_unique_story(history)


def generate_complete_manhwa_panel(scene, male_dna, female_dna, story_seed, idx, output_path):
    """Generates the complete 9:16 Manhwa panel with baked-in bubbles, age numbers, and visual effects."""
    api_key = os.getenv("POLLINATIONS_API_KEY")
    m_age = scene.get("male_age", "18")
    f_age = scene.get("female_age", "17")
    bubble_style = scene.get("bubble_style", "white manga speech bubble")
    dialogue = scene.get("dialogue", "I waited for you.")
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
    seed = story_seed + (idx * 101)
    url = (
        f"https://gen.pollinations.ai/image/{encoded_prompt}"
        f"?width=1080&height=1920&model=flux&seed={seed}&nologo=true&enhance=false"
    )
    if api_key:
        url += f"&key={api_key}"

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"[AI-PANEL] Generating Scene {idx + 1}/5...")
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
    Synthesizes the signature D-Minor 3/4 Waltz arpeggio & soaring melody of Indila's 'Love Story'
    with slowed cathedral reverb via FFmpeg if all external audio networks are blocked on the runner.
    """
    raw_wav = "workspace/waltz_raw.wav"
    sample_rate = 44100
    num_samples = int(sample_rate * duration_sec)

    # Indila 'Love Story' 3/4 Waltz Arpeggio Progression: Dm -> Bb -> Gm -> A7
    waltz_bars = [
        ([146.83, 293.66, 349.23, 440.00], [587.33, 523.25, 440.00]),  # Dm (D3, D4, F4, A4) + Melody
        ([116.54, 233.08, 293.66, 349.23], [523.25, 466.16, 392.00]),  # Bb (Bb2, Bb3, D4, F4)
        ([98.00, 196.00, 233.08, 293.66], [466.16, 440.00, 349.23]),   # Gm (G2, G3, Bb3, D4)
        ([110.00, 220.00, 277.18, 329.63], [440.00, 392.00, 329.63])   # A7 (A2, A3, C#4, E4)
    ]
    beat_len = 0.65  # Slowed waltz tempo (~92 BPM in 3/4)
    bar_len = beat_len * 3

    with wave.open(raw_wav, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(num_samples):
            t = i / sample_rate
            bar_idx = int(t / bar_len) % len(waltz_bars)
            beat_in_bar = int((t % bar_len) / beat_len)
            note_t = (t % bar_len) - (beat_in_bar * beat_len)

            arp_notes, mel_notes = waltz_bars[bar_idx]
            # Arpeggio pluck
            arp_freq = arp_notes[min(beat_in_bar + 1, 3)]
            bass_freq = arp_notes[0]
            mel_freq = mel_notes[beat_in_bar]

            env_arp = math.exp(-note_t * 3.2) * min(1.0, note_t * 40.0)
            env_bass = math.exp(-(t % bar_len) * 1.4)

            signal = 0.35 * math.sin(2 * math.pi * bass_freq * t) * env_bass
            signal += 0.35 * (
                math.sin(2 * math.pi * arp_freq * t) + 0.4 * math.sin(4 * math.pi * arp_freq * t)
            ) * env_arp

            # Bring in the sweeping chorus strings at t >= 10.4s (Scene 3 Beat Drop!)
            if t >= 10.4:
                swell = min(1.0, (t - 10.4) / 1.5)
                vibrato = 1.0 + 0.004 * math.sin(2 * math.pi * 5.2 * t)
                signal += 0.45 * swell * (
                    math.sin(2 * math.pi * mel_freq * vibrato * t)
                    + 0.5 * math.sin(2 * math.pi * (mel_freq * 2) * vibrato * t)
                )

            sample = int(max(-1.0, min(1.0, signal * 0.6)) * 32767)
            wf.writeframesraw(struct.pack("<h", sample))

    # Apply slowed & reverb atmospheric filter via FFmpeg
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_wav,
        "-af", "aecho=0.8:0.88:65:0.45,lowpass=f=3800",
        "-b:a", "192k", output_mp3
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp3


def get_indila_magical_cut():
    """
    Ensures every video gets the exact 0:45 - 1:15 magical climax cut of
    'Indila - Love Story (Instrumental Slowed & Reverb)'.
    Caches the cut in assets/indila_love_story_magical_cut.mp3 permanently.
    """
    os.makedirs("assets", exist_ok=True)
    os.makedirs("workspace", exist_ok=True)

    # 1. If the magical cut is already cached in the repository, use it immediately
    if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 40000:
        print(f"✅ Using cached magical cut: {LOCKED_SONG_PATH} (0:45-1:11 Climax Window)")
        return LOCKED_SONG_PATH

    raw_download = "workspace/indila_full_raw.mp3"
    search_queries = [
        # SoundCloud search works reliably on GitHub Actions IPs without bot blocks
        "scsearch3:Indila Love Story instrumental slowed reverb",
        "scsearch3:Indila Love Story slowed reverb instrumental",
        # YouTube search queries
        "ytsearch3:Indila Love Story instrumental slowed and reverb",
        "ytsearch3:Indila Love Story караоке instrumental slowed"
    ]

    downloaded = False
    for query in search_queries:
        print(f"[MUSIC-HUNTER] Searching for Indila Love Story via: {query}...")
        try:
            if os.path.exists(raw_download):
                os.remove(raw_download)
            cmd = [
                "yt-dlp",
                query,
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
                "--match-filter", "duration > 95 & duration < 420",
                "--max-downloads", "1",
                "--no-playlist",
                "--quiet",
                "--output", raw_download
            ]
            subprocess.run(cmd, timeout=60, check=False)
            if os.path.exists(raw_download) and os.path.getsize(raw_download) > 50000:
                print("✅ Downloaded full Indila - Love Story (Slowed & Reverb) track!")
                downloaded = True
                break
        except Exception as e:
            print(f"⚠️ Query attempt skipped: {e}")

    if downloaded:
        print(f"[AUDIO-MASTERING] Slicing magical timeline ({GOLDEN_START_SEC}s to {GOLDEN_START_SEC + GOLDEN_DURATION_SEC}s)...")
        # Slice 0:45 to 1:15 and add gentle cathedral reverb + loudness normalization
        slice_cmd = [
            "ffmpeg", "-y",
            "-ss", str(GOLDEN_START_SEC),
            "-t", str(GOLDEN_DURATION_SEC),
            "-i", raw_download,
            "-af", "aecho=0.8:0.85:50:0.25,loudnorm=I=-14:TP=-1.5:LRA=11",
            "-b:a", "192k",
            LOCKED_SONG_PATH
        ]
        subprocess.run(slice_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(LOCKED_SONG_PATH) and os.path.getsize(LOCKED_SONG_PATH) > 30000:
            print(f"🎉 Saved permanent magical cut to {LOCKED_SONG_PATH}!")
            return LOCKED_SONG_PATH

    print("[AUDIO-FALLBACK] Synthesizing Indila Love Story D-Minor Waltz (Slowed & Reverb)...")
    fallback_mp3 = "workspace/indila_waltz_fallback.mp3"
    return synthesize_indila_waltz_fallback(fallback_mp3, duration_sec=30)


def build_pipeline():
    print("=== STARTING MANHWA FACTORY (LOCKED SOUND: INDILA LOVE STORY SLOWED & REVERB) ===")
    os.makedirs("workspace", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    history = load_history()
    story_data = generate_fresh_story_via_groq(history)

    history["used_titles"].append(story_data.get("video_title", ""))
    history["used_tropes"].append(story_data.get("trope", ""))
    history["total_videos"] = history.get("total_videos", 0) + 1
    save_history(history)

    with open("workspace/video_metadata.json", "w", encoding="utf-8") as f:
        json.dump(story_data, f, indent=2, ensure_ascii=False)

    male_dna = story_data.get("male_dna", "")
    female_dna = story_data.get("female_dna", "")
    scenes = story_data.get("scenes", [])
    story_seed = random.randint(100000, 999999)

    scene_duration = 5.2  # 5 scenes * 5.2s = 26.0s total (Scene 3 hits right at 10.4s beat drop)
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

    # Attach the locked Indila - Love Story (0:45 - 1:11) magical cut
    magical_audio_path = get_indila_magical_cut()
    if magical_audio_path and os.path.exists(magical_audio_path):
        print(f"[AUDIO-SYNC] Locking Indila 'Love Story' climax cut onto {total_dur:.1f}s timeline...")
        audio_clip = AudioFileClip(magical_audio_path)
        if audio_clip.duration < total_dur:
            audio_clip = afx.audio_loop(audio_clip, duration=total_dur)
        else:
            audio_clip = audio_clip.subclip(0, total_dur)

        # Smooth 0.8s fade-in and 1.5s fade-out so Shorts looping feels seamless
        audio_clip = audio_clip.audio_fadein(0.8).audio_fadeout(1.5).volumex(0.95)
        final_video = final_video.set_audio(audio_clip)

    output_mp4 = "videos/final_manhwa_short.mp4"
    print("[RENDER] Exporting 9:16 Short with Indila - Love Story (Slowed & Reverb)...")
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
