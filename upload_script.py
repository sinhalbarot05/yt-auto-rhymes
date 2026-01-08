import os
import random
import requests
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import json

# Secrets from GitHub
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
client_secrets = json.loads(os.environ['YOUTUBE_CLIENT_SECRETS'])
token_pickle = os.environ.get('YOUTUBE_TOKEN')  # Base64 or raw pickle string

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Random theme for uniqueness
themes = ['जानवरों की दोस्ती', 'प्रकृति की सुंदरता', 'सीखने की कहानी', 'मजेदार साहसिक', 'परिवार का प्यार', 'स्कूल के दिन', 'खेलकूद की मस्ती']
random_theme = random.choice(themes)

# Generate long content (story ~300-500 words for 5-10 min audio)
long_prompt = f"एक नई, अनोखी हिंदी बच्चों की कहानी बनाओ थीम '{random_theme}' पर। कहानी 300-500 शब्दों की हो, सरल भाषा में, नैतिक सीख के साथ। पिछली कहानियों से अलग हो।"
long_response = model.generate_content(long_prompt)
long_text = long_response.text

# Generate short content (rhyme ~100 words for 30-60 sec)
short_prompt = f"एक नई, अनोखी हिंदी बच्चों की छोटी कविता या राइम बनाओ थीम '{random_theme}' पर। 100 शब्दों की हो, मजेदार और गाने लायक। पिछली से अलग हो।"
short_response = model.generate_content(short_prompt)
short_text = short_response.text

# Get free image from Pixabay
pixabay_key = 54102811-cdbcbe721d88b9b67e97256b4  # Get free from https://pixabay.com/api/docs/
image_query = f"kids cartoon {random_theme.lower().replace(' ', '+')}"
image_url = requests.get(f"https://pixabay.com/api/?key={pixabay_key}&q={image_query}&image_type=illustration&orientation=horizontal").json()['hits'][0]['largeImageURL']
image_data = requests.get(image_url).content
with open('background.jpg', 'wb') as f:
    f.write(image_data)

def create_video(text, filename, is_short=False):
    # TTS audio
    tts = gTTS(text, lang='hi')
    tts.save('audio.mp3')

    # Load audio and image
    audio = AudioFileClip('audio.mp3')
    image = ImageClip('background.jpg').set_duration(audio.duration)

    # Optional: Add text overlay (scrolling subtitle)
    txt_clip = TextClip(text[:100] + '...', fontsize=24, color='white', font='Amiri-Bold').set_position('center').set_duration(audio.duration)

    video = CompositeVideoClip([image, txt_clip])
    video = video.set_audio(audio)
    video.write_videofile(filename, fps=24)

# Create videos
create_video(long_text, 'long_video.mp4')
create_video(short_text, 'short_video.mp4', is_short=True)

# OAuth for YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
creds = None
if token_pickle:
    creds = pickle.loads(token_pickle.encode('latin1'))  # If stored as string
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_config(client_secrets, SCOPES)
        creds = flow.run_local_server(port=0)
    # For first run, print token and add to secrets (run locally once)
    print(pickle.dumps(creds))  # Copy this output for secrets

youtube = build('youtube', 'v3', credentials=creds)

def upload_video(filename, title, description, is_short=False):
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['hindi rhymes', 'kids stories', 'masti rhymes'],
            'categoryId': '24'  # Entertainment
        },
        'status': {'privacyStatus': 'public'}
    }
    if is_short:
        body['snippet']['title'] += ' #Shorts'
    media = MediaFileUpload(filename, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response = request.execute()
    print(f"Uploaded: {response['id']}")

# Upload
upload_video('long_video.mp4', f"नई हिंदी कहानी: {random_theme}", long_text)
upload_video('short_video.mp4', f"मजेदार हिंदी राइम: {random_theme}", short_text, is_short=True)
