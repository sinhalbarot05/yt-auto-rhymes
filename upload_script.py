import os, random, json, asyncio, requests, time, numpy as np, re, math, subprocess, shutil
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'): 
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (AudioFileClip, ImageClip, CompositeVideoClip,
                            concatenate_videoclips, CompositeAudioClip, ColorClip)
from moviepy.audio.AudioClip import AudioArrayClip

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# CONFIG
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
    if not os.path.exists(FONT_FILE):
        open(FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf", timeout=15).content)
    if not os.path.exists(ENG_FONT_FILE):
        open(ENG_FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf", timeout=15).content)
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

def clean_text_for_font(text, is_english=False):
    if is_english:
        return re.sub(r'[^\w\s\,\.\!\?\-\@]', '', text).strip()
    else:
        return re.sub(r'[^\u0900-\u097F\s\,\.\!\?]', '', text).strip()

def create_pop_sfx():
    fps = 44100
    dur = 0.15
    t = np.linspace(0, dur, int(fps*dur), False)
    freq = np.linspace(400, 800, len(t))
    audio = np.sin(2 * np.pi * freq * t) * np.exp(-25 * t)
    stereo = np.column_stack((audio, audio))
    return AudioArrayClip(stereo, fps=fps).volumex(0.5)

def create_swoosh_sfx():
    fps = 44100
    dur = 0.4
    t = np.linspace(0, dur, int(fps*dur), False)
    audio = np.random.normal(0, 1, len(t)) * (np.sin(np.pi * (t / dur)) ** 2)
    stereo = np.column_stack((audio, audio))
    return AudioArrayClip(stereo, fps=fps).volumex(0.12)

def openai_request(prompt):
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key: return None
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "max_tokens": 2000}, timeout=45)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: pass
    return None

def groq_request(prompt):
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "max_tokens": 3000}, timeout=45)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception: pass
    return None

def smart_llm_request(prompt):
    res = openai_request(prompt)
    if res: return res
    res = groq_request(prompt)
    if res: return res
    return None

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

    # 🌟 FIX 1: ADDED "SETTING" TO KEEP THE WORLD CONSISTENT & ENFORCED ANIMAL SPECIES
    prompt = f"""You are a top-tier Hindi children's poet and Pixar Art Director.
Topic: "{topic}"

CRITICAL RHYME RULES:
1. Write EXACTLY {line_count} scenes/lines.
2. Pure Devanagari Hindi ONLY (no English words, no numbers in the rhyme).
3. PERFECT RHYTHM: Every line must have exactly 5 to 7 words.
4. Perfect AABB rhyme scheme.
5. NO EMOJIS in the 'line' or 'title' fields.
6. CRITICAL: NO RABBITS, NO BUNNIES, NO CAKES, NO CUPCAKES.

CRITICAL VISUAL RULES:
7. Create a 'character_design'. You MUST name a specific animal or human child (e.g., "A chubby baby elephant wearing blue overalls").
8. Create a 'setting'. This is the world where the video happens (e.g., "Inside a colorful moving train", "A bright green jungle").
9. The 'action' field MUST describe EXACTLY what is happening in the Hindi line. 

Output ONLY valid JSON:
{{
  "seo_title": "Best 2026 title starting with keyword",
  "title": "Hindi catchy title (Devanagari only)",
  "keyword": "Main English character",
  "character_design": "Specific animal/child description",
  "setting": "The overall location of the video",
  "seo_tags": ["hindi bal geet", "kids rhymes"],
  "seo_description": "Description template with [TIMESTAMPS]",
  "scenes": [{{"line": "5 to 7 word Hindi sentence", "action": "Highly detailed description of this exact scene"}}]
}}"""
    
    for attempt in range(4):
        raw = smart_llm_request(prompt)
        data = clean_json(raw)
        if data and "scenes" in data and "character_design" in data:
            if len(data["scenes"]) < (line_count - 2):
                print(f"⚠️ AI wrote too few lines ({len(data['scenes'])}). Retrying...")
                continue
                
            data['generated_topic'] = topic
            save_to_memory("used_topics.json", topic)
            return data
        time.sleep(4)
    return None

# ────────────────────────────────────────────────
# VIDEO & IMAGE LOGIC
# ────────────────────────────────────────────────
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

# 🌟 FIX 2: REMOVED MASTER SEED, ADDED "SETTING" TO PROMPT FOR DYNAMIC BACKGROUNDS
def get_image(character_design, setting, action, fn, kw, is_short):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    scene_seed = random.randint(0, 999999) # New seed per scene!
    
    clean = f"{action}. Set in {setting}. Main character: {character_design}. Mango Yellow, Royal Blue, Deep Turquoise, cute pixar 3d kids cartoon vibrant masterpiece 8k".replace(" ", "%20")
    
    api = os.getenv('POLLINATIONS_API_KEY')
    if api:
        url = f"https://gen.pollinations.ai/image/{clean}?model=flux&width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true"
        if download_file(url, fn, {"Authorization": f"Bearer {api}"}):
            apply_pro_enhancement(fn, w, h); return
            
    stock = f"https://loremflickr.com/{w}/{h}/{kw.lower()}/?lock={scene_seed}"
    if download_file(stock, fn): apply_pro_enhancement(fn, w, h)
    else: Image.new('RGB', (w, h), (random.randint(70, 230),)*3).save(fn)

def generate_text_clip_pil(text, w, h, base_size, dur, color='#FFFF00', pos_y=None, pos_x=None, stroke_width=8, is_english=False):
    text = clean_text_for_font(text, is_english)
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    target_font = ENG_FONT_FILE if is_english else FONT_FILE
    
    max_w = w - 120 
    size = base_size
    
    def get_wrapped_text(t, f):
        words = t.split()
        lines, curr = [], ""
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

def create_segment(line, img_path, aud_path, is_short, idx):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    voice = AudioFileClip(aud_path)
    dur = voice.duration
    
    pop_sfx = create_pop_sfx().set_start(0.05)
    swoosh_sfx = create_swoosh_sfx().set_start(0.0)
    
    try:
        bg = AudioFileClip(os.path.join(ASSETS_DIR, "bg_music.mp3")).volumex(0.085)
        if bg.duration < dur: bg = bg.loop(duration=dur)
        else: bg = bg.subclip(random.uniform(0, max(0, bg.duration - dur)), dur)
        audio = CompositeAudioClip([voice, bg, pop_sfx, swoosh_sfx])
    except: 
        audio = CompositeAudioClip([voice, pop_sfx, swoosh_sfx])

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

    def text_bounce(t):
        if t < 0.4:
            offset = 150 * math.exp(-12*t) * math.cos(30*t)
            return ('center', int(offset))
        return ('center', 0)

    txt = generate_text_clip_pil(line, w, h, 118, dur).set_position(text_bounce)
    wm = generate_text_clip_pil("@HindiMastiRhymes", w, h, 38, dur, color='white', pos_y=40, pos_x=40, stroke_width=2, is_english=True)

    clip = CompositeVideoClip([anim, txt, wm.set_opacity(0.60)], size=(w, h)).set_audio(audio).set_duration(dur)
    if idx > 0: clip = clip.crossfadein(0.45)
    return clip

def get_voice(text, fn): 
    clean_speech = clean_text_for_font(text, is_english=False)
    if len(clean_speech) < 2: clean_speech = "मस्ती" 
    
    for attempt in range(5):
        try:
            subprocess.run([
                "edge-tts", "--voice", "hi-IN-SwaraNeural", 
                "--rate=-10%", "--pitch=+10Hz", 
                "--text", clean_speech, "--write-media", fn
            ], capture_output=True)
            if os.path.exists(fn) and os.path.getsize(fn) > 1000:
                return 
        except: pass
        time.sleep(random.uniform(1, 3)) 
        
    try: shutil.copyfile(os.path.join(ASSETS_DIR, "bg_music.mp3"), fn)
    except: pass

def make_video(content, is_short=True):
    print(f"🎥 Premium Render {'SHORT' if is_short else 'LONG'}...")
    clips = []
    suffix = "s" if is_short else "l"
    keyword = content.get('keyword', 'kids')
    character_design = content.get('character_design', 'A cute 3D cartoon character')
    setting = content.get('setting', 'A beautiful colorful 3D world')
    
    full_lyrics, times = "", []
    current_time = 0.0 

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = []
        for i, scene in enumerate(content['scenes']):
            line = scene['line']
            full_lyrics += f"{i+1}. {line}\n"
            aud = os.path.join(ASSETS_DIR, f"a_{suffix}_{i}.mp3")
            img = os.path.join(ASSETS_DIR, f"i_{suffix}_{i}.jpg")
            futures.append(ex.submit(get_voice, line, aud))
            # 🌟 FIX 3: PASSED THE "SETTING" TO THE IMAGE GENERATOR INSTEAD OF SEED
            futures.append(ex.submit(get_image, character_design, setting, scene['action'], img, keyword, is_short))
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
    
    final.write_videofile(out, fps=24, codec='libx264', audio_codec='aac', threads=8, preset='ultrafast', ffmpeg_params=['-crf', '23', '-pix_fmt', 'yuv420p'])

    for f in os.listdir(ASSETS_DIR):
        if f.startswith(('a_s_','a_l_','i_s_','i_l_')) and f.endswith(('.mp3','.jpg')):
            try: os.remove(os.path.join(ASSETS_DIR, f))
            except: pass
            
    return out, full_lyrics, times, content.get('seo_description', '')

def create_thumbnail(title, bg_path, out_path, is_short):
    try:
        clean_title = clean_text_for_font(title, is_english=False)
        with Image.open(bg_path) as im:
            im = im.convert("RGB").resize((1280,720), Image.LANCZOS)
            im = ImageEnhance.Contrast(im).enhance(1.28)
            overlay = Image.new("RGBA", (1280,720), (0,0,0,92))
            im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(im)
            
            font_size = 130 
            max_w = 1180
            
            def get_wrapped_thumb(t, f):
                words = t.split()
                lines, curr = [], ""
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
            
            for off in [(6,6),(8,8)]: 
                draw.multiline_text((x+off[0], 120+off[1]), wrapped_title, font=font_big, fill=(0,0,0), align="center")
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
    except HttpError as e: print(f"❌ YouTube API Error (Quota/Auth): {e.reason}"); return False
    except Exception as e: print(f"❌ Upload crash: {e}"); return False

if __name__ == "__main__":
    print("===== HINDI MASTI RHYMES – 2026 ULTIMATE MAX SEO + OPTIMIZED =====")
    for is_short, name in [(True, "SHORT"), (False, "LONG")]:
        print(f"\n>>> GENERATING {name} (Premium 1080p + SEO) <<<")
        data = generate_content("short" if is_short else "long")
        if data:
            vid, lyrics, times, desc = make_video(data, is_short)
            if vid: upload_video(vid, data, lyrics, times, desc, is_short)
        else: print(f"❌ Critical Failure: Could not generate content for {name}.")
    print("\n🎉 Daily broadcast workflow completed.")
