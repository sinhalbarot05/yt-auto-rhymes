import os
import random
import json
import sys
import asyncio
import requests
import textwrap
import time
from pathlib import Path
import pickle

# ────────────────────────────────────────────────
# 1. FIX PILLOW / MOVIEPY COMPATIBILITY
# ────────────────────────────────────────────────
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import (
    AudioFileClip, ImageClip, TextClip, CompositeVideoClip, 
    concatenate_videoclips, vfx
)

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"

# Ensure dirs exist
for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

# ────────────────────────────────────────────────
# 2. AI TEXT GENERATION (Groq)
# ────────────────────────────────────────────────
def groq_request(prompt, model="llama-3.3-70b-versatile"):
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 1000
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

def generate_content():
    prompt = """
    You are a creative Hindi poet for kids. Create a new, original, funny Hindi Nursery Rhyme (8-12 lines).
    The topic should be about animals, nature, or funny situations.
    
    Output ONLY valid JSON format like this:
    {
      "topic": "English description (e.g., A cute cat playing drums)",
      "title": "Hindi Title (e.g., बिल्ली रानी)",
      "rhyme_lines": ["Line 1", "Line 2", "Line 3", "Line 4"],
      "image_prompt": "cute cartoon cat playing drums, vibrant colors, 3d render style, pixar style, bright lighting, high detail"
    }
    """
    raw = groq_request(prompt)
    if not raw:
        sys.exit(1)
        
    try:
        start = raw.find('{')
        end = raw.rfind('}') + 1
        data = json.loads(raw[start:end])
        return data
    except Exception as e:
        print(f"JSON Error: {e}")
        sys.exit(1)

# ────────────────────────────────────────────────
# 3. AI IMAGE GENERATION (With RETRY & Fallback)
# ────────────────────────────────────────────────
def get_ai_image(prompt, filename):
    # Try 3 different seeds/attempts
    for attempt in range(1, 4):
        print(f"Generating Image (Attempt {attempt}/3)...")
        
        # Clean prompt
        clean_prompt = prompt.replace(",", "").replace(".", "").replace(" ", "%20")
        seed = random.randint(0, 999999)
        
        # URL with Flux model (better quality) if available, otherwise default
        url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1080&height=1920&nologo=true&seed={seed}&model=flux"
        
        try:
            resp = requests.get(url, timeout=45)
            if resp.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(resp.content)
                # Check if file is valid image
                try:
                    img = PIL.Image.open(filename)
                    img.verify()
                    print("Image SUCCESS!")
                    return True
                except:
                    print("Invalid image data received.")
            else:
                print(f"Server Error: {resp.status_code}")
                
        except Exception as e:
            print(f"Connection Error: {e}")
        
        # Wait before retry
        time.sleep(3)

    print("All image attempts failed.")
    return False

# ────────────────────────────────────────────────
# 4. AUDIO GENERATION
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    voice = "hi-IN-SwaraNeural" 
    cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

# ────────────────────────────────────────────────
# 5. VIDEO ANIMATION (Random Movements)
# ────────────────────────────────────────────────
def create_video_segment(text_line, image_path, audio_path):
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration + 0.5
    
    # Load Image
    img_clip = ImageClip(image_path).set_duration(duration)
    
    # Resize to be TALLER than 1920 so we can pan vertically, 
    # or WIDER than 1080 so we can pan horizontally.
    # Let's make it slightly larger than screen to allow movement.
    img_clip = img_clip.resize(height=2200) 
    
    # Crop to initial box
    w, h = img_clip.size
    
    # Random Animation Style
    move_type = random.choice(['zoom_in', 'zoom_out', 'pan_left', 'pan_right'])
    
    if move_type == 'zoom_in':
        # Simple center crop then resize up
        clip = img_clip.crop(width=1080, height=1920, x_center=w/2, y_center=h/2)
        anim = clip.resize(lambda t: 1 + 0.04 * t)
        
    elif move_type == 'zoom_out':
        # Start zoomed in (1.1) and go to 1.0
        clip = img_clip.crop(width=1080, height=1920, x_center=w/2, y_center=h/2)
        anim = clip.resize(lambda t: 1.1 - 0.04 * t)
        
    elif move_type == 'pan_right':
        # Move x from left to right
        anim = img_clip.crop(width=1080, height=1920, y_center=h/2, x1=0)
        # Scroll fx is hard in moviepy 1.0 without custom func, fallback to zoom
        anim = img_clip.crop(width=1080, height=1920, x_center=w/2, y_center=h/2).resize(lambda t: 1 + 0.03 * t)

    else:
        # Default Zoom
        anim = img_clip.crop(width=1080, height=1920, x_center=w/2, y_center=h/2).resize(lambda t: 1 + 0.04 * t)

    # Text Styling
    txt_clip = TextClip(
        text_line, 
        fontsize=75, 
        color='white', 
        font='DejaVu-Sans-Bold',
        stroke_color='black', 
        stroke_width=4,
        method='caption',
        size=(950, None)
    ).set_position(('center', 1450)).set_duration(duration)

    final = CompositeVideoClip([anim, txt_clip]).set_duration(duration)
    final.audio = audio_clip
    return final

def make_master_video(content):
    clips = []
    
    # 1. Download MAIN Background
    bg_image_path = os.path.join(ASSETS_DIR, "bg_main.jpg")
    
    if not get_ai_image(content['image_prompt'], bg_image_path):
        print("CRITICAL: AI Image failed 3 times. Using generic nature background.")
        # Fallback to a reliable high-quality nature image, NOT random picsum
        os.system(f"curl -L -o {bg_image_path} https://images.unsplash.com/photo-1502082553048-f009c37129b9?q=80&w=1080")

    print("Rendering clips...")
    full_lyrics = ""
    
    for i, line in enumerate(content['rhyme_lines']):
        if not line.strip(): continue
        full_lyrics += line + "\n"
        
        aud_path = os.path.join(ASSETS_DIR, f"line_{i}.mp3")
        get_voice(line, aud_path)
        
        # We reuse the same BG for visual consistency, but the 'create_video_segment'
        # will apply a RANDOM move effect to it each time.
        segment = create_video_segment(line, bg_image_path, aud_path)
        clips.append(segment)

    final_video = concatenate_videoclips(clips, method="compose")
    output_path = os.path.join(OUTPUT_DIR, "final_upload.mp4")
    final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', threads=4)
    
    return output_path, full_lyrics

# ────────────────────────────────────────────────
# 6. UPLOAD
# ────────────────────────────────────────────────
def upload_to_youtube(video_path, content, full_lyrics):
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
        
        if not creds: return False
            
        service = build('youtube', 'v3', credentials=creds)
        
        title = f"{content['title']} | Funny Hindi Rhymes 2026 🦁"
        if len(title) > 100: title = title[:90] + "..."
        
        desc = f"""{content['title']}
        
{full_lyrics}

#HindiRhymes #NurseryRhymes #KidsSongs #BalGeet #Shorts #Cartoon
"""
        
        body = {
            'snippet': {
                'title': title,
                'description': desc,
                'tags': ['hindi rhymes', 'nursery rhymes', 'kids songs', 'bal geet', 'cartoon', 'shorts'],
                'categoryId': '24'
            },
            'status': {'privacyStatus': 'public'}
        }
        
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)
        
        print(f"Uploading '{title}'...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Progress: {int(status.progress() * 100)}%")
        
        print(f"SUCCESS! Video ID: {response['id']}")
        return True

    except Exception as e:
        print(f"Upload failed: {e}")
        return False

if __name__ == "__main__":
    print("===== Magic Engine V3 (Robust) =====")
    data = generate_content()
    print(f"Title: {data['title']}")
    vid_path, lyrics = make_master_video(data)
    upload_to_youtube(vid_path, data, lyrics)
