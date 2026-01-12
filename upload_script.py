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
from pydub import AudioSegment
import requests

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
        json.dump(data, open(os.path.join(MEMORY_DIR, f), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Memory save failed for {f}: {e}")

used_stories = load_used("used_stories.json")
used_rhymes = load_used("used_rhymes.json")
used_images = load_used("used_images.json")
used_topics = load_used("used_topics.json")

# CONTENT GENERATION
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

# AUDIO (eSpeak-ng)
def make_audio(txt, out):
    try:
        wav = "temp.wav"
        subprocess.run([
            "espeak-ng",
            "-v", "hi",
            "-s", "130",
            "-p", "60",
            "-a", "180",
            "-w", wav,
            txt
        ], check=True, timeout=30)
        AudioSegment.from_wav(wav).export(out, format="mp3")
        os.remove(wav)
    except Exception as e:
        print(f"Audio creation failed: {e}")
        sys.exit(1)

# VIDEO (OpenCV + FFmpeg)
def make_video(txt, bg_path, short=False):
    try:
        img = cv2.imread(bg_path)
        if img is None:
            raise ValueError("Image load failed")

        size = (1080, 1920) if short else (1920, 1080)
        img = cv2.resize(img, size)

        # Text overlay
        font, scale, col, thick = cv2.FONT_HERSHEY_DUPLEX, 1.6 if short else 1.4, (0,255,255), 5
        lines = txt.split('\n')
        y, dy = 400 if short else 300, 80
        for i, line in enumerate(lines):
            (tw, _), _ = cv2.getTextSize(line, font, scale, thick)
            x = (size[0] - tw) // 2
            cv2.putText(img, line, (x, y + i*dy), font, scale, col, thick)

        # Zoom frames
        frames = []
        n = 1500
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
        intro = "नमस्ते छोटे दोस्तों! आज नई "
        mid = "कहानी" if "कहानी" in txt else "राइम"
        out = "। लाइक, सब्सक्राइब करो!"
        full = intro + mid + " है: " + txt + out
        aud = os.path.join(OUTPUT_DIR, "aud.mp3")
        make_audio(full, aud)

        # Final merge
        final = os.path.join(OUTPUT_DIR, f"{'s' if short else 'v'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", tmp_vid, "-i", aud,
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            "-pix_fmt", "yuv420p", "-b:v", "8000k", final
        ]
        subprocess.run(cmd, check=True, timeout=300)

        os.remove(tmp_vid)
        os.remove(aud)
        return final

    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# YOUTUBE with robust error handling & retry
def yt_service():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            creds = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes', ['https://www.googleapis.com/auth/youtube.upload'])
            )

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed token
                token_data = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }
                with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                    json.dump(token_data, f, indent=2)
            except Exception as refresh_err:
                print(f"Token refresh failed (using existing token): {refresh_err}")

        if not creds or not creds.valid:
            print("No valid credentials available. Run local OAuth once to generate token.")
            sys.exit(1)

        return build('youtube', 'v3', credentials=creds)

    except Exception as e:
        print(f"Credential loading error: {e}")
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
            print(f"Upload SUCCESS! {'Short' if short else 'Video'} ID: {vid_id} → https://youtu.be/{vid_id}")
            return vid_id

        except HttpError as http_err:
            print(f"YouTube API HTTP error (attempt {attempt+1}/{max_retries}): {http_err}")
            if 'quota' in str(http_err).lower() or 'rate' in str(http_err).lower():
                time.sleep(60 * (attempt + 1))  # Longer backoff for quota/rate limit
            elif attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                print(f"Upload failed after {max_retries} attempts.")
                return None
        except Exception as e:
            print(f"Unexpected upload error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                return None

# MAIN
if __name__ == "__main__":
    print("Starting...")
    success_count = 0

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
            success_count += 1

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
            success_count += 1

        print(f"Completed! {success_count}/2 uploads successful")

    except Exception as e:
        print(f"CRITICAL ERROR in main: {e}")
        sys.exit(1)
