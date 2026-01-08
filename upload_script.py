import os
import json
import random
import hashlib
from gtts import gTTS
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    concatenate_videoclips,
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import requests

# ---------------- CONFIG ---------------- #

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

PIXABAY_KEY = os.environ.get("PIXABAY_KEY")

SHORT_MEM = "short_mem.json"
LONG_MEM = "long_mem.json"

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# ---------------- MEMORY ---------------- #

def load_memory(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return set(json.load(f))
    return set()

def save_memory(path, data):
    with open(path, "w") as f:
        json.dump(list(data), f)

# ---------------- TEXT GENERATOR (OFFLINE, UNIQUE) ---------------- #

NAMES = ["Chintu", "Pinku", "Guddu", "Munni", "Raju", "Gudiya"]
ANIMALS = ["Sher", "Haathi", "Bandar", "Billi", "Kutta", "Mor"]
MORALS = [
    "Sach bolna achha hota hai",
    "Mehnat ka phal milta hai",
    "Dosti sabse badi taakat hai",
    "Sabse pyaar se baat karo",
]

def unique_text(kind):
    mem_file = SHORT_MEM if kind == "short" else LONG_MEM
    memory = load_memory(mem_file)

    for _ in range(50):
        name = random.choice(NAMES)
        animal = random.choice(ANIMALS)
        moral = random.choice(MORALS)

        if kind == "short":
            text = f"{name} aur {animal} ki pyari si kahani.\n{moral}."
        else:
            text = (
                f"Ek baar ki baat hai, {name} naam ka ek bachcha tha.\n"
                f"Uska dost ek {animal} tha.\n"
                f"Dono ne milkar seekha ki {moral}.\n"
                f"Is kahani se humein ye seekh milti hai."
            )

        h = hashlib.sha256(text.encode()).hexdigest()
        if h not in memory:
            memory.add(h)
            save_memory(mem_file, memory)
            return text

    raise RuntimeError("Unique text exhausted")

# ---------------- VOICE (FREE, NO BILLING) ---------------- #

def make_voice(text, out):
    tts = gTTS(text=text, lang="hi", slow=False)
    tts.save(out)

# ---------------- IMAGE FETCH ---------------- #

def fetch_images(query, count):
    url = "https://pixabay.com/api/"
    r = requests.get(url, params={
        "key": PIXABAY_KEY,
        "q": query,
        "image_type": "illustration",
        "per_page": count,
        "safesearch": "true"
    })
    data = r.json()
    files = []

    for i, hit in enumerate(data.get("hits", [])):
        img = requests.get(hit["largeImageURL"]).content
        path = f"{IMAGE_DIR}/{query}_{i}.jpg"
        with open(path, "wb") as f:
            f.write(img)
        files.append(path)

    return files

# ---------------- VIDEO ---------------- #

def make_video(text, voice_file, out, duration_per_img=3):
    images = fetch_images("kids story illustration", 5)
    audio = AudioFileClip(voice_file)

    clips = [
        ImageClip(img).set_duration(duration_per_img)
        for img in images
    ]

    video = concatenate_videoclips(clips).set_audio(audio)
    video.write_videofile(out, fps=24)

# ---------------- YOUTUBE AUTH ---------------- #

def youtube_auth():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secret.json", SCOPES
        )
        creds = flow.run_console()
        with open("token.pickle", "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)

# ---------------- UPLOAD ---------------- #

def upload(video, title, desc):
    yt = youtube_auth()
    req = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": desc,
                "categoryId": "1",
            },
            "status": {"privacyStatus": "public"},
        },
        media_body=MediaFileUpload(video),
    )
    req.execute()

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    # SHORT
    short_text = unique_text("short")
    make_voice(short_text, "short.mp3")
    make_video(short_text, "short.mp3", "short.mp4")
    upload("short.mp4", "Hindi Kids Short Story", short_text)

    # LONG
    long_text = unique_text("long")
    make_voice(long_text, "long.mp3")
    make_video(long_text, "long.mp3", "long.mp4", 4)
    upload("long.mp4", "Hindi Kids Moral Story", long_text)

    print("✅ SUCCESS: Shorts and Long uploaded without repetition")
