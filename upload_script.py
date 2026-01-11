import os
import random
import json
import sys
from pathlib import Path
from datetime import datetime

from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, TextClip
from moviepy.video.fx.all import resize
from pydub import AudioSegment
import requests

# Coqui XTTS-v2
from TTS.api import TTS
import torch

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

REFERENCE_VOICE = "reference_female.wav"  # Upload this 10–30s female Hindi WAV file to repo

CLIENT_SECRETS_FILE = "client_secret.json"
TOKEN_FILE = "youtube_token.pickle"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Load XTTS-v2 (downloads ~1.2–2GB on first run)
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading XTTS-v2 on {device}...")
tts = TTS(
    model_name="tts_models/multilingual/multi-dataset/xtts_v2",
    progress_bar=True
).to(device)

# ─── MEMORY FUNCTIONS (unchanged) ───────────────────────────────────────────────
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

# ─── CONTENT GENERATION (unchanged) ─────────────────────────────────────────────
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

# ─── IMAGE & AUDIO (XTTS-v2) ────────────────────────────────────────────────────
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
        
        # XTTS-v2 with voice cloning
        tts.tts_to_file(
            text=text,
            speaker_wav=REFERENCE_VOICE,   # Your female reference clip
            language="hi",
            file_path=temp_wav
        )
        
        audio = AudioSegment.from_wav(temp_wav)
        # Sweeten voice slightly (optional)
        audio = audio + 4  # volume boost
        audio.export(output_path, format="mp3")
        os.remove(temp_wav)
        
    except Exception as e:
        print(f"XTTS-v2 audio generation failed: {e}")
        sys.exit(1)

def create_video(content_text, bg_image_path, is_short=False):
    try:
        intro = "नमस्ते छोटे दोस्तों! 😍 आज फिर आई एक नई मजेदार "
        middle = "कहानी" if "कहानी" in content_text else "राइम"
        outro = "। बहुत पसंद आए तो लाइक करें, सब्सक्राइब करें और बेल आइकन दबाएं! 🔔"
        
        full_text = intro + middle + " है: " + content_text + outro
        
        audio_path = os.path.join(OUTPUT_DIR, "narration.mp3")
        create_audio(full_text, audio_path)

        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration

        bg_clip = ImageClip(bg_image_path).set_duration(duration)
        if is_short:
            bg_clip = bg_clip.resize(width=1080, height=1920)
        else:
            bg_clip = bg_clip.resize(width=1920, height=1080)

        bg_clip = bg_clip.fx(resize, lambda t: 1 + 0.015 * t)

        txt_clip = TextClip(
            content_text,
            fontsize=75 if is_short else 65,
            color='yellow',
            font='Noto-Sans-Devanagari',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(700 if is_short else 1100, None)
        ).set_position(('center', 'center')).set_duration(duration)

        final = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio_clip)

        prefix = 'short' if is_short else 'video'
        output_file = os.path.join(OUTPUT_DIR, f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        
        final.write_videofile(
            output_file,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            bitrate="8000k",
            preset='medium',
            threads=4,
            logger=None
        )

        return output_file

    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# ─── YOUTUBE UPLOAD (SEO optimized) ─────────────────────────────────────────────
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
        print("Starting XTTS-v2 generation & upload...")

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
