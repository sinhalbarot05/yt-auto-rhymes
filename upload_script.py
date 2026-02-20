import os, random, json, asyncio, requests, time, numpy as np
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ────────────────────────────────────────────────
# 1. STABILITY & FONT PATCHES
# ────────────────────────────────────────────────
if not hasattr(Image, 'ANTIALIAS'): 
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (AudioFileClip, ImageClip, CompositeVideoClip,
                            concatenate_videoclips, CompositeAudioClip, ColorClip)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"
FONT_FILE = os.path.join(ASSETS_DIR, "HindiFont.ttf")

for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)
for f in ["used_topics.json", "used_rhymes.json"]:
    if not os.path.exists(os.path.join(MEMORY_DIR, f)):
        json.dump([], open(os.path.join(MEMORY_DIR, f), "w"))

# ────────────────────────────────────────────────
# 2. FONT & ASSETS ENGINE
# ────────────────────────────────────────────────
def download_assets():
    if not os.path.exists(FONT_FILE):
        print("📥 Downloading Hindi Font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        open(FONT_FILE, 'wb').write(requests.get(url, timeout=15).content)
    bg = os.path.join(ASSETS_DIR, "bg_music.mp3")
    if not os.path.exists(bg):
        print("📥 Downloading Background Music...")
        url = "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3"
        open(bg, 'wb').write(requests.get(url, timeout=15).content)

download_assets()

# ────────────────────────────────────────────────
# 3. PIL TEXT RENDERER (NO MORE TEXTCLIP ERROR)
# ────────────────────────────────────────────────
def generate_text_clip_pil(text, w, h, size, dur, color='#FFFF00', pos_y=None, stroke_width=8):
    """Replaces MoviePy TextClip completely. Handles Hindi perfectly."""
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype(FONT_FILE, size)
    except: font = ImageFont.load_default()
    
    bbox = draw.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = (w - tw) // 2
    y = pos_y if pos_y is not None else (h - th - 340) # Default to subtitle position
    
    # Draw Stroke
    for dx in range(-stroke_width, stroke_width+1, 2):
        for dy in range(-stroke_width, stroke_width+1, 2):
            draw.text((x+dx, y+dy), text, font=font, fill='black')
    
    draw.text((x,y), text, font=font, fill=color)
    return ImageClip(np.array(img)).set_duration(dur)

# ────────────────────────────────────────────────
# 4. INTRO/OUTRO BUILDERS (REFIXED)
# ────────────────────────────────────────────────
def create_intro(is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    bg = ColorClip((w, h), (255, 215, 0)).set_duration(2.2)
    txt = generate_text_clip_pil("हिंदी मस्ती राइम्स 🦁 2026", w, h, 95, 2.2, color='white', pos_y=h//2 - 50)
    return CompositeVideoClip([bg, txt], size=(w, h)).crossfadeout(0.5)

def create_outro(is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    bg = ColorClip((w, h), (20, 20, 40)).set_duration(4.5)
    txt1 = generate_text_clip_pil("LIKE 👍 SUBSCRIBE 🦁", w, h, 92, 4.5, color='#FFFF00', pos_y=h//3)
    txt2 = generate_text_clip_pil("@HindiMastiRhymes", w, h, 78, 4.5, color='white', pos_y=h*0.6)
    return CompositeVideoClip([bg, txt1, txt2], size=(w, h))

# ────────────────────────────────────────────────
# 5. CONTENT & IMAGE LOGIC
# ────────────────────────────────────────────────
def groq_request(prompt):
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.75, "max_tokens": 3000}, timeout=45)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return None

def clean_json(text):
    try: return json.loads(text[text.find('{'):text.rfind('}')+1])
    except: return None

def generate_content(mode="short"):
    p = os.path.join(MEMORY_DIR, "used_topics.json")
    used = json.load(open(p)) if os.path.exists(p) else []
    topic_prompt = f"Funny topic for Hindi kids rhyme 2026. Avoid: {', '.join(used[-20:])}. Output ONLY English topic."
    topic = groq_request(topic_prompt) or "Monkey eating Mango"

    lines = 8 if mode == "short" else 16
    prompt = f"""You are ChuChu TV expert. Topic: "{topic}". Create {lines} lines with CHORUS. Output ONLY JSON:
    {{
      "seo_title": "Hindi Nursery Rhymes for Kids 2026 | ... 🦁",
      "title": "Hindi Title",
      "keyword": "Character",
      "seo_tags": ["tag1", "tag2"],
      "scenes": [{{"line": "Hindi line", "action": "Pixar 3D visual description"}}]
    }}"""
    data = clean_json(groq_request(prompt))
    if data:
        data['generated_topic'] = topic
        used.append(topic)
        json.dump(used[-1000:], open(p, "w"))
    return data

def get_image(action, fn, kw, is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    seed = random.randint(0, 999999)
    clean = f"{action}, pixar cartoon vibrant colors".replace(" ", "%20")
    api = os.getenv('POLLINATIONS_API_KEY')
    url = f"https://gen.pollinations.ai/image/{clean}?model=flux&width={w}&height={h}&seed={seed}"
    headers = {"Authorization": f"Bearer {api}"} if api else {}
    try:
        r = requests.get(url, headers=headers, timeout=60)
        open(fn, 'wb').write(r.content)
        with Image.open(fn) as im:
            im.convert("RGB").resize((w, h), Image.LANCZOS).save(fn, quality=95)
    except: Image.new('RGB', (w, h), (100, 100, 100)).save(fn)

# ────────────────────────────────────────────────
# 6. RENDERING PIPELINE
# ────────────────────────────────────────────────
async def generate_voice_async(text, fn):
    await asyncio.create_subprocess_exec("edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", fn).wait()

def get_voice(text, fn): asyncio.run(generate_voice_async(text, fn))

def create_segment(line, img_path, aud_path, is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    voice = AudioFileClip(aud_path)
    img = ImageClip(img_path)
    anim = img.resize(lambda t: 1.02 - 0.01 * t).set_position('center').set_duration(voice.duration)
    txt = generate_text_clip_pil(line, w, h, 90 if is_short else 115, voice.duration)
    return CompositeVideoClip([anim, txt], size=(w, h)).set_audio(voice)

def make_video(content, is_short=True):
    print(f"🎥 Rendering {'SHORT' if is_short else 'LONG'}...")
    clips = [create_intro(is_short)]
    suffix = "s" if is_short else "l"
    
    with ThreadPoolExecutor(max_workers=5) as ex:
        for i, scene in enumerate(content['scenes']):
            aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
            img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
            ex.submit(get_voice, scene['line'], aud)
            ex.submit(get_image, scene['action'], img, content['keyword'], is_short)
            time.sleep(0.5)

    lyrics = ""
    for i, scene in enumerate(content['scenes']):
        aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
        img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
        if os.path.exists(aud) and os.path.exists(img):
            clips.append(create_segment(scene['line'], img, aud, is_short))
            lyrics += scene['line'] + "\n"

    clips.append(create_outro(is_short))
    final = concatenate_videoclips(clips, method="compose")
    out = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    final.write_videofile(out, fps=24, codec='libx264', audio_codec='aac', preset='veryfast')
    return out, lyrics

# ────────────────────────────────────────────────
# 7. MAIN BROADCASTER
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== HINDI RHYMES PRO 2026 =====")
    for is_short in [True, False]:
        data = generate_content("short" if is_short else "long")
        if data:
            vid, lyr = make_video(data, is_short)
            # Add your upload logic here (omitted for brevity, keep your existing one)
            print(f"✅ Video ready: {vid}")
