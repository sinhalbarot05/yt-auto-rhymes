import os
import random
import requests
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip
from google.genai import Client  # New SDK
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import json
from dotenv import load_dotenv

# ------------------- Load Environment -------------------
load_dotenv()

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PIXABAY_KEY = os.environ.get('PIXABAY_KEY', '54102811-cdbcbe721d88b9b67e97256b4')  # fallback
YOUTUBE_TOKEN = os.environ.get('YOUTUBE_TOKEN')

# ------------------- YouTube Client Setup -------------------
with open('client_secrets.json', 'r') as f:
    client_secrets = json.load(f)

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

creds = None
if YOUTUBE_TOKEN:
    try:
        creds = pickle.loads(YOUTUBE_TOKEN.encode('latin1'))
    except Exception as e:
        print(f"Error loading YOUTUBE_TOKEN: {e}")

if not creds or not creds.valid:
    try:
        flow = InstalledAppFlow.from_client_config(client_secrets, SCOPES)
        creds = flow.run_local_server(port=0)
        print("----- COPY THIS ENTIRE TOKEN FOR YOUTUBE_TOKEN -----")
        print(pickle.dumps(creds))
        print("----- END TOKEN -----")
    except Exception as e:
        print(f"Error in OAuth flow: {e}")
        exit(1)

youtube = build('youtube', 'v3', credentials=creds)

# ------------------- Random Theme -------------------
themes = ['जानवरों की दोस्ती', 'प्रकृति की सुंदरता', 'सीखने की कहानी', 'मजेदार साहसिक', 'परिवार का प्यार', 'स्कूल के दिन', 'खेलकूद की मस्ती']
random_theme = random.choice(themes)

# ------------------- Initialize Gemini Client -------------------
client = Client(api_key=GEMINI_API_KEY)

# ------------------- Generate Long Story -------------------
try:
    long_prompt = f"एक नई, अनोखी हिंदी बच्चों की कहानी बनाओ थीम '{random_theme}' पर। कहानी 300-500 शब्दों की हो, सरल भाषा में, नैतिक सीख के साथ। पिछली कहानियों से अलग हो।"
    long_response = client.generate(
        model="gemini-1.5-flash",
        temperature=0.7,
        max_output_tokens=1000,
        prompt=long_prompt
    )
    long_text = long_response.output[0].content

    short_prompt = f"एक नई, अनोखी हिंदी बच्चों की छोटी कविता या राइम बनाओ थीम '{random_theme}' पर। 100 शब्दों की हो, मजेदार और गाने लायक। पिछली से अलग हो।"
    short_response = client.generate(
        model="gemini-1.5-flash",
        temperature=0.7,
        max_output_tokens=300,
        prompt=short_prompt
    )
    short_text = short_response.output[0].content

except Exception as e:
    print(f"Error generating content with Gemini: {e}")
    exit(1)

# ------------------- Fetch Pixabay Image -------------------
try:
    image_query = f"kids cartoon {random_theme.lower().replace(' ', '+')}"
    response = requests.get(f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={image_query}&image_type=illustration&orientation=horizontal")
    data = response.json()
    if 'hits' in data and data['hits']:
        image_url = data['hits'][0]['largeImageURL']
        image_data = requests.get(image_url).content
        with open('background.jpg', 'wb') as f:
            f.write(image_data)
    else:
        print("No images found on Pixabay. Using placeholder image.")
except Exception as e:
    print(f"Error fetching Pixabay image: {e}")
    exit(1)

# ------------------- Video Creation Function -------------------
def create_video(text, filename):
    try:
        # Text-to-speech
        tts = gTTS(text, lang='hi')
        tts.save('audio.mp3')

        audio = AudioFileClip('audio.mp3')
        image = ImageClip('background.jpg').set_duration(audio.duration)

        try:
            txt_clip = TextClip(text[:100] + '...', fontsize=24, color='white', font='Amiri-Bold')\
                        .set_position('center').set_duration(audio.duration)
        except Exception:
            txt_clip = TextClip(text[:100] + '...', fontsize=24, color='white')\
                        .set_position('center').set_duration(audio.duration)

        video = CompositeVideoClip([image, txt_clip])
        video = video.set_audio(audio)
        video.write_videofile(filename, fps=24)
    except Exception as e:
        print(f"Error creating video {filename}: {e}. Ensure FFmpeg is installed and in PATH.")
        exit(1)

# ------------------- Create Videos -------------------
create_video(long_text, 'long_video.mp4')
create_video(short_text, 'short_video.mp4')

# ------------------- YouTube Upload Function -------------------
def upload_video(filename, title, description, is_short=False):
    try:
        body = {
            'snippet': {
                'title': title + (' #Shorts' if is_short else ''),
                'description': description,
                'tags': ['hindi rhymes', 'kids stories', 'masti rhymes'],
                'categoryId': '24'
            },
            'status': {'privacyStatus': 'public'}
        }
        media = MediaFileUpload(filename, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        response = request.execute()
        print(f"Uploaded: {response['id']}")
    except Exception as e:
        print(f"Error uploading {filename}: {e}")

# ------------------- Upload Videos -------------------
upload_video('long_video.mp4', f"नई हिंदी कहानी: {random_theme}", long_text)
upload_video('short_video.mp4', f"मजेदार हिंदी राइम: {random_theme}", short_text, is_short=True)
