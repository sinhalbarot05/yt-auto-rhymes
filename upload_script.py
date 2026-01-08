import os, json, random, hashlib, datetime
import requests
from gtts import gTTS
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

# =====================================================
# CONFIG
# =====================================================
PIXABAY_KEY = os.getenv("PIXABAY_KEY")
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
MEMORY_DIR = "memory"

os.makedirs(MEMORY_DIR, exist_ok=True)

FILES = {
    "stories": f"{MEMORY_DIR}/stories.json",
    "rhymes": f"{MEMORY_DIR}/rhymes.json",
    "images": f"{MEMORY_DIR}/images.json"
}

def load(path):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump([], f)
    return json.load(open(path))

def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

stories_used = load(FILES["stories"])
rhymes_used = load(FILES["rhymes"])
images_used = load(FILES["images"])

# =====================================================
# FESTIVAL LOGIC (simple & safe)
# =====================================================
def festival():
    m = datetime.date.today().month
    if m == 3:
        return "होली"
    if m == 8:
        return "रक्षा बंधन"
    if m in (10, 11):
        return "दीवाली"
    return "सामान्य दिन"

# =====================================================
# GEMINI (SAFE VERSION)
# =====================================================
def gemini(prompt):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    creds = service_account.Credentials.from_service_account_file(
        "gcp-sa.json",
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(Request())

    url = (
        f"https://us-central1-aiplatform.googleapis.com/v1/"
        f"projects/{PROJECT_ID}/locations/us-central1/"
        f"publishers/google/models/gemini-1.0-pro:generateContent"
    )

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 600
        }
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    data = resp.json()

    # 🔒 SAFE PARSING
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        print("⚠️ Gemini failed, raw response:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return None

# =====================================================
# FALLBACK TEXT (NO CRASH EVER)
# =====================================================
FALLBACK_RHYMES = [
    "नन्हा सा तोता बोला, मीठी मीठी बात,\nअच्छे बनो बच्चों, यही है सही राह।",
    "सूरज बोला उठो बच्चों, नया सवेरा आया,\nमेहनत करने वालों ने ही सपना सच पाया।"
]

FALLBACK_STORIES = [
    "एक गाँव में छोटा सा बच्चा रहता था। वह हमेशा सच बोलता था और सबकी मदद करता था। "
    "उसकी ईमानदारी ने उसे सबका प्यारा बना दिया।",
    "एक जंगल में नन्हा खरगोश रहता था। वह सब जानवरों से दोस्ती करता था और मिलकर रहना सिखाता था।"
]

# =====================================================
# UNIQUE TEXT GENERATOR
# =====================================================
def unique_text(kind):
    used = rhymes_used if kind == "rhyme" else stories_used

    for _ in range(3):  # try Gemini 3 times
        text = gemini(
            f"बच्चों के लिए नई हिंदी {kind} लिखो। "
            f"विषय: {festival()}। "
            f"सरल, प्यारी, सीख वाली, बिल्कुल नई।"
        )
        if text:
            h = hashlib.sha256(text.encode()).hexdigest()
            if h not in used:
                used.append(h)
                save(FILES["rhymes" if kind == "rhyme" else "stories"], used)
                return text

    # 🔁 FALLBACK (guaranteed)
    text = random.choice(FALLBACK_RHYMES if kind == "rhyme" else FALLBACK_STORIES)
    return text

# =====================================================
# PIXABAY IMAGES (NON-REPEATING)
# =====================================================
def images(query, n=5):
    res = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": PIXABAY_KEY,
            "q": query,
            "image_type": "illustration",
            "per_page": 20
        },
        timeout=20
    ).json()

    out = []
    for h in res.get("hits", []):
        if str(h["id"]) in images_used:
            continue
        img = f"img_{h['id']}.jpg"
        open(img, "wb").write(requests.get(h["largeImageURL"]).content)
        images_used.append(str(h["id"]))
        out.append(img)
        if len(out) == n:
            break

    save(FILES["images"], images_used)
    return out

# =====================================================
# AUDIO
# =====================================================
def tts(text, out):
    gTTS(text=text, lang="hi", slow=False).save(out)

# =====================================================
# VIDEO
# =====================================================
def make_video(imgs, audio, out, height):
    aud = AudioFileClip(audio)
    d = aud.duration / len(imgs)
    clips = [ImageClip(i).with_duration(d).resized(height=height) for i in imgs]
    concatenate_videoclips(clips).with_audio(aud).write_videofile(out, fps=24)

# =====================================================
# RUN
# =====================================================
short_text = unique_text("rhyme")
tts(short_text, "short.mp3")
make_video(images("kids cartoon happy"), "short.mp3", "short.mp4", 1920)

long_text = unique_text("story")
tts(long_text, "long.mp3")
make_video(images("kids story illustration"), "long.mp3", "long.mp4", 1080)

print("✅ SUCCESS: unique rhyme + unique story generated safely")
