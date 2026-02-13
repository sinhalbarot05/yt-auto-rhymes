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
import PIL.Image
# Force old Antialias method to satisfy MoviePy 1.0.3
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import (
    AudioFileClip, ImageClip, TextClip, CompositeVideoClip, 
    concatenate_videoclips
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
# 2. CONTENT GENERATION (Smart)
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
                "max_tokens": 1000
            },
            timeout=30
        )
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def generate_content():
    # Prompt for Hindi Rhymes
    prompt = """
    Create a catchy, simple Hindi Nursery Rhyme for kids (8 lines).
    Output ONLY valid JSON:
    {
      "keyword": "ONE_ENGLISH_WORD_FOR_IMAGE_SEARCH (e.g. Lion)",
      "title": "Hindi Title",
      "rhyme_lines": ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5", "Line 6", "Line 7", "Line 8"],
      "image_prompt": "cute cartoon Lion face close up, vibrant colors, 3d render style, bright lighting"
    }
    """
    raw = groq_request(prompt)
    if not raw: sys.exit(1)
    try:
        start, end = raw.find('{'), raw.rfind('}') + 1
        return json.loads(raw[start:end])
    except:
        return {
            "keyword": "cartoon",
            "title": "मजेदार कविता",
            "rhyme_lines": ["मछली जल की रानी है", "जीवन उसका पानी है", "हाथ लगाओ डर जाएगी", "बाहर निकालो मर जाएगी"],
            "image_prompt": "cute cartoon fish underwater"
        }

# ────────────────────────────────────────────────
# 3. SMART IMAGE ENGINE
# ────────────────────────────────────────────────
def download_file(url, filename):
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            PIL.Image.open(filename).verify() # Verify image
            return True
    except:
        pass
    return False

def get_best_image(content, filename):
    print("--- Finding Best Image ---")
    
    # 1. Try AI (Square Turbo)
    prompt = content.get('image_prompt', 'cartoon').replace(" ", "%20")
    seed = random.randint(0, 99999)
    url_ai = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    
    print(f"Attempt 1: AI Image ({content.get('keyword')})...")
    if download_file(url_ai, filename):
        return True

    # 2. Try Real Photo (Keyword Based)
    keyword = content.get('keyword', 'cartoon').replace(" ", "")
    print(f"Attempt 2: Stock Search for '{keyword}'...")
    url_real = f"https://loremflickr.com/1080/1920/{keyword}"
    
    if download_file(url_real, filename):
        return True

    # 3. Fallback
    print("Attempt 3: Generic Fallback")
    download_file("https://images.unsplash.com/photo-1502082553048-f009c37129b9?q=80&w=1080", filename)
    return True

# ────────────────────────────────────────────────
# 4. AUDIO (Neural Voice)
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    cmd = ["edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

# ────────────────────────────────────────────────
# 5. VIDEO RENDERER (Crash-Proof Logic)
# ────────────────────────────────────────────────
def create_segment(text_line, image_path, audio_path):
    # Load Audio
    audio = AudioFileClip(audio_path)
    # FIX: Duration must match EXACTLY. No adding +0.5s or it crashes.
    duration = audio.duration
    
    # Image Setup
    img = ImageClip(image_path).set_duration(duration)
    
    # Smart Crop to Vertical
    if img.w / img.h > (1080/1920):
        img = img.resize(height=1920)
        img = img.crop(x_center=img.w/2, width=1080, height=1920)
    else:
        img = img.resize(width=1080)
        img = img.crop(y_center=img.h/2, width=1080, height=1920)
        
    # Gentle Animation
    anim = img.resize(lambda t: 1 + 0.04 * t).set_position('center')

    # Karaoke Text (Yellow + Outline)
    txt = TextClip(
        text_line, 
        fontsize=70, 
        color='yellow', 
        font='DejaVu-Sans-Bold', 
        stroke_color='black', 
        stroke_width=4, 
        method='caption', 
        size=(900, None)
    ).set_position(('center', 1450)).set_duration(duration)

    # Compose
    video = CompositeVideoClip([anim, txt], size=(1080,1920))
    video = video.set_audio(audio).set_duration(duration)
    return video

def make_video(content):
    clips = []
    bg_path = os.path.join(ASSETS_DIR, "bg.jpg")
    
    get_best_image(content, bg_path)
    
    full_lyrics = ""
    print("Rendering Clips...")
    
    for i, line in enumerate(content['rhyme_lines']):
        if not line.strip(): continue
        full_lyrics += line + "\n"
        
        aud_path = os.path.join(ASSETS_DIR, f"voice_{i}.mp3")
        get_voice(line, aud_path)
        
        try:
            # Check if audio exists and has size
            if os.path.exists(aud_path) and os.path.getsize(aud_path) > 0:
                clip = create_segment(line, bg_path, aud_path)
                clips.append(clip)
            else:
                print(f"Skipping empty audio for line {i}")
        except Exception as e:
            print(f"Error on line {i}: {e}")

    if not clips: 
        print("No clips created. Exiting.")
        sys.exit(1)
    
    final = concatenate_videoclips(clips, method="compose")
    out_file = os.path.join(OUTPUT_DIR, "final.mp4")
    
    final.write_videofile(out_file, fps=24, codec='libx264', audio_codec='aac', threads=4)
    return out_file, full_lyrics

# ────────────────────────────────────────────────
# 6. UPLOAD
# ────────────────────────────────────────────────
def upload_video(video_path, content, lyrics):
    try:
        if not os.path.exists(TOKEN_FILE): 
            print("Token file not found.")
            return False
            
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        
        service = build('youtube', 'v3', credentials=creds)
        
        title = f"{content['title']} | Hindi Rhymes 2026 🦁"
        desc = f"{content['title']}\n\n{lyrics}\n\n#HindiRhymes #NurseryRhymes #KidsSongs"
        
        body = {
            'snippet': {'title': title[:99], 'description': desc, 'tags': ['hindi rhymes', 'kids songs'], 'categoryId': '24'},
            'status': {'privacyStatus': 'public'}
        }
        
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)
        
        print(f"Uploading '{title}'...")
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status: print(f"Upload: {int(status.progress()*100)}%")
            
        print(f"SUCCESS! ID: {resp['id']}")
        return True
    except Exception as e:
        print(f"Upload Error: {e}")
        return False

if __name__ == "__main__":
    print("===== Magic Engine (Duration Fix) =====")
    data = generate_content()
    print(f"Topic: {data['title']}")
    vid, lyrics = make_video(data)
    upload_video(vid, data, lyrics)
