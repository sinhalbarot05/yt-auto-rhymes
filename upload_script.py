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
# 1. FIX PILLOW / MOVIEPY COMPATIBILITY
# ────────────────────────────────────────────────
import PIL.Image
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
    
    Output ONLY valid JSON format like this:
    {
      "keyword": "ONE_ENGLISH_WORD (e.g., Monkey)",
      "topic": "English description",
      "title": "Hindi Title (e.g., बंदर मामा)",
      "rhyme_lines": ["Line 1", "Line 2", "Line 3", "Line 4"],
      "image_prompt": "cute cartoon Monkey face close up, vibrant colors, 3d render style, bright lighting"
    }
    """
    raw = groq_request(prompt)
    if not raw: sys.exit(1)
        
    try:
        start = raw.find('{')
        end = raw.rfind('}') + 1
        data = json.loads(raw[start:end])
        return data
    except Exception as e:
        print(f"JSON Error: {e}")
        sys.exit(1)

# ────────────────────────────────────────────────
# 3. ROBUST IMAGE ENGINE
# ────────────────────────────────────────────────
def download_file(url, filename):
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            return True
    except:
        pass
    return False

def get_best_image(content, filename):
    print("--- Image Engine Started ---")
    
    # STRATEGY 1: Pollinations AI (SQUARE + TURBO MODEL)
    # Using Square (1024x1024) and Turbo is much more stable than Portrait/Flux
    prompt = content['image_prompt'].replace(" ", "%20")
    seed = random.randint(0, 99999)
    
    # Try Turbo Model
    ai_url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    print(f"Attempt 1: AI Generation ({content['image_prompt']})...")
    
    if download_file(ai_url, filename):
        # Verify it's not a text file (error message)
        try:
            img = PIL.Image.open(filename)
            img.verify()
            print(">>> Success: AI Image Generated!")
            return True
        except:
            print("AI generated broken file.")

    # STRATEGY 2: Smart Fallback (Real Photo via Flickr)
    # If AI fails, we get a real photo of the "Keyword" (e.g., Monkey)
    keyword = content.get('keyword', 'cartoon').replace(" ", "")
    print(f"Attempt 2: Fetching Real Photo of '{keyword}'...")
    
    real_url = f"https://loremflickr.com/1080/1920/{keyword}"
    if download_file(real_url, filename):
        print(">>> Success: Used Real Photo Fallback.")
        return True

    # STRATEGY 3: Last Resort (Generic Cartoon)
    print("Attempt 3: Ultimate Fallback.")
    fallback_url = "https://loremflickr.com/1080/1920/cartoon"
    download_file(fallback_url, filename)
    return True

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
# 5. VIDEO ANIMATION (With Center Crop for Square Images)
# ────────────────────────────────────────────────
def create_video_segment(text_line, image_path, audio_path):
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration + 0.5
    
    # 1. Load Image
    img_clip = ImageClip(image_path)
    
    # 2. INTELLIGENT CROP/RESIZE
    # Since we might get a Square AI image (1024x1024) or a Tall Real image (1080x1920)
    # We must ensure it fills the 1080x1920 Vertical Video frame
    
    target_ratio = 1080 / 1920
    img_ratio = img_clip.w / img_clip.h
    
    if img_ratio > target_ratio:
        # Image is wider (like a Square), crop the sides
        new_h = 1920
        new_w = int(new_h * img_ratio)
        img_clip = img_clip.resize(height=new_h)
        # Center Crop
        img_clip = img_clip.crop(x1=(new_w/2 - 540), width=1080, height=1920)
    else:
        # Image is tall/thin, resize width to fit
        new_w = 1080
        img_clip = img_clip.resize(width=new_w)
        # Center Crop vertically if needed
        img_clip = img_clip.crop(y1=0, width=1080, height=1920)

    # 3. Dynamic Animation (Zoom/Pan Mix)
    move_type = random.choice(['zoom_in', 'zoom_out', 'pan'])
    
    if move_type == 'zoom_in':
        anim = img_clip.resize(lambda t: 1 + 0.04 * t)
    elif move_type == 'zoom_out':
        anim = img_clip.resize(lambda t: 1.1 - 0.04 * t) # Start slightly zipped
    else: # Pan (Simulated via crop movement on a slightly larger resize)
        # Resize up 10%
        pan_clip = img_clip.resize(1.1)
        # Slide window
        anim = pan_clip.crop(
            x1=lambda t: 50 + (10 * t), 
            y1=lambda t: 50, 
            width=1080, height=1920
        )
        
    # 4. Text Overlay
    txt_clip = TextClip(
        text_line, 
        fontsize=75, 
        color='yellow', 
        font='DejaVu-Sans-Bold',
        stroke_color='black', 
        stroke_width=4,
        method='caption',
        size=(950, None)
    ).set_position(('center', 1450)).set_duration(duration)

    final = CompositeVideoClip([anim.set_duration(duration), txt_clip]).set_duration(duration)
    final.audio = audio_clip
    return final

def make_master_video(content):
    clips = []
    
    # Download the best available image
    bg_image_path = os.path.join(ASSETS_DIR, "bg_main.jpg")
    get_best_image(content, bg_image_path)
    
    print("Rendering video clips...")
    full_lyrics = ""
    
    for i, line in enumerate(content['rhyme_lines']):
        if not line.strip(): continue
        full_lyrics += line + "\n"
        
        aud_path = os.path.join(ASSETS_DIR, f"line_{i}.mp3")
        get_voice(line, aud_path)
        
        try:
            segment = create_video_segment(line, bg_image_path, aud_path)
            clips.append(segment)
        except Exception as e:
            print(f"Skipping line due to error: {e}")

    if not clips: sys.exit(1)

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
        
        title = f"{content['title']} | Hindi Rhymes 2026"
        if len(title) > 90: title = title[:90] + "..."
        
        desc = f"""{content['title']} - {content.get('topic', 'Kids Song')}
        
{full_lyrics}

#HindiRhymes #NurseryRhymes #KidsSongs #BalGeet #Shorts
"""
        body = {
            'snippet': {
                'title': title,
                'description': desc,
                'tags': ['hindi rhymes', 'nursery rhymes', 'kids songs', 'shorts'],
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
                print(f"Upload Progress: {int(status.progress() * 100)}%")
        
        print(f"SUCCESS! Video ID: {response['id']}")
        return True

    except Exception as e:
        print(f"Upload failed: {e}")
        return False

if __name__ == "__main__":
    print("===== Magic Engine V4 (Robust Image) =====")
    data = generate_content()
    print(f"Topic: {data['topic']}")
    vid_path, lyrics = make_master_video(data)
    upload_to_youtube(vid_path, data, lyrics)
