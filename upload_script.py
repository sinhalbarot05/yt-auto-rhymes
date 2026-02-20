import os
import random
import json
import asyncio
import requests
import time
import numpy as np
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
if not hasattr(Image, 'ANTIALIAS'): Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    AudioFileClip, ImageClip, TextClip, CompositeVideoClip,
    concatenate_videoclips, CompositeAudioClip, ColorClip
)

# CONFIG
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"
FONT_FILE = os.path.join(ASSETS_DIR, "HindiFont.ttf")

for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)

for f in ["used_topics.json", "used_rhymes.json"]:
    if not os.path.exists(os.path.join(MEMORY_DIR, f)):
        with open(os.path.join(MEMORY_DIR, f), "w") as file: json.dump([], file)

def download_assets():
    if not os.path.exists(FONT_FILE):
        requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf", timeout=20).content >> open(FONT_FILE, 'wb')
    if not os.path.exists(os.path.join(ASSETS_DIR, "bg_music.mp3")):
        requests.get("https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3", timeout=20).content >> open(os.path.join(ASSETS_DIR, "bg_music.mp3"), 'wb')
download_assets()

def load_memory(f): 
    p = os.path.join(MEMORY_DIR, f)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else []

def save_to_memory(f, item):
    data = load_memory(f)
    if item not in data:
        data.append(item)
        json.dump(data[-1000:], open(os.path.join(MEMORY_DIR, f), 'w', encoding='utf-8'), ensure_ascii=False)

def groq_request(prompt):
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8, "max_tokens": 2500}, timeout=40)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return None

def clean_json(text):
    try: return json.loads(text[text.find('{'):text.rfind('}')+1])
    except: return None

def generate_content(mode="short"):
    used = load_memory("used_topics.json")
    topic = groq_request(f"Give 1 super cute funny topic for Hindi kids rhyme. Avoid: {', '.join(used[-15:])}. Only English topic.") or "Dolphin Veena Party"
    
    lines = 8 if mode == "short" else 16
    prompt = f"""You are ChuChu TV level Hindi rhyme writer for toddlers.
Topic: "{topic}"
Write {lines} highly singable lines with REPEATING CHORUS (repeat chorus 3 times).
Style: Fun, rhythmic, AABB, educational (colors/animals/numbers).
Output ONLY valid JSON:
{{
  "seo_title": "Catchy Title | Hindi Nursery Rhymes for Kids 2026 🦁 Bal Geet",
  "title": "Hindi Title",
  "keyword": "Main character",
  "seo_tags": ["hindi nursery rhymes for kids","bal geet", ... up to 25],
  "seo_description": "Full description with timestamps",
  "scenes": [{{"line": "Hindi line", "action": "Pixar cute visual"}} , ...]]
}}"""
    
    for _ in range(3):
        data = clean_json(groq_request(prompt))
        if data:
            data['generated_topic'] = topic
            save_to_memory("used_topics.json", topic)
            return data
    return None

def download_file(url, fn, headers=None):
    try:
        r = requests.get(url, headers=headers or {"User-Agent":"Mozilla"}, timeout=60)
        if r.status_code == 200:
            open(fn, 'wb').write(r.content)
            Image.open(fn).verify()
            return True
    except: pass
    return False

def apply_pro_enhancement(fn, w, h):
    try:
        with Image.open(fn) as im:
            im = im.convert("RGB").resize((w,h), Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(2, 300, 3))
            im = ImageEnhance.Contrast(im).enhance(1.2)
            im = ImageEnhance.Color(im).enhance(1.15)
            im.save(fn, "JPEG", quality=98)
    except: pass

def get_image(action, fn, kw, is_short):
    w, h = (1080,1920) if is_short else (1920,1080)
    seed = random.randint(0,999999)
    clean = f"{action}, cute pixar 3d kids cartoon vibrant masterpiece 8k".replace(" ","%20")
    api = os.getenv('POLLINATIONS_API_KEY')
    if api:
        url = f"https://gen.pollinations.ai/image/{clean}?model=flux&width={w}&height={h}&seed={seed}&enhance=true"
        if download_file(url, fn, {"Authorization": f"Bearer {api}"}): 
            apply_pro_enhancement(fn,w,h); return
    url_stock = f"https://loremflickr.com/{w}/{h}/{kw.lower()}/?lock={seed}"
    if download_file(url_stock, fn): apply_pro_enhancement(fn,w,h)
    else: Image.new('RGB',(w,h), (random.randint(60,220),)*3).save(fn)

def create_intro(is_short):
    w, h = (1080,1920) if is_short else (1920,1080)
    clip = ColorClip((w,h), (255,215,0)).set_duration(2)
    txt = TextClip("Hindi Masti Rhymes 🦁", fontsize=90, color='white', font=FONT_FILE if os.path.exists(FONT_FILE) else 'Arial', stroke_color='black', stroke_width=5).set_position('center').set_duration(2).crossfadein(1)
    return CompositeVideoClip([clip, txt], size=(w,h))

def create_outro(is_short):
    w, h = (1080,1920) if is_short else (1920,1080)
    clip = ColorClip((w,h), (0,0,0)).set_duration(4)
    txt1 = TextClip("LIKE 👍 SUBSCRIBE 🦁", fontsize=85, color='#FFFF00', font=FONT_FILE if os.path.exists(FONT_FILE) else 'Arial', stroke_color='black', stroke_width=6).set_position(('center', h//3)).set_duration(4)
    txt2 = TextClip("@hindimastirhymes", fontsize=70, color='white', font=FONT_FILE if os.path.exists(FONT_FILE) else 'Arial').set_position(('center', h*0.6)).set_duration(4)
    return CompositeVideoClip([clip, txt1, txt2], size=(w,h))

def generate_text_clip_pil(text, w, h, size, dur):
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_FILE, size) if os.path.exists(FONT_FILE) else ImageFont.load_default()
    bbox = draw.textbbox((0,0), text, font=font)
    x = (w - (bbox[2]-bbox[0])) // 2
    y = h - 320
    for dx in range(-10,11,2):
        for dy in range(-10,11,2):
            draw.text((x+dx, y+dy), text, font=font, fill='black')
    draw.text((x-3,y-3), text, font=font, fill='white')
    draw.text((x+3,y+3), text, font=font, fill='white')
    draw.text((x,y), text, font=font, fill='#FFFF00')
    return ImageClip(np.array(img)).set_duration(dur)

def create_segment(line, img_path, aud_path, is_short, idx, total):
    w,h = (1080,1920) if is_short else (1920,1080)
    voice = AudioFileClip(aud_path)
    bg = AudioFileClip(os.path.join(ASSETS_DIR,"bg_music.mp3")).volumex(0.08)
    if bg.duration < voice.duration: bg = bg.loop(duration=voice.duration)
    else: bg = bg.subclip(random.uniform(0, bg.duration-voice.duration), voice.duration)
    audio = CompositeAudioClip([voice, bg])

    img = ImageClip(img_path)
    anim = img.resize(lambda t: 1.02 - 0.015*t).set_position('center').set_duration(voice.duration)  # slower cinematic zoom

    txt = generate_text_clip_pil(line, w, h, 88 if is_short else 115, voice.duration)

    wm = TextClip("Hindi Masti Rhymes", fontsize=28, color='white', font=FONT_FILE if os.path.exists(FONT_FILE) else 'Arial').set_position((20,20)).set_duration(voice.duration).set_opacity(0.7)

    clip = CompositeVideoClip([anim, txt, wm], size=(w,h)).set_audio(audio).set_duration(voice.duration)
    if idx > 0: clip = clip.crossfadein(0.4)
    return clip

def make_video(content, is_short=True):
    print(f"🎥 Rendering {'SHORT' if is_short else 'LONG'} (Premium + SEO)...")
    clips = [create_intro(is_short)]
    suffix = "s" if is_short else "l"
    keyword = content.get('keyword','kids')
    full_lyrics = ""
    times = []
    current_time = 2.0

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = []
        for i, scene in enumerate(content['scenes']):
            line = scene['line']
            full_lyrics += line + "\n"
            aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
            img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
            futures.append(ex.submit(get_voice, line, aud))  # defined below
            futures.append(ex.submit(get_image, scene['action'], img, keyword, is_short))
        
        for f in as_completed(futures): f.result()

    for i, scene in enumerate(content['scenes']):
        aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
        img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
        clip = create_segment(scene['line'], img, aud, is_short, i, len(content['scenes']))
        clips.append(clip)
        times.append(f"{time.strftime('%M:%S', time.gmtime(current_time))} {scene['line'][:60]}")
        current_time += clip.duration

    clips.append(create_outro(is_short))
    final = concatenate_videoclips(clips, method="compose")

    out = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    final.write_videofile(out, fps=24, codec='libx264', audio_codec='aac',
                          threads=os.cpu_count() or 8, preset='veryfast',
                          ffmpeg_params=['-crf','19','-pix_fmt','yuv420p'])

    # Cleanup
    for f in os.listdir(ASSETS_DIR):
        if f.startswith(('a_s_','a_l_','i_s_','i_l_')): os.remove(os.path.join(ASSETS_DIR,f))

    return out, full_lyrics, times, content.get('seo_description','')

async def generate_voice_async(text, fn):
    await asyncio.create_subprocess_exec("edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", fn).wait()
def get_voice(text, fn): asyncio.run(generate_voice_async(text, fn))

def create_thumbnail(title, bg, out):
    with Image.open(bg) as im:
        im = im.convert("RGB").resize((1280,720), Image.LANCZOS)
        im = ImageEnhance.Contrast(im).enhance(1.25)
        overlay = Image.new("RGBA",(1280,720),(0,0,0,90))
        im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(FONT_FILE, 125) if os.path.exists(FONT_FILE) else ImageFont.load_default()
        x = (1280 - draw.textbbox((0,0), title, font=font)[2]) // 2
        for off in [(8,8),(10,10)]: draw.text((x+off[0],180+off[1]), title, font=font, fill=(0,0,0))
        draw.text((x,180), title + " 🦁", font=font, fill="#FFEA00")
        draw.text((300,520), "FOR KIDS 2026", font=ImageFont.truetype(FONT_FILE, 65) if os.path.exists(FONT_FILE) else ImageFont.load_default(), fill="#FFFF00")
        im.save(out, quality=98)

def upload_video(vid, content, lyrics, times, desc_template, is_short):
    try:
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)
        
        title = content['seo_title'] if 'seo_title' in content else content['title'] + " | Hindi Nursery Rhymes for Kids 2026 🦁"
        tags = content.get('seo_tags', [])[:25]
        desc = f"""{title}

{content.get('seo_description', desc_template)}

{chr(10).join(times)}

🦁 LIKE + SUBSCRIBE for daily rhymes!
#HindiRhymes #BalGeet #KidsSongs"""

        body = {'snippet': {'title': title[:100], 'description': desc, 'tags': tags, 'categoryId': '24'},
                'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': True}}
        
        media = MediaFileUpload(vid, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)
        while (status := req.next_chunk()[0]) is not None:
            print(f"Upload {int(status.progress()*100)}%")
        
        thumb = os.path.join(OUTPUT_DIR, "thumb.png")
        create_thumbnail(content['title'], os.path.join(ASSETS_DIR, "i_l_0.jpg" if not is_short else "i_s_0.jpg"), thumb)  # use first image
        service.thumbnails().set(videoId=req.execute()['id'], media_body=MediaFileUpload(thumb)).execute()
        
        print(f"✅ UPLOADED! {title}")
        save_to_memory("used_rhymes.json", content['title'])
        return True
    except Exception as e: print(f"Upload error: {e}"); return False

if __name__ == "__main__":
    print("===== HINDI MASTI RHYMES – PREMIUM 1080p + SEO v3.0 =====")
    for is_short, name in [(True,"SHORT"), (False,"LONG")]:
        print(f"\n>>> {name} <<<")
        data = generate_content("short" if is_short else "long")
        if data:
            vid, lyrics, times, desc = make_video(data, is_short)
            if vid: upload_video(vid, data, lyrics, times, desc, is_short)
    print("🎉 Daily batch finished! (Faster + Better SEO)")
