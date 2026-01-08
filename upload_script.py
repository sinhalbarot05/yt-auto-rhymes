import os
import json
import random
import requests
import datetime
import hashlib
import base64
import subprocess
import time

from gtts import gTTS
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ======================================================
# CONFIG
# ======================================================
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
PIXABAY_KEY = os.getenv("PIXABAY_KEY")
SA_KEY_B64 = os.getenv("GCP_SA_KEY_B64")

MEMORY_DIR = "memory"
USED_STORIES = os.path.join(MEMORY_DIR, "used_stories.json")
USED_RHYMES = os.path.join(MEMORY_DIR, "used_rhymes.json")
USED_TOPICS = os.path.join(MEMORY_DIR, "used_topics.json")
USED_IMAGES = os.path.join(MEMORY_DIR, "used_images.json")

# ======================================================
# HELPER: Load / Save Memory
# ======================================================
def load_json(path):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump([], f)
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Load memories
stories_mem = load_json(USED_STORIES)
rhymes_mem = load_json(USED_RHYMES)
topics_mem = load_json(USED_TOPICS)
images_mem = load_json(USED_IMAGES)

# ======================================================
# FESTIVAL CHECK
# ======================================================
FESTIVALS = {
    "Holi": (3, 14),
    "Diwali": (11, 1),
    "Raksha Bandhan": (8, 19),
    "Janmashtami": (8, 26),
}

def upcoming_festival():
    today = datetime.date.today()
    for name, (m, d) in FESTIVALS.items():
        f = datetime.date(today.year, m, d)
        if 0 <= (f - today).days <= 2:
            return name
    return None

# ======================================================
# VERTEX GEMINI SETUP
# ======================================================
sa_info = json.loads(base64.b64decode(SA_KEY_B64))
credentials = service_account.Credentials.from_service_account_info(sa_info)
scoped_creds = credentials.with_scopes(["https://www.googleapis.com/auth/cloud-platform"])

def vertex_gemini_generate(prompt):
    """Generate unique content via Vertex AI Gemini"""
    from google.cloud import aiplatform
    aiplatform.init(project=PROJECT_ID, credentials=scoped_creds, location="us-central1")
    model = aiplatform.TextGenerationModel.from_pretrained("text-bison@001")
    
    # Retry loop for safety
    for _ in range(3):
        try:
            response = model.predict(
                prompt,
                max_output_tokens=512,
                temperature=0.7
            )
            return response.text
        except Exception as e:
            time.sleep(2)
    raise RuntimeError("Vertex AI Gemini generation failed")

# ======================================================
# IMAGE FETCHING (Pixabay, unique)
# ======================================================
def fetch_images(prompt, count=5):
    images = []
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_KEY,
                "q": prompt,
                "image_type": "illustration",
                "safesearch": "true",
                "per_page": count
            },
            timeout=20
        ).json()
        hits = resp.get("hits", [])
        for h in hits:
            img_id = str(h["id"])
            if img_id in images_mem:
                continue
            path = f"img_{img_id}.jpg"
            with open(path, "wb") as f:
                f.write(requests.get(h["largeImageURL"]).content)
            images_mem.append(img_id)
            images.append(path)
            if len(images) >= count:
                break
    except Exception:
        # fallback single color image
        fallback = "fallback.jpg"
        if not os.path.exists(fallback):
            ImageClip((1280,720), color=(255,200,200)).save_frame(fallback)
        images = [fallback]*count
    return images

# ======================================================
# TTS with gTTS (Hindi, child-friendly)
# ======================================================
def tts(text, filename):
    # Split long text into sentences
    sentences = [s.strip() for s in text.replace("\n"," ").split(".") if s.strip()]
    audio_files = []
    for i, s in enumerate(sentences):
        f = f"tts_{i}.mp3"
        gTTS(text=s, lang="hi", slow=False).save(f)
        audio_files.append(f)
    # Concatenate
    clips = [AudioFileClip(f) for f in audio_files]
    final = concatenate_videoclips(clips, method="compose").audio
    final.write_audiofile(filename)
    for f in audio_files:
        os.remove(f)

# ======================================================
# VIDEO CREATION
# ======================================================
def make_video(images, audio_path, height, out):
    audio = AudioFileClip(audio_path)
    per = audio.duration / len(images)
    clips = [ImageClip(img).with_duration(per).resized(height=height) for img in images]
    concatenate_videoclips(clips, method="compose").with_audio(audio).write_videofile(out, fps=24)

# ======================================================
# THUMBNAIL (simplest, just first image)
# ======================================================
def make_thumbnail(img):
    ImageClip(img).resized((1280,720)).save_frame("thumbnail.jpg")

# ======================================================
# YOUTUBE UPLOAD
# ======================================================
# Load token.json in repo manually
from google.oauth2.credentials import Credentials
creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/youtube.upload"])
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
yt = build("youtube", "v3", credentials=creds)

def upload(path, title, desc, tags, thumb=None):
    res = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": desc,
                "tags": tags,
                "categoryId": "24",
                "defaultLanguage":"hi",
                "defaultAudioLanguage":"hi"
            },
            "status": {"privacyStatus":"public"}
        },
        media_body=MediaFileUpload(path)
    ).execute()
    if thumb:
        yt.thumbnails().set(videoId=res["id"], media_body=MediaFileUpload(thumb)).execute()

# ======================================================
# GENERATE NON-REPEATING CONTENT
# ======================================================
def generate_unique_story():
    festival = upcoming_festival()
    prompt = f"Generate a unique, fun Hindi kids story. Festival: {festival}. Do NOT repeat any previous story or topic: {stories_mem}."
    story = vertex_gemini_generate(prompt)
    # hash check
    h = hashlib.sha256(story.encode()).hexdigest()
    if h in stories_mem:
        return generate_unique_story()  # retry
    stories_mem.append(h)
    save_json(USED_STORIES, stories_mem)
    return story

def generate_unique_rhyme():
    festival = upcoming_festival()
    prompt = f"Generate a unique Hindi kids rhyme ≤60 seconds. Festival: {festival}. Do NOT repeat any previous rhyme or topic: {rhymes_mem}."
    rhyme = vertex_gemini_generate(prompt)
    h = hashlib.sha256(rhyme.encode()).hexdigest()
    if h in rhymes_mem:
        return generate_unique_rhyme()
    rhymes_mem.append(h)
    save_json(USED_RHYMES, rhymes_mem)
    return rhyme

# ======================================================
# RUN PIPELINE
# ======================================================
# --- SHORT / Reel ---
short_text = generate_unique_rhyme()
tts(short_text, "short.mp3")
short_imgs = fetch_images("kids rhyme colorful illustration")
make_video(short_imgs, "short.mp3", 1920, "short.mp4")
upload(
    "short.mp4",
    "मजेदार हिंदी राइम | Majedar Hindi Rhymes #Shorts",
    short_text,
    ["hindi rhymes","kids shorts","nursery rhyme"]
)

# --- LONG Video ---
long_text = generate_unique_story()
tts(long_text, "long.mp3")
long_imgs = fetch_images("kids story colorful illustration")
make_video(long_imgs, "long.mp3", 1080, "long.mp4")
make_thumbnail(long_imgs[0])
upload(
    "long.mp4",
    "नई हिंदी बच्चों की कहानी | New Hindi Kids Story",
    long_text,
    ["hindi kids story","moral story","bedtime story"],
    "thumbnail.jpg"
)
