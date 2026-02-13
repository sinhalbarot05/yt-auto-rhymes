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
# 1. COMPATIBILITY FIXES
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

for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

# ────────────────────────────────────────────────
# 2. CONTENT GENERATION
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
    # We ask for a "Sing-Along" style rhyme
    prompt = """
    Create a catchy, rhythmic Hindi Nursery Rhyme for kids (8 lines).
    
    Output ONLY valid JSON:
    {
      "keyword": "ONE_ENGLISH_WORD (e.g. Monkey)",
      "title": "Hindi Title",
      "rhyme_lines": ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5", "Line 6", "Line 7", "Line 8"],
      "image_prompt": "cute cartoon Monkey dancing, vibrant colors, 3d render style, bright lighting"
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
# 3. IMAGE ENGINE (Robust)
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
    
    # 1. Try AI (Square Image - Most Stable)
    prompt = content['image_prompt'].replace(" ", "%20")
    seed = random.randint(0, 99999)
    # Using 'turbo' model for speed and stability
    ai_url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true&seed={seed}&model=turbo"
    
    print("Attempt 1: AI Generation...")
    if download_file(ai_url, filename):
        try:
            img = PIL.Image.open(filename)
            img.verify()
            print(">>> Success: AI Image!")
            return True
        except:
            print("AI Image invalid.")

    # 2. Fallback: Real Photo
    keyword = content.get('keyword', 'cartoon').replace(" ", "")
    print(f"Attempt 2: Real Photo of '{keyword}'...")
    real_url = f"https://loremflickr.com/1080/1920/{keyword}"
    
    if download_file(real_url, filename):
        print(">>> Success: Real Photo.")
        return True

    # 3. Ultimate Fallback
    print("Attempt 3: Generic Fallback.")
    download_file("https://loremflickr.com/1080/1920/cartoon", filename)
    return True

# ────────────────────────────────────────────────
# 4. AUDIO ENGINE
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    # Using a high pitch "Kid" like voice usually requires adjusting pitch, 
    # but SwaraNeural is the best standard Hindi voice we have for free.
    voice = "hi-IN-SwaraNeural" 
    cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

# ────────────────────────────────────────────────
# 5. VIDEO ENGINE (No-Crash Animation)
# ────────────────────────────────────────────────
def create_video_segment(text_line, image_path, audio_path):
    # 1. Audio
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration + 0.5
    
    # 2. Image Setup
    # Load and Resize to cover screen
    img_clip = ImageClip(image_path)
    
    # Smart resize: Make sure it covers 1080x1920
    # We make it slightly bigger (1300 width) to allow sliding
    img_clip = img_clip.resize(height=1920)
    if img_clip.w < 1080:
        img_clip = img_clip.resize(width=1080)
        img_clip = img_clip.crop(x1=0, width=1080, height=1920, y_center=img_clip.h/2)
    else:
        img_clip = img_clip.crop(x_center=img_clip.w/2, width=1080, height=1920, y_center=img_clip.h/2)

    # 3. Safe Animation (Simple Zoom)
    # We removed the 'Pan' logic that was crashing
    anim = img_clip.resize(lambda t: 1 + 0.04 * t).set_duration(duration).set_position('center')

    # 4. "Sing-Along" Style Text
    # Big White Text with Thick Black Outline (Stroke)
    txt_clip = TextClip(
        text_line, 
        fontsize=80, 
        color='white', 
        font='DejaVu-Sans-Bold',
        stroke_color='black', 
        stroke_width=5, 
        method='caption',
        size=(950, None)
    ).set_position(('center', 1400)).set_duration(duration)

    # 5. Compose
    final = CompositeVideoClip([anim, txt_clip], size=(1080,1920)).set_duration(duration)
    final.audio = audio_clip
    return final

def make_master_video(content):
    clips = []
    
    bg_image_path = os.path.join(ASSETS_DIR, "bg_main.jpg")
    get_best_image(content, bg_image_path)
    
    print("Rendering...")
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
            print(f"Skipping line: {e}")

    if not clips: sys.exit(1)

    final_video = concatenate_videoclips(clips, method="compose")
    output_path = os.path.join(OUTPUT_DIR, "final_upload.mp4")
    
    # Threads=4 speeds up rendering significantly on GitHub Actions
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
        
        title = f"{content['title']} | Hindi Rhymes 2026 🦁"
        if len(title) > 90: title = title[:90] + "..."
        
        desc = f"""{content['title']} - Fun Hindi Rhyme for Kids!
        
{full_lyrics}

#HindiRhymes #NurseryRhymes #KidsSongs #BalGeet #Shorts
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
                print(f"Upload: {int(status.progress() * 100)}%")
        
        print(f"SUCCESS! Video ID: {response['id']}")
        return True

    except Exception as e:
        print(f"Upload failed: {e}")
        return False

if __name__ == "__main__":
    print("===== Magic Engine V5 (Stable) =====")
    data = generate_content()
    print(f"Topic: {data['title']}")
    vid_path, lyrics = make_master_video(data)
    upload_to_youtube(vid_path, data, lyrics)
