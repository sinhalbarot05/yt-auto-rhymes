import os
import random
import json
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment
import requests

from piper.voice import PiperVoice

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
VOICE_MODEL = "voices/hi_IN-swara-medium.onnx"

for d in [MEMORY_DIR, OUTPUT_DIR, BG_IMAGES_DIR]:
    Path(d).mkdir(exist_ok=True)

# Load Piper once (natural Hindi female)
try:
    piper = PiperVoice.load(VOICE_MODEL)
except Exception as e:
    print(f"Piper load failed: {e}")
    sys.exit(1)

# MEMORY (unchanged)
def load_used(f):
    p = os.path.join(MEMORY_DIR, f)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []

def save_used(f, data):
    try:
        json.dump(data, open(os.path.join(MEMORY_DIR, f), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except:
        pass

used_stories = load_used("used_stories.json")
used_rhymes = load_used("used_rhymes.json")
used_images = load_used("used_images.json")
used_topics = load_used("used_topics.json")

# CONTENT GENERATION (simplified)
animals = ["खरगोश", "तोता", "मछली", "हाथी", "शेर"]
places = ["जंगल", "समंदर", "पहाड़", "नदी", "गाँव"]
actions = ["खो गया", "सीखा", "मिला", "खेला"]
adventures = ["दोस्त बनाए", "जादू सीखा", "खजाना पाया"]
endings = ["घर लौट आया", "खुश रहा", "समझदार हो गया"]
lessons = ["दोस्ती", "साहस", "मेहनत", "प्यार"]

def gen_story():
    global used_stories
    while True:
        s = f"एक छोटा {random.choice(animals)} {random.choice(places)} में {random.choice(actions)}। {random.choice(adventures)}। अंत में {random.choice(endings)}। {random.choice(lessons)} सिखाती है।"
        if s not in used_stories:
            used_stories.append(s)
            save_used("used_stories.json", used_stories)
            return s

def gen_rhyme():
    global used_rhymes
    while True:
        r = f"छोटी-छोटी बातें, बड़ी सीख।\nखेलो हँसो मुस्कुराओ यार।\nसपनों को पकड़ो उड़ो ऊँचा।\nप्यार बाँटो जीवन सुंदर बनाओ।"
        if r not in used_rhymes:
            used_rhymes.append(r)
            save_used("used_rhymes.json", used_rhymes)
            return r

def gen_topic(txt):
    global used_topics
    t = " ".join(txt.split()[:4])
    while t in used_topics:
        t += f" {random.choice(['नई','मजेदार'])}"
    used_topics.append(t)
    save_used("used_topics.json", used_topics)
    return t

# IMAGE
def get_image(topic, orient="horizontal"):
    q = f"cute hindi kids cartoon {topic}"
    u = f"https://pixabay.com/api/?key={os.getenv('PIXABAY_KEY')}&q={q}&image_type=illustration&orientation={orient}&per_page=10&safesearch=true"
    try:
        h = requests.get(u, timeout=15).json().get("hits", [])
        random.shuffle(h)
        for i in h:
            url = i.get("largeImageURL")
            if url and url not in used_images:
                used_images.append(url)
                save_used("used_images.json", used_images)
                return url
        print("No suitable image found.")
        sys.exit(1)
    except Exception as e:
        print(f"Pixabay error: {e}")
        sys.exit(1)

def dl_image(url, path):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Image download failed: {e}")
        sys.exit(1)

# AUDIO (Piper TTS - natural female Hindi)
def make_audio(txt, out):
    try:
        wav_bytes = piper.synthesize(txt)
        temp_wav = "temp.wav"
        with open(temp_wav, "wb") as f:
            f.write(wav_bytes)

        audio = AudioSegment.from_wav(temp_wav)
        audio = audio.normalize()
        audio = audio + 10  # Boost if needed
        audio.export(out, format="mp3", bitrate="192k")
        os.remove(temp_wav)
    except Exception as e:
        print(f"Piper TTS failed: {e}")
        sys.exit(1)

# VIDEO (OpenCV + Pillow for perfect Hindi text)
def make_video(txt, bg_path, short=False):
    try:
        # Load background
        img = cv2.imread(bg_path)
        if img is None:
            raise ValueError("Image load failed")

        size = (1080, 1920) if short else (1920, 1080)
        img = cv2.resize(img, size)

        # Use Pillow to render Hindi text (perfect Devanagari support)
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        try:
            font_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"  # System Noto font
            font = ImageFont.truetype(font_path, 80 if short else 70)
        except:
            font = ImageFont.load_default()  # Fallback

        lines = txt.split('\n')
        y, dy = 400 if short else 300, 100
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (size[0] - text_w) // 2
            draw.text((x, y), line, font=font, fill=(255, 255, 0))  # Yellow
            y += dy

        # Convert back to OpenCV
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Zoom frames
        frames = []
        n = 1800
        for i in range(n):
            s = 1 + 0.015 * (i / n)
            h, w = img.shape[:2]
            nh, nw = int(h*s), int(w*s)
            z = cv2.resize(img, (nw, nh))
            frames.append(z[(nh-h)//2:(nh-h)//2+h, (nw-w)//2:(nw-w)//2+w])

        # Temp video
        tmp_vid = os.path.join(OUTPUT_DIR, "tmp.mp4")
        out = cv2.VideoWriter(tmp_vid, cv2.VideoWriter_fourcc(*'mp4v'), 24, size)
        for f in frames:
            out.write(f)
        out.release()

        # Audio
        intro = "नमस्ते छोटे दोस्तों! आज फिर आई एक नई मजेदार "
        mid = "कहानी" if "कहानी" in txt else "राइम"
        outro = "। बहुत पसंद आए तो लाइक करें, सब्सक्राइब करें और बेल आइकन दबाएं!"
        full = intro + mid + " है: " + txt + outro
        aud = os.path.join(OUTPUT_DIR, "aud.mp3")
        make_audio(full, aud)

        # Merge
        final = os.path.join(OUTPUT_DIR, f"{'s' if short else 'v'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", tmp_vid, "-i", aud,
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            "-pix_fmt", "yuv420p", "-b:v", "8000k", final
        ], check=True, timeout=300)

        os.remove(tmp_vid)
        os.remove(aud)
        return final

    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# YOUTUBE (robust)
def yt_service():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            creds = Credentials(**token_data)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(vars(creds), f, indent=2)

        if not creds or not creds.valid:
            print("No valid credentials.")
            sys.exit(1)

        return build('youtube', 'v3', credentials=creds)

    except Exception as e:
        print(f"Credential error: {e}")
        sys.exit(1)

def upload(vid, title, desc, tags, short=False):
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
            return vid_id

        except HttpError as e:
            print(f"HTTP error (attempt {attempt+1}): {e}")
            time.sleep(10 * (attempt + 1))
        except Exception as e:
            print(f"Upload error (attempt {attempt+1}): {e}")
            time.sleep(10 * (attempt + 1))

    print("Upload failed after retries.")
    return None

# MAIN
if __name__ == "__main__":
    print("Starting...")
    success = 0
    try:
        # Video
        story_mode = random.random() > 0.4
        txt_v = gen_story() if story_mode else gen_rhyme()
        top_v = gen_topic(txt_v)

        url_v = get_image(top_v, "horizontal")
        p_v = os.path.join(BG_IMAGES_DIR, "bg_v.jpg")
        dl_image(url_v, p_v)

        v_path = make_video(txt_v, p_v, False)

        t_v = f"मजेदार नई {'कहानी' if story_mode else 'राइम'} | {top_v} | 2026"
        d_v = f"नमस्ते! {txt_v[:100]}...\n#HindiKids #BacchonKiKahani"
        tags_v = ["हिंदी कहानी", "बच्चों की कहानी", "नई राइम 2026"] + txt_v.split()[:5]
        if upload(v_path, t_v, d_v, tags_v):
            success += 1

        # Short
        story_mode_s = random.random() > 0.5
        txt_s = gen_story() if story_mode_s else gen_rhyme()
        top_s = gen_topic(txt_s)

        url_s = get_image(top_s, "vertical")
        p_s = os.path.join(BG_IMAGES_DIR, "bg_s.jpg")
        dl_image(url_s, p_s)

        s_path = make_video(txt_s, p_s, True)

        t_s = f"प्यारी {'कहानी' if story_mode_s else 'राइम'} #shorts | {top_s}"
        d_s = f"{txt_s[:80]}...\n#Shorts"
        tags_s = tags_v + ["shorts"]
        if upload(s_path, t_s, d_s, tags_s, True):
            success += 1

        print(f"Completed! {success}/2 successful")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
