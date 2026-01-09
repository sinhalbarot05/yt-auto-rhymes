import os
import random
import json
from pathlib import Path
from moviepy.editor import (
    ImageClip, AudioFileClip, concatenate_videoclips,
    CompositeVideoClip, TextClip
)
from gtts import gTTS
from pydub import AudioSegment
import requests
from datetime import datetime
import sys

# -----------------------------
# Configuration
# -----------------------------
MEMORY_FILE = "memory.json"
BG_IMAGES = "images/"
OUTPUT_DIR = "videos/"
Path(OUTPUT_DIR).mkdir(exist_ok=True)
Path(BG_IMAGES).mkdir(exist_ok=True)
# Load memory of used stories, rhymes, and images
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        MEMORY = json.load(f)
else:
    MEMORY = {"stories": [], "rhymes": [], "images": []}
# -----------------------------
# Helpers
# -----------------------------
def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(MEMORY, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving memory: {e}")
        sys.exit(1)

def generate_story_rhyme():
    # Offline AI-like generation of a unique story + rhyme
    stories = [
        "एक छोटा खरगोश था जो जादुई जंगल में खो गया।",
        "सूरज और चाँद की दोस्ती के बारे में एक कहानी।",
        "बच्चों के लिए खेल-खेल में सीखने की मज़ेदार कहानी।",
        "एक नन्हा तोता जो गाना सीख रहा था।",
        "आओ जानें रंगों की कहानी, बच्चों के लिए मज़ेदार।"
    ]
    rhymes = [
        "छोटी-छोटी बातें, बड़ी-सी सीख।",
        "खेलो, पढ़ो, हँसो, और मुस्कुराओ।",
        "सपनों में उड़ो, खुशियों में खो जाओ।",
        "सूरज की किरणें, चाँद की रोशनी।",
        "प्यारे दोस्त, सुनो ये मज़ेदार कहानी।"
    ]
    # Ensure uniqueness
    available_stories = [s for s in stories if s not in MEMORY["stories"]]
    available_rhymes = [r for r in rhymes if r not in MEMORY["rhymes"]]
    if not available_stories:
        print("No unique stories left.")
        sys.exit(1)
    if not available_rhymes:
        print("No unique rhymes left.")
        sys.exit(1)
    story = random.choice(available_stories)
    rhyme = random.choice(available_rhymes)
    MEMORY["stories"].append(story)
    MEMORY["rhymes"].append(rhyme)
    save_memory()
    return story, rhyme

def fetch_random_image():
    try:
        # Pixabay API for random images (kids safe)
        query = "kids story illustration"
        url = f"https://pixabay.com/api/?key={os.getenv('PIXABAY_KEY')}&q={query}&image_type=photo&orientation=horizontal&per_page=50"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        hits = data.get("hits", [])
        for h in hits:
            img_url = h["largeImageURL"]
            if img_url not in MEMORY["images"]:
                MEMORY["images"].append(img_url)
                save_memory()
                return img_url
        print("No new images found.")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Error fetching image from Pixabay: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error in fetch_random_image: {e}")
        sys.exit(1)
    return None

def download_image(url, filename):
    try:
        r = requests.get(url)
        r.raise_for_status()
        with open(filename, "wb") as f:
            f.write(r.content)
    except requests.RequestException as e:
        print(f"Error downloading image: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error in download_image: {e}")
        sys.exit(1)

def make_audio(text, filename, lang="hi"):
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(filename)
        # Ensure compatibility
        audio = AudioSegment.from_file(filename)
        audio.export(filename, format="mp3")
    except Exception as e:
        print(f"Error creating audio: {e}")
        sys.exit(1)

def make_video(story_text, rhyme_text, duration=60, bg_image=None):
    try:
        # Background image
        clip_img = ImageClip(bg_image).set_duration(duration).resize(height=1080)
        # Audio
        audio_path = os.path.join(OUTPUT_DIR, "audio.mp3")
        make_audio(f"{story_text} {rhyme_text}", audio_path)
        audio_clip = AudioFileClip(audio_path)
        # Text overlay
        txt_clip = TextClip(rhyme_text, fontsize=70, color="yellow", font="Noto-Sans-Devanagari").set_position("center").set_duration(audio_clip.duration)
        video = CompositeVideoClip([clip_img, txt_clip]).set_audio(audio_clip)
        out_path = os.path.join(OUTPUT_DIR, f"video_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4")
        video.write_videofile(out_path, fps=24)
        return out_path
    except Exception as e:
        print(f"Error creating video: {e}")
        sys.exit(1)

# -----------------------------
# Main Execution
# -----------------------------
if __name__ == "__main__":
    try:
        story, rhyme = generate_story_rhyme()
        img_url = fetch_random_image()
        if img_url is None:
            print("Failed to fetch image URL.")
            sys.exit(1)
        img_path = os.path.join(BG_IMAGES, "bg.jpg")
        download_image(img_url, img_path)
        video_path = make_video(story, rhyme, duration=60, bg_image=img_path)
        print(f"✅ SUCCESS: Video created at {video_path}")
    except Exception as e:
        print(f"Unexpected error in main execution: {e}")
        sys.exit(1)
