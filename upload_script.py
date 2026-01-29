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
from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment
import requests
from piper.voice import PiperVoice
import wave

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

# Force espeak-ng data path (helps with Hindi phonemization)
os.environ["ESPEAK_DATA_PATH"] = "/usr/share/espeak-ng-data"

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
BG_IMAGES_DIR = "images/"
TOKEN_FILE = "youtube_token.pickle"

for d in [MEMORY_DIR, OUTPUT_DIR, BG_IMAGES_DIR]:
    Path(d).mkdir(exist_ok=True)

# Piper TTS - load from local downloaded files
MODEL_DIR = "piper-voices/hi_IN-pratham-medium"
MODEL_PATH = os.path.join(MODEL_DIR, "hi_IN-pratham-medium.onnx")

piper_voice = None

def load_piper_voice():
    global piper_voice
    if piper_voice is None:
        if not os.path.exists(MODEL_PATH):
            print(f"Critical: Model file not found at {MODEL_PATH}")
            sys.exit(1)
        print(f"Loading local Piper model: {MODEL_PATH}")
        piper_voice = PiperVoice.load(MODEL_PATH)
    return piper_voice

# MEMORY
def load_used(f):
    p = os.path.join(MEMORY_DIR, f)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []

def save_used(f, data):
    try:
        json.dump(data, open(os.path.join(MEMORY_DIR, f), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Memory save failed for {f}: {e}")

used_stories = load_used("used_stories.json")
used_rhymes = load_used("used_rhymes.json")
used_images = load_used("used_images.json")
used_topics = load_used("used_topics.json")

# CONTENT GENERATION
animals = ["खरगोश", "तोता", "मछली", "हाथी", "शेर", "लोमड़ी", "गिलहरी"]
places = ["जंगल", "समंदर", "पहाड़", "नदी", "गाँव", "खेत"]
actions = ["खो गया", "सीखा", "मिला", "खेला", "डर गया"]
adventures = ["दोस्त बनाए", "जादू सीखा", "खजाना पाया", "साहस दिखाया"]
endings = ["घर लौट आया", "खुश रहा", "समझदार हो गया", "सबके हीरो बन गया"]
lessons = ["दोस्ती", "साहस", "मेहनत", "प्यार", "ईमानदारी"]

def gen_story():
    global used_stories
    while True:
        s = f"एक छोटा {random.choice(animals)} {random.choice(places)} में {random.choice(actions)}। " \
            f"वहाँ उसने {random.choice(adventures)}। अंत में {random.choice(endings)}। " \
            f"{random.choice(lessons)} की सीख मिली।"
        if s not in used_stories:
            used_stories.append(s)
            save_used("used_stories.json", used_stories)
            return s

def gen_rhyme():
    global used_rhymes
    while True:
        r = random.choice([
            "छोटी-छोटी बातें, बड़ी सीख लाती हैं\nखेलो, हँसो, मुस्कुराओ यारों\nसपनों को पकड़ो, उड़ो ऊँचा आसमान\nप्यार बाँटो, जीवन को सुंदर बनाओ",
            "सूरज की किरण, चाँदनी रात\nहर पल में छुपा है जादू साथ\nदोस्तों संग हँसी-खुशी का मेला\nजीवन है एक अनमोल खेला",
            "पढ़ाई करो, खेलो भी साथ\nदोनों से मिलेगी जीवन की बात\nमेहनत करो, हार मत मानो\nसपने पूरे करो, आगे बढ़ो यारो"
        ])
        if r not in used_rhymes:
            used_rhymes.append(r)
            save_used("used_rhymes.json", used_rhymes)
            return r

def gen_topic(txt):
    global used_topics
    t = " ".join(txt.split()[:5])
    while t in used_topics:
        t += f" {random.choice(['की कहानी','की मस्ती','का मजा','नई वाली'])}"
    used_topics.append(t)
    save_used("used_topics.json", used_topics)
    return t

# IMAGE
def get_image(topic, orient="horizontal"):
    q = f"cute hindi kids cartoon {topic} illustration"
    u = f"https://pixabay.com/api/?key={os.getenv('PIXABAY_KEY')}&q={q}&image_type=illustration&orientation={orient}&per_page=12&safesearch=true"
    try:
        hits = requests.get(u, timeout=20).json().get("hits", [])
        random.shuffle(hits)
        for img in hits:
            url = img.get("largeImageURL")
            if url and url not in used_images:
                used_images.append(url)
                save_used("used_images.json", used_images)
                return url
        print("No suitable image found from Pixabay")
        sys.exit(1)
    except Exception as e:
        print(f"Pixabay API error: {e}")
        sys.exit(1)

def dl_image(url, path):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Image download failed: {e}")
        sys.exit(1)

# AUDIO - Piper TTS with debug and fallback test
def make_audio(txt, out_mp3):
    try:
        voice = load_piper_voice()

        print(f"Input text length: {len(txt)} chars")
        print(f"Sample text preview: {txt[:100]}...")

        temp_wav = os.path.join(OUTPUT_DIR, "temp_piper.wav")

        wav_file = wave.open(temp_wav, 'wb')
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)

        print("Calling synthesize...")
        voice.synthesize(txt, wav_file)

        wav_file.close()

        wav_size = os.path.getsize(temp_wav)
        print(f"Raw WAV size after synthesize: {wav_size} bytes")

        if wav_size < 1000:
            print("ERROR: Synthesized WAV is empty or too small → synthesis produced no audio")
            
            # Quick test with very simple Hindi
            test_txt = "नमस्ते छोटे दोस्तों यह एक छोटा परीक्षण है"
            print(f"Running simple Hindi test: '{test_txt}'")
            test_wav = os.path.join(OUTPUT_DIR, "test_fallback.wav")
            test_file = wave.open(test_wav, 'wb')
            test_file.setnchannels(1)
            test_file.setsampwidth(2)
            test_file.setframerate(voice.config.sample_rate)
            voice.synthesize(test_txt, test_file)
            test_file.close()
            
            test_size = os.path.getsize(test_wav)
            print(f"Test WAV size: {test_size} bytes")
            
            if test_size > 1000:
                print("Test succeeded → problem is likely with the long/complex full_text")
            else:
                print("Test also failed → phonemizer or model issue in this environment")
            
            if os.path.exists(test_wav):
                os.remove(test_wav)
            sys.exit(1)

        audio = AudioSegment.from_wav(temp_wav)
        print(f"Audio duration loaded: {len(audio)/1000:.2f} seconds")

        audio = audio.normalize()
        audio = audio + 12

        audio.export(
            out_mp3,
            format="mp3",
            bitrate="192k",
            parameters=["-write_xing", "0"]
        )

        mp3_size = os.path.getsize(out_mp3)
        print(f"Exported MP3 size: {mp3_size} bytes")

        if mp3_size < 10000:
            print("ERROR: Final MP3 too small")
            sys.exit(1)

        os.remove(temp_wav)
        print(f"Audio created successfully: {out_mp3}")

    except Exception as e:
        print(f"Audio generation failed: {e}")
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        sys.exit(1)

# VIDEO
def make_video(txt, bg_path, short=False):
    try:
        img = cv2.imread(bg_path)
        if img is None:
            raise ValueError("Background image load failed")

        size = (1080, 1920) if short else (1920, 1080)
        img = cv2.resize(img, size)

        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", 80 if short else 70)
        except:
            font = ImageFont.load_default()

        lines = txt.split('\n')
        y, dy = 420 if short else 320, 110
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (size[0] - text_w) // 2
            draw.text((x, y), line, font=font, fill=(255, 255, 80))
            y += dy

        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        frames = []
        n_frames = 1500
        for i in range(n_frames):
            s = 1 + 0.012 * (i / n_frames)
            h, w = img.shape[:2]
            nh, nw = int(h * s), int(w * s)
            zoomed = cv2.resize(img, (nw, nh))
            crop = zoomed[(nh-h)//2:(nh-h)//2+h, (nw-w)//2:(nw-w)//2+w]
            frames.append(crop)

        tmp_vid = os.path.join(OUTPUT_DIR, "tmp.mp4")
        out = cv2.VideoWriter(tmp_vid, cv2.VideoWriter_fourcc(*'mp4v'), 24, size)
        for f in frames:
            out.write(f)
        out.release()

        intro = "नमस्ते प्यारे बच्चों! आज फिर लाए हैं एकदम नई "
        mid = "कहानी" if "सीख" in txt or "कहानी" in txt else "राइम"
        outro = "। बहुत पसंद आए तो लाइक, शेयर और सब्सक्राइब जरूर करना। बेल आइकन भी दबा दो!"
        full_text = intro + mid + " है:\n\n" + txt + "\n\n" + outro

        aud_path = os.path.join(OUTPUT_DIR, "aud.mp3")
        make_audio(full_text, aud_path)

        final_name = f"{'short' if short else 'video'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        final_path = os.path.join(OUTPUT_DIR, final_name)

        print("Starting ffmpeg merge...")
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", tmp_vid,
            "-i", aud_path,
            "-c:v", "libx264", "-preset", "slow", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            final_path
        ], check=True, capture_output=True, text=True)

        print("ffmpeg stdout:", result.stdout)
        print("ffmpeg stderr:", result.stderr)

        os.remove(tmp_vid)
        os.remove(aud_path)

        return final_path

    except subprocess.CalledProcessError as e:
        print("ffmpeg merge failed with code", e.returncode)
        print("ffmpeg stdout:", e.stdout)
        print("ffmpeg stderr:", e.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# YOUTUBE (unchanged)
def yt_service():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            creds = Credentials(**token_data)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(vars(creds), f, indent=2)
        if not creds or not creds.valid:
            print("No valid credentials.")
            sys.exit(1)
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        print(f"Credential error: {e}")
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
            print(f"Upload SUCCESS! {'Short' if short else 'Video'} ID: {vid_id}")
            return vid_id
        except HttpError as e:
            print(f"HTTP error (attempt {attempt+1}): {e}")
            time.sleep(10 * (attempt + 1))
        except Exception as e:
            print(f"Upload error (attempt {attempt+1}): {e}")
            time.sleep(10 * (attempt + 1))
    print("Upload failed after retries.")
    return None

# MAIN
if __name__ == "__main__":
    print("===== Hindi Kids Video Auto-Generator - Piper TTS (debug version) =====")
    success = 0

    try:
        # Long Video
        is_story = random.random() > 0.35
        text_v = gen_story() if is_story else gen_rhyme()
        topic_v = gen_topic(text_v)
        img_url_v = get_image(topic_v, "horizontal")
        bg_v = os.path.join(BG_IMAGES_DIR, "bg_v.jpg")
        dl_image(img_url_v, bg_v)

        video_path = make_video(text_v, bg_v, short=False)
        title_v = f"नई {'कहानी' if is_story else 'राइम'} 2026 | {topic_v} | बच्चों के लिए"
        desc_v = f"{text_v[:120]}...\n#HindiKahani #BacchonKiKahani #HindiRhymes"
        tags_v = ["हिंदी कहानी", "बच्चों की कहानी", "हिंदी राइम", "kids story hindi"] + text_v.split()[:6]

        if upload(video_path, title_v, desc_v, tags_v):
            success += 1

        # Short
        is_story_s = random.random() > 0.5
        text_s = gen_story() if is_story_s else gen_rhyme()
        topic_s = gen_topic(text_s)
        img_url_s = get_image(topic_s, "vertical")
        bg_s = os.path.join(BG_IMAGES_DIR, "bg_s.jpg")
        dl_image(img_url_s, bg_s)

        short_path = make_video(text_s, bg_s, short=True)
        title_s = f"प्यारी {'कहानी' if is_story_s else 'राइम'} #shorts | {topic_s}"
        desc_s = f"{text_s[:90]}...\n#Shorts #HindiKids"
        tags_s = tags_v + ["shorts", "youtubeshorts"]

        if upload(short_path, title_s, desc_s, tags_s, short=True):
            success += 1

        print(f"\n===== Finished! {success}/2 uploads successful =====")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
