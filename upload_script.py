import os
import json
import time
import random
import requests
from pathlib import Path

from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ======================================================
# CONFIG
# ======================================================
LANG = "hi"
THEMES = ["दोस्ती", "ईमानदारी", "प्रकृति", "परिवार", "सीख", "त्योहार"]
PIXABAY_KEY = os.getenv("PIXABAY_KEY")
if not PIXABAY_KEY:
    raise RuntimeError("PIXABAY_KEY missing")

VIDEO_DIR = Path("videos")
VIDEO_DIR.mkdir(exist_ok=True)

# ======================================================
# OFFLINE STORY/RHYME GENERATOR
# ======================================================
USED_STORIES_FILE = Path("memory_used_stories.json")
if USED_STORIES_FILE.exists():
    with open(USED_STORIES_FILE, "r", encoding="utf-8") as f:
        USED_STORIES = json.load(f)
else:
    USED_STORIES = {"story": [], "rhyme": []}

def save_used():
    with open(USED_STORIES_FILE, "w", encoding="utf-8") as f:
        json.dump(USED_STORIES, f, ensure_ascii=False, indent=2)

def generate_story():
    """Generate a unique story (offline, random)."""
    while True:
        theme = random.choice(THEMES)
        story = f"एक बार की बात है, {theme} से जुड़ी यह मजेदार कहानी बच्चों को सिखाती है कि सच्चाई और मेहनत हमेशा काम आती है।"
        if story not in USED_STORIES["story"]:
            USED_STORIES["story"].append(story)
            save_used()
            return story

def generate_rhyme():
    """Generate a unique 1-min rhyme (offline, random)."""
    while True:
        theme = random.choice(THEMES)
        rhyme = f"{theme} से सीखो, अच्छे बनो, हमेशा सच बोलो, खुशी से खेलो और हंसते रहो।"
        if rhyme not in USED_STORIES["rhyme"]:
            USED_STORIES["rhyme"].append(rhyme)
            save_used()
            return rhyme

# ======================================================
# IMAGE FETCHER
# ======================================================
def fetch_image(query="kids cartoon illustration"):
    resp = requests.get(
        "https://pixabay.com/api/",
        params={"key": PIXABAY_KEY, "q": query, "image_type": "illustration"},
        timeout=20
    ).json()
    if resp.get("hits"):
        return resp["hits"][0]["largeImageURL"]
    else:
        raise RuntimeError("No Pixabay image found for query: " + query)

def download_image(url, filename):
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)

# ======================================================
# VIDEO CREATION
# ======================================================
def make_video(text, out_path, duration=60, bg_image=None):
    # Voice generation
    gTTS(text=text, lang=LANG).save("audio.mp3")
    audio_clip = AudioFileClip("audio.mp3")

    # Image
    if not bg_image:
        bg_image = "bg.jpg"
    clip_img = ImageClip(bg_image).set_duration(audio_clip.duration).resize(height=1080)
    
    # Optional: Add title text on top
    title_clip = TextClip(text, fontsize=60, color="white", bg_color="purple", size=(clip_img.w, 150))
    title_clip = title_clip.set_position(("center", "top")).set_duration(audio_clip.duration)

    video = CompositeVideoClip([clip_img, title_clip]).set_audio(audio_clip)
    video.write_videofile(out_path, fps=24, codec="libx264", audio_codec="aac")

# ======================================================
# YOUTUBE UPLOAD CLIENT
# ======================================================
def youtube_client():
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    if not Path("token.json").exists():
        raise RuntimeError("token.json missing! Generate locally and save as secret.")
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def upload_video(path, title, description, is_short=False):
    yt = youtube_client()
    body = {
        "snippet": {
            "title": title + (" #Shorts" if is_short else ""),
            "description": description,
            "tags": ["हिंदी कहानी", "kids hindi", "hindi rhymes"],
            "defaultLanguage": "hi",
            "defaultAudioLanguage": "hi",
            "categoryId": "24"
        },
        "status": {"privacyStatus": "public"}
    }
    for i in range(5):
        try:
            yt.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(path, resumable=True)
            ).execute()
            print(f"Uploaded {path}")
            return
        except Exception as e:
            print(f"Upload attempt {i+1} failed: {e}")
            time.sleep(2 ** i)
    raise RuntimeError("Upload failed")

# ======================================================
# THUMBNAIL CREATION
# ======================================================
def make_thumbnail(text, filename="thumbnail.jpg"):
    img_url = fetch_image("kids story illustration")
    download_image(img_url, "thumb_bg.jpg")
    bg_clip = ImageClip("thumb_bg.jpg").resize((1280, 720))
    title_clip = TextClip(text, fontsize=70, color="yellow", bg_color="purple", size=(bg_clip.w, 150))
    title_clip = title_clip.set_position("center")
    thumb = CompositeVideoClip([bg_clip, title_clip])
    thumb.save_frame(filename)

# ======================================================
# MAIN EXECUTION
# ======================================================
if __name__ == "__main__":
    # 1-minute short
    rhyme_text = generate_rhyme()
    short_bg = fetch_image("kids cartoon playful")
    download_image(short_bg, "bg_short.jpg")
    short_path = VIDEO_DIR / "short.mp4"
    make_video(rhyme_text, str(short_path), duration=60, bg_image="bg_short.jpg")
    upload_video(str(short_path), "मज़ेदार हिंदी राइम / Majedar Hindi Rhymes", rhyme_text, is_short=True)

    # 4-5 minute long story
    story_text = generate_story()
    long_bg = fetch_image("kids story illustration")
    download_image(long_bg, "bg_long.jpg")
    long_path = VIDEO_DIR / "long.mp4"
    make_video(story_text, str(long_path), duration=300, bg_image="bg_long.jpg")
    make_thumbnail(story_text, "thumbnail_long.jpg")
    upload_video(str(long_path), "नई हिंदी बच्चों की कहानी / New Hindi Kids Story", story_text, is_short=False)
