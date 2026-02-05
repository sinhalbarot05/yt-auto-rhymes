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
def openrouter_request(prompt, model="openrouter/free"):
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
                "max_tokens": 500
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenRouter error: {e}")
        return None

# ────────────────────────────────────────────────
# PIXAZO FLUX SCHNELL API FOR THUMBNAIL GENERATION (FREE)
# ────────────────────────────────────────────────
def gen_thumbnail(rhyme, short=False):
    prompt = f"Vibrant cute cartoon thumbnail for Hindi kids nursery rhyme: {rhyme[:100]}... Bright colors, fun characters, animals, text overlay with main rhyme line, viral kids style."
    try:
        response = requests.post(
            "https://api.pixazo.ai/v1/text-to-image",  # Confirm exact endpoint after signup
            headers={
                "Authorization": f"Bearer {os.getenv('PIXAZO_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "prompt": prompt,
                "model": "flux-schnell",
                "steps": 20,
                "width": 1280,
                "height": 720,
                "seed": random.randint(0, 1000000)
            },
            timeout=60
        )
        response.raise_for_status()
        image_url = response.json()["image_url"]  # Adjust based on actual response
        print("Thumbnail generated:", image_url)
        return image_url
    except Exception as e:
        print(f"Pixazo error: {e}")
        return None

# ────────────────────────────────────────────────
# GENERATE UNIQUE NURSERY RHYME USING OPENROUTER
# ────────────────────────────────────────────────
def gen_rhyme(short=False):
    global used_rhymes
    line_count = 10 if short else 20
    prompt = f"एक पूरी तरह नई, मजेदार हिंदी नर्सरी राइम बनाओ ({line_count} लाइनें)। तुकबंदी हो, बच्चों को बहुत पसंद आए, थीम खुशी, दोस्ती, प्रकृति, जानवर या खेल का हो। केवल राइम लिखो, कोई अतिरिक्त टिप्पणी नहीं।"

    rhyme = openrouter_request(prompt)
    if rhyme and rhyme not in used_rhymes:
        used_rhymes.append(rhyme)
        save_used("used_rhymes.json", used_rhymes)
        print("AI-generated unique rhyme:\n", rhyme)
        return rhyme

    # Fallback if API fails or duplicate
    fallback = "चंदा मामा दूर के\nपुए पाके बूर के\nहमको भी दो थोड़े से\nहम भी खाएं पूरे से" * (line_count // 4 + 1)
    if fallback not in used_rhymes:
        used_rhymes.append(fallback)
        save_used("used_rhymes.json", used_rhymes)
    return fallback

# ────────────────────────────────────────────────
# GENERATE VIRAL TITLE USING OPENROUTER
# ────────────────────────────────────────────────
def gen_title(rhyme):
    prompt = f"इस हिंदी नर्सरी राइम के लिए एक वायरल YouTube टाइटल बनाओ (इमोजी, नंबर, सवाल, बच्चों को आकर्षित करने वाला): {rhyme[:200]}... केवल टाइटल लिखो।"
    title = openrouter_request(prompt)
    return title or "प्यारी नर्सरी राइम | बच्चों के लिए मजेदार गाना 😍"

# ────────────────────────────────────────────────
# GENERATE SEO DESCRIPTION USING OPENROUTER
# ────────────────────────────────────────────────
def gen_desc(rhyme):
    prompt = f"इस हिंदी नर्सरी राइम के लिए एक आकर्षक YouTube डिस्क्रिप्शन बनाओ (150-200 शब्द, कीवर्ड्स, इमोजी, लाइक/सब्सक्राइब कॉल टू एक्शन के साथ): {rhyme[:200]}... डिस्क्रिप्शन वायरल हो। केवल डिस्क्रिप्शन लिखो।"
    desc = openrouter_request(prompt)
    return desc or f"{rhyme[:120]}...\n#HindiNurseryRhyme #BacchonKiRhyme #KidsSongs"

# ────────────────────────────────────────────────
# GENERATE VIRAL HASHTAGS USING OPENROUTER
# ────────────────────────────────────────────────
def gen_hashtags(rhyme):
    prompt = f"इस हिंदी नर्सरी राइम के लिए 12-15 वायरल YouTube हैशटैग बनाओ (मिक्स लोकल + ग्लोबल, व्यूज बढ़ाने वाले, इमोजी के साथ): {rhyme[:200]}... केवल हैशटैग लिस्ट लिखो।"
    hashtags = openrouter_request(prompt)
    return hashtags or "#HindiNurseryRhyme #KidsRhymes #ViralKidsSong #NurseryRhymes #BacchonKaGaana"

# ────────────────────────────────────────────────
# DOWNLOAD IMAGE & ADD TEXT TO THUMBNAIL
# ────────────────────────────────────────────────
def create_thumbnail(image_url, rhyme, path):
    try:
        r = requests.get(image_url, timeout=20)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)

        img = Image.open(path)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", 60)
        except:
            font = ImageFont.load_default()

        main_line = rhyme.split('\n')[0][:30] + "..." if len(rhyme.split('\n')[0]) > 30 else rhyme.split('\n')[0]
        bbox = draw.textbbox((0, 0), main_line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (img.width - text_w) // 2
        draw.text((x, img.height - 100), main_line, font=font, fill=(255, 255, 0), stroke_width=4, stroke_fill=(0,0,0))

        img.save(path)
        print("Thumbnail with text saved:", path)
    except Exception as e:
        print(f"Thumbnail creation failed: {e}")

# ────────────────────────────────────────────────
# YOUTUBE UPLOAD
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
                print("Token refreshed")
            else:
                print("Token valid")

        else:
            print("No credentials")
            sys.exit(1)

        return build('youtube', 'v3', credentials=creds)

    except Exception as e:
        print(f"Credential error: {e}")
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
    print("===== Hindi Kids Nursery Rhymes Auto-Generator with Flux & OpenRouter =====")
    success = 0

    try:
        # Long Video (20 lines)
        text_v = gen_rhyme(short=False)
        topic_v = gen_topic(text_v)
        title_v = gen_title(text_v)
        desc_v = gen_desc(text_v)
        tags_v = gen_hashtags(text_v).split()
        thumbnail_url_v = gen_thumbnail(text_v, short=False)
        thumbnail_path_v = os.path.join(BG_IMAGES_DIR, "thumbnail_long.png")
        if thumbnail_url_v:
            create_thumbnail(thumbnail_url_v, text_v, thumbnail_path_v)

        bg_v = os.path.join(BG_IMAGES_DIR, "bg_v.jpg")
        dl_image(thumbnail_url_v or "fallback_url", bg_v)
        video_path = make_video(text_v, bg_v, short=False)

        if upload(video_path, title_v, desc_v, tags_v, thumbnail_path=thumbnail_path_v):
            success += 1

        # Short Video (10 lines)
        text_s = gen_rhyme(short=True)
        topic_s = gen_topic(text_s)
        title_s = gen_title(text_s)
        desc_s = gen_desc(text_s)
        tags_s = gen_hashtags(text_s).split()
        thumbnail_url_s = gen_thumbnail(text_s, short=True)
        thumbnail_path_s = os.path.join(BG_IMAGES_DIR, "thumbnail_short.png")
        if thumbnail_url_s:
            create_thumbnail(thumbnail_url_s, text_s, thumbnail_path_s)

        bg_s = os.path.join(BG_IMAGES_DIR, "bg_s.jpg")
        dl_image(thumbnail_url_s or "fallback_url", bg_s)
        short_path = make_video(text_s, bg_s, short=True)

        if upload(short_path, title_s, desc_s, tags_s, short=True, thumbnail_path=thumbnail_path_s):
            success += 1

        print(f"\n===== Finished! {success}/2 rhymes uploaded =====")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
