import os
import time
import random
import json
import requests
from pathlib import Path
from gtts import gTTS
from PIL import Image

# Patch for Pillow 10+ (ANTIALIAS removed)
if not hasattr(Image, "ANTIALIAS") and hasattr(Image, "Resampling"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ======================================================
# CONFIG
# ======================================================
LANG = "hi"
THEMES = ["दोस्ती", "ईमानदारी", "प्रकृति", "परिवार", "सीख", "त्योहार"]
VIDEO_DIR = Path("videos")
VIDEO_DIR.mkdir(exist_ok=True)

PIXABAY_KEY = os.getenv("PIXABAY_KEY")
if not PIXABAY_KEY:
    raise RuntimeError("PIXABAY_KEY missing")

YOUTUBE_SECRETS = Path("client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# ======================================================
# OFFLINE STORY / RHYME GENERATOR
# ======================================================
used_memory = Path("memory.json")
if used_memory.exists():
    memory = json.loads(used_memory.read_text())
else:
    memory = {"stories": [], "rhyme": []}

def save_memory():
    used_memory.write_text(json.dumps(memory, ensure_ascii=False))

def generate_story():
    theme = random.choice(THEMES)
    story = f"एक समय की बात है, {theme} से जुड़ी एक मजेदार और सीखने वाली कहानी। बच्चों को यह सिखाती है कि सच्चाई और मेहनत हमेशा काम आती है।"
    # Avoid repetition
    while story in memory["stories"]:
        theme = random.choice(THEMES)
        story = f"एक समय की बात है, {theme} से जुड़ी एक मजेदार और सीखने वाली कहानी। बच्चों को यह सिखाती है कि सच्चाई और मेहनत हमेशा काम आती है।"
    memory["stories"].append(story)
    save_memory()
    return story, theme

def generate_rhyme():
    theme = random.choice(THEMES)
    rhyme = f"{theme} से सीखो, अच्छे बनो और हमेशा सच बोलो। यह बच्चों के लिए एक प्यारी राइम है।"
    # Avoid repetition
    while rhyme in memory["rhyme"]:
        theme = random.choice(THEMES)
        rhyme = f"{theme} से सीखो, अच्छे बनो और हमेशा सच बोलो। यह बच्चों के लिए एक प्यारी राइम है।"
    memory["rhyme"].append(rhyme)
    save_memory()
    return rhyme, theme

# ======================================================
# PIXABAY IMAGE FETCHER
# ======================================================
def fetch_image(query="kids cartoon"):
    resp = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": PIXABAY_KEY,
            "q": query,
            "image_type": "illustration",
            "orientation": "horizontal"
        },
        timeout=20
    ).json()
    if not resp.get("hits"):
        raise RuntimeError("No images found for query: " + query)
    img_url = resp["hits"][0]["largeImageURL"]
    img_path = VIDEO_DIR / f"{query.replace(' ','_')}.jpg"
    with open(img_path, "wb") as f:
        f.write(requests.get(img_url).content)
    return str(img_path)

# ======================================================
# VIDEO CREATION
# ======================================================
def make_video(text, out_path, duration=None, bg_image=None):
    audio_path = VIDEO_DIR / "audio.mp3"
    gTTS(text=text, lang="hi").save(audio_path)
    audio_clip = AudioFileClip(str(audio_path))

    if duration:
        audio_clip = audio_clip.subclip(0, duration)

    if not bg_image:
        bg_image = fetch_image("kids cartoon")

    clip_img = ImageClip(bg_image).set_duration(audio_clip.duration).resize(height=1080)
    clip = clip_img.set_audio(audio_clip)
    clip.write_videofile(str(out_path), fps=24, codec="libx264", audio_codec="aac")
    return out_path

# ======================================================
# THUMBNAIL CREATION
# ======================================================
def make_thumbnail(title, image_path):
    bg = ImageClip(image_path).resize((1280,720))
    txt_clip = TextClip(title, fontsize=60, color='white', font='DejaVu-Sans-Bold').set_position('center').set_duration(5)
    thumb = CompositeVideoClip([bg, txt_clip])
    thumb_path = str(VIDEO_DIR / "thumb.jpg")
    thumb.save_frame(thumb_path)
    return thumb_path

# ======================================================
# YOUTUBE CLIENT
# ======================================================
def youtube_client():
    flow = InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_SECRETS), SCOPES)
    creds = flow.run_local_server(port=0)
    return build("youtube", "v3", credentials=creds)

youtube = youtube_client()

# ======================================================
# UPLOAD FUNCTION
# ======================================================
def upload(path, title, description, tags=None, thumbnail=None, is_short=False):
    body = {
        "snippet": {
            "title": title + (" #Shorts" if is_short else ""),
            "description": description,
            "tags": tags or ["हिंदी कहानी", "kids hindi"],
            "defaultLanguage": "hi",
            "defaultAudioLanguage": "hi",
            "categoryId": "24"
        },
        "status": {"privacyStatus": "public"}
    }

    media = MediaFileUpload(str(path), resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    for i in range(5):
        try:
            response = request.execute()
            break
        except HttpError as e:
            print("Upload failed, retrying...", i, e)
            time.sleep(2 ** i)
    if thumbnail and response:
        youtube.thumbnails().set(videoId=response['id'], media_body=MediaFileUpload(thumbnail)).execute()
    print(f"Uploaded: {path}")

# ======================================================
# MAIN
# ======================================================
if __name__ == "__main__":
    # Generate unique story + rhyme
    story_text, story_theme = generate_story()
    rhyme_text, rhyme_theme = generate_rhyme()

    # Fetch images
    story_bg = fetch_image(story_theme)
    rhyme_bg = fetch_image(rhyme_theme)

    # Make videos
    long_video_path = make_video(story_text, VIDEO_DIR / "long.mp4", bg_image=story_bg)
    short_video_path = make_video(rhyme_text, VIDEO_DIR / "short.mp4", duration=60, bg_image=rhyme_bg)

    # Make thumbnails
    long_thumb = make_thumbnail("नई हिंदी बच्चों की कहानी / New Hindi Kids Story", story_bg)
    short_thumb = make_thumbnail("मजेदार हिंदी राइम / Majedar Hindi Rhymes", rhyme_bg)

    # Upload
    upload(long_video_path, "नई हिंदी बच्चों की कहानी / New Hindi Kids Story", story_text, thumbnail=long_thumb)
    upload(short_video_path, "मजेदार हिंदी राइम / Majedar Hindi Rhymes", rhyme_text, thumbnail=short_thumb, is_short=True)
