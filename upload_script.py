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

# MEMORY
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

# AI-generated nursery rhyme using Groq API
def gen_rhyme():
    global used_rhymes
    prompt = """एक छोटी, मधुर हिंदी नर्सरी राइम (नर्सरी राइम) बनाओ (4-8 लाइनें)।
राइम में तुकबंदी हो, बच्चों को पसंद आए, खुशी, दोस्ती, प्रकृति, जानवर या खेल का थीम हो।
कहानी जैसा नहीं, सिर्फ मजेदार गीत जैसा।
केवल राइम लिखो, कोई शीर्षक या अतिरिक्त टिप्पणी मत डालो। पूरी तरह नई हो।"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",  # valid Groq alias
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.95,
                "max_tokens": 200
            },
            timeout=20
        )
        response.raise_for_status()
        rhyme = response.json()["choices"][0]["message"]["content"].strip()
        
        if rhyme not in used_rhymes:
            used_rhymes.append(rhyme)
            save_used("used_rhymes.json", used_rhymes)
            print("AI-generated rhyme:", rhyme)
            return rhyme
    
    except Exception as e:
        print(f"Groq API error: {e}")
        fallback = "चंदा मामा दूर के\nपुए पाके बूर के\nहमको भी दो थोड़े से\nहम भी खाएं पूरे से"
        if fallback not in used_rhymes:
            used_rhymes.append(fallback)
            save_used("used_rhymes.json", used_rhymes)
        return fallback

# ... (rest of the script remains the same as previous - gen_topic, get_image, dl_image, make_audio, make_video, upload)

# FIXED YOUTUBE
def yt_service():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)

        if creds:
            print(f"Credentials loaded from pickle. Expiry: {creds.expiry} (type: {type(creds.expiry)})")

            if creds.expiry is None:
                print("No expiry set — assuming valid")
            else:
                now_utc = datetime.now(timezone.utc)
                if creds.expiry < now_utc:
                    print("Token expired - refreshing")
                    creds.refresh(Request())
                    with open(TOKEN_FILE, 'wb') as f:
                        pickle.dump(creds, f)
                    print("Token refreshed and saved as pickle")
                else:
                    print("Token valid")

        else:
            print("No credentials in pickle")
            sys.exit(1)

        return build('youtube', 'v3', credentials=creds)

    except Exception as e:
        print(f"Credential error: {e}")
        if os.path.exists(TOKEN_FILE):
            print("Token file size:", os.path.getsize(TOKEN_FILE))
        sys.exit(1)

# MAIN (unchanged)
if __name__ == "__main__":
    print("===== Hindi Kids Nursery Rhymes Auto-Generator with Groq AI =====")
    success = 0

    try:
        # Long Video - rhyme
        text_v = gen_rhyme()
        topic_v = gen_topic(text_v)
        img_url_v = get_image(topic_v, "horizontal")
        bg_v = os.path.join(BG_IMAGES_DIR, "bg_v.jpg")
        dl_image(img_url_v, bg_v)

        video_path = make_video(text_v, bg_v, short=False)
        title_v = f"प्यारी नर्सरी राइम 2026 | {topic_v} | बच्चों के लिए"
        desc_v = f"{text_v[:120]}...\n#HindiNurseryRhyme #BacchonKiRhyme #KidsSongs"
        tags_v = ["हिंदी नर्सरी राइम", "बच्चों की राइम", "kids rhyme hindi", "nursery rhymes"] + text_v.split()[:6]

        if upload(video_path, title_v, desc_v, tags_v):
            success += 1

        # Short Video - rhyme
        text_s = gen_rhyme()
        topic_s = gen_topic(text_s)
        img_url_s = get_image(topic_s, "vertical")
        bg_s = os.path.join(BG_IMAGES_DIR, "bg_s.jpg")
        dl_image(img_url_s, bg_s)

        short_path = make_video(text_s, bg_s, short=True)
        title_s = f"मस्ती वाली नर्सरी राइम #shorts | {topic_s}"
        desc_s = f"{text_s[:90]}...\n#Shorts #NurseryRhyme"
        tags_s = tags_v + ["shorts", "youtubeshorts", "kids rhyme shorts"]

        if upload(short_path, title_s, desc_s, tags_s, True):
            success += 1

        print(f"\n===== Finished! {success}/2 rhymes uploaded =====")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
