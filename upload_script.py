import os
import random
import json
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone
import pickle
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment
import requests
from gtts import gTTS

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
BG_IMAGES_DIR = "images/"
TOKEN_FILE = "youtube_token.pickle"

for d in [MEMORY_DIR, OUTPUT_DIR, BG_IMAGES_DIR]:
    Path(d).mkdir(exist_ok=True)

# ────────────────────────────────────────────────
# MEMORY MANAGEMENT
# ────────────────────────────────────────────────
def load_used(f):
    p = os.path.join(MEMORY_DIR, f)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []

def save_used(f, data):
    try:
        json.dump(data, open(os.path.join(MEMORY_DIR, f), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Memory save failed for {f}: {e}")

used_rhymes = load_used("used_rhymes.json")
used_images = load_used("used_images.json")
used_topics = load_used("used_topics.json")

# ────────────────────────────────────────────────
# GENERATE NURSERY RHYME USING GROQ API
# ────────────────────────────────────────────────
def gen_rhyme():
    global used_rhymes
    prompt = """एक छोटी हिंदी नर्सरी राइम बनाओ (4-8 लाइनें)। तुकबंदी हो, मजेदार हो, थीम खुशी/दोस्ती/प्रकृति/जानवर हो। केवल राइम लिखो, कोई अतिरिक्त टिप्पणी नहीं। नई हो।"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.95,
                "max_tokens": 200
            },
            timeout=20
        )
        response.raise_for_status()
        rhyme = response.json()["choices"][0]["message"]["content"].strip()
        
        if rhyme not in used_rhymes:
            used_rhymes.append(rhyme)
            save_used("used_rhymes.json", used_rhymes)
            print("AI-generated rhyme:\n", rhyme)
            return rhyme
    
    except Exception as e:
        print(f"Groq API error: {e}")
        fallback = "चंदा मामा दूर के\nपुए पाके बूर के\nहमको भी दो थोड़े से\nहम भी खाएं पूरे से"
        if fallback not in used_rhymes:
            used_rhymes.append(fallback)
            save_used("used_rhymes.json", used_rhymes)
        print("Using fallback rhyme")
        return fallback

def gen_topic(txt):
    global used_topics
    t = " ".join(txt.split()[:5])
    while t in used_topics:
        t += f" {random.choice(['की राइम','की मस्ती','का गाना','नई वाली'])}"
    used_topics.append(t)
    save_used("used_topics.json", used_topics)
    return t

# ────────────────────────────────────────────────
# IMAGE HANDLING
# ────────────────────────────────────────────────
def get_image(topic, orient="horizontal"):
    q = f"cute hindi kids cartoon {topic} nursery rhyme illustration"
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

# ────────────────────────────────────────────────
# AUDIO GENERATION - gTTS
# ────────────────────────────────────────────────
def make_audio(txt, out_mp3):
    try:
        print(f"Generating rhyme audio with gTTS (length {len(txt)} chars)")
        print(f"Preview: {txt[:100]}...")

        tts = gTTS(txt, lang='hi', tld='co.in')
        tts.save(out_mp3)

        mp3_size = os.path.getsize(out_mp3)
        print(f"MP3 created, size: {mp3_size} bytes")

        if mp3_size < 10000:
            print("ERROR: MP3 too small")
            sys.exit(1)

        print(f"Audio created successfully: {out_mp3}")

    except Exception as e:
        print(f"gTTS failed: {e}")
        sys.exit(1)

# ────────────────────────────────────────────────
# VIDEO CREATION
# ────────────────────────────────────────────────
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
            font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", 90 if short else 80)
        except:
            font = ImageFont.load_default()

        lines = txt.split('\n')
        y, dy = 300 if short else 250, 100
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (size[0] - text_w) // 2
            draw.text((x, y), line, font=font, fill=(255, 255, 0))
            y += dy

        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        frames = []
        n_frames = 1200
        for i in range(n_frames):
            s = 1 + 0.01 * (i / n_frames)
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

        intro = "नमस्ते छोटे दोस्तों! आज सुनो एक प्यारी "
        mid = "नर्सरी राइम"
        outro = "। बहुत पसंद आए तो लाइक, कमेंट और सब्सक्राइब करो! बेल आइकन दबाओ!"
        full_text = intro + mid + ":\n\n" + txt + "\n\n" + outro

        aud_path = os.path.join(OUTPUT_DIR, "aud.mp3")
        make_audio(full_text, aud_path)

        final_name = f"rhyme_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
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

# ────────────────────────────────────────────────
# YOUTUBE - BINARY PICKLE LOADING (this matches the binary decode in workflow)
# ────────────────────────────────────────────────
def yt_service():
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)

        if creds:
            print(f"Credentials loaded from pickle. Expiry: {creds.expiry if creds.expiry else 'None'}")
            now_utc = datetime.now(timezone.utc)
            if creds.expiry and creds.expiry < now_utc:
                print("Token expired - refreshing")
                creds.refresh(Request())
                with open(TOKEN_FILE, 'wb') as f:
                    pickle.dump(creds, f)
                print("Token refreshed and saved as pickle")
            else:
                print("Token is valid or no expiry")

        else:
            print("No credentials in pickle")
            sys.exit(1)

        return build('youtube', 'v3', credentials=creds)

    except Exception as e:
        print(f"Credential error: {e}")
        if os.path.exists(TOKEN_FILE):
            print("Token file size:", os.path.getsize(TOKEN_FILE))
            with open(TOKEN_FILE, 'rb') as f:
                first_bytes = f.read(50)
                print("First 50 bytes (hex):", first_bytes.hex())
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

# ────────────────────────────────────────────────
# MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== Hindi Kids Nursery Rhymes Auto-Generator with Groq AI =====")
    success = 0

    try:
        # Long Video - rhyme
        text_v = gen_rhyme()
        topic_v = gen_topic(text_v)
        img_url_v = get_image(topic_v, "horizontal")
        bg_v = os.path.join(BG_IMAGES_DIR, "bg_v.jpg")
        dl_image(img_url_v, bg_v)

        video_path = make_video(text_v, bg_v, short=False)
        title_v = f"प्यारी नर्सरी राइम 2026 | {topic_v} | बच्चों के लिए"
        desc_v = f"{text_v[:120]}...\n#HindiNurseryRhyme #BacchonKiRhyme #KidsSongs"
        tags_v = ["हिंदी नर्सरी राइम", "बच्चों की राइम", "kids rhyme hindi", "nursery rhymes"] + text_v.split()[:6]

        if upload(video_path, title_v, desc_v, tags_v):
            success += 1

        # Short Video - rhyme
        text_s = gen_rhyme()
        topic_s = gen_topic(text_s)
        img_url_s = get_image(topic_s, "vertical")
        bg_s = os.path.join(BG_IMAGES_DIR, "bg_s.jpg")
        dl_image(img_url_s, bg_s)

        short_path = make_video(text_s, bg_s, short=True)
        title_s = f"मस्ती वाली नर्सरी राइम #shorts | {topic_s}"
        desc_s = f"{text_s[:90]}...\n#Shorts #NurseryRhyme"
        tags_s = tags_v + ["shorts", "youtubeshorts", "kids rhyme shorts"]

        if upload(short_path, title_s, desc_s, tags_s, True):
            success += 1

        print(f"\n===== Finished! {success}/2 rhymes uploaded =====")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
