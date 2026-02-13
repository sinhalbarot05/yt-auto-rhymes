import os
import random
import json
import sys
import asyncio
import requests
import textwrap
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
    # We ask for JSON to make parsing 100% reliable
    prompt = """
    You are a creative Hindi poet for kids. Create a new, original, funny Hindi Nursery Rhyme (8-12 lines).
    
    Output ONLY valid JSON format like this, do not add any other text:
    {
      "topic": "English description of topic (e.g., A cute cat playing drums)",
      "title": "Hindi Title (e.g., बिल्ली रानी)",
      "rhyme_lines": ["Line 1", "Line 2", "Line 3", "Line 4"],
      "image_prompt": "cute cartoon cat playing drums, vibrant colors, 3d render style, pixar style"
    }
    """
    raw = groq_request(prompt)
    if not raw:
        print("Failed to gen content")
        sys.exit(1)
        
    try:
        # Find the JSON object inside the response
        start = raw.find('{')
        end = raw.rfind('}') + 1
        data = json.loads(raw[start:end])
        return data
    except Exception as e:
        print(f"JSON Parse Error: {e}\nRaw: {raw}")
        sys.exit(1)

# ────────────────────────────────────────────────
# 3. AI IMAGE GENERATION (Pollinations - Fixed)
# ────────────────────────────────────────────────
def get_ai_image(prompt, filename):
    print(f"Generating Image for: {prompt}")
    
    # 1. Clean prompt to prevent URL errors
    clean_prompt = prompt.replace(",", "").replace(".", "").replace(" ", "%20")
    
    # 2. Add style keywords for better quality
    style = "children%20book%20illustration%20style%20vibrant%20colors%20high%20quality"
    final_url = f"https://image.pollinations.ai/prompt/{clean_prompt}%20{style}?width=1080&height=1920&nologo=true&seed={random.randint(0,99999)}"
    
    try:
        resp = requests.get(final_url, timeout=40)
        resp.raise_for_status()
        with open(filename, 'wb') as f:
            f.write(resp.content)
        print("Image downloaded successfully.")
        return True
    except Exception as e:
        print(f"Image Gen Failed: {e}")
        return False

# ────────────────────────────────────────────────
# 4. AI AUDIO (Edge-TTS - Neural Voice)
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    # 'hi-IN-SwaraNeural' is the best free female Hindi voice
    voice = "hi-IN-SwaraNeural" 
    cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

# ────────────────────────────────────────────────
# 5. VIDEO EDITOR (Motion + Text)
# ────────────────────────────────────────────────
def create_video_segment(text_line, image_path, audio_path):
    # Load Audio
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration + 0.5  # Add 0.5s pause
    
    # Load Image
    img_clip = ImageClip(image_path).set_duration(duration)
    
    # Resize to vertical video (1080x1920) if not already
    img_clip = img_clip.resize(height=1920)
    img_clip = img_clip.crop(x1=0, y1=0, width=1080, height=1920, x_center=img_clip.w/2, y_center=img_clip.h/2)
    
    # Apply "Ken Burns" Zoom Effect (Zoom in 5%)
    moving_bg = img_clip.resize(lambda t: 1 + 0.05 * t) 
    
    # Create Text Overlay
    # Note: stroke_width adds a black outline so text is readable on any background
    txt_clip = TextClip(
        text_line, 
        fontsize=70, 
        color='white', 
        font='DejaVu-Sans-Bold',
        stroke_color='black', 
        stroke_width=3,
        method='caption',
        size=(900, None) # Wrap text at 900px width
    ).set_position(('center', 1400)).set_duration(duration) # Position near bottom

    # Combine
    final_clip = CompositeVideoClip([moving_bg, txt_clip]).set_duration(duration)
    final_clip.audio = audio_clip
    return final_clip

def make_master_video(content):
    clips = []
    
    # Download Background Image
    bg_image_path = os.path.join(ASSETS_DIR, "bg_main.jpg")
    
    # Try AI image, fallback to random picsum if it fails
    if not get_ai_image(content['image_prompt'], bg_image_path):
        print("Using Fallback Image")
        os.system(f"curl -L -o {bg_image_path} https://picsum.photos/1080/1920")

    print("Generating video segments...")
    full_lyrics = ""
    
    for i, line in enumerate(content['rhyme_lines']):
        if not line.strip(): continue
        
        full_lyrics += line + "\n"
        
        # Generate Audio for this line
        aud_path = os.path.join(ASSETS_DIR, f"line_{i}.mp3")
        get_voice(line, aud_path)
        
        # Create Video Segment
        try:
            segment = create_video_segment(line, bg_image_path, aud_path)
            clips.append(segment)
        except Exception as e:
            print(f"Error creating segment {i}: {e}")
            continue

    if not clips:
        print("No clips created!")
        sys.exit(1)

    # Combine all segments
    final_video = concatenate_videoclips(clips, method="compose")
    
    output_path = os.path.join(OUTPUT_DIR, "final_upload.mp4")
    # Write file (threads=4 speeds up rendering on GitHub Actions)
    final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', threads=4)
    
    return output_path, full_lyrics

# ────────────────────────────────────────────────
# 6. UPLOAD TO YOUTUBE
# ────────────────────────────────────────────────
def upload_to_youtube(video_path, content, full_lyrics):
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
        
        if not creds:
            print("No valid token found.")
            return False
            
        service = build('youtube', 'v3', credentials=creds)
        
        # Create Title
        title = f"{content['title']} | Hindi Rhymes 2026 🦁"
        if len(title) > 100: title = title[:90] + "..."
        
        # Create Description
        desc = f"""{content['title']}
        
{full_lyrics}

#HindiRhymes #NurseryRhymes #KidsSongs #BalGeet #Shorts
"""
        
        body = {
            'snippet': {
                'title': title,
                'description': desc,
                'tags': ['hindi rhymes', 'nursery rhymes', 'kids songs', 'bal geet', 'cartoon'],
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

# ────────────────────────────────────────────────
# MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== Hindi Kids Nursery Rhymes V2 =====")
    
    # 1. Generate Rhyme & Prompts
    data = generate_content()
    print(f"Topic: {data['topic']}")
    print(f"Title: {data['title']}")
    
    # 2. Render Video
    vid_path, lyrics = make_master_video(data)
    
    # 3. Upload
    upload_to_youtube(vid_path, data, lyrics)
