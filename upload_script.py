import os
import random
import json
import sys
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import pickle
import requests

# Video Engine
from moviepy.editor import (
    AudioFileClip, ImageClip, TextClip, CompositeVideoClip, 
    ColorClip, concatenate_videoclips
)
from moviepy.video.fx.all import resize

# Google/YouTube
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"

# Ensure dirs exist
for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

# ────────────────────────────────────────────────
# 1. AI TEXT GENERATION (Groq)
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
    # Prompt for a structured JSON response to handle Title, Rhyme, and Image Prompts together
    prompt = """
    Create a new, original Hindi Nursery Rhyme for kids.
    Output ONLY valid JSON format like this:
    {
      "topic": "English description of topic (e.g., A cute cat playing drums)",
      "title": "Hindi Title (e.g., बिल्ली रानी)",
      "rhyme_lines": ["Line 1", "Line 2", "Line 3", "Line 4", "Line 5", "Line 6", "Line 7", "Line 8"],
      "image_prompt": "A cute cartoon cat playing drums, vibrant colors, 3d render style, pixar style, bright lighting"
    }
    """
    raw = groq_request(prompt)
    if not raw:
        print("Failed to gen content")
        sys.exit(1)
        
    try:
        # Extract JSON if the model added extra text
        start = raw.find('{')
        end = raw.rfind('}') + 1
        data = json.loads(raw[start:end])
        return data
    except Exception as e:
        print(f"JSON Parse Error: {e}")
        sys.exit(1)

# ────────────────────────────────────────────────
# 2. AI IMAGE GENERATION (Pollinations - Free)
# ────────────────────────────────────────────────
def get_ai_image(prompt, filename):
    # Enhancing prompt for better quality
    enhanced_prompt = f"{prompt}, masterpiece, best quality, 8k, cute kids animation style, vibrant colors, soft lighting, vector art"
    encoded = requests.utils.quote(enhanced_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&seed={random.randint(0,999999)}"
    
    print(f"Downloading AI Image: {prompt}...")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(filename, 'wb') as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"Image Gen Failed: {e}")
        return False

# ────────────────────────────────────────────────
# 3. AI AUDIO (Edge-TTS - Neural Voice)
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    # Using a cute female Hindi voice
    voice = "hi-IN-SwaraNeural" 
    cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

# ────────────────────────────────────────────────
# 4. VIDEO EDITOR (MoviePy - Ken Burns Style)
# ────────────────────────────────────────────────
def create_video_segment(text_line, image_path, audio_path):
    # 1. Load Audio
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration + 0.5 # Small buffer
    
    # 2. Create Background with Zoom Effect (Ken Burns)
    # Load image
    img_clip = ImageClip(image_path).set_duration(duration).resize(height=1080)
    img_clip = img_clip.crop(x1=0, y1=0, width=1080, height=1920, x_center=img_clip.w/2, y_center=img_clip.h/2)
    
    # Apply Zoom: Resize from 1.0 to 1.1 over duration
    # Note: MoviePy v1.0.3 resize syntax
    moving_bg = img_clip.resize(lambda t: 1 + 0.04 * t) 
    
    # 3. Create Text Overlay (Stroke for visibility)
    # Note: Using standard font. Ensure ImageMagick is set up in YAML.
    txt_clip = TextClip(
        text_line, 
        fontsize=70, 
        color='yellow', 
        font='DejaVu-Sans-Bold', # Standard Linux font
        stroke_color='black', 
        stroke_width=3,
        method='caption',
        size=(900, None) # Wrap text
    ).set_position(('center', 'bottom')).set_duration(duration).set_start(0)

    # 4. Compose
    final_clip = CompositeVideoClip([moving_bg, txt_clip]).set_duration(duration)
    final_clip.audio = audio_clip
    return final_clip

def make_master_video(content):
    clips = []
    
    # Download ONE main background image for visual consistency
    bg_image_path = os.path.join(ASSETS_DIR, "bg_main.jpg")
    if not get_ai_image(content['image_prompt'], bg_image_path):
        print("Using fallback image")
        # Download a generic fallback if AI fails
        os.system(f"curl -L -o {bg_image_path} https://picsum.photos/1280/720")

    print("Generating clips for each line...")
    
    full_text_for_desc = ""
    
    for i, line in enumerate(content['rhyme_lines']):
        if not line.strip(): continue
        
        full_text_for_desc += line + "\n"
        
        # Audio for this line
        aud_path = os.path.join(ASSETS_DIR, f"line_{i}.mp3")
        get_voice(line, aud_path)
        
        # Create segment
        # We reuse the same BG image but you could generate 
        # a new one for each line if you wanted to be fancy.
        # For consistency, we stick to one nice scene.
        segment = create_video_segment(line, bg_image_path, aud_path)
        clips.append(segment)

    # Intro/Outro (Optional - kept simple)
    final_video = concatenate_videoclips(clips, method="compose")
    
    output_path = os.path.join(OUTPUT_DIR, "final_upload.mp4")
    final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')
    
    return output_path, full_text_for_desc

# ────────────────────────────────────────────────
# 5. UPLOAD LOGIC
# ────────────────────────────────────────────────
def upload_to_youtube(video_path, content, full_lyrics):
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
        
        # Refresh logic omitted for brevity, assuming standard setup
        
        service = build('youtube', 'v3', credentials=creds)
        
        title = f"{content['title']} | Hindi Nursery Rhymes 2026 🐱"
        if len(title) > 100: title = title[:90] + "..."
        
        desc = f"""{content['title']} - A fun Hindi rhyme for kids!
        
{full_lyrics}

#HindiRhymes #NurseryRhymes #KidsSongs #BalGeet
"""
        
        body = {
            'snippet': {
                'title': title,
                'description': desc,
                'tags': ['hindi rhymes', 'nursery rhymes', 'kids songs', 'bal geet', 'cartoon'],
                'categoryId': '24' # Entertainment
            },
            'status': {'privacyStatus': 'public'}
        }
        
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        
        print(f"Upload Complete! Video ID: {response['id']}")
        return True

    except Exception as e:
        print(f"Upload failed: {e}")
        return False

# ────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting Magic V2 Engine...")
    
    # 1. Get Content
    data = generate_content()
    print(f"Topic: {data['topic']}")
    
    # 2. Create Video
    vid_path, lyrics = make_master_video(data)
    
    # 3. Upload
    upload_to_youtube(vid_path, data, lyrics)
