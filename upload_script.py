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
# 1. ADVANCED IMAGE ENGINE IMPORTS
# ────────────────────────────────────────────────
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

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
# 4. CONTENT GENERATION (GROQ WITH RETRY)
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
                "temperature": 0.8, 
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
    
    # 1. Get Topic
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
    
    # 2. Get Script (With Retry Logic)
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
    
    # Retry 3 times if JSON fails
    for attempt in range(3):
        raw = groq_request(script_prompt)
        data = clean_json(raw)
        if data:
            data['generated_topic'] = topic
            return data
        print(f"⚠️ Groq JSON failed (Attempt {attempt+1}). Retrying...")
        time.sleep(2)
        
    print("❌ Failed to parse Groq JSON after 3 attempts.")
    return None

# ────────────────────────────────────────────────
# 5. ADVANCED IMAGE ENGINE (NATIVE RES + LANCZOS)
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
    """LANCZOS resize + UnsharpMask + professional cartoon enhancement"""
    try:
        with Image.open(filename) as img:
            img = img.convert("RGB")
            
            # LANCZOS – best quality up/down-sampling
            if img.size != (target_w, target_h):
                img = img.resize((target_w, target_h), resample=Image.LANCZOS)
            
            # UnsharpMask (industry standard for crisp video frames)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=250, threshold=3))
            
            # Final cartoon pop
            img = ImageEnhance.Contrast(img).enhance(1.15)
            img = ImageEnhance.Sharpness(img).enhance(1.8)
            img = ImageEnhance.Color(img).enhance(1.10)
            
            img.save(filename, "JPEG", quality=98, optimize=True, subsampling=0)
        print(f"  ✓ LANCZOS + UnsharpMask enhanced to exact {target_w}×{target_h}")
    except Exception as e:
        print(f"  Enhance note: {e}")

def generate_backup_image(filename, target_w=1920, target_h=1080):
    color = (random.randint(60, 220), random.randint(60, 220), random.randint(60, 220))
    img = Image.new('RGB', (target_w, target_h), color=color)
    img.save(filename, quality=95, optimize=True)
    return True

def get_image(action_desc, filename, keyword, is_short=False):
    print(f"--- HD Img: {action_desc[:40]}... ( {'1080x1920 SHORT' if is_short else '1920x1080 LONG'} ) ---")
    seed = random.randint(0, 999999)
    
    target_w = 1080 if is_short else 1920
    target_h = 1920 if is_short else 1080
    
    # Enhanced prompt for maximum sharpness at 1080p
    visual_style = "cute pixar 3d cartoon, vibrant colors, highly detailed, sharp focus, intricate details, masterpiece, 8k uhd, smooth edges, professional kids animation"
    clean_prompt = f"{action_desc}, {visual_style}".replace(" ", "%20").replace(",", "%2C").replace("'", "%27").replace("(", "%28").replace(")", "%29")
    
    success = False
    api_key = os.getenv('POLLINATIONS_API_KEY')
    if api_key:
        url_flux = f"https://gen.pollinations.ai/image/{clean_prompt}?model=flux&width={target_w}&height={target_h}&nologo=true&seed={seed}&enhance=true"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        for attempt in range(3):
            if download_file(url_flux, filename, headers):
                print(f"  ✓ Direct {target_w}×{target_h} Flux HD image!")
                success = True
                break
            print(f"   Retry {attempt+1}/3...")
            time.sleep(4)
    
    if not success:
        print("  → HD Stock fallback...")
        rand_id = random.randint(1, 10000)
        # Using lormeflickr with exact dimensions
        url_stock = f"https://loremflickr.com/{target_w}/{target_h}/{keyword.replace(' ','')}/?random={rand_id}"
        success = download_file(url_stock, filename)
    
    if not success:
        generate_backup_image(filename, target_w, target_h)
    
    # === ADVANCED RESIZING TECHNIQUES (LANCZOS + Pro Enhancements) ===
    apply_pro_enhancement(filename, target_w, target_h)
    return True

# ────────────────────────────────────────────────
# 6. THUMBNAIL ENGINE (PRO RESIZE)
# ────────────────────────────────────────────────
def create_thumbnail(title, bg_path, output_path):
    try:
        if not os.path.exists(bg_path): 
            generate_backup_image(bg_path, 1920, 1080)
        
        with Image.open(bg_path) as img:
            img = img.convert("RGB")
            img = img.resize((1280, 720), resample=Image.LANCZOS)   # ← Pro resize
            
            # Match video enhancements
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=180, threshold=3))
            img = ImageEnhance.Contrast(img).enhance(1.12)
            img = ImageEnhance.Color(img).enhance(1.08)
            
            # Dark overlay
            overlay = Image.new("RGBA", img.size, (0,0,0,75))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            
            draw = ImageDraw.Draw(img)
            try: font = ImageFont.truetype(FONT_FILE, 105)
            except: font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), title, font=font)
            text_w = bbox[2] - bbox[0]
            x = (1280 - text_w) // 2
            y = 160   # Better thumbnail positioning

            # Shadow for pop
            for off in [(4,4), (5,5)]:
                draw.text((x+off[0], y+off[1]), title, font=font, fill=(0,0,0))
            draw.text((x, y), title, font=font, fill="#FFEA00")
            
            img.save(output_path, quality=98, optimize=True)
        return output_path
    except Exception as e:
        print(f"Thumbnail error: {e}")
        return None

# ────────────────────────────────────────────────
# 7. RENDERER (Karaoke Style)
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
    
    if not os.path.exists(image_path): 
        generate_backup_image(image_path, w, h)

    try:
        voice = AudioFileClip(audio_path)
        
        # Background music mix
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
        
        # Image + gentle Ken-Burns zoom (perfect for kids rhymes)
        img = ImageClip(image_path)
        move = random.choice(['zoom_in', 'zoom_out'])
        if move == 'zoom_in':
            anim = img.resize(lambda t: 1 + 0.035 * t)
        else:
            anim = img.resize(lambda t: 1.04 - 0.035 * t)
        anim = anim.set_position('center').set_duration(voice.duration)

        # === PRO KARAOKE TEXT WITH GLOW (much better readability) ===
        font_size = 78 if is_short else 95
        font_to_use = FONT_FILE if os.path.exists(FONT_FILE) else 'Arial'

        # Main yellow text
        txt = TextClip(
            text_line, fontsize=font_size, color='#FFFF00', font=font_to_use,
            stroke_color='black', stroke_width=6, method='caption',
            size=(w-140, None), align='center'
        ).set_position(('center', h - 280)).set_duration(voice.duration)

        # Soft white glow layer (kids love this pop)
        glow = TextClip(
            text_line, fontsize=font_size, color='white', font=font_to_use,
            stroke_color='white', stroke_width=3, method='caption',
            size=(w-140, None), align='center'
        ).set_position(('center', h - 280)).set_duration(voice.duration).set_opacity(0.35)

        return CompositeVideoClip([anim, glow, txt], size=(w, h)).set_audio(voice)

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
        
        # PATCH 4: Pass is_short to generate correct size
        get_image(scene['action'], img, keyword, is_short=is_short)
        
        if i == 0: first_bg = img
        
        clip = create_segment(line, img, aud, is_short)
        if clip: clips.append(clip)

    if not clips: return None, None, None
    
    final = concatenate_videoclips(clips, method="compose")
    out = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    thumb = os.path.join(OUTPUT_DIR, "thumb.png") if not is_short and first_bg else None
    
    if thumb: create_thumbnail(content['title'], first_bg, thumb)
    
    # PATCH 5: Pro Encoding Settings (CRF 18 + Medium) + Cleanup
    final.write_videofile(
        out, 
        fps=24, 
        codec='libx264', 
        audio_codec='aac', 
        threads=4,
        preset='medium',
        ffmpeg_params=['-crf', '18', '-pix_fmt', 'yuv420p', '-tune', 'film']
    )
    
    # === CLEANUP temp files (prevents disk bloat) ===
    for f in os.listdir(ASSETS_DIR):
        if f.startswith(('a_s_', 'a_l_', 'i_s_', 'i_l_')) and f.endswith(('.mp3', '.jpg')):
            try: os.remove(os.path.join(ASSETS_DIR, f))
            except: pass

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
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': True
            }
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
    print("===== HINDI RHYMES PRO (CINEMA QUALITY 1080p) =====")
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
