# upload_script.py

import os
import random
import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

import cv2
import numpy as np
from pydub import AudioSegment
import requests

# YouTube API
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ─── CONFIGURATION ──────────────────────────────────────────────────────────────
MEMORY_DIR = "memory/"
Path(MEMORY_DIR).mkdir(exist_ok=True)

OUTPUT_DIR = "videos/"
Path(OUTPUT_DIR).mkdir(exist_ok=True)

BG_IMAGES_DIR = "images/"
Path(BG_IMAGES_DIR).mkdir(exist_ok=True)

CLIENT_SECRETS_FILE = "client_secret.json"
TOKEN_FILE = "youtube_token.pickle"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# ─── MEMORY FUNCTIONS ───────────────────────────────────────────────────────────
def load_used(file_name):
    path = os.path.join(MEMORY_DIR, file_name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_used(file_name, data):
    path = os.path.join(MEMORY_DIR, file_name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save {file_name}: {e}")

used_stories = load_used("used_stories.json")
used_rhymes = load_used("used_rhymes.json")
used_images = load_used("used_images.json")
used_topics = load_used("used_topics.json")

# ─── CONTENT GENERATION ─────────────────────────────────────────────────────────
animals = ["खरगोश", "तोता", "मछली", "हाथी", "शेर", "मोर", "बिल्ली", "कुत्ता"]
places = ["जंगल", "समंदर", "पहाड़", "नदी", "गाँव", "बाग", "झील"]
actions = ["खो गया", "सीखा", "मिला", "खेला", "तैरा", "दौड़ा", "गाया"]
adventures = ["अद्भुत चीजें देखीं", "नए दोस्त बनाए", "खजाना पाया", "जादू सीखा"]
endings = ["घर लौट आया", "खुश रहा", "समझदार हो गया", "जीत गया"]
lessons = ["दोस्ती", "साहस", "मेहनत", "प्यार", "ईमानदारी"]

def generate_story():
    while True:
        animal = random.choice(animals)
        place = random.choice(places)
        action = random.choice(actions)
        adv = random.sample(adventures, 3)
        end = random.sample(endings, 2)
        lesson = random.choice(lessons)
        
        story = (
            f"एक छोटा {animal} था जो {place} में {action}। "
            f"वहाँ उसने {adv[0]}, {adv[1]} और {adv[2]}। "
            f"अंत में वह {end[0]} और {end[1]}। "
            f"यह कहानी बच्चों को {lesson} का महत्व सिखाती है।"
        )
        if story not in used_stories:
            used_stories.append(story)
            save_used("used_stories.json", used_stories)
            return story

def generate_rhyme():
    while True:
        line1 = f"छोटी-छोटी {random.choice(['बातें','खुशियाँ','सपने'])}, बड़ी-बड़ी {random.choice(lessons)}।"
        line2 = f"{random.choice(['खेलो','हँसो','गाओ','नाचो'])} {random.choice(['दोस्तों','सबके साथ'])}।"
        line3 = f"सपनों को पकड़ो, ऊँचा {random.choice(['उड़ो','जाओ'])}।"
        line4 = f"प्यार बाँटो, जीवन को {random.choice(['सुंदर','खुशहाल'])} बनाओ।"
        
        rhyme = f"{line1}\n{line2}\n{line3}\n{line4}"
        if rhyme not in used_rhymes:
            used_rhymes.append(rhyme)
            save_used("used_rhymes.json", used_rhymes)
            return rhyme

def generate_topic(text):
    words = text.split()[:5]
    topic = " ".join(words)
    i = 0
    while topic in used_topics and i < 10:
        topic += f" {random.choice(['नई','मजेदार','प्यारी','2026'])}"
        i += 1
    used_topics.append(topic)
    save_used("used_topics.json", used_topics)
    return topic

# ─── IMAGE & AUDIO (using eSpeak-ng) ────────────────────────────────────────────
def fetch_random_image(topic, orientation="horizontal"):
    query = f"cute hindi kids cartoon illustration {topic}"
    url = f"https://pixabay.com/api/?key={os.getenv('PIXABAY_KEY')}&q={query}&image_type=illustration&orientation={orientation}&per_page=20&safesearch=true"
    
    try:
        resp = requests.get(url).json()
        hits = resp.get("hits", [])
        random.shuffle(hits)
        for hit in hits:
            img_url = hit.get("largeImageURL")
            if img_url and img_url not in used_images:
                used_images.append(img_url)
                save_used("used_images.json", used_images)
                return img_url
        print("No new image found.")
        sys.exit(1)
    except Exception as e:
        print(f"Pixabay error: {e}")
        sys.exit(1)

def download_image(url, path):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Download failed: {e}")
        sys.exit(1)

def create_audio(text, output_path):
    try:
        temp_wav = "temp_audio.wav"
        
        # eSpeak-ng with Hindi voice + child-friendly settings
        subprocess.run([
            "espeak-ng",
            "-v", "hi",           # Hindi voice
            "-s", "130",          # Slightly slower speed
            "-p", "60",           # Higher pitch (more female/child-like)
            "-a", "180",          # Louder volume
            "-w", temp_wav,
            text
        ], check=True)
        
        audio = AudioSegment.from_wav(temp_wav)
        audio = audio + 10  # Extra volume boost
        audio.export(output_path, format="mp3")
        os.remove(temp_wav)
        
    except Exception as e:
        print(f"eSpeak-ng audio failed: {e}")
        sys.exit(1)

def create_video(content_text, bg_image_path, is_short=False):
    try:
        # Load background image
        img = cv2.imread(bg_image_path)
        if img is None:
            raise ValueError("Failed to load background image")

        # Resize
        if is_short:
            img = cv2.resize(img, (1080, 1920))
        else:
            img = cv2.resize(img, (1920, 1080))

        # Add multi-line text overlay
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 1.8 if is_short else 1.5
        color = (0, 255, 255)  # Yellow
        thickness = 5
        lines = content_text.split('\n')
        y0, dy = 400 if is_short else 300, 90
        for i, line in enumerate(lines):
            y = y0 + i * dy
            text_size = cv2.getTextSize(line, font, font_scale, thickness)[0]
            x = (img.shape[1] - text_size[0]) // 2  # Center
            cv2.putText(img, line, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)

        # Add gentle zoom effect (frame-by-frame)
        frames = []
        num_frames = 1500  # ~62 seconds at 24fps
        for i in range(num_frames):
            scale = 1 + 0.015 * (i / num_frames)  # Slow zoom-in
            h, w = img.shape[:2]
            new_h, new_w = int(h * scale), int(w * scale)
            zoomed = cv2.resize(img, (new_w, new_h))
            start_y = (new_h - h) // 2
            start_x = (new_w - w) // 2
            cropped = zoomed[start_y:start_y+h, start_x:start_x+w]
            frames.append(cropped)

        # Write temp video (no audio)
        temp_video = os.path.join(OUTPUT_DIR, "temp_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_video, fourcc, 24.0, (img.shape[1], img.shape[0]))
        for frame in frames:
            out.write(frame)
        out.release()

        # Generate audio
        intro = "नमस्ते छोटे दोस्तों! आज फिर आई एक नई मजेदार "
        middle = "कहानी" if "कहानी" in content_text else "राइम"
        outro = "। बहुत पसंद आए तो लाइक करें, सब्सक्राइब करें और बेल आइकन दबाएं!"
        full_text = intro + middle + " है: " + content_text + outro
        
        audio_path = os.path.join(OUTPUT_DIR, "narration.mp3")
        create_audio(full_text, audio_path)

        # Calculate duration from audio (in seconds)
        audio = AudioSegment.from_mp3(audio_path)
        audio_duration_sec = len(audio) / 1000.0  # pydub length in ms → sec

        # Desired video duration should match audio (or be slightly longer)
        desired_fps = 24
        desired_frames = int(audio_duration_sec * desired_fps) + 100  # extra frames for safety

        # Re-write temp video with correct duration
        out = cv2.VideoWriter(temp_video, fourcc, desired_fps, (img.shape[1], img.shape[0]))
        for i in range(desired_frames):
            frame_idx = min(i, len(frames) - 1)
            out.write(frames[frame_idx])
        out.release()

        # Merge with FFmpeg
        final_output = os.path.join(OUTPUT_DIR, f"{'short' if is_short else 'video'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", audio_path,
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest", "-pix_fmt", "yuv420p",
            "-b:v", "8000k",
            final_output
        ]
        subprocess.run(cmd, check=True)

        # Cleanup
        os.remove(temp_video)
        os.remove(audio_path)

        return final_output

    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# ─── YOUTUBE UPLOAD ─────────────────────────────────────────────────────────────
def get_authenticated_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            creds = Credentials(**token_data)
        except Exception as e:
            print(f"Credentials load error: {e}")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(vars(creds), f, indent=2)
        except Exception as e:
            print(f"Refresh failed: {e}")

    if not creds or not creds.valid:
        print("No valid credentials. Need manual OAuth first.")
        sys.exit(1)

    return build('youtube', 'v3', credentials=creds)

def upload_to_youtube(video_file, title, description, tags, is_short=False):
    youtube = get_authenticated_service()

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': '24'
        },
        'status': {
            'privacyStatus': 'public'
        }
    }

    media = MediaFileUpload(video_file, mimetype='video/mp4', resumable=True)

    print(f"Uploading {'Short' if is_short else 'Video'}...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        except Exception as e:
            print(f"Upload error: {e}")
            retry += 1
            if retry > 5:
                raise

    video_id = response['id']
    print(f"SUCCESS! ID: {video_id} → https://youtu.be/{video_id}")
    return video_id

# ─── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        print("Starting OpenCV + FFmpeg + eSpeak-ng generation & upload...")

        # Video
        is_story_video = random.random() > 0.4
        content_video = generate_story() if is_story_video else generate_rhyme()
        topic_video = generate_topic(content_video)

        img_url_v = fetch_random_image(topic_video, "horizontal")
        img_path_v = os.path.join(BG_IMAGES_DIR, "bg_video.jpg")
        download_image(img_url_v, img_path_v)

        video_path = create_video(content_video, img_path_v, is_short=False)

        title_video = f"मजेदार नई {'हिंदी कहानी' if is_story_video else 'राइम'} बच्चों के लिए | {topic_video} | 2026"
        desc_video = f"""नमस्ते छोटे दोस्तों! 😍 आज सुनिए बहुत प्यारी {'कहानी' if is_story_video else 'राइम'}!

{content_video[:150]}...

00:00 नमस्ते छोटे दोस्तों!
00:15 {'कहानी' if is_story_video else 'राइम'} शुरू
03:00 मजेदार अंत 🎉

पसंद आए तो लाइक 👍, सब्सक्राइब करें 🔔 और कमेंट में बताएं अगली बार कौन सी कहानी सुनना चाहते हो!

#HindiKahani #BacchonKiKahani #NurseryRhymes #HindiRhymes #KidsStories

Business/Collaboration: sinhalbarot05@gmail.com
"""
        tags_video = [
            "हिंदी कहानी", "बच्चों की कहानी", "नई हिंदी कहानी 2026", "मजेदार कहानी",
            "bacchon ki kahani", "hindi story for kids", "nursery rhymes hindi", "hindi rhymes",
            "kids stories hindi", "moral stories hindi"
        ] + [w for w in topic_video.split() if len(w) > 3][:5]

        upload_to_youtube(video_path, title_video, desc_video, tags_video, is_short=False)

        # Short
        is_story_short = random.random() > 0.5
        content_short = generate_story() if is_story_short else generate_rhyme()
        topic_short = generate_topic(content_short)

        img_url_s = fetch_random_image(topic_short, "vertical")
        img_path_s = os.path.join(BG_IMAGES_DIR, "bg_short.jpg")
        download_image(img_url_s, img_path_s)

        short_path = create_video(content_short, img_path_s, is_short=True)

        title_short = f"प्यारी {'कहानी' if is_story_short else 'राइम'} बच्चों के लिए #shorts | {topic_short}"
        desc_short = f"""नमस्ते दोस्तों! 😊 यहाँ है मजेदार {'कहानी' if is_story_short else 'राइम'}!

{content_short[:80]}...

पूरा वीडियो ऊपर देखो ↑
लाइक + सब्सक्राइब जरूर करें! ❤️

#Shorts #HindiRhymes #BacchonKiKahani"""

        tags_short = tags_video + ["shorts", "hindi shorts", "kids shorts"]

        upload_to_youtube(short_path, title_short, desc_short, tags_short, is_short=True)

        print("All done! Videos uploaded successfully.")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
