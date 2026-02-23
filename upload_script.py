import os
import random
import json
import sys
import asyncio
import requests
import time
import re
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (AudioFileClip, ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips, CompositeAudioClip, ColorClip)

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"
FONT_FILE = os.path.join(ASSETS_DIR, "HindiFont.ttf")
ENG_FONT_FILE = os.path.join(ASSETS_DIR, "EngFont.ttf")

for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

for f in ["used_topics.json", "used_rhymes.json"]:
    if not os.path.exists(os.path.join(MEMORY_DIR, f)):
        json.dump([], open(os.path.join(MEMORY_DIR, f), "w"))

# Download assets
def download_assets():
    if not os.path.exists(FONT_FILE):
        open(FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf", timeout=15).content)
    if not os.path.exists(ENG_FONT_FILE):
        open(ENG_FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf", timeout=15).content)
    bg = os.path.join(ASSETS_DIR, "bg_music.mp3")
    if not os.path.exists(bg):
        open(bg, 'wb').write(requests.get("https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3", timeout=15).content)  # Free music loop

download_assets()

# LLM request
def smart_llm_request(prompt):
    print(" -> Attempting Groq (llama-3.3-70b)...")
    res = groq_request(prompt)
    if res:
        print(" -> Success via Groq!")
        return res
    print(" -> Groq failed. Falling back to OpenRouter...")
    res = openrouter_request(prompt)
    if res:
        print(" -> Success via OpenRouter!")
        return res
    print("❌ BOTH AI ENGINES FAILED!")
    return None

# Improved content generation
def generate_content(mode="short"):
    print("\n🧠 Contacting AI for script...")
    used = load_memory("used_topics.json")
    topic_prompt = f"Super cute funny topic for Hindi kids rhyme 2026. Avoid: {', '.join(used[-20:])}. Output ONLY English topic."
    topic = smart_llm_request(topic_prompt) or "Cute Elephant Dancing"
    print(f"★ Generated Topic: {topic}")
    time.sleep(3)

    lines = 8 if mode == "short" else 16
    prompt = f"""You are a top-tier Hindi children's poet. Topic: "{topic}"
    Write a highly melodic, catchy, and rhythmic nursery rhyme.
    CRITICAL RHYME RULES:
    1. Pure Devanagari Hindi (no English words in the rhyme).
    2. PERFECT RHYTHM: Every line must have exactly 5 to 7 words! Make it a complete, singable sentence.
    3. Perfect AABB rhyme scheme.
    4. NO EMOJIS in the 'line' or 'title' fields.
    CRITICAL VISUAL RULES:
    5. The 'action' field MUST be a highly detailed English prompt that exactly matches the Hindi 'line'.
    6. Every single 'action' MUST include the main character's description so the scene matches the lyrics perfectly!
    Output ONLY valid JSON:
    {{"keyword": "Main English character", "title": "Hindi catchy title", "rhyme_lines": ["Line 1", "Line 2",...], "image_prompt": "cute pixar 3d cartoon style, vibrant colors, kids style"}}
    """
    for attempt in range(4):
        raw = smart_llm_request(prompt)
        data = clean_json(raw)
        if data and "rhyme_lines" in data:
            print("✅ Valid Rhyme Script Generated!")
            data['generated_topic'] = topic
            save_to_memory("used_topics.json", topic)
            return data
        print(f"⚠️ Formatting failed (Attempt {attempt+1}/4). Retrying in 5s...")
        time.sleep(5)
    return None

# Improved image engine
def get_image(action, fn, kw, is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    seed = random.randint(0, 999999)
    clean = f"{kw}, {action}, Mango Yellow, Royal Blue, Deep Turquoise, cute pixar 3d kids cartoon vibrant masterpiece 8k".replace(" ", "%20")
    api = os.getenv('POLLINATIONS_API_KEY')
    if api:
        url = f"https://gen.pollinations.ai/image/{clean}?model=flux&width={w}&height={h}&nologo=true&seed={seed}&enhance=true"
        if download_file(url, fn, {"Authorization": f"Bearer {api}"}):
            apply_pro_enhancement(fn, w, h)
            return

    # Improved fallback
    stock = f"https://loremflickr.com/{w}/{h}/{kw.lower()}/?lock={seed}"
    if download_file(stock, fn):
        apply_pro_enhancement(fn, w, h)
        return

    # Ultimate fallback
    Image.new('RGB', (w, h), (random.randint(70, 230),)*3).save(fn)

# Voice
async def generate_voice_async(text, fn):
    clean_speech = clean_text_for_font(text)
    proc = await asyncio.create_subprocess_exec(
        "edge-tts", "--voice", "hi-IN-SwaraNeural", "--rate=-15%", "--pitch=+8Hz", "--text", clean_speech, "--write-media", fn
    )
    await proc.wait()

def get_voice(text, fn):
    asyncio.run(generate_voice_async(text, fn))

# Video
def create_segment(text_line, image_path, audio_path, idx):
    audio = AudioFileClip(audio_path)
    duration = audio.duration + 0.5
    img = ImageClip(image_path).resize(height=1920).crop(x_center=img.w/2, width=1080, height=1920)
    anim = img.resize(lambda t: 1 + 0.04 * t).set_duration(duration).set_position('center')
    txt = TextClip(
        text_line, fontsize=75, color='yellow', font='DejaVu-Sans-Bold', stroke_color='black', stroke_width=4, method='caption', size=(950, None)
    ).set_position(('center', 1450)).set_duration(duration)
    clip = CompositeVideoClip([anim, txt], size=(1080,1920)).set_audio(audio).set_duration(duration)
    if idx > 0:
        clip = clip.crossfadein(0.5)
    return clip

def make_video(content, is_short=True):
    clips = []
    bg_path = os.path.join(ASSETS_DIR, "bg.jpg")
    get_image(content['image_prompt'], bg_path, content['keyword'], is_short)
    full_lyrics = ""
    for i, line in enumerate(content['rhyme_lines']):
        if not line.strip(): continue
        full_lyrics += line + "\n"

        aud_path = os.path.join(ASSETS_DIR, f"voice_{i}.mp3")
        get_voice(line, aud_path)

        clip = create_segment(line, bg_path, aud_path, i)
        clips.append(clip)

    # End screen
    outro = ColorClip((1080,1920), (15,15,20)).set_duration(4)
    txt1 = TextClip("LIKE 👍 SUBSCRIBE", fontsize=85, color='yellow', font='DejaVu-Sans-Bold', stroke_color='black', stroke_width=5).set_position('center').set_duration(4)
    outro = CompositeVideoClip([outro, txt1])
    clips.append(outro)

    final = concatenate_videoclips(clips, method="compose")
    out = os.path.join(OUTPUT_DIR, "final.mp4")
    final.write_videofile(out, fps=24, codec='libx264', audio_codec='aac', threads=4, preset='veryfast', ffmpeg_params=['-crf', '20', '-pix_fmt', 'yuv420p'])
    return out, full_lyrics

# UPLOAD
def upload_video(video_path, content, lyrics):
    try:
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)

        title = content.get('title', "Hindi Rhyme 2026")
        desc = f"{title}\n\n{lyrics}\n\n#HindiRhymes #KidsSongs"

        body = {
            'snippet': {'title': title, 'description': desc, 'tags': ['hindi rhymes', 'kids songs'], 'categoryId': '24'},
            'status': {'privacyStatus': 'public'}
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)

        print("Uploading...")
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                print(f"Progress: {int(status.progress()*100)}%")

        print(f"SUCCESS! Video ID: {resp['id']}")
        return True
    except Exception as e:
        print(f"Upload error: {e}")
        return False

if __name__ == "__main__":
    print("===== Magic Engine V6 (Final) =====")
    data = generate_content()
    print(f"Topic: {data['title']}")
    vid, lyrics = make_video(data)
    upload_video(vid, data, lyrics)
