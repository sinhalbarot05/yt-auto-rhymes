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
from moviepy.video.fx.all import resize
from gTTS import gTTS
from pydub import AudioSegment
import requests

# ─── YouTube Upload ─────────────────────────────────────────────────────────────
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
TOKEN_FILE = "youtube_token.pickle"  # Treated as JSON

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

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

# Word lists for generation
animals = ["खरगोश", "तोता", "मछली", "हाथी", "शेर", "मोर", "बिल्ली", "कुत्ता", "गिलहरी", "मेंढक", "चीता", "मोरनी", "घोड़ा", "गाय", "बकरी"]
places = ["जंगल", "समंदर", "पहाड़", "नदी", "आकाश", "गाँव", "शहर", "बाग", "स्कूल", "घर", "मंदिर", "पार्क", "झील", "रेगिस्तान", "जंगल का किनारा"]
actions = ["खो गया", "सीखा", "मिला", "खेला", "उड़ा", "तैरा", "दौड़ा", "गाया", "नाचा", "पढ़ा", "कूदा", "छिपा", "ढूंढा", "बचाया", "जीता"]
adventures = ["कई अद्भुत चीजें देखीं", "नए दोस्त बनाए", "खजाना पाया", "जादू सीखा", "साहसिक कार्य किया", "रहस्य सुलझाया", "पार्टी की", "यात्रा की", "खेल खेले", "सीखा सबक", "मदद की", "हंसी", "रोया", "उत्सव मनाया", "सपना देखा"]
endings = ["घर लौट आया", "खुश रहा", "दोस्तों के साथ रहा", "नई शुरुआत की", "सपना पूरा किया", "समझदार हो गया", "जीत गया", "प्यार पाया", "शांति मिली", "उत्सव मनाया", "बड़ा हो गया", "दुनिया घूमा", "राजा बना", "रानी बनी", "खुशी से जिया"]
lessons = ["साहस", "दोस्ती", "सीखने", "खुशी", "प्यार", "ईमानदारी", "मेहनत", "धैर्य", "साझेदारी", "क्षमा"]

adj = ["छोटी", "बड़ी", "प्यारी", "मजेदार", "रंगीन", "चमकीली", "नरम", "कड़ी", "मीठी", "खुश"]
noun = ["बातें", "सीख", "खुशियां", "सपने", "किरणें", "चाँदनी", "दोस्ती", "रंग", "संगीत", "उड़ान"]
verb = ["खेलो", "हँसो", "मुस्कुराओ", "उड़ो", "बरसो", "बांटो", "गाओ", "नाचो", "पढ़ो", "सीखो"]

def generate_story():
    while True:
        animal = random.choice(animals)
        place = random.choice(places)
        action = random.choice(actions)
        adventure1 = random.choice(adventures)
        adventure2 = random.choice(adventures)
        adventure3 = random.choice(adventures)
        ending1 = random.choice(endings)
        ending2 = random.choice(endings)
        lesson = random.choice(lessons)
        story = f"एक छोटा {animal} था जो {place} में {action}। वहां उसने {adventure1}, {adventure2} और {adventure3}। अंत में वह {ending1} और {ending2}। यह कहानी बच्चों को {lesson} का महत्व सिखाती है। वहाँ से लौटकर उसने सबको अपनी कहानी सुनाई और सभी खुश हुए। कहानी का अंत खुशी से हुआ।"
        if story not in used_stories:
            used_stories.append(story)
            save_used("used_stories.json", used_stories)
            return story

def generate_rhyme():
    while True:
        line1 = f"{random.choice(adj)}-{random.choice(adj)} {random.choice(noun)}, {random.choice(adj)}-{random.choice(adj)} {random.choice(lesson)}।"
        line2 = f"{random.choice(verb)} {random.choice(noun)}, {random.choice(verb)} {random.choice(noun)} हर पल।"
        line3 = f"{random.choice(adj)} {random.choice(noun)}, {random.choice(adj)} {random.choice(noun)} सबको।"
        line4 = f"{random.choice(verb)} {random.choice(noun)}, जीवन {random.choice(adj)} बनाओ।"
        rhyme = f"{line1}\n{line2}\n{line3}\n{line4}"
        if rhyme not in used_rhymes:
            used_rhymes.append(rhyme)
            save_used("used_rhymes.json", used_rhymes)
            return rhyme

def generate_topic(text):
    words = text.split()[:3]
    topic = " ".join(words)
    while topic in used_topics:
        topic += " " + random.choice(lessons)
    used_topics.append(topic)
    save_used("used_topics.json", used_topics)
    return topic

def generate_content(type):
    if type == 'story':
        return generate_story()
    else:
        return generate_rhyme()

def fetch_random_image(topic, orientation="horizontal"):
    query = f"illustration of {topic} for kids hindi cartoon"
    url = f"https://pixabay.com/api/?key={os.getenv('PIXABAY_KEY')}&q={query}&image_type=illustration&orientation={orientation}&per_page=30&safesearch=true"

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
        print("No suitable new image found.")
        sys.exit(1)
    except Exception as e:
        print(f"Pixabay error: {e}")
        sys.exit(1)

# Pitch shift for female voice
def shift_pitch(audio, semitones=5):
    factor = 2 ** (semitones / 12)
    shifted = audio._spawn(audio.raw_data, overrides={"frame_rate": int(audio.frame_rate * factor)})
    shifted = shifted.set_frame_rate(audio.frame_rate)
    return shifted

def create_audio(text, output_path, lang="hi"):
    try:
        tts = gTTS(text=text, lang=lang, slow=True)
        temp_mp3 = "temp_audio.mp3"
        tts.save(temp_mp3)

        audio = AudioSegment.from_mp3(temp_mp3)
        audio = shift_pitch(audio)
        audio.export(output_path, format="mp3")
        os.remove(temp_mp3)
    except Exception as e:
        print(f"Audio creation failed: {e}")
        sys.exit(1)

def create_video(text, bg_image_path, is_short=False):
    try:
        audio_path = os.path.join(OUTPUT_DIR, "narration.mp3")
        create_audio(text, audio_path)

        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        if is_short:
            duration = min(duration, 60)
        else:
            duration = max(duration, 65)

        bg_clip = ImageClip(bg_image_path).set_duration(duration)
        if is_short:
            bg_clip = bg_clip.resize(width=1080, height=1920)
        else:
            bg_clip = bg_clip.resize(width=1920, height=1080)

        bg_clip = bg_clip.fx(resize, lambda t: 1 + 0.02 * t)  # Slower zoom

        txt_clip = TextClip(
            text,
            fontsize=70 if is_short else 65,
            color='yellow',
            font='Noto-Sans-Devanagari',
            stroke_color='black',
            stroke_width=2.5,
            method='caption',
            size=(700 if is_short else 900, None)
        ).set_position(('center', 'center')).set_duration(duration)

        final = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio_clip)

        output_file = os.path.join(OUTPUT_DIR, f"{'short' if is_short else 'video'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        final.write_videofile(
            output_file,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            bitrate="8000k",
            preset='medium',
            threads=4
        )

        return output_file

    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# ─── YOUTUBE AUTH & UPLOAD ──────────────────────────────────────────────────────
def get_authenticated_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                token_data = json.load(f)

            creds = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes', SCOPES)
            )
        except json.JSONDecodeError as e:
            print(f"Token file is not valid JSON: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading credentials from JSON: {e}")
            sys.exit(1)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            updated_data = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(updated_data, f, indent=2)
            print("Token refreshed successfully")
        except Exception as e:
            print(f"Token refresh failed: {e}")
            sys.exit(1)

    if not creds or not creds.valid:
        print("No valid credentials available.")
        sys.exit(1)

    return build('youtube', 'v3', credentials=creds)

def upload_to_youtube(video_file, title, description, is_short=False):
    youtube = get_authenticated_service()

    tags = ['hindi', 'kids', 'rhymes', 'storytime', 'bacchon ki kahani']
    if is_short:
        tags.append('shorts')

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': '24'  # Entertainment
        },
        'status': {
            'privacyStatus': 'public'
        }
    }

    media = MediaFileUpload(
        video_file,
        mimetype='video/mp4',
        resumable=True
    )

    print(f"Starting YouTube {'short' if is_short else 'video'} upload...")
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
                raise Exception("Upload failed after retries")

    if response:
        video_id = response['id']
        print(f"Upload SUCCESS! Video ID: {video_id}")
        print(f"Link: https://youtu.be/{video_id}")
        return video_id
    else:
        raise Exception("No response from YouTube")

# ─── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        print("Starting Hindi Kids Video Generator & Uploader...")

        # For video
        type_video = random.choice(['story', 'rhyme'])
        text_video = generate_content(type_video)
        topic_video = generate_topic(text_video)
        print(f"Video Type: {type_video}")
        print(f"Video Text: {text_video}")

        img_url_video = fetch_random_image(topic_video, orientation="horizontal")
        img_path_video = os.path.join(BG_IMAGES_DIR, "bg_video.jpg")
        download_image(img_url_video, img_path_video)

        video_path = create_video(text_video, img_path_video, is_short=False)

        title_video = f"मजेदार हिंदी {'कहानी' if type_video == 'story' else 'राइम'} बच्चों के लिए | {topic_video}"
        description_video = f"बच्चों की पसंदीदा {'कहानी' if type_video == 'story' else 'राइम'}: {text_video}\n#HindiStories #KidsRhymes"

        upload_to_youtube(video_path, title_video, description_video, is_short=False)

        # For short
        type_short = random.choice(['story', 'rhyme'])
        text_short = generate_content(type_short)
        topic_short = generate_topic(text_short)
        print(f"Short Type: {type_short}")
        print(f"Short Text: {text_short}")

        img_url_short = fetch_random_image(topic_short, orientation="vertical")
        img_path_short = os.path.join(BG_IMAGES_DIR, "bg_short.jpg")
        download_image(img_url_short, img_path_short)

        short_path = create_video(text_short, img_path_short, is_short=True)

        title_short = f"छोटी हिंदी {'कहानी' if type_short == 'story' else 'राइम'} | {topic_short} #shorts"
        description_short = f"मजेदार {'कहानी' if type_short == 'story' else 'राइम'}: {text_short}\n#Shorts #KidsRhymes"

        upload_to_youtube(short_path, title_short, description_short, is_short=True)

        print("Job completed successfully!")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
