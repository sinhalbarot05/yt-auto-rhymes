import os
import random
import json
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone
import pickle
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment
import requests
from gtts import gTTS

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
BG_IMAGES_DIR = "images/"
TOKEN_FILE = "youtube_token.pickle"

for d in [MEMORY_DIR, OUTPUT_DIR, BG_IMAGES_DIR]:
    Path(d).mkdir(exist_ok=True)

# ────────────────────────────────────────────────
# MEMORY MANAGEMENT
# ────────────────────────────────────────────────
def load_used(f):
    p = os.path.join(MEMORY_DIR, f)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []

def save_used(f, data):
    try:
        json.dump(data, open(os.path.join(MEMORY_DIR, f), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Memory save failed for {f}: {e}")

used_rhymes = load_used("used_rhymes.json")
used_images = load_used("used_images.json")
used_topics = load_used("used_topics.json")

# ────────────────────────────────────────────────
# OPENROUTER API FOR TEXT GENERATION (FREE MODELS)
# ────────────────────────────────────────────────
def openrouter_request(prompt, model="openrouter/free"):  # Uses free router for random free model
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.95,
                "max_tokens": 400
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenRouter error: {e}")
        return None

# ────────────────────────────────────────────────
# GENERATE NURSERY RHYME USING OPENROUTER
# ────────────────────────────────────────────────
def gen_rhyme(short=False):
    global used_rhymes
    line_count = 10 if short else 20
    prompt = f"एक पूरी तरह नई, मजेदार हिंदी नर्सरी राइम बनाओ ({line_count} लाइनें)। तुकबंदी हो, बच्चों को पसंद आए, थीम खुशी, दोस्ती, प्रकृति, जानवर या खेल का हो। केवल राइम लिखो, कोई अतिरिक्त टिप्पणी नहीं।"

    rhyme = openrouter_request(prompt)
    if rhyme:
        if rhyme not in used_rhymes:
            used_rhymes.append(rhyme)
            save_used("used_rhymes.json", used_rhymes)
            print("AI-generated rhyme:\n", rhyme)
            return rhyme

    # Fallback if API fails
    fallback = "चंदा मामा दूर के\nपुए पाके बूर के\nहमको भी दो थोड़े से\nहम भी खाएं पूरे से" * (line_count // 4)
    if fallback not in used_rhymes:
        used_rhymes.append(fallback)
        save_used("used_rhymes.json", used_rhymes)
    return fallback

# ────────────────────────────────────────────────
# GENERATE TITLE USING OPENROUTER
# ────────────────────────────────────────────────
def gen_title(rhyme):
    prompt = f"इस हिंदी नर्सरी राइम के लिए एक आकर्षक, वायरल होने वाला YouTube टाइटल बनाओ (इमोजी, नंबर, सवाल के साथ): {rhyme[:200]}... टाइटल बच्चों को आकर्षित करे और व्यूज बढ़ाए। केवल टाइटल लिखो।"
    title = openrouter_request(prompt)
    return title or "प्यारी नर्सरी राइम | बच्चों के लिए मजेदार गाना"

# ────────────────────────────────────────────────
# GENERATE DESCRIPTION USING OPENROUTER
# ────────────────────────────────────────────────
def gen_desc(rhyme):
    prompt = f"इस हिंदी नर्सरी राइम के लिए एक SEO ऑप्टिमाइज्ड YouTube डिस्क्रिप्शन बनाओ (100-150 शब्द, कीवर्ड्स, इमोजी, कॉल टू एक्शन के साथ): {rhyme[:200]}... डिस्क्रिप्शन वायरल होने और सब्सक्राइबर्स बढ़ाने में मदद करे। केवल डिस्क्रिप्शन लिखो।"
    desc = openrouter_request(prompt)
    return desc or f"{rhyme[:120]}...\n#HindiNurseryRhyme #BacchonKiRhyme #KidsSongs"

# ────────────────────────────────────────────────
# GENERATE HASHTAGS USING OPENROUTER
# ────────────────────────────────────────────────
def gen_hashtags(rhyme):
    prompt = f"इस हिंदी नर्सरी राइम के लिए 10-15 वायरल YouTube हैशटैग बनाओ (मिक्स लोकल और ग्लोबल, व्यूज बढ़ाने वाले): {rhyme[:200]}... हैशटैग वीडियो को वायरल बनाने में मदद करें। केवल हैशटैग लिस्ट लिखो।"
    hashtags = openrouter_request(prompt)
    return hashtags or "#HindiNurseryRhyme #KidsRhymes #ViralKidsSong #NurseryRhymes"

# ────────────────────────────────────────────────
# GENERATE THUMBNAIL IMAGE USING PRODIA API (FREE TIER)
# ────────────────────────────────────────────────
def gen_thumbnail(rhyme, short=False):
    prompt = f"Create a colorful, cute cartoon thumbnail for a kids nursery rhyme video: {rhyme[:100]}... Include main rhyme elements, bright colors, fun characters, and text of main rhyme line. Make it viral-looking with emojis if possible. Style: cartoon for kids."
    try:
        response = requests.post(
            "https://api.prodia.com/v1/sd/generate",
            headers={
                "X-Prodia-Key": os.getenv('PRODIA_API_KEY')
            },
            json={
                "prompt": prompt,
                "model": "sd_xl_base_1.0.safetensors [be9edd61]",
                "steps": 25,
                "cfg_scale": 7,
                "seed": random.randint(0, 1000000)
            },
            timeout=60
        )
        response.raise_for_status()
        job_id = response.json()["job"]
        
        # Poll for result
        for _ in range(30):
            status = requests.get(f"https://api.prodia.com/v1/job/{job_id}", headers={"X-Prodia-Key": os.getenv('PRODIA_API_KEY')}).json()
            if status["status"] == "succeeded":
                image_url = status["imageUrl"]
                return image_url
            time.sleep(2)
        print("Prodia timeout")
        return None
    except Exception as e:
        print(f"Prodia error: {e}")
        return None

# ────────────────────────────────────────────────
# GENERATE MULTI-FRAME IMAGES FOR ANIMATION USING PRODIA
# ────────────────────────────────────────────────
def gen_animation_images(rhyme):
    lines = rhyme.split('\n')
    stanzas = [ '\n'.join(lines[i:i+4]) for i in range(0, len(lines), 4) ]  # Split into stanzas of 4 lines
    images = []
    for stanza in stanzas:
        prompt = f"Cute cartoon scene matching this kids rhyme stanza: {stanza}. Bright colors, fun characters, educational theme."
        image_url = gen_thumbnail(prompt)  # Reuse thumbnail gen for simplicity
        if image_url:
            images.append(image_url)
        else:
            images.append("fallback_image_url")  # Use Pixabay fallback if needed
    return images

# ────────────────────────────────────────────────
# DOWNLOAD AND ADD TEXT TO THUMBNAIL
# ────────────────────────────────────────────────
def create_thumbnail(image_url, rhyme, path):
    dl_image(image_url, path)
    # Add text to thumbnail with main rhyme line
    img = Image.open(path)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    main_line = rhyme.split('\n')[0]  # First line as main text
    draw.text((10, 10), main_line, font=font, fill=(255, 0, 0))
    img.save(path)

# ────────────────────────────────────────────────
# YOUTUBE UPLOAD (unchanged)
# ────────────────────────────────────────────────
def yt_service():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)

        if creds:
            print(f"Credentials loaded from pickle. Expiry: {creds.expiry if creds.expiry else 'None'}")
            now_utc = datetime.now(timezone.utc)
            if creds.expiry and creds.expiry < now_utc:
                print("Token expired - refreshing")
                creds.refresh(Request())
                with open(TOKEN_FILE, 'wb') as f:
                    pickle.dump(creds, f)
                print("Token refreshed and saved as pickle")
            else:
                print("Token is valid or no expiry")

        else:
            print("No credentials in pickle")
            sys.exit(1)

        return build('youtube', 'v3', credentials=creds)

    except Exception as e:
        print(f"Credential error: {e}")
        if os.path.exists(TOKEN_FILE):
            print("Token file size:", os.path.getsize(TOKEN_FILE))
            with open(TOKEN_FILE, 'rb') as f:
                print("First 50 bytes (hex):", f.read(50).hex())
        sys.exit(1)

def upload(vid, title, desc, tags, short=False, thumbnail_path=None):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            yt = yt_service()
            body = {
                'snippet': {'title': title, 'description': desc, 'tags': tags, 'categoryId': '24'},
                'status': {'privacyStatus': 'public'}
            }
            media = MediaFileUpload(vid, mimetype='video/mp4', resumable=True)
            req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
            resp = None
            while resp is None:
                status, resp = req.next_chunk()
                if status:
                    print(f"Upload progress: {int(status.progress()*100)}%")
            vid_id = resp['id']
            print(f"Upload SUCCESS! {'Short' if short else 'Video'} ID: {vid_id}")

            # Upload thumbnail if provided
            if thumbnail_path:
                yt.thumbnails().set(
                    videoId=vid_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype='image/png')
                ).execute()
                print("Thumbnail uploaded")

            return vid_id
        except HttpError as e:
            print(f"HTTP error (attempt {attempt+1}): {e}")
            time.sleep(10 * (attempt + 1))
        except Exception as e:
            print(f"Upload error (attempt {attempt+1}): {e}")
            time.sleep(10 * (attempt + 1))
    print("Upload failed after retries.")
    return None

# ────────────────────────────────────────────────
# MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== Hindi Kids Nursery Rhymes Auto-Generator with OpenRouter AI =====")
    success = 0

    try:
        # Long Video
        text_v = gen_rhyme(short=False)  # 20 lines
        topic_v = gen_topic(text_v)
        title_v = gen_title(text_v)
        desc_v = gen_desc(text_v)
        tags_v = gen_hashtags(text_v)
        animation_images = gen_animation_images(text_v)
        bg_v = os.path.join(BG_IMAGES_DIR, "bg_v.jpg")
        dl_image(animation_images[0] if animation_images else "fallback_url", bg_v)  # Use first image as bg
        video_path = make_video(text_v, bg_v, short=False)
        thumbnail_url = gen_thumbnail(text_v, short=False)
        thumbnail_path = os.path.join(BG_IMAGES_DIR, "thumbnail_v.png")
        create_thumbnail(thumbnail_url, text_v, thumbnail_path)

        if upload(video_path, title_v, desc_v, tags_v.split(), thumbnail_path=thumbnail_path):
            success += 1

        # Short Video
        text_s = gen_rhyme(short=True)  # 10 lines
        topic_s = gen_topic(text_s)
        title_s = gen_title(text_s)
        desc_s = gen_desc(text_s)
        tags_s = gen_hashtags(text_s)
        animation_images_s = gen_animation_images(text_s)
        bg_s = os.path.join(BG_IMAGES_DIR, "bg_s.jpg")
        dl_image(animation_images_s[0] if animation_images_s else "fallback_url", bg_s)
        short_path = make_video(text_s, bg_s, short=True)
        thumbnail_url_s = gen_thumbnail(text_s, short=True)
        thumbnail_path_s = os.path.join(BG_IMAGES_DIR, "thumbnail_s.png")
        create_thumbnail(thumbnail_url_s, text_s, thumbnail_path_s)

        if upload(short_path, title_s, desc_s, tags_s.split(), short=True, thumbnail_path=thumbnail_path_s):
            success += 1

        print(f"\n===== Finished! {success}/2 rhymes uploaded =====")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
