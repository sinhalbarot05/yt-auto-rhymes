# upload_script.py

import os
import random
import json
import sys
from pathlib import Path
from datetime import datetime

from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeVideoClip, TextClip
)
from gtts import gTTS
from pydub import AudioSegment

import requests

# ─── YouTube Upload ─────────────────────────────────────────────────────────────
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pickle

# ─── CONFIGURATION ──────────────────────────────────────────────────────────────
MEMORY_FILE = "memory.json"
BG_IMAGES_DIR = "images/"
OUTPUT_DIR = "videos/"
Path(OUTPUT_DIR).mkdir(exist_ok=True)
Path(BG_IMAGES_DIR).mkdir(exist_ok=True)

CLIENT_SECRETS_FILE = "client_secret.json"
TOKEN_FILE = "youtube_token.pickle"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Load or initialize memory
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        MEMORY = json.load(f)
else:
    MEMORY = {"stories": [], "rhymes": [], "images": []}

def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(MEMORY, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save memory: {e}")

# ─── CONTENT GENERATION ─────────────────────────────────────────────────────────
def generate_story_rhyme():
    stories = [
        "एक छोटा खरगोश था जो जादुई जंगल में खो गया।",
        "सूरज और चाँद की दोस्ती की मधुर कहानी।",
        "नन्हा तोता जो नया गाना सीख रहा था।",
        "रंगों की दुनिया में एक मजेदार सफर।",
        "छोटी मछली और बड़ा समंदर की कहानी।"
    ]
    rhymes = [
        "छोटी-छोटी बातें, बड़ी-बड़ी सीख।",
        "हँसो, खेलो, और मुस्कुराओ यार।",
        "सपनों की उड़ान, खुशियों का संसार।",
        "सूरज की किरण, चाँद की चाँदनी।",
        "दोस्ती का रंग, प्यार का संगीत।"
    ]

    avail_stories = [s for s in stories if s not in MEMORY["stories"]]
    avail_rhymes = [r for r in rhymes if r not in MEMORY["rhymes"]]

    if not avail_stories or not avail_rhymes:
        print("No more unique content left!")
        sys.exit(1)

    story = random.choice(avail_stories)
    rhyme = random.choice(avail_rhymes)

    MEMORY["stories"].append(story)
    MEMORY["rhymes"].append(rhyme)
    save_memory()

    return story, rhyme

def fetch_random_image():
    query = "cute kids story illustration cartoon"
    url = f"https://pixabay.com/api/?key={os.getenv('PIXABAY_KEY')}&q={query}&image_type=illustration&orientation=horizontal&per_page=30&safesearch=true"

    try:
        resp = requests.get(url).json()
        hits = resp.get("hits", [])
        for hit in hits:
            img_url = hit.get("largeImageURL")
            if img_url and img_url not in MEMORY["images"]:
                MEMORY["images"].append(img_url)
                save_memory()
                return img_url
        print("No suitable new image found.")
        sys.exit(1)
    except Exception as e:
        print(f"Pixabay error: {e}")
        sys.exit(1)

def download_image(url, path):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Image download failed: {e}")
        sys.exit(1)

def create_audio(text, output_path, lang="hi"):
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        temp_mp3 = "temp_audio.mp3"
        tts.save(temp_mp3)

        audio = AudioSegment.from_mp3(temp_mp3)
        audio.export(output_path, format="mp3")
        os.remove(temp_mp3)
    except Exception as e:
        print(f"Audio creation failed: {e}")
        sys.exit(1)

def create_video(story, rhyme, bg_image_path, duration=65):
    try:
        # Background
        bg_clip = ImageClip(bg_image_path).set_duration(duration).resize(height=1080)

        # Audio
        audio_path = os.path.join(OUTPUT_DIR, "narration.mp3")
        full_text = f"{story} ... अब सुनो ये प्यारा राइम: {rhyme}"
        create_audio(full_text, audio_path)

        audio_clip = AudioFileClip(audio_path)

        # Text overlay (rhyme only)
        txt_clip = TextClip(
            rhyme,
            fontsize=65,
            color='yellow',
            font='Noto-Sans-Devanagari',
            stroke_color='black',
            stroke_width=2.5,
            method='caption',
            size=(900, None)
        ).set_position(('center', 'center')).set_duration(audio_clip.duration)

        # Final video
        final = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio_clip)

        output_file = os.path.join(OUTPUT_DIR, f"kids_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        final.write_videofile(output_file, fps=24, codec='libx264', audio_codec='aac', threads=2)

        return output_file

    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# ─── YOUTUBE UPLOAD ─────────────────────────────────────────────────────────────
def get_authenticated_service():
    creds = None

    # Try to load existing token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token_file:
            creds = pickle.load(token_file)

    # If no/invalid credentials → refresh or new flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print("client_secret.json not found!")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)  # ← This needs browser → first run locally!

        # Save updated credentials
        with open(TOKEN_FILE, 'wb') as token_file:
            pickle.dump(creds, token_file)

    return build('youtube', 'v3', credentials=creds)

def upload_to_youtube(video_file, title, description):
    youtube = get_authenticated_service()

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['hindi', 'kids', 'rhymes', 'storytime', 'bacchon ki kahani', 'hindi rhymes'],
            'categoryId': '24'  # Entertainment
        },
        'status': {
            'privacyStatus': 'private'   # Change to 'public' / 'unlisted' when ready
        }
    }

    media = MediaFileUpload(
        video_file,
        mimetype='video/mp4',
        resumable=True
    )

    print("Starting YouTube upload...")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    error = None
    retry = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        except Exception as e:
            print(f"Upload chunk error: {e}")
            error = e
            retry += 1
            if retry > 5:
                raise Exception("Upload failed after multiple retries")

    if response:
        video_id = response['id']
        print(f"Upload SUCCESSFUL!")
        print(f"Video ID: {video_id}")
        print(f"Link: https://youtu.be/{video_id}")
        return video_id
    else:
        raise Exception("Upload failed - no response from YouTube")

# ─── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        print("Starting Hindi Kids Video Generator & Uploader...")

        story, rhyme = generate_story_rhyme()
        print(f"Story: {story}")
        print(f"Rhyme: {rhyme}")

        img_url = fetch_random_image()
        img_path = os.path.join(BG_IMAGES_DIR, "bg.jpg")
        download_image(img_url, img_path)

        video_path = create_video(story, rhyme, img_path)

        print(f"Video successfully created → {video_path}")

        # ── Upload ───────────────────────────────────────────────────────────────
        title = f"मजेदार हिंदी कहानी + राइम | {rhyme[:40]}... | Kids Story Time"
        description = f"""नन्हे बच्चों के लिए एक प्यारी कहानी और मजेदार राइम!
Story: {story}
Rhyme: {rhyme}

#HindiRhymes #KidsStories #BacchonKiKahani #HindiStory #NurseryRhymes"""

        upload_to_youtube(video_path, title, description)

        print("Job completed successfully!")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
