import os
import random
import json
import sys
import asyncio
import requests
import time
import re
import numpy as np  # <--- FIXED: Added this missing import
from pathlib import Path
import pickle

# ────────────────────────────────────────────────
# 1. ADVANCED IMAGE & TEXT ENGINE
# ────────────────────────────────────────────────
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    AudioFileClip, ImageClip, CompositeVideoClip, 
    concatenate_videoclips, CompositeAudioClip, ColorClip, TextClip
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"
FONT_FILE = os.path.join(ASSETS_DIR, "HindiFont.ttf")

# Ensure folders exist
for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

# Initialize memory files
for f in ["used_topics.json", "used_rhymes.json"]:
    fpath = os.path.join(MEMORY_DIR, f)
    if not os.path.exists(fpath):
        with open(fpath, "w") as file: json.dump([], file)

# ────────────────────────────────────────────────
# 2. FONT & ASSETS ENGINE
# ────────────────────────────────────────────────
def download_assets():
    """Downloads Font + Background Music"""
    if not os.path.exists(FONT_FILE):
        print("📥 Downloading Hindi Font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        try:
            with open(FONT_FILE, 'wb') as f: f.write(requests.get(url, timeout=30).content)
        except: pass

    bg_music = os.path.join(ASSETS_DIR, "bg_music.mp3")
    if not os.path.exists(bg_music):
        print("📥 Downloading Background Music...")
        try:
            url = "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3"
            with open(bg_music, 'wb') as f: f.write(requests.get(url, timeout=30).content)
        except: pass

download_assets()

# ────────────────────────────────────────────────
# 3. MEMORY MANAGEMENT
# ────────────────────────────────────────────────
def load_memory(filename):
    path = os.path.join(MEMORY_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: return []
    return []

def save_to_memory(filename, item):
    path = os.path.join(MEMORY_DIR, filename)
    data = load_memory(filename)
    if item not in data:
        data.append(item)
        if len(data) > 1000: data = data[-1000:]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

# ────────────────────────────────────────────────
# 4. CONTENT GENERATION (CREATIVE MODE RESTORED)
# ────────────────────────────────────────────────
def groq_request(prompt):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9, # High creativity
                "max_tokens": 2000
            },
            timeout=30
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def clean_json(text):
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start == -1 or end == 0: return None
        json_str = text[start:end]
        return json.loads(json_str)
    except:
        return None

def generate_content(mode="short"):
    used_topics = load_memory("used_topics.json")
    
    # 1. Creative Topic Generation
    topic_prompt = f"""
    Generate 1 funny, imaginative topic for a Hindi Kids Rhyme.
    Examples: "Elephant flying a kite", "Cat wearing sunglasses", "Sun eating ice cream".
    Do NOT use: {", ".join(used_topics[-15:])}
    Output ONLY the English topic string.
    """
    topic = groq_request(topic_prompt)
    if not topic: topic = "Funny Animal Dance"
    topic = topic.replace('"', '').replace("Topic:", "").strip()

    print(f"★ Generated Topic: {topic}")
    
    lines = 8 if mode == "short" else 16
    
    # 2. Script Generation (RESTORED TO FUN MODE)
    script_prompt = f"""
    You are a creative songwriter for a Hindi Kids YouTube Channel (like ChuChu TV).
    Topic: "{topic}"
    Format: Nursery Rhyme (Bal Geet).
    Length: {lines} lines.
    
    INSTRUCTIONS:
    1. Write in HINDI (Devanagari script).
    2. MUST RHYME (AABB scheme).
    3. Make it funny and rhythmic. Kids should want to dance.
    4. Simple words, distinct rhyming endings.
    
    Output ONLY valid JSON:
    {{
      "title": "Hindi Title (Fun & Catchy)",
      "keyword": "Main Character (English)",
      "video_tags": ["Tag1", "Tag2", "Tag3"],
      "scenes": [
        {{ "line": "Hindi Rhyme Line 1", "action": "Visual description in English (Cartoon style)" }},
        {{ "line": "Hindi Rhyme Line 2", "action": "Visual description in English" }},
        ...
      ]
    }}
    """
    
    for attempt in range(3):
        raw = groq_request(script_prompt)
        data = clean_json(raw)
        if data:
            data['generated_topic'] = topic
            return data
        print(f"⚠️ Retrying Script Generation ({attempt+1})...")
        time.sleep(2)
        
    return None

# ────────────────────────────────────────────────
# 5. IMAGE ENGINE (FLUX 1080p)
# ────────────────────────────────────────────────
def download_file(url, filename, headers=None):
    try:
        if headers is None: headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 200:
            with open(filename, 'wb') as f: f.write(resp.content)
            try: Image.open(filename).verify(); return True
            except: return False
        return False
    except: return False

def apply_pro_enhancement(filename, target_w, target_h):
    try:
        with Image.open(filename) as img:
            img = img.convert("RGB")
            if img.size != (target_w, target_h):
                img = img.resize((target_w, target_h), resample=Image.LANCZOS)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=250, threshold=3))
            img = ImageEnhance.Contrast(img).enhance(1.15)
            img = ImageEnhance.Color(img).enhance(1.10)
            img.save(filename, "JPEG", quality=98, optimize=True)
    except: pass

def generate_backup_image(filename, target_w=1920, target_h=1080):
    color = (random.randint(60, 220), random.randint(60, 220), random.randint(60, 220))
    img = Image.new('RGB', (target_w, target_h), color=color)
    img.save(filename)
    return True

def get_image(action_desc, filename, keyword, is_short=False):
    print(f"--- HD Img: {action_desc[:30]}... ---")
    seed = random.randint(0, 999999)
    target_w = 1080 if is_short else 1920
    target_h = 1920 if is_short else 1080
    
    clean_prompt = f"{action_desc}, cute pixar 3d cartoon, vibrant colors, masterpiece, 8k uhd".replace(" ", "%20")
    
    api_key = os.getenv('POLLINATIONS_API_KEY')
    success = False
    
    if api_key:
        url_flux = f"https://gen.pollinations.ai/image/{clean_prompt}?model=flux&width={target_w}&height={target_h}&nologo=true&seed={seed}&enhance=true"
        headers = {"Authorization": f"Bearer {api_key}"}
        for _ in range(3):
            if download_file(url_flux, filename, headers):
                success = True
                break
            time.sleep(3)
    
    if not success:
        print("Using Stock Fallback...")
        url_stock = f"https://loremflickr.com/{target_w}/{target_h}/{keyword.replace(' ','')}/?random={seed}"
        success = download_file(url_stock, filename)
    
    if not success: generate_backup_image(filename, target_w, target_h)
    
    apply_pro_enhancement(filename, target_w, target_h)
    return True

# ────────────────────────────────────────────────
# 6. PERFECT HINDI TEXT RENDERER
# ────────────────────────────────────────────────
def generate_text_clip_pil(text, w, h, font_size, duration):
    """Generates a Hindi text clip using PIL (Fixes broken font issues)"""
    # Create transparent canvas
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Load Font
    try: font = ImageFont.truetype(FONT_FILE, font_size)
    except: font = ImageFont.load_default()
    
    # Calculate Text Position (Bottom Center)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (w - text_w) // 2
    y = h - text_h - 250 # Lift from bottom
    
    # Draw Thick Black Stroke
    stroke_width = 8
    for off_x in range(-stroke_width, stroke_width+1):
        for off_y in range(-stroke_width, stroke_width+1):
            draw.text((x+off_x, y+off_y), text, font=font, fill='black')
            
    # Draw Main Text (Bright Yellow)
    draw.text((x, y), text, font=font, fill='#FFFF00')
    
    return ImageClip(np.array(img)).set_duration(duration)

def create_thumbnail(title, bg_path, output_path):
    try:
        if not os.path.exists(bg_path): generate_backup_image(bg_path, 1920, 1080)
        img = Image.open(bg_path).convert("RGBA").resize((1280, 720))
        
        overlay = Image.new("RGBA", img.size, (0,0,0,80))
        img = Image.alpha_composite(img, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        
        try: font = ImageFont.truetype(FONT_FILE, 100)
        except: font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), title, font=font)
        text_w = bbox[2] - bbox[0]
        x = (1280 - text_w) // 2
        y = (720 - bbox[3]) // 2

        for off in range(-4, 5):
            draw.text((x+off, y), title, font=font, fill="black")
            draw.text((x, y+off), title, font=font, fill="black")
        
        draw.text((x, y), title, font=font, fill="#FFD700")
        img.save(output_path, quality=95)
        return output_path
    except: return None

# ────────────────────────────────────────────────
# 7. RENDERER
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    cmd = ["edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", filename]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

def create_segment(text_line, image_path, audio_path, is_short):
    if not os.path.exists(audio_path): return None
    w, h = (1080, 1920) if is_short else (1920, 1080)
    
    if not os.path.exists(image_path): generate_backup_image(image_path, w, h)

    try:
        voice = AudioFileClip(audio_path)
        
        bg_path = os.path.join(ASSETS_DIR, "bg_music.mp3")
        if os.path.exists(bg_path):
            try:
                bg = AudioFileClip(bg_path).volumex(0.12)
                if bg.duration < voice.duration:
                    bg = bg.loop(duration=voice.duration)
                else:
                    start = random.uniform(0, max(0, bg.duration - voice.duration))
                    bg = bg.subclip(start, start + voice.duration)
                voice = CompositeAudioClip([voice, bg])
            except: pass
        
        try: img = ImageClip(image_path)
        except: 
            generate_backup_image(image_path, w, h)
            img = ImageClip(image_path)

        move = random.choice(['zoom_in', 'zoom_out'])
        if move == 'zoom_in': anim = img.resize(lambda t: 1 + 0.035 * t)
        else: anim = img.resize(lambda t: 1.04 - 0.035 * t)
        anim = anim.set_position('center').set_duration(voice.duration)

        # Use Perfect Hindi Renderer
        font_size = 85 if is_short else 100
        txt_clip = generate_text_clip_pil(text_line, w, h, font_size, voice.duration)

        return CompositeVideoClip([anim, txt_clip], size=(w,h)).set_audio(voice)
    except Exception as e:
        print(f"Segment Error: {e}") 
        return None

def make_video(content, is_short=True):
    print(f"Rendering {'SHORT' if is_short else 'LONG'} video...")
    clips = []
    suffix = "s" if is_short else "l"
    keyword = content.get('keyword', 'cartoon')
    
    full_lyrics = ""
    
    for i, scene in enumerate(content['scenes']):
        line = scene['line']
        full_lyrics += line + "\n"
        
        aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
        get_voice(line, aud)
        
        img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
        get_image(scene['action'], img, keyword, is_short=is_short)
        
        clip = create_segment(line, img, aud, is_short)
        if clip: clips.append(clip)

    if not clips: return None, None, None
    
    final = concatenate_videoclips(clips, method="compose")
    out = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    thumb = os.path.join(OUTPUT_DIR, "thumb.png") if not is_short else None
    
    if thumb: create_thumbnail(content['title'], os.path.join(ASSETS_DIR, f"i_{suffix}_0.jpg"), thumb)
    
    # Cleanup Temp Files
    for f in os.listdir(ASSETS_DIR):
        if f.endswith(('.mp3', '.jpg')) and f != "bg_music.mp3" and f != "HindiFont.ttf":
            try: os.remove(os.path.join(ASSETS_DIR, f))
            except: pass

    final.write_videofile(
        out, fps=24, codec='libx264', audio_codec='aac', threads=4,
        preset='medium', ffmpeg_params=['-crf', '18', '-pix_fmt', 'yuv420p']
    )
    return out, full_lyrics, thumb

# ────────────────────────────────────────────────
# 8. UPLOAD ENGINE
# ────────────────────────────────────────────────
def upload_video(vid, content, lyrics, thumb, is_short):
    try:
        if not os.path.exists(TOKEN_FILE): return False
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)
        
        title = f"{content['title']} 🦁 #Shorts" if is_short else f"{content['title']} | Hindi Rhymes 2026 🦁"
        
        static_tags = ['hindi rhymes', 'kids songs', 'bal geet', 'cartoon', 'nursery rhymes']
        ai_tags = content.get('video_tags', [])
        final_tags = list(set(static_tags + ai_tags))[:15]
        dynamic_hashtags = " ".join([f"#{t.replace(' ', '')}" for t in ai_tags[:5]])
        
        desc = f"""{content['title']}

{lyrics}

🦁 SUBSCRIBE for more Rhymes!
✨ New videos daily!

{dynamic_hashtags} #HindiRhymes #KidsSongs #BalGeet
"""
        body = {
            'snippet': {'title': title[:99], 'description': desc, 'tags': final_tags, 'categoryId': '24'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': True}
        }
        
        media = MediaFileUpload(vid, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status: print(f"Progress: {int(status.progress()*100)}%")
            
        print(f"SUCCESS! ID: {resp['id']}")
        
        save_to_memory("used_topics.json", content.get('generated_topic', ''))
        save_to_memory("used_rhymes.json", content['title'])

        if thumb: 
            try: service.thumbnails().set(videoId=resp['id'], media_body=MediaFileUpload(thumb)).execute()
            except: pass
            
        return True
    except HttpError as e:
        if "uploadLimitExceeded" in str(e): print("⚠️ Quota Reached.")
        else: print(f"Upload Error: {e}")
        return False
    except: return False

# ────────────────────────────────────────────────
# MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== HINDI RHYMES PRO (FUN MODE + 1080p) =====")
    summary = []

    # Short
    try:
        print("\n>>> PRODUCING SHORT <<<")
        d = generate_content("short")
        if d:
            v, l, t = make_video(d, True)
            if v: 
                res = upload_video(v, d, l, t, True)
                summary.append(f"Short: {'✅' if res else '❌'} {d['title']}")
    except Exception as e: summary.append(f"Short Error: {e}")

    # Long
    try:
        print("\n>>> PRODUCING LONG <<<")
        d = generate_content("long")
        if d:
            v, l, t = make_video(d, False)
            if v: 
                res = upload_video(v, d, l, t, False)
                summary.append(f"Long: {'✅' if res else '❌'} {d['title']}")
    except Exception as e: summary.append(f"Long Error: {e}")

    print("\n" + "="*40)
    print("📢 BROADCAST SUMMARY")
    for line in summary: print(line)
    print("="*40)
