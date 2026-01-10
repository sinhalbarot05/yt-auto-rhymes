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
from gtts import gTTS
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

# ─── CONTENT GENERATION ─────────────────────────────────────────────────────────
stories = [
    "एक छोटा खरगोश था जो जादुई जंगल में खो गया था। वहां उसने कई अद्भुत चीजें देखीं और नए दोस्त बनाए। अंत में वह घर लौट आया और सबको अपनी कहानी सुनाई।",
    "सूरज और चाँद की दोस्ती की मधुर कहानी। वे दोनों आकाश में साथ रहते हैं लेकिन मिलते कम हैं। एक दिन उन्होंने मिलकर एक बड़ा उत्सव मनाया।",
    "नन्हा तोता जो नया गाना सीख रहा था। वह रोज अभ्यास करता और अपने दोस्तों को सुनाता। आखिरकार वह एक बड़ा गायक बन गया।",
    "रंगों की दुनिया में एक मजेदार सफर। छोटी लड़की ने रंगों के साथ खेला और नई चीजें सीखीं। हर रंग ने उसे एक सबक दिया।",
    "छोटी मछली और बड़ा समंदर की कहानी। मछली ने साहसिक यात्रा की और कई खतरे पार किए। अंत में वह समझदार हो गई।"
]

rhymes = [
    "छोटी-छोटी बातें, बड़ी-बड़ी सीख।\nखेलो कूदो, खुश रहो हर पल।\nदोस्त बनाओ, प्यार बांटो सबको।",
    "हँसो, खेलो, और मुस्कुराओ यार।\nसपनों को पकड़ो, उड़ो ऊंचे आकाश में।\nजीवन है सुंदर, जीयो खुलकर।",
    "सपनों की उड़ान, खुशियों का संसार।\nफूलों जैसे खिलो, बारिश जैसे बरसो।\nप्यार की बूंदें, सबको भिगो दो।",
    "सूरज की किरण, चाँद की चाँदनी।\nतारों से बातें करो, रातें गुजारो।\nसुबह की ओस, जीवन का रस।",
    "दोस्ती का रंग, प्यार का संगीत।\nगाओ बजाओ, नाचो गाओ।\nखुशियां मनाओ, हर दिन त्योहार।"
]

def generate_unique_content(used_stories_list, used_rhymes_list, used_images_list, used_topics_list):
    avail_stories = [s for s in stories if s not in used_stories_list]
    avail_rhymes = [r for r in rhymes if r not in used_rhymes_list]

    if not avail_stories or not avail_rhymes:
        print("No more unique content left!")
        sys.exit(1)

    story = random.choice(avail_stories)
    rhyme = random.choice(avail_rhymes)
    topic = story.split()[0] + " " + rhyme.split()[0]  # Simple topic generation

    if topic in used_topics_list:
        print("Topic already used, skipping to avoid repeat.")
        sys.exit(1)

    return story, rhyme, topic

def fetch_random_image(orientation="horizontal"):
    query = "cute kids story illustration cartoon"
    url = f"https://pixabay.com/api/?key={os.getenv('PIXABAY_KEY')}&q={query}&image_type=illustration&orientation={orientation}&per_page=30&safesearch=true"

    try:
        resp = requests.get(url).json()
        hits = resp.get("hits", [])
        random.shuffle(hits)  # Randomize to avoid repeats
        for hit in hits:
            img_url = hit.get("largeImageURL")
            if img_url and img_url not in used_images:
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
        tts = gTTS(text=text, lang=lang, slow=True)  # Slow for better, less robotic
        temp_mp3 = "temp_audio.mp3"
        tts.save(temp_mp3)

        audio = AudioSegment.from_mp3(temp_mp3)
        audio.export(output_path, format="mp3")
        os.remove(temp_mp3)
    except Exception as e:
        print(f"Audio creation failed: {e}")
        sys.exit(1)

def create_video(story, rhyme, bg_image_path, is_short=False):
    try:
        full_text = f"नमस्ते छोटे दोस्तों! आज की मजेदार कहानी है: {story}। और अब सुनिए यह प्यारी राइम: {rhyme}। पसंद आई? लाइक और सब्सक्राइब करें!"

        audio_path = os.path.join(OUTPUT_DIR, "narration.mp3")
        create_audio(full_text, audio_path)

        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration

        bg_clip = ImageClip(bg_image_path).set_duration(duration)
        if is_short:
            bg_clip = bg_clip.resize(width=1080)  # Vertical for shorts
        else:
            bg_clip = bg_clip.resize(height=1080)  # Horizontal for videos

        # Add zoom animation
        bg_clip = bg_clip.fx(resize, lambda t: 1 + 0.01 * t)  # Slow zoom in

        txt_clip = TextClip(
            rhyme,
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
            bitrate="5000k",
            preset='medium',
            threads=4
        )

        return output_file

    except Exception as e:
        print(f"Video creation failed: {e}")
        sys.exit(1)

# ─── YOUTUBE AUTH & UPLOAD (JSON version) ───────────────────────────────────────
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

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save updated token back to file
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

        # Generate for full video
        story_video, rhyme_video, topic_video = generate_unique_content(used_stories, used_rhymes, used_images, used_topics)
        print(f"Video Story: {story_video}")
        print(f"Video Rhyme: {rhyme_video}")

        img_url_video = fetch_random_image(orientation="horizontal")
        img_path_video = os.path.join(BG_IMAGES_DIR, "bg_video.jpg")
        download_image(img_url_video, img_path_video)

        video_path = create_video(story_video, rhyme_video, img_path_video, is_short=False)

        title_video = f"मजेदार हिंदी कहानी और राइम बच्चों के लिए | {topic_video}"
        description_video = f"बच्चों की पसंदीदा कहानी: {story_video}\nराइम: {rhyme_video}\n#HindiStories #KidsRhymes"

        upload_to_youtube(video_path, title_video, description_video, is_short=False)

        used_stories.append(story_video)
        used_rhymes.append(rhyme_video)
        used_images.append(img_url_video)
        used_topics.append(topic_video)

        save_used("used_stories.json", used_stories)
        save_used("used_rhymes.json", used_rhymes)
        save_used("used_images.json", used_images)
        save_used("used_topics.json", used_topics)

        # Generate for short
        story_short, rhyme_short, topic_short = generate_unique_content(used_stories, used_rhymes, used_images, used_topics)
        print(f"Short Story: {story_short}")
        print(f"Short Rhyme: {rhyme_short}")

        img_url_short = fetch_random_image(orientation="vertical")
        img_path_short = os.path.join(BG_IMAGES_DIR, "bg_short.jpg")
        download_image(img_url_short, img_path_short)

        short_path = create_video(story_short, rhyme_short, img_path_short, is_short=True)

        title_short = f"छोटी हिंदी राइम बच्चों के लिए | {topic_short} #shorts"
        description_short = f"मजेदार राइम: {rhyme_short}\nकहानी स्निपेट: {story_short[:50]}...\n#Shorts #KidsRhymes"

        upload_to_youtube(short_path, title_short, description_short, is_short=True)

        used_stories.append(story_short)
        used_rhymes.append(rhyme_short)
        used_images.append(img_url_short)
        used_topics.append(topic_short)

        save_used("used_stories.json", used_stories)
        save_used("used_rhymes.json", used_rhymes)
        save_used("used_images.json", used_images)
        save_used("used_topics.json", used_topics)

        print("Job completed successfully!")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)
