import os, random, json, asyncio, requests, time, numpy as np
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'): 
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (AudioFileClip, ImageClip, CompositeVideoClip,
                            concatenate_videoclips, CompositeAudioClip, ColorClip, TextClip)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

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
        json.dump([], open(os.path.join(MEMORY_DIR, f), "w"))

def download_assets():
    if not os.path.exists(FONT_FILE):
        open(FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf", timeout=15).content)
    bg = os.path.join(ASSETS_DIR, "bg_music.mp3")
    if not os.path.exists(bg):
        open(bg, 'wb').write(requests.get("https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3", timeout=15).content)
download_assets()

def load_memory(f):
    p = os.path.join(MEMORY_DIR, f)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else []

def save_to_memory(f, item):
    data = load_memory(f)
    if item not in data:
        data.append(item)
        json.dump(data[-1000:], open(os.path.join(MEMORY_DIR, f), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

def groq_request(prompt):
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.75, "max_tokens": 3000}, timeout=45)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return None

def clean_json(text):
    try: return json.loads(text[text.find('{'):text.rfind('}')+1])
    except: return None

def generate_content(mode="short"):
    used = load_memory("used_topics.json")
    topic_prompt = f"Super cute funny topic for Hindi kids rhyme 2026. Avoid: {', '.join(used[-20:])}. Output ONLY English topic."
    topic = groq_request(topic_prompt) or "Dolphin Playing Veena"

    lines = 8 if mode == "short" else 16
    prompt = f"""You are 2026 ChuChu TV level Hindi kids rhyme expert.
Topic: "{topic}"
Create HIGHLY singable {lines} lines with REPEATING CHORUS (repeat 3x for retention).
Output ONLY valid JSON with MAX SEO 2026:
{{
  "seo_title": "Best 2026 title starting with keyword (e.g. Hindi Nursery Rhymes for Kids 2026 | ... 🦁)",
  "title": "Hindi catchy title",
  "keyword": "Main English character",
  "seo_tags": [array of 40 tags: 10 broad + 20 long-tail like "hindi bal geet for toddlers 2026" + 10 hindi],
  "seo_description": "Full description template with [TIMESTAMPS] placeholder",
  "scenes": [{{"line": "Hindi line", "action": "Pixar cute 3D visual description"}} , ...]]
}}"""
    for _ in range(4):
        data = clean_json(groq_request(prompt))
        if data and len(data.get('seo_tags', [])) > 25:
            data['generated_topic'] = topic
            save_to_memory("used_topics.json", topic)
            return data
    return None

def download_file(url, fn, headers=None):
    try:
        r = requests.get(url, headers=headers or {"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code == 200:
            open(fn, 'wb').write(r.content)
            Image.open(fn).verify()
            return True
    except: pass
    return False

def apply_pro_enhancement(fn, w, h):
    try:
        with Image.open(fn) as im:
            im = im.convert("RGB").resize((w, h), Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(2.2, 320, 4))
            im = ImageEnhance.Contrast(im).enhance(1.22)
            im = ImageEnhance.Color(im).enhance(1.18)
            im.save(fn, "JPEG", quality=98, optimize=True)
    except: pass

def get_image(action, fn, kw, is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    seed = random.randint(0, 999999)
    clean = f"{action}, cute pixar 3d kids cartoon vibrant colors masterpiece 8k sharp".replace(" ", "%20")
    api = os.getenv('POLLINATIONS_API_KEY')
    if api:
        url = f"https://gen.pollinations.ai/image/{clean}?model=flux&width={w}&height={h}&seed={seed}&enhance=true"
        if download_file(url, fn, {"Authorization": f"Bearer {api}"}):
            apply_pro_enhancement(fn, w, h); return
    stock = f"https://loremflickr.com/{w}/{h}/{kw.lower()}/?lock={seed}"
    if download_file(stock, fn): apply_pro_enhancement(fn, w, h)
    else: Image.new('RGB', (w, h), (random.randint(70, 230),)*3).save(fn)

def generate_text_clip_pil(text, w, h, size, dur, color='#FFFF00', pos_y=None, stroke_width=8):
    """Generates perfect Hindi text bypassing ImageMagick crashes"""
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_FILE, size) if os.path.exists(FONT_FILE) else ImageFont.load_default()
    bbox = draw.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = (w - tw) // 2
    y = pos_y if pos_y is not None else (h - th - 340)
    
    for dx in range(-stroke_width, stroke_width+1, 2):
        for dy in range(-stroke_width, stroke_width+1, 2):
            draw.text((x+dx, y+dy), text, font=font, fill='black')
    draw.text((x,y), text, font=font, fill=color)
    return ImageClip(np.array(img)).set_duration(dur)

def create_intro(is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    clip = ColorClip((w, h), (255, 215, 0)).set_duration(2.2)
    txt = generate_text_clip_pil("हिंदी मस्ती राइम्स 🦁 2026", w, h, 95, 2.2, color='white', pos_y=h//2 - 100)
    return CompositeVideoClip([clip, txt], size=(w, h)).crossfadeout(0.5)

def create_outro(is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    clip = ColorClip((w, h), (20, 20, 40)).set_duration(4.5)
    txt1 = generate_text_clip_pil("LIKE 👍 SUBSCRIBE 🦁", w, h, 92, 4.5, pos_y=h//3)
    txt2 = generate_text_clip_pil("@HindiMastiRhymes", w, h, 78, 4.5, color='white', pos_y=int(h*0.6))
    return CompositeVideoClip([clip, txt1, txt2], size=(w, h))

def create_segment(line, img_path, aud_path, is_short, idx):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    voice = AudioFileClip(aud_path)
    
    try:
        bg = AudioFileClip(os.path.join(ASSETS_DIR, "bg_music.mp3")).volumex(0.085)
        if bg.duration < voice.duration: bg = bg.loop(duration=voice.duration)
        else: bg = bg.subclip(random.uniform(0, max(0, bg.duration - voice.duration)), voice.duration)
        audio = CompositeAudioClip([voice, bg])
    except:
        audio = voice

    img = ImageClip(img_path)
    anim = img.resize(lambda t: 1.015 - 0.012 * t).set_position('center').set_duration(voice.duration)

    txt = generate_text_clip_pil(line, w, h, 90 if is_short else 118, voice.duration)
    wm = TextClip("Hindi Masti Rhymes", fontsize=26, color='white', font='Arial').set_position((25,25)).set_duration(voice.duration).set_opacity(0.75)

    clip = CompositeVideoClip([anim, txt, wm], size=(w, h)).set_audio(audio).set_duration(voice.duration)
    if idx > 0: clip = clip.crossfadein(0.45)
    return clip

# === THIS IS THE FIXED SECTION ===
async def generate_voice_async(text, fn):
    proc = await asyncio.create_subprocess_exec("edge-tts", "--voice", "hi-IN-SwaraNeural", "--text", text, "--write-media", fn)
    await proc.wait()

def get_voice(text, fn): 
    asyncio.run(generate_voice_async(text, fn))
# =================================

def make_video(content, is_short=True):
    print(f"🎥 Premium Render {'SHORT' if is_short else 'LONG'}...")
    clips = [create_intro(is_short)]
    suffix = "s" if is_short else "l"
    keyword = content.get('keyword', 'kids')
    full_lyrics = ""
    times = []
    current_time = 2.2

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = []
        for i, scene in enumerate(content['scenes']):
            line = scene['line']
            full_lyrics += f"{i+1}. {line}\n"
            aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
            img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
            futures.append(ex.submit(get_voice, line, aud))
            futures.append(ex.submit(get_image, scene['action'], img, keyword, is_short))
        for f in as_completed(futures): f.result()

    for i, scene in enumerate(content['scenes']):
        aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
        img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
        clip = create_segment(scene['line'], img, aud, is_short, i)
        clips.append(clip)
        times.append(f"{time.strftime('%M:%S', time.gmtime(current_time))} - {scene['line'][:55]}...")
        current_time += clip.duration

    clips.append(create_outro(is_short))
    final = concatenate_videoclips(clips, method="compose")
    out = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    final.write_videofile(out, fps=24, codec='libx264', audio_codec='aac',
                          threads=8, preset='veryfast',
                          ffmpeg_params=['-crf', '20', '-pix_fmt', 'yuv420p'])

    for f in os.listdir(ASSETS_DIR):
        if f.startswith(('a_s_','a_l_','i_s_','i_l_')) and f.endswith(('.mp3','.jpg')):
            try: os.remove(os.path.join(ASSETS_DIR, f))
            except: pass
            
    return out, full_lyrics, times, content.get('seo_description', '')

def create_thumbnail(title, bg_path, out_path, is_short):
    try:
        with Image.open(bg_path) as im:
            im = im.convert("RGB").resize((1280,720), Image.LANCZOS)
            im = ImageEnhance.Contrast(im).enhance(1.28)
            overlay = Image.new("RGBA", (1280,720), (0,0,0,92))
            im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(im)
            font_big = ImageFont.truetype(FONT_FILE, 138) if os.path.exists(FONT_FILE) else ImageFont.load_default()
            font_small = ImageFont.truetype(FONT_FILE, 72) if os.path.exists(FONT_FILE) else ImageFont.load_default()
            x = (1280 - draw.textbbox((0,0), title, font=font_big)[2]) // 2
            for off in [(10,10),(12,12)]: draw.text((x+off[0], 155+off[1]), title, font=font_big, fill=(0,0,0))
            draw.text((x, 155), title, font=font_big, fill="#FFEA00")
            draw.text((380, 480), "2026 🦁 FOR KIDS", font=font_small, fill="#FFFF00")
            im.save(out_path, quality=98, optimize=True)
    except: pass

def upload_video(vid, content, lyrics, times, desc_template, is_short):
    try:
        print(f"🚀 Initializing YouTube Upload for: {content['title']}")
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)
        title = content.get('seo_title', content['title'] + " | Hindi Nursery Rhymes for Kids 2026 🦁")
        tags = content.get('seo_tags', [])[:40]
        desc = f"""{title}

{desc_template.replace('[TIMESTAMPS]', chr(10).join(times))}

🦁 LIKE + SUBSCRIBE + SHARE for daily new rhymes!
#HindiRhymes #BalGeet #NurseryRhymesForKids"""

        body = {
            'snippet': {'title': title[:100], 'description': desc, 'tags': tags, 'categoryId': '24'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': True}
        }
        media = MediaFileUpload(vid, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)
        
        while True:
            status, response = req.next_chunk()
            if status: print(f"   Upload progress: {int(status.progress()*100)}%")
            if response is not None:
                print(f"✅ VIDEO UPLOADED SUCCESS! ID: {response['id']}")
                break

        if not is_short:
            thumb = os.path.join(OUTPUT_DIR, "thumb.png")
            first_img = os.path.join(ASSETS_DIR, "i_l_0.jpg")
            create_thumbnail(content['title'], first_img, thumb, is_short)
            if os.path.exists(thumb):
                print("   Uploading custom thumbnail...")
                service.thumbnails().set(videoId=response['id'], media_body=MediaFileUpload(thumb)).execute()

        save_to_memory("used_rhymes.json", content['title'])
        return True
    except HttpError as e:
        print(f"❌ YouTube API Error (Quota/Auth): {e.reason}")
        return False
    except Exception as e:
        print(f"❌ Upload crash: {e}")
        return False

# ────────────────────────────────────────────────
# MAIN EXECUTION
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("===== HINDI MASTI RHYMES – 2026 ULTIMATE MAX SEO + OPTIMIZED =====")
    for is_short, name in [(True, "SHORT"), (False, "LONG")]:
        print(f"\n>>> GENERATING {name} (Premium 1080p + SEO) <<<")
        data = generate_content("short" if is_short else "long")
        if data:
            vid, lyrics, times, desc = make_video(data, is_short)
            if vid: 
                success = upload_video(vid, data, lyrics, times, desc, is_short)
                if not success:
                    print(f"⚠️ {name} Video created but FAILED to upload to YouTube.")
    print("\n🎉 Daily broadcast workflow completed.")
