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
    # 1. Font (Noto Sans Devanagari)
    if not os.path.exists(FONT_FILE):
        print("📥 Downloading Hindi Font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        try:
            with open(FONT_FILE, 'wb') as f: f.write(requests.get(url, timeout=30).content)
        except: pass

    # 2. Music (Royalty Free Kids Loop)
    bg_music = os.path.join(ASSETS_DIR, "bg_music.mp3")
    if not os.path.exists(bg_music):
        print("📥 Downloading Background Music...")
        try:
            # A cheerful, safe-for-youtube kids track
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
# 4. CONTENT GENERATION (POWERED BY GROQ)
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
                "temperature": 0.9, 
                "max_tokens": 2000
            },
            timeout=30
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def clean_json(text):
    """Cleans Markdown formatting from LLM"""
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start == -1 or end == 0: return None
        json_str = text[start:end]
        return json.loads(json_str)
    except:
        return None

def generate_content(mode="short"):
    # 1. Topic Selection (Rhyme Only)
    used_topics = load_memory("used_topics.json")
    
    topic_prompt = f"""
    Generate 1 unique, creative, and funny topic for a Hindi Nursery Rhyme for kids.
    Examples: "A monkey driving a bus", "A star falling into a pond", "An elephant dancing".
    Do NOT use these previous topics: {", ".join(used_topics[-15:])}
    Output ONLY the English topic string. No explanations.
    """
    topic = groq_request(topic_prompt)
    if not topic: topic = "Funny Animal Party"
    topic = topic.replace('"', '').replace("Topic:", "").strip()

    print(f"★ Generated Topic: {topic}")
    
    # 2. Script Generation
    lines = 8 if mode == "short" else 16
    
    script_prompt = f"""
    You are a professional Hindi poet for Kids YouTube.
    Topic: "{topic}"
    Format: Hindi Nursery Rhyme (Bal Geet).
    Length: {lines} lines.
    Style: Funny, rhythmic, easy to sing.
    
    Output ONLY valid JSON with this structure:
    {{
      "title": "Hindi Title (in Hindi Script)",
      "keyword": "Main Subject in English (e.g. Monkey)",
      "video_tags": ["Tag1", "Tag2", "Tag3", "Tag4", "Tag5"],
      "scenes": [
        {{ "line": "Hindi Line 1", "action": "Detailed visual description in English for AI image generator (Pixar style)" }},
        {{ "line": "Hindi Line 2", "action": "Detailed visual description in English" }},
        ...
      ]
    }}
    """
    
    raw = groq_request(script_prompt)
    data = clean_json(raw)
    
    if data:
        data['generated_topic'] = topic
        return data
    else:
        print("Failed to parse Groq JSON")
        return None

# ────────────────────────────────────────────────
# 5. SMART VISUALS (Cartoon Style)
# ────────────────────────────────────────────────
def generate_backup_image(filename):
    """Creates a solid color image as safety net"""
    color = (random.randint(50,255), random.randint(50,255), random.randint(50,255))
    PIL.Image.new('RGB', (1024, 1024), color=color).save(filename)
    return True

def download_file(url, filename):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200:
            with open(filename, 'wb') as f: f.write(resp.content)
            try: PIL.Image.open(filename).verify(); return True
            except: return False
        return False
    except: return False

def get_image(action_desc, filename, keyword):
    print(f"--- Img: {action_desc[:40]}... ---")
    seed = random.randint(0, 999999)
    
    # 1. AI Generation (Pollinations - Turbo Model)
    # Force "Pixar/Disney Style" for consistency
    prompt = f"cartoon {action_desc}, 3d render, pixar style, vibrant colors, cute, high quality"
    clean_prompt = prompt.replace(" ", "%20").replace(",", "")
    
    url_ai = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    if download_file(url_ai, filename): return True
    
    # 2. Stock Fallback
    print("AI Failed. Trying Stock...")
    rand_id = random.randint(1, 10000)
    url_stock = f"https://loremflickr.com/1024/1024/{keyword.replace(' ','')}?random={rand_id}"
    if download_file(url_stock, filename): return True

    return generate_backup_image(filename)

# ────────────────────────────────────────────────
# 6. THUMBNAIL ENGINE
# ────────────────────────────────────────────────
def create_thumbnail(title, bg_path, output_path):
    try:
        if not os.path.exists(bg_path): generate_backup_image(bg_path)
        img = PIL.Image.open(bg_path).convert("RGBA").resize((1280, 720))
        
        # Add slight dark overlay for text pop
        overlay = PIL.Image.new("RGBA", img.size, (0,0,0,60))
        img = PIL.Image.alpha_composite(img, overlay)
        draw = PIL.ImageDraw.Draw(img)
        
        try: font = PIL.ImageFont.truetype(FONT_FILE, 100)
        except: font = PIL.ImageFont.load_default()

        # Center Text
        bbox = draw.textbbox((0, 0), title, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (1280 - text_w) // 2, (720 - text_h) // 2

        # Stroke/Shadow
        for off in range(1, 6):
            draw.text((x+off, y+off), title, font=font, fill="black")
        
        draw.text((x, y), title, font=font, fill="#FFD700") # Gold
        img.convert("RGB").save(output_path)
        return output_path
    except: return None

# ────────────────────────────────────────────────
# 7. RENDERER (Karaoke Style)
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    # SwaraNeural is the industry standard for Hindi AI narration
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
        
        # Add Background Music (Low Volume)
        bg_path = os.path.join(ASSETS_DIR, "bg_music.mp3")
        if os.path.exists(bg_path):
            try:
                bg = AudioFileClip(bg_path).volumex(0.1) # 10% volume
                if bg.duration < voice.duration:
                    bg = bg.loop(duration=voice.duration)
                else:
                    start = random.uniform(0, bg.duration - voice.duration)
                    bg = bg.subclip(start, start + voice.duration)
                voice = CompositeAudioClip([voice, bg])
            except: pass
        
        w, h = (1080, 1920) if is_short else (1920, 1080)
        
        try: img = ImageClip(image_path)
        except: 
            generate_backup_image(image_path)
            img = ImageClip(image_path)

        # Smart Crop (Fill Screen)
        if img.w/img.h > w/h: img = img.resize(height=h)
        else: img = img.resize(width=w)
        img = img.crop(x_center=img.w/2, y_center=img.h/2, width=w, height=h)

        # Subtle Animation (Zoom)
        move = random.choice(['zoom_in', 'zoom_out'])
        if move == 'zoom_in':
            anim = img.resize(lambda t: 1 + 0.04 * t)
        else:
            anim = img.resize(lambda t: 1.05 - 0.04 * t)
        anim = anim.set_position('center').set_duration(voice.duration)

        # Subtitles (Using Local Hindi Font)
        font_arg = FONT_FILE if os.path.exists(FONT_FILE) else 'Arial'
        font_size = 75 if is_short else 90
        
        # Yellow Text with Black Stroke
        txt = TextClip(
            text_line, fontsize=font_size, color='yellow', font=font_arg, 
            stroke_color='black', stroke_width=4, method='caption', size=(w-100, None)
        )
        txt = txt.set_position(('center', 'bottom')).set_duration(voice.duration)
        txt = txt.set_position(('center', h - 250)) # Lift from bottom edge

        return CompositeVideoClip([anim, txt], size=(w,h)).set_audio(voice).set_duration(voice.duration)
    except Exception as e:
        print(f"Segment Error: {e}") 
        return None

def make_video(content, is_short=True):
    print(f"Rendering {'SHORT' if is_short else 'LONG'} video...")
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
# 8. UPLOAD ENGINE (Smart Metadata)
# ────────────────────────────────────────────────
def upload_video(vid, content, lyrics, thumb, is_short):
    try:
        if not os.path.exists(TOKEN_FILE): return False
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)
        
        # Smart Titles
        title = f"{content['title']} 🦁 #Shorts" if is_short else f"{content['title']} | Hindi Rhymes 2026 🦁"
        
        # Tags Logic
        static_tags = ['hindi rhymes', 'kids songs', 'bal geet', 'cartoon', 'nursery rhymes']
        ai_tags = content.get('video_tags', [])
        final_tags = list(set(static_tags + ai_tags))[:15]
        
        # Hashtags
        dynamic_hashtags = " ".join([f"#{t.replace(' ', '')}" for t in ai_tags[:5]])
        
        desc = f"""{content['title']}

{lyrics}

🦁 SUBSCRIBE for more Rhymes!
✨ New videos daily!

{dynamic_hashtags} #HindiRhymes #KidsSongs #BalGeet
"""
        body = {
            'snippet': {'title': title[:99], 'description': desc, 'tags': final_tags, 'categoryId': '24'},
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': True # Pushes to Kids App
            }
        }
        
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
# MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__
