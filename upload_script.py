import os
import random
import json
import sys
import asyncio
import requests
import time
from pathlib import Path
import pickle

# ────────────────────────────────────────────────
# 1. STABILITY PATCHES
# ────────────────────────────────────────────────
import PIL.Image, PIL.ImageDraw, PIL.ImageFont
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import (
    AudioFileClip, ImageClip, TextClip, CompositeVideoClip, 
    concatenate_videoclips, CompositeAudioClip, ColorClip
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"

for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

# Initialize memory files
for f in ["used_topics.json", "used_rhymes.json"]:
    fpath = os.path.join(MEMORY_DIR, f)
    if not os.path.exists(fpath):
        with open(fpath, "w") as file: json.dump([], file)

# ────────────────────────────────────────────────
# 2. MEMORY MANAGEMENT
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
# 3. CONTENT GENERATION
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
                "temperature": 0.95, 
                "max_tokens": 1500
            },
            timeout=30
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def generate_unique_topic():
    used_topics = load_memory("used_topics.json")
    for _ in range(3):
        prompt = f"""
        Generate 1 unique, creative topic for a Hindi Nursery Rhyme.
        Avoid: {", ".join(used_topics[-10:])}
        Output ONLY the English topic string.
        """
        topic = groq_request(prompt)
        if topic and topic not in used_topics: return topic.replace('"', '').strip()
    return "Funny Animal Party"

def generate_content(mode="short"):
    topic = generate_unique_topic()
    print(f"★ Topic: {topic}")
    lines = 8 if mode == "short" else 16
    
    prompt = f"""
    Topic: "{topic}"
    Write a Hindi Nursery Rhyme ({lines} lines).
    For EACH line, write a specific image prompt in ENGLISH.
    
    Output ONLY JSON:
    {{
      "title": "Hindi Title",
      "keyword": "Main Subject (e.g. Cat)",
      "scenes": [
        {{ "line": "Hindi Line 1", "action": "English Action 1" }},
        ...
      ]
    }}
    """
    raw = groq_request(prompt)
    if not raw: return None
    try:
        start, end = raw.find('{'), raw.rfind('}') + 1
        data = json.loads(raw[start:end])
        data['generated_topic'] = topic
        return data
    except:
        return None

# ────────────────────────────────────────────────
# 4. VARIETY ASSET ENGINE (No Duplicates)
# ────────────────────────────────────────────────
def generate_backup_image(filename):
    color = (random.randint(0,255), random.randint(0,255), random.randint(0,255))
    PIL.Image.new('RGB', (1024, 1024), color=color).save(filename)
    return True

def download_file(url, filename):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200:
            with open(filename, 'wb') as f: f.write(resp.content)
            try:
                PIL.Image.open(filename).verify()
                return True
            except: return False
        return False
    except: return False

def get_image(action_desc, filename, keyword):
    print(f"--- Img: {action_desc[:30]}... ---")
    
    # 1. AI Generation (Random Seed per image = VARIETY)
    clean_action = action_desc.replace(" ", "%20").replace(",", "")
    seed = random.randint(0, 999999) # NEW SEED EVERY TIME
    url_ai = f"https://image.pollinations.ai/prompt/cartoon%20{clean_action}%20vibrant?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    if download_file(url_ai, filename): return True
    
    # 2. Stock Photo (Randomized = NO DUPLICATES)
    print("AI Failed. Trying Random Stock...")
    random_param = random.randint(1, 10000) # Force new image
    url_stock = f"https://loremflickr.com/1024/1024/{keyword.replace(' ','')}?random={random_param}"
    if download_file(url_stock, filename): return True

    return generate_backup_image(filename)

def get_intro_sound(filename):
    if not os.path.exists(filename):
        download_file("https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3", filename)

# ────────────────────────────────────────────────
# 5. THUMBNAIL
# ────────────────────────────────────────────────
def create_thumbnail(title, bg_path, output_path):
    try:
        if not os.path.exists(bg_path): generate_backup_image(bg_path)
        img = PIL.Image.open(bg_path).convert("RGBA").resize((1280, 720))
        overlay = PIL.Image.new("RGBA", img.size, (0,0,0,80))
        img = PIL.Image.alpha_composite(img, overlay)
        draw = PIL.ImageDraw.Draw(img)
        
        font_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
        try: font = PIL.ImageFont.truetype(font_path, 90)
        except: font = PIL.ImageFont.load_default()

        bbox = draw.textbbox((0, 0), title, font=font)
        x = (1280 - (bbox[2] - bbox[0])) // 2
        y = (720 - (bbox[3] - bbox[1])) // 2

        draw.text((x+5, y+5), title, font=font, fill="black")
        draw.text((x, y), title, font=font, fill="#FFD700")
        img.convert("RGB").save(output_path)
        return output_path
    except: return None

# ────────────────────────────────────────────────
# 6. RENDERER
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    cmd = ["edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", filename]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

def create_segment(text_line, image_path, audio_path, is_short, is_first):
    if not os.path.exists(audio_path): return None
    if not os.path.exists(image_path): generate_backup_image(image_path)

    try:
        voice = AudioFileClip(audio_path)
        if is_first:
            intro_path = os.path.join(ASSETS_DIR, "intro.mp3")
            get_intro_sound(intro_path)
            if os.path.exists(intro_path):
                try:
                    intro = AudioFileClip(intro_path).volumex(0.3)
                    if intro.duration > voice.duration: intro = intro.subclip(0, voice.duration)
                    voice = CompositeAudioClip([voice, intro])
                except: pass
        
        w, h = (1080, 1920) if is_short else (1920, 1080)
        
        try: img = ImageClip(image_path)
        except: 
            generate_backup_image(image_path)
            img = ImageClip(image_path)

        if img.w/img.h > w/h: img = img.resize(height=h)
        else: img = img.resize(width=w)
        img = img.crop(x_center=img.w/2, y_center=img.h/2, width=w, height=h)

        move = random.choice(['zoom_in', 'zoom_out'])
        anim = img.resize(lambda t: 1+0.04*t) if move == 'zoom_in' else img.resize(lambda t: 1.05-0.04*t)
        anim = anim.set_position('center').set_duration(voice.duration)

        font_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
        font = PIL.ImageFont.truetype(font_path, 80) if os.path.exists(font_path) else None
        
        # Proper MoviePy Text
        txt = TextClip(text_line, fontsize=70 if is_short else 85, color='yellow', font=font_path if font else 'Arial', stroke_color='black', stroke_width=3, method='caption', size=(w-100, None))
        txt = txt.set_position(('center', 'bottom')).set_duration(voice.duration)

        return CompositeVideoClip([anim, txt], size=(w,h)).set_audio(voice).set_duration(voice.duration)
    except: return None

def make_video(content, is_short=True):
    print(f"Rendering {'SHORT' if is_short else 'LONG'}...")
    clips = []
    suffix = "s" if is_short else "l"
    keyword = content.get('keyword', 'cartoon')
    
    full_lyrics = ""
    first_bg = None
    
    for i, scene in enumerate(content['scenes']):
        line = scene['line']
        full_lyrics += line + "\n"
        
        aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
        get_voice(line, aud)
        
        img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
        # Pass keyword + random seed per line
        get_image(scene['action'], img, keyword)
        
        if i == 0: first_bg = img
        
        clip = create_segment(line, img, aud, is_short, (i==0))
        if clip: clips.append(clip)

    if not clips: return None, None, None
    
    final = concatenate_videoclips(clips, method="compose")
    out = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    thumb = os.path.join(OUTPUT_DIR, "thumb.png") if not is_short and first_bg else None
    
    if thumb: create_thumbnail(content['title'], first_bg, thumb)
    
    final.write_videofile(out, fps=24, codec='libx264', audio_codec='aac', threads=4)
    return out, full_lyrics, thumb

# ────────────────────────────────────────────────
# 7. UPLOAD
# ────────────────────────────────────────────────
def upload_video(vid, content, lyrics, thumb, is_short):
    try:
        if not os.path.exists(TOKEN_FILE): return False
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)
        
        title = f"{content['title']} 🦁 #Shorts" if is_short else f"{content['title']} | Hindi Rhymes 2026 🦁"
        desc = f"{content['title']}\n\n{lyrics}\n\n#HindiRhymes #KidsSongs"
        tags = ['shorts', 'hindi rhymes', 'kids'] if is_short else ['hindi rhymes', 'kids songs']
        
        body = {'snippet': {'title': title[:99], 'description': desc, 'tags': tags, 'categoryId': '24'}, 'status': {'privacyStatus': 'public'}}
        media = MediaFileUpload(vid, chunksize=-1, resumable=True)
        
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status: print(f"Progress: {int(status.progress()*100)}%")
            
        print(f"SUCCESS! ID: {resp['id']}")
        
        # Save Memory
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
# MAIN
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== VARIETY ENGINE =====")
    summary = []

    # Short
    try:
        d = generate_content("short")
        if d:
            v, l, t = make_video(d, True)
            if v: 
                res = upload_video(v, d, l, t, True)
                summary.append(f"Short: {'✅' if res else '❌'} {d['title']}")
    except Exception as e: summary.append(f"Short Error: {e}")

    # Long
    try:
        d = generate_content("long")
        if d:
            v, l, t = make_video(d, False)
            if v: 
                res = upload_video(v, d, l, t, False)
                summary.append(f"Long: {'✅' if res else '❌'} {d['title']}")
    except Exception as e: summary.append(f"Long Error: {e}")

    print("\n".join(summary))
