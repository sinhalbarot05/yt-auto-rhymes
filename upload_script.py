import os, random, json, asyncio, requests, time, numpy as np, re, math, subprocess, shutil, sys
import urllib.parse
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'): 
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (AudioFileClip, ImageClip, CompositeVideoClip,
                            concatenate_videoclips, CompositeAudioClip, ColorClip,
                            concatenate_audioclips)
from moviepy.audio.AudioClip import AudioArrayClip

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ==========================================
# CONFIGURATION
# ==========================================
MEMORY_DIR = "memory/"
OUTPUT_DIR = "videos/"
ASSETS_DIR = "assets/"
TOKEN_FILE = "youtube_token.pickle"
FONT_FILE = os.path.join(ASSETS_DIR, "HindiFont.ttf")
ENG_FONT_FILE = os.path.join(ASSETS_DIR, "EngFont.ttf")

for d in [MEMORY_DIR, OUTPUT_DIR, ASSETS_DIR]:
    Path(d).mkdir(exist_ok=True)
for f in ["used_topics.json", "used_rhymes.json"]:
    if not os.path.exists(os.path.join(MEMORY_DIR, f)):
        json.dump([], open(os.path.join(MEMORY_DIR, f), "w"))

def download_assets():
    # 🌟 FIX: Wrapped in try/except so network blips on boot don't crash the script
    try:
        if not os.path.exists(FONT_FILE):
            open(FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf", timeout=20).content)
        if not os.path.exists(ENG_FONT_FILE):
            open(ENG_FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf", timeout=20).content)
        bg = os.path.join(ASSETS_DIR, "bg_music_default.mp3")
        if not os.path.exists(bg):
            open(bg, 'wb').write(requests.get("https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3", timeout=30).content)
    except Exception as e:
        print(f"⚠️ Boot Asset Warning: {e}")

download_assets()

def load_memory(f):
    p = os.path.join(MEMORY_DIR, f)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else []

def save_to_memory(f, item):
    data = load_memory(f)
    if item not in data:
        data.append(item)
        json.dump(data[-1000:], open(os.path.join(MEMORY_DIR, f), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

def clean_text_for_font(text, is_english=False):
    if is_english: return re.sub(r'[^\w\s\,\.\!\?\-\@]', '', text).strip()
    else: return re.sub(r'[^\u0900-\u097F\s\,\.\!\?]', '', text).strip()

# ==========================================
# 🎵 BULLETPROOF AUDIO ENGINE
# ==========================================
def fetch_dynamic_background_music(out_path):
    print("🎵 Fetching dynamic background track...")
    safe_audio_tracks = [
        "https://ia800408.us.archive.org/27/items/UpbeatKidsMusic/Upbeat_Kids_Music.mp3",
        "https://ia801402.us.archive.org/16/items/happy-upbeat-background-music/Happy%20Upbeat.mp3",
        "https://ia600504.us.archive.org/33/items/bensound-music/bensound-ukulele.mp3",
        "https://ia800504.us.archive.org/33/items/bensound-music/bensound-buddy.mp3",
        "https://ia801509.us.archive.org/13/items/bensound-music/bensound-clearday.mp3",
        "https://ia801509.us.archive.org/13/items/bensound-music/bensound-littleidea.mp3",
        "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3" # Rock solid raw CDN
    ]
    
    track_url = random.choice(safe_audio_tracks)
    print(f"🔄 Attempting to fetch: {track_url.split('/')[-1]}")
    
    try:
        r = requests.get(track_url, timeout=30)
        r.raise_for_status()
        with open(out_path, 'wb') as f:
            f.write(r.content)
        print("✅ Background Track Downloaded Successfully!")
        return True
    except Exception as e:
        print(f"❌ Audio Fetch Error: {e}. Defaulting to safe fallback.")
        shutil.copyfile(os.path.join(ASSETS_DIR, "bg_music_default.mp3"), out_path)
        return False

# ==========================================
# 🧠 AI BRAIN
# ==========================================
def openai_request(prompt):
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key: return None
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "max_tokens": 2000}, timeout=45)
        if r.status_code == 200: return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: pass
    return None

def groq_request(prompt):
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "max_tokens": 3000}, timeout=45)
        if r.status_code == 200: return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: pass
    return None

def smart_llm_request(prompt):
    res = openai_request(prompt)
    if res: return res
    return groq_request(prompt)

def clean_json(text):
    if not text: return None
    try:
        if "```json" in text: text = text.split("```json")[1].split("```")[0]
        elif "```" in text: text = text.split("```")[1].split("```")[0]
        return json.loads(text[text.find('{'):text.rfind('}')+1])
    except Exception: return None

def generate_content(mode="short"):
    print("\n🧠 Contacting AI for script...")
    used = load_memory("used_topics.json")
    themes = ["Outer Space Planets", "Jungle Safari Animals", "Underwater Ocean Fish", "Magic Trains and Cars", "Dinosaur Friends", "Talking Fruits", "Superheroes", "Construction Trucks", "Flying Vehicles", "Robot Pets", "Brave Birds", "Snowy Penguins", "Farm Animals"]
    theme = random.choice(themes)
    
    topic_prompt = f"Output ONLY a 3-to-4 word English topic for a Hindi kids rhyme about: {theme}. CRITICAL: Do NOT use rabbits, bunnies, cakes, cupcakes, or sweets. Avoid: {', '.join(used[-20:])}."
    topic = smart_llm_request(topic_prompt) or f"Cute {theme}"
    time.sleep(2)

    line_count = 14 if mode == "short" else 26
    prompt = f"""You are a top-tier Hindi children's poet and Pixar Art Director.
Topic: "{topic}"

CRITICAL RHYME RULES:
1. Write EXACTLY {line_count} scenes/lines.
2. Pure Devanagari Hindi ONLY (no English words, no numbers in the rhyme).
3. PERFECT RHYTHM: Every line must have exactly 5 to 7 words.
4. Perfect AABB rhyme scheme.
5. NO EMOJIS in the 'line' or 'title' fields.
6. CRITICAL: NO RABBITS, NO BUNNIES, NO CAKES, NO CUPCAKES.

CRITICAL VISUAL RULES (1-to-1 MATCHING):
7. The 'image_prompt' field is the DIRECT instruction to the AI image generator.
8. It MUST PERFECTLY MATCH the Hindi line. 
9. If the line says a farmer is working, the 'image_prompt' MUST ONLY describe a farmer working in a field.
10. DO NOT force the main character into the scene if the line doesn't mention them. The camera must show EXACTLY what the lyrics say.

Output ONLY valid JSON:
{{
  "seo_title": "Best 2026 title starting with keyword",
  "title": "Hindi catchy title (Devanagari only)",
  "keyword": "Main subject",
  "seo_tags": ["hindi bal geet", "kids rhymes"],
  "seo_description": "Description template with [TIMESTAMPS]",
  "scenes": [{{"line": "5 to 7 word Hindi sentence", "image_prompt": "Highly detailed standalone English description of EXACTLY what should be visible on screen for this specific line."}}]
}}"""
    for attempt in range(4):
        raw = smart_llm_request(prompt)
        data = clean_json(raw)
        if data and "scenes" in data:
            if len(data["scenes"]) < (line_count - 2): continue
            data['generated_topic'] = topic
            save_to_memory("used_topics.json", topic)
            return data
        time.sleep(4)
    return None

# ==========================================
# VIDEO & IMAGE LOGIC
# ==========================================
def download_file(url, fn, headers=None):
    try:
        r = requests.get(url, headers=headers or {"User-Agent": "Mozilla/5.0"}, timeout=45)
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

def get_image(image_prompt, fn, kw, is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    scene_seed = random.randint(0, 999999) 
    
    clean = f"{image_prompt}, Mango Yellow, Royal Blue, Deep Turquoise, 3D Pixar Cocomelon style kids cartoon vibrant masterpiece 8k"
    clean_encoded = urllib.parse.quote(clean)
    
    api = os.getenv('POLLINATIONS_API_KEY')
    if api:
        url = f"https://gen.pollinations.ai/image/{clean_encoded}?model=flux&width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true"
        if download_file(url, fn, {"Authorization": f"Bearer {api}"}):
            apply_pro_enhancement(fn, w, h); return
            
    # 🌟 FIX: Removed loremflickr (ugly cat photos). Failsafe is now a clean branded color backdrop.
    print(f"⚠️ Image API Failed. Creating branded fallback for {fn}")
    brand_colors = [(255, 204, 0), (65, 105, 225), (0, 139, 139)] # Mango, Royal, Turquoise
    img = Image.new('RGB', (w, h), random.choice(brand_colors))
    img.save(fn)

def generate_text_clip_pil(text, w, h, base_size, dur, color='#FFFF00', pos_y=None, pos_x=None, stroke_width=8, is_english=False):
    text = clean_text_for_font(text, is_english)
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    target_font = ENG_FONT_FILE if is_english else FONT_FILE
    max_w = w - 120 
    size = base_size
    
    def get_wrapped_text(t, f):
        words = t.split(); lines, curr = [], ""
        for word in words:
            test = curr + " " + word if curr else word
            if draw.textbbox((0,0), test, font=f)[2] <= max_w: curr = test
            else:
                if curr: lines.append(curr)
                curr = word
        if curr: lines.append(curr)
        return "\n".join(lines)

    font = ImageFont.truetype(target_font, size) if os.path.exists(target_font) else ImageFont.load_default()
    wrapped_text = get_wrapped_text(text, font)
    bbox = draw.multiline_textbbox((0,0), wrapped_text, font=font, align="center")
    
    while (bbox[2] - bbox[0] > max_w) and size > 40:
        size -= 4
        font = ImageFont.truetype(target_font, size)
        wrapped_text = get_wrapped_text(text, font)
        bbox = draw.multiline_textbbox((0,0), wrapped_text, font=font, align="center")
        
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = pos_x if pos_x is not None else (w - tw) // 2
    y = pos_y if pos_y is not None else (h - th - 340)
    
    for dx in range(-stroke_width, stroke_width+1, 2):
        for dy in range(-stroke_width, stroke_width+1, 2):
            draw.multiline_text((x+dx, y+dy), wrapped_text, font=font, fill='black', align="center" if pos_x is None else "left")
    draw.multiline_text((x,y), wrapped_text, font=font, fill=color, align="center" if pos_x is None else "left")
    return ImageClip(np.array(img)).set_duration(dur)

def create_outro(is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    clip = ColorClip((w, h), (15, 15, 20)).set_duration(4.0)
    txt1 = generate_text_clip_pil("LIKE 👍 SUBSCRIBE", w, h, 85, 4.0, pos_y=h//3, is_english=True)
    txt2 = generate_text_clip_pil("@HindiMastiRhymes", w, h, 65, 4.0, color='#AAAAAA', pos_y=int(h*0.55), is_english=True)
    return CompositeVideoClip([clip, txt1, txt2], size=(w, h)).crossfadein(0.5)

def create_segment_unified(line, img_path, is_short, idx, dur):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    
    img = ImageClip(img_path).resize(1.15)
    ex_x, ex_y = img.w - w, img.h - h
    
    camera_move = random.choice(['zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down'])
    if camera_move == 'zoom_in': anim = img.resize(lambda t: 1.0 + 0.15 * (t/dur)).set_position('center')
    elif camera_move == 'zoom_out': anim = img.resize(lambda t: 1.15 - 0.15 * (t/dur)).set_position('center')
    elif camera_move == 'pan_left': anim = img.set_position(lambda t: (-ex_x * (t/dur), 'center'))
    elif camera_move == 'pan_right': anim = img.set_position(lambda t: (-ex_x + (ex_x * (t/dur)), 'center'))
    elif camera_move == 'pan_up': anim = img.set_position(lambda t: ('center', -ex_y * (t/dur)))
    elif camera_move == 'pan_down': anim = img.set_position(lambda t: ('center', -ex_y + (ex_y * (t/dur))))

    anim = anim.set_duration(dur)
    txt = generate_text_clip_pil(line, w, h, 118, dur).crossfadein(0.4)
    wm = generate_text_clip_pil("@HindiMastiRhymes", w, h, 38, dur, color='white', pos_y=40, pos_x=40, stroke_width=2, is_english=True)

    clip = CompositeVideoClip([anim, txt, wm.set_opacity(0.60)], size=(w, h)).set_duration(dur)
    if idx > 0: clip = clip.crossfadein(0.45)
    return clip

def get_voice(text, fn): 
    clean_speech = clean_text_for_font(text, is_english=False)
    if len(clean_speech) < 2: clean_speech = "मस्ती" 
    for attempt in range(5):
        try:
            subprocess.run(["edge-tts", "--voice", "hi-IN-SwaraNeural", "--rate=-10%", "--pitch=+10Hz", "--text", clean_speech, "--write-media", fn], capture_output=True, timeout=15)
            if os.path.exists(fn) and os.path.getsize(fn) > 1000: return True
        except Exception as e: 
            pass 
        time.sleep(random.uniform(1, 3)) 
        
    # 🌟 FIX: If TTS critically fails 5 times, we do NOT replace it with instrumental music.
    # We log a fatal error and return False so the script aborts the broken render.
    print(f"❌ FATAL TTS ERROR: Could not render voice for '{clean_speech[:20]}...'")
    return False

def make_video(content, is_short=True):
    print(f"🎥 Premium Render {'SHORT' if is_short else 'LONG'}...")
    clips = []
    suffix = "s" if is_short else "l"
    keyword = content.get('keyword', 'kids')
    
    full_lyrics_lines = [scene['line'] for scene in content['scenes']]
    full_lyrics_text = "\n".join(full_lyrics_lines)
    
    ai_music_path = os.path.join(ASSETS_DIR, "bg_music_dynamic.mp3") 
    fetch_dynamic_background_music(ai_music_path)
    
    print("🎨 Generating Images and Hindi Voiceovers...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = []
        for i, scene in enumerate(content['scenes']):
            img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
            img_prompt = scene.get('image_prompt', scene.get('action', 'cute kids cartoon'))
            futures.append(ex.submit(get_image, img_prompt, img, keyword, is_short))
            
            aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
            futures.append(ex.submit(get_voice, scene['line'], aud))
        for f in as_completed(futures): f.result()

    times = []
    current_time = 0.0 

    print("🎧 Mixing Edge-TTS Vocals with Dynamic Instrumental...")
    for i, scene in enumerate(content['scenes']):
        aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
        img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
        
        # 🌟 FIX: Hard-abort if the asset generation pipeline failed
        if not os.path.exists(aud):
            print("❌ Critical Audio missing. Aborting render to prevent silent video upload.")
            return None, None, None, None

        voice = AudioFileClip(aud)
        dur = voice.duration
        
        bg_clip = AudioFileClip(ai_music_path).volumex(0.085)
        if bg_clip.duration > 0:
            repeats = int(math.ceil(dur / bg_clip.duration))
            bg_looped = concatenate_audioclips([bg_clip] * repeats).subclip(0, dur)
        else:
            bg_looped = bg_clip
            
        audio = CompositeAudioClip([voice, bg_looped])
        
        clip = create_segment_unified(scene['line'], img, is_short, i, dur).set_audio(audio)
        clips.append(clip)
        times.append(f"{time.strftime('%M:%S', time.gmtime(current_time))} - {scene['line'][:55]}...")
        current_time += clip.duration
        
    clips.append(create_outro(is_short))
    final = concatenate_videoclips(clips, method="compose")

    out = os.path.join(OUTPUT_DIR, f"final_{suffix}.mp4")
    
    # 🌟 FIX: Reduced threads=8 to threads=2. GitHub Ubuntu runners only have 2 CPU cores. 
    # High thread counts cause context-switching deadlock and freeze the pipeline.
    final.write_videofile(out, fps=24, codec='libx264', audio_codec='aac', threads=2, preset='ultrafast', ffmpeg_params=['-crf', '23', '-pix_fmt', 'yuv420p'])
    return out, full_lyrics_text, times, content.get('seo_description', '')

def create_thumbnail(title, bg_path, out_path, is_short):
    try:
        clean_title = clean_text_for_font(title, is_english=False)
        with Image.open(bg_path) as im:
            im = im.convert("RGB").resize((1280,720), Image.LANCZOS)
            im = ImageEnhance.Contrast(im).enhance(1.28)
            overlay = Image.new("RGBA", (1280,720), (0,0,0,92))
            im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(im)
            font_size = 130; max_w = 1180
            def get_wrapped_thumb(t, f):
                words = t.split(); lines, curr = "", ""
                for word in words:
                    test = curr + " " + word if curr else word
                    if draw.textbbox((0,0), test, font=f)[2] <= max_w: curr = test
                    else:
                        if curr: lines.append(curr)
                        curr = word
                if curr: lines.append(curr)
                return "\n".join(lines)
            
            font_big = ImageFont.truetype(FONT_FILE, font_size) if os.path.exists(FONT_FILE) else ImageFont.load_default()
            wrapped_title = get_wrapped_thumb(clean_title, font_big)
            bbox = draw.multiline_textbbox((0,0), wrapped_title, font=font_big, align="center")
            while (bbox[2] - bbox[0] > max_w) and font_size > 50:
                font_size -= 5
                font_big = ImageFont.truetype(FONT_FILE, font_size)
                wrapped_title = get_wrapped_thumb(clean_title, font_big)
                bbox = draw.multiline_textbbox((0,0), wrapped_title, font=font_big, align="center")

            x = (1280 - (bbox[2]-bbox[0])) // 2
            for off in [(6,6),(8,8)]: draw.multiline_text((x+off[0], 120+off[1]), wrapped_title, font=font_big, fill=(0,0,0), align="center")
            draw.multiline_text((x, 120), wrapped_title, font=font_big, fill="#FFEA00", align="center")
            font_small = ImageFont.truetype(ENG_FONT_FILE, 72) if os.path.exists(ENG_FONT_FILE) else ImageFont.load_default()
            draw.text((420, 520), "2026 FOR KIDS", font=font_small, fill="#FFFF00")
            im.save(out_path, quality=98, optimize=True)
    except: pass

def upload_video(vid, content, lyrics, times, desc_template, is_short):
    try:
        print(f"🚀 Initializing YouTube Upload for: {content['title']}")
        with open(TOKEN_FILE, 'rb') as f: creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)
        title = content.get('seo_title', content['title'] + " | Hindi Nursery Rhymes for Kids 2026")
        
        raw_tags = content.get('seo_tags', ['hindi rhymes', 'bal geet', 'kids songs', 'nursery rhymes'])
        valid_tags, total_chars = [], 0
        for tag in raw_tags:
            clean_tag = str(tag).replace('<', '').replace('>', '').replace('"', '').replace(',', '').strip()
            if clean_tag and len(clean_tag) < 50 and total_chars + len(clean_tag) < 450: 
                valid_tags.append(clean_tag)
                total_chars += len(clean_tag) + 1 
        
        desc = f"""{title}\n\n{desc_template.replace('[TIMESTAMPS]', chr(10).join(times))}\n\nLIKE + SUBSCRIBE + SHARE for daily new rhymes!\n#HindiRhymes #BalGeet #NurseryRhymesForKids"""
        body = {
            'snippet': {'title': title[:100], 'description': desc, 'tags': valid_tags, 'categoryId': '24', 'defaultLanguage': 'hi', 'defaultAudioLanguage': 'hi'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': True}
        }
        media = MediaFileUpload(vid, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)
        
        # 🌟 FIX: Chunk upload retry logic in case Google's ingest server drops connection
        response = None
        error_count = 0
        while response is None:
            try:
                status, response = req.next_chunk()
                if status: print(f"   Upload progress: {int(status.progress()*100)}%")
                if response is not None:
                    print(f"✅ VIDEO UPLOADED SUCCESS! ID: {response['id']}")
            except (HttpError, ConnectionResetError, BrokenPipeError) as e:
                error_count += 1
                if error_count > 5:
                    print(f"❌ Upload dropped 5 times. Aborting. {e}")
                    return False
                print(f"⚠️ Upload connection dropped. Retrying {error_count}/5 in 5 seconds...")
                time.sleep(5)

        if not is_short:
            thumb = os.path.join(OUTPUT_DIR, "thumb.png")
            first_img = os.path.join(ASSETS_DIR, "i_l_0.jpg")
            create_thumbnail(content['title'], first_img, thumb, is_short)
            if os.path.exists(thumb):
                service.thumbnails().set(videoId=response['id'], media_body=MediaFileUpload(thumb)).execute()

        save_to_memory("used_rhymes.json", content['title'])
        return True
    except HttpError as e: print(f"❌ YouTube API Error (Quota/Auth): {e.reason}"); return False
    except Exception as e: print(f"❌ Upload crash: {e}"); return False

if __name__ == "__main__":
    print("===== HINDI MASTI RHYMES – 2026 STUDIO MUSIC EDITION =====")
    
    total_successes = 0
    
    for is_short, name in [(True, "SHORT"), (False, "LONG")]:
        print(f"\n>>> GENERATING {name} <<<")
        data = generate_content("short" if is_short else "long")
        if data:
            vid, lyrics, times, desc = make_video(data, is_short)
            if vid: 
                if upload_video(vid, data, lyrics, times, desc, is_short):
                    total_successes += 1
            else:
                print(f"❌ Render failed for {name}. Skipping upload.")
        else: 
            print(f"❌ Critical Failure: Could not generate content for {name}.")
            
    print("\n🎉 Daily broadcast workflow completed.")
    
    # 🌟 FIX: Let GitHub Actions know if the script completely failed
    if total_successes == 0:
        print("🚨 ALL PIPELINES FAILED. Throwing exit code 1 to alert GitHub Actions.")
        sys.exit(1)
