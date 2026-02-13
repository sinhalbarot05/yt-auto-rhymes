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
                "max_tokens": 1200
            },
            timeout=30
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def generate_content(mode="short"):
    lines_count = 6 if mode == "short" else 12
    prompt = f"""
    You are a professional Hindi writer for a Kids YouTube Channel.
    Create a funny, rhythmic Hindi Nursery Rhyme ({lines_count} lines).
    
    Output ONLY valid JSON format:
    {{
      "keyword": "ONE_ENGLISH_WORD_FOR_IMAGE (e.g. Train)",
      "title": "Hindi Title (e.g. रेल चली)",
      "rhyme_lines": ["Line 1", "Line 2", ...],
      "image_prompt": "cute cartoon Train scenery, vibrant colors, 3d render style, pixar style"
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
# 3. ASSET ENGINE (Images + Intro Sound)
# ────────────────────────────────────────────────
def download_file(url, filename):
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            if filename.endswith(('.jpg', '.png')):
                PIL.Image.open(filename).verify() 
            return True
    except:
        pass
    return False

def get_best_image(content, filename):
    print("--- Fetching Image ---")
    prompt = content.get('image_prompt', 'cartoon').replace(" ", "%20")
    seed = random.randint(0, 99999)
    
    # 1. AI (Square Turbo)
    url_ai = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    if download_file(url_ai, filename): return True

    # 2. Real Photo Fallback
    keyword = content.get('keyword', 'cartoon').replace(" ", "")
    url_real = f"https://loremflickr.com/1080/1920/{keyword}"
    if download_file(url_real, filename): return True

    # 3. Generic Fallback
    download_file("https://images.unsplash.com/photo-1502082553048-f009c37129b9?q=80&w=1080", filename)
    return True

def get_intro_sound(filename):
    # Downloads a royalty-free "Kids Cheering" sound effect
    if not os.path.exists(filename):
        print("Downloading Intro Sound...")
        # Direct link to a generic happy sound
        url = "https://cdn.pixabay.com/download/audio/2021/08/04/audio_12b218829d.mp3"
        download_file(url, filename)

# ────────────────────────────────────────────────
# 4. THUMBNAIL ENGINE (New Feature!)
# ────────────────────────────────────────────────
def create_thumbnail(content, bg_path, output_path):
    print("Generating Professional Thumbnail...")
    try:
        # Load BG
        img = PIL.Image.open(bg_path).convert("RGBA")
        img = img.resize((1280, 720)) # Youtube standard
        
        # Add Dark Overlay for text pop
        overlay = PIL.Image.new("RGBA", img.size, (0,0,0,80))
        img = PIL.Image.alpha_composite(img, overlay)
        
        draw = PIL.ImageDraw.Draw(img)
        
        # Load Hindi Font (Installed via apt-get)
        try:
            font = PIL.ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", 100)
        except:
            font = PIL.ImageFont.load_default()

        # Text Logic
        text = content['title']
        # Calculate text size (rudimentary)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        x = (1280 - text_w) // 2
        y = (720 - text_h) // 2

        # Draw Shadow (Black)
        draw.text((x+5, y+5), text, font=font, fill="black")
        # Draw Main Text (Yellow)
        draw.text((x, y), text, font=font, fill="#FFD700") # Gold color
        
        # Convert back to RGB and Save
        img = img.convert("RGB")
        img.save(output_path)
        return output_path
    except Exception as e:
        print(f"Thumbnail failed: {e}")
        return None

# ────────────────────────────────────────────────
# 5. AUDIO & VIDEO RENDERER
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    cmd = ["edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

def create_segment(text_line, image_path, audio_path, is_short=True, is_first_clip=False):
    # 1. Audio Setup
    voice_clip = AudioFileClip(audio_path)
    
    # INTRO HOOK: Mix intro sound if it's the first clip
    if is_first_clip:
        intro_path = os.path.join(ASSETS_DIR, "intro.mp3")
        get_intro_sound(intro_path)
        if os.path.exists(intro_path):
            intro_clip = AudioFileClip(intro_path).volumex(0.4) # Lower volume
            # Ensure intro isn't longer than voice
            if intro_clip.duration > voice_clip.duration:
                intro_clip = intro_clip.subclip(0, voice_clip.duration)
            final_audio = CompositeAudioClip([voice_clip, intro_clip])
        else:
            final_audio = voice_clip
    else:
        final_audio = voice_clip

    duration = final_audio.duration
    
    # 2. Resolution Setup
    w, h = (1080, 1920) if is_short else (1920, 1080)
    
    # 3. Image Setup (Smart Crop)
    img = ImageClip(image_path)
    img_ratio = img.w / img.h
    target_ratio = w / h
    
    if img_ratio > target_ratio:
        img = img.resize(height=h)
        img = img.crop(x_center=img.w/2, width=w, height=h)
    else:
        img = img.resize(width=w)
        img = img.crop(y_center=img.h/2, width=w, height=h)

    # 4. Animation
    zoom_func = (lambda t: 1 + 0.04 * t) if is_short else (lambda t: 1.05 - 0.04 * t)
    anim = img.resize(zoom_func).set_position('center').set_duration(duration)

    # 5. Text (Karaoke Style)
    font_size = 75 if is_short else 90
    txt = TextClip(
        text_line, 
        fontsize=font_size, 
        color='yellow', 
        font='DejaVu-Sans-Bold', 
        stroke_color='black', 
        stroke_width=4, 
        method='caption', 
        size=(w - 100, None)
    ).set_position(('center', 'bottom' if is_short else 'bottom')).set_duration(duration)
    
    txt = txt.set_position(('center', h - 250))

    return CompositeVideoClip([anim, txt], size=(w,h)).set_audio(final_audio).set_duration(duration)

def make_video(content, is_short=True):
    print(f"rendering {'SHORT' if is_short else 'LONG'} video...")
    clips = []
    
    suffix = "s" if is_short else "l"
    bg_path = os.path.join(ASSETS_DIR, f"bg_{suffix}.jpg")
    get_best_image(content, bg_path)
    
    full_lyrics = ""
    
    for i, line in enumerate(content['rhyme_lines']):
        if not line.strip(): continue
        full_lyrics += line + "\n"
        
        aud_path = os.path.join(ASSETS_DIR, f"voice_{suffix}_{i}.mp3")
        get_voice(line, aud_path)
        
        try:
            if os.path.exists(aud_path):
                # Pass True if it's the very first line (for Intro Sound)
                is_first = (i == 0)
                clip = create_segment(line, bg_path, aud_path, is_short, is_first)
                clips.append(clip)
        except Exception as e:
            print(f"Skipped line {i}: {e}")

    if not clips: return None, None
    
    final = concatenate_videoclips(clips, method="compose")
    out_file = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    
    # Create Thumbnail if it's a Long video
    thumb_path = None
    if not is_short:
        thumb_path = os.path.join(OUTPUT_DIR, "thumbnail.png")
        create_thumbnail(content, bg_path, thumb_path)

    final.write_videofile(out_file, fps=24, codec='libx264', audio_codec='aac', threads=4)
    return out_file, full_lyrics, thumb_path

# ────────────────────────────────────────────────
# 6. UPLOAD ENGINE
# ────────────────────────────────────────────────
def upload_video(video_path, content, lyrics, thumb_path=None, is_short=True):
    try:
        if not os.path.exists(TOKEN_FILE): return False
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        
        service = build('youtube', 'v3', credentials=creds)
        
        if is_short:
            title = f"{content['title']} 🦁 #Shorts #HindiRhymes"
            tags = ['shorts', 'hindi rhymes', 'nursery rhymes', 'kids']
        else:
            title = f"{content['title']} | New Hindi Rhymes 2026 🦁"
            tags = ['hindi rhymes', 'nursery rhymes', 'kids songs', 'bal geet', 'cartoon']

        desc = f"""{content['title']}
        
{lyrics}

🦁 SUBSCRIBE for more Rhymes!
✨ New videos at 7AM, 2PM, and 8PM!

#HindiRhymes #NurseryRhymes #KidsSongs #BalGeet
"""
        
        body = {
            'snippet': {'title': title[:99], 'description': desc, 'tags': tags, 'categoryId': '24'},
            'status': {'privacyStatus': 'public'}
        }
        
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)
        
        print(f"Uploading '{title}'...")
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status: print(f"Progress: {int(status.progress()*100)}%")
            
        vid_id = resp['id']
        print(f"SUCCESS! ID: {vid_id}")

        # Upload Thumbnail (Only for Long Videos)
        if thumb_path and os.path.exists(thumb_path):
            print("Uploading Thumbnail...")
            service.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(thumb_path)).execute()

        return True
    except Exception as e:
        print(f"Upload Error: {e}")
        return False

if __name__ == "__main__":
    print("===== SKYROCKET BROADCASTER INITIATED =====")
    
    # 1. Short Video
    print("\n>>> PRODUCING SHORT <<<")
    data_s = generate_content(mode="short")
    if data_s:
        vid_s, lyrics_s, _ = make_video(data_s, is_short=True)
        if vid_s: upload_video(vid_s, data_s, lyrics_s, None, is_short=True)

    # 2. Long Video
    print("\n>>> PRODUCING LONG <<<")
    data_l = generate_content(mode="long")
    if data_l:
        vid_l, lyrics_l, thumb_l = make_video(data_l, is_short=False)
        if vid_l: upload_video(vid_l, data_l, lyrics_l, thumb_l, is_short=False)
        
    print("\n===== BROADCAST COMPLETE =====")
