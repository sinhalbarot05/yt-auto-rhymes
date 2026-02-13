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
# 2. GENERATE CONTENT (With Character Consistency)
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
        "Elephant playing football", "Butterfly in garden", "Moon and stars", 
        "Train journey", "School Bus adventure", "Ice Cream truck", 
        "Cat stealing milk", "Dog guarding house", "Lion the king", 
        "Parrot talking", "Car racing", "Doctor helping", "Police catching thief", 
        "Sun waking up", "Fish in ocean", "Frog jumping", "Peacock dancing",
        "Rabbit and Tortoise", "Cow giving milk", "Traffic Light", "Rainbow"
    ]
    selected_topic = random.choice(topics)
    
    lines_count = 6 if mode == "short" else 10
    
    # We ask AI to define the CHARACTER LOOK separately
    prompt = f"""
    You are a professional Hindi writer for a Kids YouTube Channel.
    Topic: "{selected_topic}"
    
    1. Create a simple Hindi Nursery Rhyme ({lines_count} lines).
    2. Define a consistent visual description for the main character.
    3. For EACH line, write a specific image prompt using that character description.
    
    Output ONLY valid JSON format:
    {{
      "title": "Hindi Title",
      "main_char_visual": "Detailed description (e.g. A cute baby elephant wearing a red cap and blue shorts, 3d pixar style)",
      "scenes": [
        {{ "line": "Hindi Line 1", "action": "Elephant kicking a football in a green field" }},
        {{ "line": "Hindi Line 2", "action": "Elephant running happily after the ball" }},
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
# 3. ASSET ENGINE (Consistent Seeds)
# ────────────────────────────────────────────────
def download_file(url, filename):
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            if filename.endswith(('.jpg', '.png')):
                PIL.Image.open(filename).verify() 
            return True
    except:
        pass
    return False

def get_image(visual_desc, action_desc, filename, fixed_seed):
    print(f"--- Gen Image: {action_desc} ---")
    
    # COMBINE Character Look + Specific Action
    # We use the SAME fixed_seed for every image in the video to keep character consistent
    full_prompt = f"{visual_desc}, {action_desc}, vibrant colors, 3d render, high quality".replace(" ", "%20")
    
    # Turbo model is best for consistency
    url_ai = f"https://image.pollinations.ai/prompt/{full_prompt}?width=1024&height=1024&nologo=true&seed={fixed_seed}&model=turbo"
    
    if download_file(url_ai, filename): return True
    
    # Fallback
    print("AI Failed, using fallback.")
    download_file("https://images.unsplash.com/photo-1602192509153-0360a16d5d23?q=80&w=1080", filename)
    return True

def get_intro_sound(filename):
    if not os.path.exists(filename):
        url = "https://cdn.pixabay.com/download/audio/2021/08/04/audio_12b218829d.mp3"
        download_file(url, filename)

# ────────────────────────────────────────────────
# 4. THUMBNAIL ENGINE
# ────────────────────────────────────────────────
def create_thumbnail(title, bg_path, output_path):
    print("Generating Thumbnail...")
    try:
        img = PIL.Image.open(bg_path).convert("RGBA")
        img = img.resize((1280, 720)) 
        
        overlay = PIL.Image.new("RGBA", img.size, (0,0,0,80))
        img = PIL.Image.alpha_composite(img, overlay)
        draw = PIL.ImageDraw.Draw(img)
        
        try:
            font = PIL.ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", 90)
        except:
            font = PIL.ImageFont.load_default()

        # Center Text
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
    except:
        return None

# ────────────────────────────────────────────────
# 5. RENDERER (Multi-Scene + Consistency)
# ────────────────────────────────────────────────
async def generate_voice_async(text, filename):
    cmd = ["edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", filename]
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.wait()

def get_voice(text, filename):
    asyncio.run(generate_voice_async(text, filename))

def create_segment(text_line, image_path, audio_path, is_short=True, is_first=False):
    voice_clip = AudioFileClip(audio_path)
    
    if is_first:
        intro_path = os.path.join(ASSETS_DIR, "intro.mp3")
        get_intro_sound(intro_path)
        if os.path.exists(intro_path):
            intro = AudioFileClip(intro_path).volumex(0.3)
            if intro.duration > voice_clip.duration: intro = intro.subclip(0, voice_clip.duration)
            final_audio = CompositeAudioClip([voice_clip, intro])
        else:
            final_audio = voice_clip
    else:
        final_audio = voice_clip

    duration = final_audio.duration
    w, h = (1080, 1920) if is_short else (1920, 1080)
    
    img = ImageClip(image_path)
    if img.w / img.h > w/h:
        img = img.resize(height=h).crop(x_center=img.w/2, width=w, height=h)
    else:
        img = img.resize(width=w).crop(y_center=img.h/2, width=w, height=h)

    # Random movement per scene to keep it fresh
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
    
    # 1. Define the Consistent Character Seed
    fixed_seed = random.randint(0, 999999)
    char_desc = content['main_char_visual']
    
    full_lyrics = ""
    first_bg_path = None
    
    # 2. Iterate through Scenes (Generate NEW Image for EVERY Line)
    for i, scene in enumerate(content['scenes']):
        line = scene['line']
        action = scene['action']
        
        full_lyrics += line + "\n"
        
        # Audio
        aud_path = os.path.join(ASSETS_DIR, f"aud_{suffix}_{i}.mp3")
        get_voice(line, aud_path)
        
        # Image (Unique per scene, but consistent character)
        img_path = os.path.join(ASSETS_DIR, f"img_{suffix}_{i}.jpg")
        get_image(char_desc, action, img_path, fixed_seed)
        
        if i == 0: first_bg_path = img_path
        
        try:
            if os.path.exists(aud_path) and os.path.getsize(aud_path) > 0:
                clip = create_segment(line, img_path, aud_path, is_short, (i==0))
                clips.append(clip)
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
# 6. UPLOAD
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
                service.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(thumb_path)).execute()
                
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
    print("===== STORYBOARD ENGINE (Consistent Char) =====")
    
    # 1. Short
    data_s = generate_content("short")
    if data_s:
        v, l, t = make_video(data_s, True)
        if v: upload_video(v, data_s, l, t, True)

    # 2. Long
    data_l = generate_content("long")
    if data_l:
        v, l, t = make_video(data_l, False)
        if v: upload_video(v, data_l, l, t, False)
