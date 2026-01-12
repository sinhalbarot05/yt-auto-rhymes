import os
import random
import json
import sys
import subprocess
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

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
BG_IMAGES_DIR = "images/"

for d in [MEMORY_DIR, OUTPUT_DIR, BG_IMAGES_DIR]:
    Path(d).mkdir(exist_ok=True)

# MEMORY
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

# CONTENT
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
        h = requests.get(u).json().get("hits", [])
        random.shuffle(h)
        for i in h:
            url = i.get("largeImageURL")
            if url and url not in used_images:
                used_images.append(url)
                save_used("used_images.json", used_images)
                return url
        sys.exit("No image")
    except:
        sys.exit("Pixabay fail")

def dl_image(url, path):
    with open(path, "wb") as f:
        f.write(requests.get(url, timeout=15).content)

# AUDIO (eSpeak-ng - offline)
def make_audio(txt, out):
    wav = "temp.wav"
    subprocess.run([
        "espeak-ng",
        "-v", "hi",           # Hindi voice
        "-s", "130",          # Slower for kids
        "-p", "60",           # Higher pitch (female/child-like)
        "-a", "180",          # Louder
        "-w", wav,
        txt
    ], check=True)
    AudioSegment.from_wav(wav).export(out, format="mp3")
    os.remove(wav)

# VIDEO (OpenCV + FFmpeg)
def make_video(txt, bg_path, short=False):
    img = cv2.imread(bg_path)
    if img is None:
        sys.exit("Image load fail")

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
    n = 1500  # ~62s at 24fps
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
    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_vid, "-i", aud,
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
        "-pix_fmt", "yuv420p", "-b:v", "8000k", final
    ], check=True)

    os.remove(tmp_vid)
    os.remove(aud)
    return final

# YOUTUBE
def yt_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            creds = Credentials(**json.load(f))

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(vars(creds), f, indent=2)

    if not creds or not creds.valid:
        print("No credentials")
        sys.exit(1)

    return build('youtube', 'v3', credentials=creds)

def upload(vid, title, desc, tags, short=False):
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
            print(f"Uploaded {int(status.progress()*100)}%")

    vid_id = resp['id']
    print(f"Done: https://youtu.be/{vid_id}")
    return vid_id

# MAIN
if __name__ == "__main__":
    print("Starting...")
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
        upload(v_path, t_v, d_v, tags_v)

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
        upload(s_path, t_s, d_s, tags_s, True)

        print("Success!")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
