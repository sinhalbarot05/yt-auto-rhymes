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
FONT_FILE = os.path.join(ASSETS_DIR, "HindiFont.ttf")

for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

# Initialize memory files
for f in ["used_topics.json", "used_rhymes.json"]:
    fpath = os.path.join(MEMORY_DIR, f)
    if not os.path.exists(fpath):
        with open(fpath, "w") as file: json.dump([], file)

# ────────────────────────────────────────────────
# 2. FONT & MUSIC ENGINE (New!)
# ────────────────────────────────────────────────
def download_assets():
    """Downloads Font + Random Music Tracks"""
    # 1. Font
    if not os.path.exists(FONT_FILE):
        print("📥 Downloading Hindi Font...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf"
        try:
            with open(FONT_FILE, 'wb') as f: f.write(requests.get(url, timeout=30).content)
        except: pass

    # 2. Music Library (Royalty Free)
    music_tracks = {
        "happy.mp3": "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3",
        "calm.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", # Placeholder safe links
    }
    
    # Just ensure we have at least one usable track
    default_bg = os.path.join(ASSETS_DIR, "bg_music.mp3")
    if not os.path.exists(default_bg):
        print("📥 Downloading Background Music...")
        try:
            # Using a known safe sample for now
            url = "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3"
            with open(default_bg, 'wb') as f: f.write(requests.get(url, timeout=30).content)
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
# 4. MULTI-NICHE BRAIN (The "Implant")
# ────────────────────────────────────────────────
def groq_request(prompt):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.95, "max_tokens": 1500},
            timeout=30
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def generate_content(mode="short"):
    # RANDOMIZE NICHE to keep channel fresh
    niche_type = random.choice(["rhyme", "fact", "riddle"])
    print(f"★ Selected Niche: {niche_type.upper()}")

    used_topics = load_memory("used_topics.json")
    
    # 1. Generate Topic based on Niche
    topic_prompt = f"""
    Generate 1 unique topic for a Hindi {niche_type}.
    - If Rhyme: Funny animal or daily life.
    - If Fact: Surprising science or nature fact.
    - If Riddle: "Guess who am I?" style.
    Avoid: {", ".join(used_topics[-10:])}
    Output ONLY the English topic string.
    """
    topic = groq_request(topic_prompt)
    if not topic: topic = "Funny Cat"
    topic = topic.replace('"', '').strip()
    
    print(f"★ Topic: {topic}")
    lines = 8 if mode == "short" else 16
    
    # 2. Generate Script
    script_prompt = f"""
    You are a Hindi content creator.
    Type: {niche_type.upper()}
    Topic: "{topic}"
    Length: {lines} lines/sentences.
    
    Instructions:
    - If Rhyme: Rhyming, funny, for kids.
    - If Fact: "Did you know?" style, engaging, clear Hindi.
    - If Riddle: Clues first, answer at the end.
    
    Output ONLY JSON:
    {{
      "title": "Hindi Title (Engaging)",
      "keyword": "Main Subject in English (e.g. Tiger)",
      "style": "{niche_type}",
      "video_tags": ["Tag1", "Tag2", "Tag3", "Tag4", "Tag5"],
      "scenes": [
        {{ "line": "Hindi text line 1", "action": "Specific Image Prompt in English (Visual description)" }},
        ...
      ]
    }}
    """
    raw = groq_request(script_prompt)
    if not raw: return None
    try:
        start, end = raw.find('{'), raw.rfind('}') + 1
        data = json.loads(raw[start:end])
        data['generated_topic'] = topic
        return data
    except: return None

# ────────────────────────────────────────────────
# 5. SMART VISUALS (Real vs Cartoon)
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
            try: PIL.Image.open(filename).verify(); return True
            except: return False
        return False
    except: return False

def get_image(action_desc, filename, keyword, style):
    print(f"--- Img: {action_desc[:30]}... ---")
    seed = random.randint(0, 999999)
    
    # Adjust style based on Niche
    if style == "fact":
        visual_style = "realistic, 4k, high quality photo, national geographic style"
    else:
        visual_style = "cartoon style, vibrant, 3d render, pixar style"

    clean_action = action_desc.replace(" ", "%20").replace(",", "")
    clean_style = visual_style.replace(" ", "%20").replace(",", "")
    
    # 1. AI Generation
    url_ai = f"https://image.pollinations.ai/prompt/{clean_action}%20{clean_style}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    if download_file(url_ai, filename): return True
    
    # 2. Stock Fallback
    print("AI Failed. Trying Stock...")
    rand_id = random.randint(1, 10000)
    url_stock = f"https://loremflickr.com/1024/1024/{keyword.replace(' ','')}?random={rand_id}"
    if download_file(url_stock, filename): return True

    return generate_backup_image(filename)

# ────────────────────────────────────────────────
# 6. THUMBNAIL
# ────────────────────────────────────────────────
def create_thumbnail(title, bg_path, output_path):
    try:
        if not os.path.exists(bg_path): generate_backup_image(bg_path)
        img = PIL.Image.open(bg_path).convert("RGBA").resize((1280, 720))
        overlay = PIL.Image.new("RGBA", img.size, (0,0,0,80))
        img = PIL.Image.alpha_composite(img, overlay)
        draw = PIL.ImageDraw.Draw(img)
        
        try: font = PIL.ImageFont.truetype(FONT_FILE, 90)
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
# 7. RENDERER (With Background Music)
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
        
        # Add Background Music (Low Volume)
        bg_music_path = os.path.join(ASSETS_DIR, "bg_music.mp3")
        if os.path.exists(bg_music_path):
            try:
                bg = AudioFileClip(bg_music_path).volumex(0.15) # 15% volume
                # Loop background if voice is longer, or subclip if shorter
                if bg.duration < voice.duration:
                    bg = bg.loop(duration=voice.duration)
                else:
                    # Random start point for variety
                    start = random.uniform(0, max(0, bg.duration - voice.duration))
                    bg = bg.subclip(start, start + voice.duration)
                
                voice = CompositeAudioClip([voice, bg])
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

        font_arg = FONT_FILE if os.path.exists(FONT_FILE) else 'Arial'
        txt = TextClip(text_line, fontsize=70 if is_short else 85, color='yellow', font=font_arg, stroke_color='black', stroke_width=3, method='caption', size=(w-100, None))
        txt = txt.set_position(('center', 'bottom')).set_duration(voice.duration)
        txt = txt.set_position(('center', h - 250))

        return CompositeVideoClip([anim, txt], size=(w,h)).set_audio(voice).set_duration(voice.duration)
    except Exception as e:
        print(f"Segment Error: {e}") 
        return None

def make_video(content, is_short=True):
    print(f"Rendering {'SHORT' if is_short else 'LONG'}...")
    clips = []
    suffix = "s" if is_short else "l"
    keyword = content.get('keyword', 'cartoon')
    style = content.get('style', 'rhyme')
    
    full_lyrics = ""
    first_bg = None
    
    for i, scene in enumerate(content['scenes']):
        line = scene['line']
        full_lyrics += line + "\n"
        
        aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
        get_voice(line, aud)
        
        img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
        get_image(scene['action'], img, keyword, style)
        
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
# 8. UPLOAD
# ────────────────────────────────────────────────
def upload_video(vid, content, lyrics, thumb, is_short):
    try:
        if not os.path.exists(TOKEN_FILE): return False
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)
        
        style_icon = "🦁"
        if content.get('style') == 'fact': style_icon = "🧠"
        if content.get('style') == 'riddle': style_icon = "🕵️"

        title = f"{content['title']} {style_icon} #Shorts" if is_short else f"{content['title']} | Hindi {content.get('style','Video').title()} 2026 {style_icon}"
        
        static_tags = ['hindi rhymes', 'kids songs', 'facts', 'gk', 'trivia']
        ai_tags = content.get('video_tags', [])
        final_tags = list(set(static_tags + ai_tags))[:15]
        
        dynamic_hashtags = " ".join([f"#{t.replace(' ', '')}" for t in ai_tags[:5]])
        
        desc = f"""{content['title']}

{lyrics}

🦁 SUBSCRIBE for more!
✨ New videos daily!

{dynamic_hashtags} #HindiRhymes #KidsSongs #GK #Facts
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
# MAIN
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== MULTI-NICHE BROADCASTER =====")
    summary = []

    # Short
    try:
        d = generate_content("short")
        if d:
            v, l, t = make_video(d, True)
            if v: 
                res = upload_video(v, d, l, t, True)
                summary.append(f"Short ({d.get('style','?')}) : {'✅' if res else '❌'} {d['title']}")
    except Exception as e: summary.append(f"Short Error: {e}")

    # Long
    try:
        d = generate_content("long")
        if d:
            v, l, t = make_video(d, False)
            if v: 
                res = upload_video(v, d, l, t, False)
                summary.append(f"Long ({d.get('style','?')}): {'✅' if res else '❌'} {d['title']}")
    except Exception as e: summary.append(f"Long Error: {e}")

    print("\n".join(summary))
