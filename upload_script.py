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
    concatenate_videoclips, CompositeAudioClip
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

# ────────────────────────────────────────────────
# 2. GENERATE CONTENT (Groq)
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
                "temperature": 0.85, 
                "max_tokens": 1500
            },
            timeout=30
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def generate_content(mode="short"):
    topics = [
        "Elephant playing football", "Butterfly in garden", "Train journey", 
        "School Bus adventure", "Ice Cream truck", "Cat stealing milk", 
        "Lion the king", "Parrot talking", "Car racing", "Doctor helping", 
        "Police catching thief", "Sun waking up", "Fish in ocean", 
        "Rabbit and Tortoise", "Cow giving milk", "Traffic Light"
    ]
    selected_topic = random.choice(topics)
    lines_count = 6 if mode == "short" else 10
    
    prompt = f"""
    You are a professional Hindi writer for a Kids YouTube Channel.
    Topic: "{selected_topic}"
    
    1. Create a simple Hindi Nursery Rhyme ({lines_count} lines).
    2. Define a character visual description in ENGLISH only.
    3. For EACH line, write a specific image action prompt in ENGLISH only.
    
    Output ONLY valid JSON format:
    {{
      "title": "Hindi Title",
      "keyword": "Main Subject in English (e.g. Elephant)",
      "main_char_visual": "Detailed visual description in ENGLISH",
      "scenes": [
        {{ "line": "Hindi Line 1", "action": "Action in ENGLISH" }},
        ... (Total {lines_count} items)
      ]
    }}
    """
    raw = groq_request(prompt)
    if not raw: return None
    try:
        start, end = raw.find('{'), raw.rfind('}') + 1
        return json.loads(raw[start:end])
    except:
        return None

# ────────────────────────────────────────────────
# 3. UNBREAKABLE IMAGE ENGINE (Browser Headers)
# ────────────────────────────────────────────────
def download_file(url, filename):
    try:
        # Browser Headers to prevent "403 Forbidden" or Corrupt Files
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            
            # Verify Image
            try:
                img = PIL.Image.open(filename)
                img.verify()
                # Re-open to check dimensions
                img = PIL.Image.open(filename)
                if img.width < 100 or img.height < 100:
                    return False
                return True
            except:
                return False
        return False
    except:
        return False

def get_image(visual_desc, action_desc, filename, fixed_seed, keyword):
    print(f"--- Gen Image: {action_desc} ---")
    
    # 1. AI Generation (Pollinations)
    clean_prompt = f"{visual_desc} {action_desc}, vibrant colors, 3d render, pixar style".replace(" ", "%20").replace(",", "")
    url_ai = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1024&height=1024&nologo=true&seed={fixed_seed}&model=turbo"
    if download_file(url_ai, filename): return True
    
    # 2. Keyword Search (First Attempt - Specific)
    print(f"AI Failed. Trying Stock Photo for '{keyword}'...")
    url_stock = f"https://loremflickr.com/1080/1920/{keyword.replace(' ','')}"
    if download_file(url_stock, filename): return True

    # 3. Keyword Search (Second Attempt - Generic)
    # If "Car Racing" fails, try "Car"
    simple_keyword = keyword.split()[0] 
    print(f"Stock Failed. Trying generic '{simple_keyword}'...")
    url_stock_2 = f"https://loremflickr.com/1080/1920/{simple_keyword}"
    if download_file(url_stock_2, filename): return True

    # 4. Ultimate Fallback (High Quality Cartoon)
    # Never fails, always looks good for kids
    print("All failed. Using High-Quality Cartoon fallback.")
    url_fallback = "https://loremflickr.com/1080/1920/cartoon"
    if download_file(url_fallback, filename): return True
    
    return False

def get_intro_sound(filename):
    if not os.path.exists(filename):
        # Reliable source
        url = "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3" 
        download_file(url, filename)

# ────────────────────────────────────────────────
# 4. THUMBNAIL ENGINE
# ────────────────────────────────────────────────
def create_thumbnail(title, bg_path, output_path):
    print("Generating Thumbnail...")
    try:
        if not os.path.exists(bg_path): return None

        img = PIL.Image.open(bg_path).convert("RGBA")
        img = img.resize((1280, 720)) 
        
        overlay = PIL.Image.new("RGBA", img.size, (0,0,0,80))
        img = PIL.Image.alpha_composite(img, overlay)
        draw = PIL.ImageDraw.Draw(img)
        
        try:
            font = PIL.ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", 90)
        except:
            font = PIL.ImageFont.load_default()

        bbox = draw.textbbox((0, 0), title, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (1280 - text_w) // 2
        y = (720 - text_h) // 2

        draw.text((x+5, y+5), title, font=font, fill="black")
        draw.text((x, y), title, font=font, fill="#FFD700") 
        
        img = img.convert("RGB")
        img.save(output_path)
        return output_path
    except Exception as e:
        print(f"Thumbnail error: {e}")
        return None

# ────────────────────────────────────────────────
# 5. RENDERER (With Smart Resize to Fix "Tile" Error)
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    cmd = ["edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

def create_segment(text_line, image_path, audio_path, is_short=True, is_first=False):
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0: return None
    if not os.path.exists(image_path): return None

    try:
        voice_clip = AudioFileClip(audio_path)
        
        # Intro Logic
        if is_first:
            intro_path = os.path.join(ASSETS_DIR, "intro.mp3")
            get_intro_sound(intro_path)
            if os.path.exists(intro_path):
                try:
                    intro = AudioFileClip(intro_path).volumex(0.3)
                    if intro.duration > voice_clip.duration: 
                        intro = intro.subclip(0, voice_clip.duration)
                    final_audio = CompositeAudioClip([voice_clip, intro])
                except:
                    final_audio = voice_clip
            else:
                final_audio = voice_clip
        else:
            final_audio = voice_clip

        duration = final_audio.duration
        target_w, target_h = (1080, 1920) if is_short else (1920, 1080)
        
        img = ImageClip(image_path)

        # ─── CRITICAL FIX: SMART RESIZE ───
        # This logic prevents "tile cannot extend outside image" crash
        # It forces the image to be AT LEAST the size of the video before cropping.
        
        # Calculate aspect ratios
        img_ratio = img.w / img.h
        target_ratio = target_w / target_h

        if img_ratio < target_ratio:
            # Image is too tall/narrow -> Width is the limiting factor
            # Resize width to match target width, height will exceed target height
            new_width = target_w
            new_height = int(target_w / img_ratio)
            img = img.resize(width=new_width)
        else:
            # Image is too wide -> Height is the limiting factor
            # Resize height to match target height, width will exceed target width
            new_height = target_h
            new_width = int(target_h * img_ratio)
            img = img.resize(height=new_height)

        # Now Safe to Crop (Center)
        img = img.crop(
            x_center=img.w/2, 
            y_center=img.h/2, 
            width=target_w, 
            height=target_h
        )

        # Animation (Zoom)
        move = random.choice(['zoom_in', 'zoom_out'])
        if move == 'zoom_in':
            anim = img.resize(lambda t: 1 + 0.04 * t)
        else:
            anim = img.resize(lambda t: 1.05 - 0.04 * t)
            
        anim = anim.set_position('center').set_duration(duration)

        # Text
        font_size = 70 if is_short else 85
        txt = TextClip(
            text_line, fontsize=font_size, color='yellow', font='DejaVu-Sans-Bold', 
            stroke_color='black', stroke_width=4, method='caption', size=(target_w-100, None)
        ).set_position(('center', 'bottom' if is_short else 'bottom')).set_duration(duration)
        
        txt = txt.set_position(('center', target_h - 200))

        return CompositeVideoClip([anim, txt], size=(target_w, target_h)).set_audio(final_audio).set_duration(duration)

    except Exception as e:
        print(f"Segment creation error: {e}")
        return None

def make_video(content, is_short=True):
    print(f"Rendering {'SHORT' if is_short else 'LONG'} video...")
    clips = []
    suffix = "s" if is_short else "l"
    
    fixed_seed = random.randint(0, 999999)
    char_desc = content.get('main_char_visual', 'cute cartoon character')
    keyword = content.get('keyword', 'cartoon')
    
    full_lyrics = ""
    first_bg_path = None
    
    for i, scene in enumerate(content['scenes']):
        line = scene['line']
        action = scene['action']
        full_lyrics += line + "\n"
        
        aud_path = os.path.join(ASSETS_DIR, f"aud_{suffix}_{i}.mp3")
        get_voice(line, aud_path)
        
        img_path = os.path.join(ASSETS_DIR, f"img_{suffix}_{i}.jpg")
        
        # Try to get image, if fails completely, skip line
        if not get_image(char_desc, action, img_path, fixed_seed, keyword):
            print(f"Skipping line {i} due to missing image.")
            continue
        
        if i == 0: first_bg_path = img_path
        
        clip = create_segment(line, img_path, aud_path, is_short, (i==0))
        if clip: clips.append(clip)

    if not clips: 
        print("No clips generated. Aborting video.")
        return None, None, None
    
    final = concatenate_videoclips(clips, method="compose")
    out_file = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    
    thumb_path = None
    if not is_short and first_bg_path:
        thumb_path = os.path.join(OUTPUT_DIR, "thumb.png")
        create_thumbnail(content['title'], first_bg_path, thumb_path)

    # Fast Render for GitHub
    final.write_videofile(out_file, fps=24, codec='libx264', audio_codec='aac', threads=4)
    return out_file, full_lyrics, thumb_path

# ────────────────────────────────────────────────
# 6. UPLOAD ENGINE
# ────────────────────────────────────────────────
def upload_video(video_path, content, lyrics, thumb_path, is_short=True):
    try:
        if not os.path.exists(TOKEN_FILE): return False
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        
        service = build('youtube', 'v3', credentials=creds)
        
        if is_short:
            title = f"{content['title']} 🦁 #Shorts #HindiRhymes"
            tags = ['shorts', 'hindi rhymes', 'kids']
        else:
            title = f"{content['title']} | Hindi Rhymes 2026 🦁"
            tags = ['hindi rhymes', 'kids songs', 'bal geet', 'cartoon']

        desc = f"{content['title']}\n\n{lyrics}\n\n#HindiRhymes #KidsSongs"
        
        body = {'snippet': {'title': title[:99], 'description': desc, 'tags': tags, 'categoryId': '24'}, 'status': {'privacyStatus': 'public'}}
        
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        try:
            req = service.videos().insert(part="snippet,status", body=body, media_body=media)
            resp = None
            while resp is None:
                status, resp = req.next_chunk()
                if status: print(f"Progress: {int(status.progress()*100)}%")
            vid_id = resp['id']
            print(f"SUCCESS! ID: {vid_id}")
            
            if thumb_path and os.path.exists(thumb_path):
                try:
                    service.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(thumb_path)).execute()
                except:
                    print("Thumbnail upload failed.")
            return True
        except HttpError as e:
            if "uploadLimitExceeded" in str(e):
                print("⚠️ Daily Quota Reached.")
                return False
            print(f"Upload Error: {e}")
            return False
    except Exception as e:
        print(f"Upload Error: {e}")
        return False

if __name__ == "__main__":
    print("===== SKYROCKET ENGINE (Bulletproof V3) =====")
    
    data_s = generate_content("short")
    if data_s:
        v, l, t = make_video(data_s, True)
        if v: upload_video(v, data_s, l, t, True)

    data_l = generate_content("long")
    if data_l:
        v, l, t = make_video(data_l, False)
        if v: upload_video(v, data_l, l, t, False)
