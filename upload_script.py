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

# ────────────────────────────────────────────────
# 2. GENERATE CONTENT (Smart Language Logic)
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
    # English topics ensure the visual keyword is English
    topics = [
        "Elephant playing football", "Butterfly in garden", "Train journey", 
        "School Bus adventure", "Ice Cream truck", "Cat stealing milk", 
        "Lion the king", "Parrot talking", "Car racing", "Doctor helping", 
        "Police catching thief", "Sun waking up", "Fish in ocean", 
        "Rabbit and Tortoise", "Cow giving milk", "Traffic Light"
    ]
    selected_topic = random.choice(topics)
    lines_count = 6 if mode == "short" else 10
    
    # CRITICAL FIX: We explicitly ask for visual_desc in ENGLISH
    prompt = f"""
    You are a professional Hindi writer for a Kids YouTube Channel.
    Topic: "{selected_topic}"
    
    1. Create a simple Hindi Nursery Rhyme ({lines_count} lines).
    2. Define a consistent visual description for the main character in ENGLISH.
    3. For EACH line, write a specific image prompt in ENGLISH.
    
    Output ONLY valid JSON format:
    {{
      "title": "Hindi Title",
      "keyword": "Main Subject in English (e.g. Elephant)",
      "main_char_visual": "Detailed visual description in ENGLISH (e.g. A cute baby elephant wearing a red cap)",
      "scenes": [
        {{ "line": "Hindi Line 1", "action": "English description of action (e.g. Elephant kicking a football)" }},
        {{ "line": "Hindi Line 2", "action": "English description of action" }},
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
# 3. UNBREAKABLE ASSET ENGINE
# ────────────────────────────────────────────────
def generate_backup_image(filename):
    """Creates a solid color image so the script NEVER crashes"""
    print("Generating Safety Image...")
    try:
        color = (random.randint(0,255), random.randint(0,255), random.randint(0,255))
        img = PIL.Image.new('RGB', (1024, 1024), color=color)
        
        # Add some text so it's not just a blank color
        draw = PIL.ImageDraw.Draw(img)
        try:
            font = PIL.ImageFont.load_default()
            draw.text((400, 500), "Image Loading...", fill="white", font=font)
        except:
            pass
            
        img.save(filename)
        return True
    except Exception as e:
        print(f"Safety generator failed: {e}")
        return False

def download_file(url, filename):
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            # Verify image integrity
            try:
                img = PIL.Image.open(filename)
                img.verify()
                return True
            except:
                print("Downloaded file was corrupt (Verify failed).")
                return False
        else:
            print(f"Download failed: Status {resp.status_code}")
            return False
    except Exception as e:
        print(f"Download Error: {e}")
        return False

def get_image(visual_desc, action_desc, filename, fixed_seed, keyword):
    print(f"--- Gen Image: {action_desc} ---")
    
    # 1. AI Generation (Pollinations) - Primary
    # Clean the prompt to ensure it works in URL
    clean_action = action_desc.replace(" ", "%20").replace(",", "")
    clean_visual = visual_desc.replace(" ", "%20").replace(",", "")
    
    full_prompt = f"{clean_visual}%20{clean_action}%20cartoon%20style%20vibrant"
    url_ai = f"https://image.pollinations.ai/prompt/{full_prompt}?width=1024&height=1024&nologo=true&seed={fixed_seed}&model=turbo"
    
    if download_file(url_ai, filename): return True
    
    # 2. Keyword Search (LoremFlickr) - Secondary
    # Only use the simple English keyword (e.g. "Cat") NOT the Hindi sentence
    print(f"AI Failed. Trying Stock Photo for '{keyword}'...")
    url_stock = f"https://loremflickr.com/1024/1024/{keyword.replace(' ','')}"
    if download_file(url_stock, filename): return True

    # 3. Ultimate Safety Net - Tertiary
    print("Network Failed. Creating Safety Image.")
    generate_backup_image(filename)
    return True

def get_intro_sound(filename):
    if not os.path.exists(filename):
        url = "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3" 
        download_file(url, filename)

# ────────────────────────────────────────────────
# 4. THUMBNAIL ENGINE
# ────────────────────────────────────────────────
def create_thumbnail(title, bg_path, output_path):
    print("Generating Thumbnail...")
    try:
        if not os.path.exists(bg_path):
            generate_backup_image(bg_path)

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
# 5. RENDERER
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    cmd = ["edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

def create_segment(text_line, image_path, audio_path, is_short=True, is_first=False):
    # Audio Validation
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        return None

    voice_clip = AudioFileClip(audio_path)
    
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
    w, h = (1080, 1920) if is_short else (1920, 1080)
    
    # Image Validation & Recovery
    if not os.path.exists(image_path):
        generate_backup_image(image_path)
    
    try:
        img = ImageClip(image_path)
    except:
        # If ImageClip fails to load, regenerate clean backup and retry
        generate_backup_image(image_path)
        img = ImageClip(image_path)

    # Robust Crop Logic (Prevent 'tile cannot extend' error)
    if img.w < w or img.h < h:
        # If image is too small, resize it UP to cover the screen
        img = img.resize(height=h) if img.w/img.h > w/h else img.resize(width=w)
    
    # Standard Crop
    if img.w / img.h > w/h:
        img = img.resize(height=h).crop(x_center=img.w/2, width=w, height=h)
    else:
        img = img.resize(width=w).crop(y_center=img.h/2, width=w, height=h)

    # Animation
    move = random.choice(['zoom_in', 'zoom_out'])
    if move == 'zoom_in':
        anim = img.resize(lambda t: 1 + 0.04 * t)
    else:
        anim = img.resize(lambda t: 1.05 - 0.04 * t)
        
    anim = anim.set_position('center').set_duration(duration)

    font_size = 70 if is_short else 85
    txt = TextClip(
        text_line, fontsize=font_size, color='yellow', font='DejaVu-Sans-Bold', 
        stroke_color='black', stroke_width=4, method='caption', size=(w-100, None)
    ).set_position(('center', 'bottom' if is_short else 'bottom')).set_duration(duration)
    
    txt = txt.set_position(('center', h - 200))

    return CompositeVideoClip([anim, txt], size=(w,h)).set_audio(final_audio).set_duration(duration)

def make_video(content, is_short=True):
    print(f"Rendering {'SHORT' if is_short else 'LONG'} video...")
    clips = []
    suffix = "s" if is_short else "l"
    
    fixed_seed = random.randint(0, 999999)
    # Fallbacks in case JSON is missing keys
    char_desc = content.get('main_char_visual', 'cute cartoon character')
    keyword = content.get('keyword', 'cartoon')
    
    full_lyrics = ""
    first_bg_path = None
    
    for i, scene in enumerate(content['scenes']):
        line = scene['line']
        action = scene['action'] # This is now ENGLISH
        full_lyrics += line + "\n"
        
        aud_path = os.path.join(ASSETS_DIR, f"aud_{suffix}_{i}.mp3")
        get_voice(line, aud_path)
        
        img_path = os.path.join(ASSETS_DIR, f"img_{suffix}_{i}.jpg")
        # Pass the ENGLISH action prompt
        get_image(char_desc, action, img_path, fixed_seed, keyword)
        
        if i == 0: first_bg_path = img_path
        
        try:
            clip = create_segment(line, img_path, aud_path, is_short, (i==0))
            if clip: clips.append(clip)
        except Exception as e:
            print(f"Error line {i}: {e}")

    if not clips: return None, None, None
    
    final = concatenate_videoclips(clips, method="compose")
    out_file = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    
    thumb_path = None
    if not is_short and first_bg_path:
        thumb_path = os.path.join(OUTPUT_DIR, "thumb.png")
        create_thumbnail(content['title'], first_bg_path, thumb_path)

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
    print("===== SKYROCKET ENGINE (Unbreakable V2) =====")
    
    data_s = generate_content("short")
    if data_s:
        v, l, t = make_video(data_s, True)
        if v: upload_video(v, data_s, l, t, True)

    data_l = generate_content("long")
    if data_l:
        v, l, t = make_video(data_l, False)
        if v: upload_video(v, data_l, l, t, False)
