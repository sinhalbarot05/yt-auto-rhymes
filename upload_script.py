import os, random, json, requests, time, numpy as np, re, math, subprocess, shutil, sys, io
import urllib.parse
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (AudioFileClip, ImageClip, CompositeVideoClip,
                            concatenate_videoclips, CompositeAudioClip, ColorClip,
                            concatenate_audioclips)

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
    try:
        if not os.path.exists(FONT_FILE):
            open(FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf", timeout=20).content)
        if not os.path.exists(ENG_FONT_FILE):
            open(ENG_FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf", timeout=20).content)
        bg = os.path.join(ASSETS_DIR, "bg_music_default.mp3")
        if not os.path.exists(bg):
            open(bg, 'wb').write(requests.get("https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3", timeout=30).content)
    except Exception as e:
        print(f"Boot Asset Warning: {e}")
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

def fetch_dynamic_background_music(out_path):
    print("Fetching dynamic background track...")
    safe_audio_tracks = [
        "https://ia800408.us.archive.org/27/items/UpbeatKidsMusic/Upbeat_Kids_Music.mp3",
        "https://ia801402.us.archive.org/16/items/happy-upbeat-background-music/Happy%20Upbeat.mp3",
        "https://ia600504.us.archive.org/33/items/bensound-music/bensound-ukulele.mp3",
        "https://ia800504.us.archive.org/33/items/bensound-music/bensound-buddy.mp3",
        "https://ia801509.us.archive.org/13/items/bensound-music/bensound-clearday.mp3",
        "https://ia801509.us.archive.org/13/items/bensound-music/bensound-littleidea.mp3",
        "https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3"
    ]
    try:
        r = requests.get(random.choice(safe_audio_tracks), timeout=30)
        r.raise_for_status()
        with open(out_path, 'wb') as f:
            f.write(r.content)
        return True
    except Exception:
        shutil.copyfile(os.path.join(ASSETS_DIR, "bg_music_default.mp3"), out_path)
        return False

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
    return openai_request(prompt) or groq_request(prompt)

def clean_json(text):
    if not text: return None
    try:
        # 🛡️ FIX: Avoid literal markdown backticks so UI parser doesn't break
        marker = '`' * 3
        json_marker = marker + 'json'
        if json_marker in text:
            text = text.split(json_marker)[1].split(marker)[0]
        elif marker in text:
            text = text.split(marker)[1].split(marker)[0]
        return json.loads(text[text.find('{'):text.rfind('}')+1])
    except Exception: return None

def generate_content(mode="short"):
    print("\nContacting AI for script, SEO, and character design...")
    used = load_memory("used_topics.json")
    
    # ── 50 HYPER-VIRAL INDIAN TODDLER THEMES ──
    themes = [
        "Yellow JCB Excavator Digging Mud", "Red Tractor Driving in Village Farm",
        "Big Red Fire Truck Rescue", "Police Car Chasing Thieves",
        "Colorful Choo Choo Train on Tracks", "Giant Monster Truck Jumping",
        "Garbage Truck Cleaning the City", "Flying Helicopter Rescue",
        "Hathi Raja (King Elephant) Dancing", "Naughty Bandar Mama (Monkey) Eating Bananas",
        "Sher Khan (Lion King) Roaring loudly", "Chalak Lomdi (Clever Fox) Running",
        "Pyaasa Kauwa (Thirsty Crow) Drinking Water", "Dancing Mor (Colorful Peacock) in Rain",
        "Bhalu (Bear) Dancing in Jungle", "Kachhua (Slow Turtle) Winning Race",
        "Moti Kutta (Chubby Dog) Barking", "Billi Mausi (Aunt Cat) Drinking Milk",
        "Happy Baby Brushing Teeth Song", "Crying Baby Takes a Bubble Bath",
        "Toddler Eating Healthy Green Vegetables", "Baby Going to Sleep Lullaby",
        "Getting Dressed for School Morning", "Washing Hands with Soap Song",
        "Sharing Toys with Friends", "Funny Bhoot (Friendly Ghost) in House",
        "Naughty Baby Hiding from Mummy", "Five Little Monkeys Jumping on Bed",
        "Baby Falling Down and Crying loudly", "Magic Flying Carpet in Starry Sky",
        "Rainbow Unicorn Flying in Clouds", "Talking Colorful Ice Cream Cones",
        "Dancing Mangoes and Apples", "Beautiful Mermaid in Deep Blue Ocean",
        "Glowing Fireflies in Dark Forest", "Magic Wand Changing Colors",
        "Mummy and Papa Loving Baby", "Dada Dadi (Grandparents) Telling Story",
        "Playing with Little Sister", "Baby Helping Mummy in Kitchen"
    ]

    available_themes = [t for t in themes if t not in used[-40:]]
    if not available_themes:
        available_themes = themes
    theme = random.choice(available_themes)

    archetypes = [
        "an adorable little Indian girl with big brown eyes in a bright pink lehenga",
        "a cute chubby Indian baby boy with curly hair in a yellow kurta",
        "a friendly baby animal perfectly matching the video theme (species, color, costume)",
        "a magical glowing fairy with tiny wings in pastel purple and gold",
        "a cute funny round robot with blinking LED eyes and colorful buttons",
        "a brave little Indian superhero toddler wearing a tiny cape and mask",
        "a cheerful baby alien with big blue eyes and a shiny silver suit",
        "a playful little Indian boy dressed as a chef with a tiny white hat",
        "an energetic baby girl dressed as an astronaut in a white and orange suit",
        "a tiny talking animal sidekick duo — one big, one small, same theme"
    ]
    archetype = random.choice(archetypes)
    topic_prompt = f"Output ONLY a 3-to-4 word English topic for a Hindi kids rhyme about: {theme}. CRITICAL: Do NOT use rabbits, bunnies, cakes, cupcakes, or sweets. Avoid: {', '.join(used[-20:])}."
    topic = smart_llm_request(topic_prompt) or f"Cute {theme}"
    time.sleep(2)
    line_count = 14 if mode == "short" else 26
    
    prompt = f"""You are a native Hindi-speaking children's poet and a top YouTube India SEO expert.
Topic: "{topic}"
Character archetype: [{archetype}]

━━ NATIVE HINDI LINGUISTIC RULES (CRITICAL) ━━
1. Write EXACTLY {line_count} scenes/lines.
2. PERFECT HINDI GRAMMAR: The rhyme must sound completely natural, like a classic Indian balgeet (similar to "मछली जल की रानी है"). Avoid clunky literal translations. Use simple, lovely, conversational Hindi words for toddlers (e.g., use "प्यारा तोता" instead of unnatural words).
3. PURE DEVANAGARI: Use 100% correct Hindi spelling. NEVER mix English, Roman, or Cyrillic letters in the Hindi text. 
4. PERFECT RHYTHM (तुकबंदी): Focus on a bouncy, sing-song meter. Lines must be 4 to 8 words long. 
5. RHYME SCHEME: AABB. (Lines 1 & 2 rhyme perfectly, Lines 3 & 4 rhyme perfectly, etc.). NEVER sacrifice Hindi grammar just to force a rhyme.

━━ CHARACTER CONSISTENCY RULES ━━
6. Design ONE protagonist matching the archetype. Describe clothes, color, and ONE unique feature in exactly 12–15 English words.
7. EVERY image_prompt MUST start with the exact protagonist description word-for-word.
8. Scene 1 image_prompt MUST show the character doing something energetic (jumping, flying, dancing).

━━ ADVANCED SEO RULES ━━
9. TITLE: Create a highly clickable, grammatically perfect Hindi title. 
   Format EXACTLY: "Perfect Hindi Catchphrase | English Translation | 3D Balgeet 2026 | Hindi Rhymes for Kids"
   Example: "प्यारा तोता उड़ गया | Cute Flying Parrot | 3D Balgeet 2026 | Hindi Rhymes for Kids"
10. SEO_TAGS: Generate exactly 30 tags (mix of broad, specific, long-tail, and Devanagari).
11. SEO_DESCRIPTION: 250 words total with hook sentence, [TIMESTAMPS] placeholder, and [LYRICS] placeholder.

Output ONLY valid JSON:
{{
  "title": "Grammatically Perfect Hindi | English | 3D Balgeet 2026 | Hindi Rhymes for Kids",
  "keyword": "single most searchable English word for this topic",
  "seo_tags": ["tag1","tag2"],
  "seo_description": "Full description with [TIMESTAMPS] and [LYRICS] placeholders",
  "main_character": "Exactly 12-15 word English visual description of protagonist",
  "scenes": [{{"line": "4-8 word perfectly grammatical Devanagari Hindi sentence", "image_prompt": "protagonist description + energetic action"}}]
}}"""
    
    for attempt in range(4):
        raw = smart_llm_request(prompt)
        data = clean_json(raw)
        if data and "scenes" in data and "main_character" in data:
            if len(data["scenes"]) < (line_count - 2): continue
            data['generated_topic'] = topic
            save_to_memory("used_topics.json", topic)
            print(f"Character: {data['main_character']}")
            print(f"SEO Title: {data['title']}")
            return data
        time.sleep(4)
    return None

# ==========================================
# 🛡️ THE HYDRA IMAGE ENGINE (4-LAYER FALLBACK)
# ==========================================
def download_file(url, fn, headers=None):
    session = requests.Session()
    retry = Retry(
        total=4, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET"}, raise_on_status=False
    )
    session.mount('https://', HTTPAdapter(max_retries=retry))
    session.mount('http://',  HTTPAdapter(max_retries=retry))

    try:
        r = session.get(
            url,
            headers=headers or {"User-Agent": "Mozilla/5.0"},
            timeout=35
        )
        r.raise_for_status()

        if 'image' not in r.headers.get('Content-Type', '').lower():
            print(f"   ↳ Non-image Content-Type rejected: {r.headers.get('Content-Type')}")
            return False

        try:
            Image.open(io.BytesIO(r.content)).verify()
        except Exception as e:
            print(f"   ↳ Corrupted image bytes rejected: {e}")
            return False

        with open(fn, 'wb') as f:
            f.write(r.content)
        return True

    except Exception as e:
        print(f"   ↳ Download failed [{url[:50]}...]: {e}")
        return False

def get_image(image_prompt, fn, kw, is_short, video_seed):
    w, h = (1080, 1920) if is_short else (1920, 1080)
    scene_seed = video_seed + random.randint(1, 50)

    clean = (
        f"{image_prompt}, Mango Yellow, Royal Blue, Deep Turquoise, "
        f"3D Pixar Cocomelon style kids cartoon vibrant masterpiece 8k"
    )
    clean_encoded = urllib.parse.quote(clean)
    api = os.getenv('POLLINATIONS_API_KEY')
    success = False

    if api:
        url_auth = (
            f"https://gen.pollinations.ai/image/{clean_encoded}"
            f"?model=flux&width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true"
        )
        success = download_file(url_auth, fn, {"Authorization": f"Bearer {api}"})

    if not success:
        print("   ↳ Layer 1 failed. Trying Layer 2 (public Pollinations)...")
        time.sleep(2)
        url_pub = (
            f"https://image.pollinations.ai/prompt/{clean_encoded}"
            f"?width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true"
        )
        success = download_file(url_pub, fn)

    if not success:
        print("   ↳ Layer 2 failed. Trying Layer 3 (LoremFlickr stock photo)...")
        kw_encoded = urllib.parse.quote(kw or "colorful kids cartoon")
        url_stock = f"https://loremflickr.com/{w}/{h}/{kw_encoded}?lock={scene_seed}"
        success = download_file(url_stock, fn)

    if success:
        try:
            with Image.open(fn) as im:
                im = im.convert("RGB").resize((w, h), Image.LANCZOS)
                im = ImageEnhance.Color(im).enhance(1.15)
                im = ImageEnhance.Contrast(im).enhance(1.10)
                im = ImageEnhance.Sharpness(im).enhance(1.20)
                im.save(fn, "JPEG", quality=98, optimize=True)
        except Exception as e:
            print(f"   ↳ Color grade skipped (image preserved): {e}")
        return

    print(f"🚨 All network layers failed. Generating branded color block.")
    brand_colors = [(255, 204, 0), (65, 105, 225), (0, 139, 139)]
    Image.new('RGB', (w, h), random.choice(brand_colors)).save(fn)

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

    while (bbox[2]-bbox[0] > max_w) and size > 40:
        size -= 4
        font = ImageFont.truetype(target_font, size)
        wrapped_text = get_wrapped_text(text, font)
        bbox = draw.multiline_textbbox((0,0), wrapped_text, font=font, align="center")

    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = pos_x if pos_x is not None else (w-tw)//2
    y = pos_y if pos_y is not None else (h-th-340)

    draw.multiline_text((x+6, y+6), wrapped_text, font=font, fill=(0,0,0,160), align="center" if pos_x is None else "left")
    for dx in range(-stroke_width, stroke_width+1, 2):
        for dy in range(-stroke_width, stroke_width+1, 2):
            draw.multiline_text((x+dx, y+dy), wrapped_text, font=font, fill='black', align="center" if pos_x is None else "left")
    draw.multiline_text((x,y), wrapped_text, font=font, fill=color, align="center" if pos_x is None else "left")
    return ImageClip(np.array(img)).set_duration(dur)

def create_outro(is_short):
    w, h = (1080,1920) if is_short else (1920,1080)
    clip = ColorClip((w,h),(15,15,20)).set_duration(4.0)
    txt1 = generate_text_clip_pil("LIKE SUBSCRIBE", w, h, 85, 4.0, pos_y=h//3, is_english=True)
    txt2 = generate_text_clip_pil("@HindiMastiRhymes", w, h, 65, 4.0, color='#AAAAAA', pos_y=int(h*0.55), is_english=True)
    return CompositeVideoClip([clip,txt1,txt2],size=(w,h)).crossfadein(0.5)

def create_segment_unified(line, img_path, is_short, idx, dur):
    w, h = (1080,1920) if is_short else (1920,1080)
    img = ImageClip(img_path).resize(1.15)
    ex_x, ex_y = img.w-w, img.h-h
    camera_move = random.choice(['zoom_in','zoom_out','pan_left','pan_right','pan_up','pan_down'])
    if camera_move=='zoom_in': anim=img.resize(lambda t:1.0+0.15*(t/dur)).set_position('center')
    elif camera_move=='zoom_out': anim=img.resize(lambda t:1.15-0.15*(t/dur)).set_position('center')
    elif camera_move=='pan_left': anim=img.set_position(lambda t:(-ex_x*(t/dur),'center'))
    elif camera_move=='pan_right': anim=img.set_position(lambda t:(-ex_x+(ex_x*(t/dur)),'center'))
    elif camera_move=='pan_up': anim=img.set_position(lambda t:('center',-ex_y*(t/dur)))
    elif camera_move=='pan_down': anim=img.set_position(lambda t:('center',-ex_y+(ex_y*(t/dur))))
    anim=anim.set_duration(dur)
    txt=generate_text_clip_pil(line,w,h,118,dur).crossfadein(0.4)
    wm=generate_text_clip_pil("@HindiMastiRhymes",w,h,38,dur,color='white',pos_y=40,pos_x=40,stroke_width=2,is_english=True)
    clip=CompositeVideoClip([anim,txt,wm.set_opacity(0.60)],size=(w,h)).set_duration(dur)
    if idx>0: clip=clip.crossfadein(0.45)
    return clip

def get_voice(text, fn):
    clean_speech = clean_text_for_font(text, is_english=False)
    if len(clean_speech)<2: clean_speech="मस्ती"
    for attempt in range(5):
        try:
            subprocess.run(["edge-tts","--voice","hi-IN-SwaraNeural","--rate=-10%","--pitch=+10Hz","--text",clean_speech,"--write-media",fn],capture_output=True,timeout=15)
            if os.path.exists(fn) and os.path.getsize(fn)>1000: return True
        except Exception: pass
        time.sleep(random.uniform(1,3))
    print(f"FATAL TTS ERROR: Could not render voice for '{clean_speech[:20]}...'")
    return False

def make_video(content, is_short=True):
    print(f"Premium Render {'SHORT' if is_short else 'LONG'}...")
    clips=[]
    suffix="s" if is_short else "l"
    keyword=content.get('keyword','kids')
    full_lyrics_lines=[scene['line'] for scene in content['scenes']]
    full_lyrics_text="\n".join(full_lyrics_lines)
    ai_music_path=os.path.join(ASSETS_DIR,f"bg_music_dynamic_{suffix}.mp3")
    fetch_dynamic_background_music(ai_music_path)
    video_master_seed=random.randint(1000,999999)

    print("Generating Images and Voiceovers in parallel...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures=[]
        for i,scene in enumerate(content['scenes']):
            img=os.path.join(ASSETS_DIR,f"i_{suffix}_{i}.jpg")
            img_prompt=scene.get('image_prompt',scene.get('action','cute kids cartoon'))
            futures.append(ex.submit(get_image,img_prompt,img,keyword,is_short,video_master_seed))
            aud=os.path.join(ASSETS_DIR,f"a_{suffix}_{i}.mp3")
            futures.append(ex.submit(get_voice,scene['line'],aud))
        for f in as_completed(futures): f.result()

    times=[]
    current_time=0.0
    print("Applying Studio Reverb + BGM...")
    for i,scene in enumerate(content['scenes']):
        aud=os.path.join(ASSETS_DIR,f"a_{suffix}_{i}.mp3")
        img=os.path.join(ASSETS_DIR,f"i_{suffix}_{i}.jpg")
        if not os.path.exists(aud):
            print("Critical Audio missing. Aborting render.")
            return None,None,None,None
        voice=AudioFileClip(aud)
        echo=voice.volumex(0.25).set_start(0.18)
        enhanced_voice=CompositeAudioClip([voice,echo]).set_duration(voice.duration+0.3)
        dur=enhanced_voice.duration
        bg_clip=AudioFileClip(ai_music_path).volumex(0.085).audio_fadein(2.5).audio_fadeout(2.5)
        if bg_clip.duration>0:
            repeats=int(math.ceil(dur/bg_clip.duration))
            bg_looped=concatenate_audioclips([bg_clip]*repeats).subclip(0,dur)
        else:
            bg_looped=bg_clip
        final_audio=CompositeAudioClip([enhanced_voice,bg_looped])
        clip=create_segment_unified(scene['line'],img,is_short,i,dur).set_audio(final_audio)
        clips.append(clip)
        times.append(f"{time.strftime('%M:%S',time.gmtime(current_time))} - {scene['line'][:55]}...")
        current_time+=clip.duration

    if not is_short:
        clips.append(create_outro(is_short))

    final=concatenate_videoclips(clips,method="compose")
    out=os.path.join(OUTPUT_DIR,f"final_{suffix}.mp4")

    final.write_videofile(out,fps=24,codec='libx264',audio_codec='aac',threads=2,
                          preset='medium',ffmpeg_params=['-crf','19','-pix_fmt','yuv420p'])
    return out,full_lyrics_text,times,content.get('seo_description','')

def create_thumbnail(title, bg_path, out_path, is_short):
    try:
        short_title = title.split('|')[0].strip() if '|' in title else title
        clean_title = clean_text_for_font(short_title, is_english=False)
        
        with Image.open(bg_path) as im:
            im = im.convert("RGB").resize((1280, 720), Image.LANCZOS)
            im = ImageEnhance.Color(im).enhance(1.4)
            im = ImageEnhance.Contrast(im).enhance(1.2)
            
            draw = ImageDraw.Draw(im)
            font_size = 95
            font_big = ImageFont.truetype(FONT_FILE, font_size) if os.path.exists(FONT_FILE) else ImageFont.load_default()
            
            bbox = draw.textbbox((0,0), clean_title, font=font_big)
            tw = bbox[2] - bbox[0]
            
            while tw > 1180 and font_size > 50:
                font_size -= 5
                font_big = ImageFont.truetype(FONT_FILE, font_size)
                bbox = draw.textbbox((0,0), clean_title, font=font_big)
                tw = bbox[2] - bbox[0]
            
            x = (1280 - tw) // 2
            y = 570 
            
            stroke_width = 8
            for dx in range(-stroke_width, stroke_width+1, 2):
                for dy in range(-stroke_width, stroke_width+1, 2):
                    draw.text((x+dx, y+dy), clean_title, font=font_big, fill='black')
            
            draw.text((x, y), clean_title, font=font_big, fill="#FFCC00")
            im.save(out_path, quality=98, optimize=True)
            print("✅ High-CTR Thumbnail Generated.")
    except Exception as e:
        print(f"Thumbnail warning: {e}")

def upload_video(vid, content, lyrics, times, desc_template, is_short):
    try:
        print(f"Uploading: {content['title']}")
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
        service = build('youtube', 'v3', credentials=creds)

        title = content.get('title', "Hindi Nursery Rhymes for Kids 2026")
        keyword = content.get('keyword', 'kids')
        topic_tag = keyword.replace(' ', '')

        baseline_tags = [
            "hindi nursery rhymes", "balgeet", "bachon ke geet",
            "hindi rhymes for kids", "hindi bal geet",
            "3d hindi rhymes for toddlers", "hindi rhymes for 2 year old",
            "hindi nursery rhymes with lyrics", "balgeet with lyrics",
            "3d animated hindi rhymes", "cartoon rhymes hindi",
            "preschool hindi songs", "hindi kids songs 2026",
            "infobells hindi", "cocomelon hindi", "kids channel india",
            "hindi kavita", "bal geet 3d", "nursery rhymes in hindi",
            "hindi rhymes compilation",
        ]
        ai_tags = content.get('seo_tags', [])
        all_tags = list(dict.fromkeys(ai_tags + baseline_tags))

        valid_tags, total_chars = [], 0
        for tag in all_tags:
            clean_tag = re.sub(r'[<>",#|\[\]{}\n\r]', '', str(tag)).strip()
            
            if len(clean_tag) > 2 and len(clean_tag) < 40:
                if total_chars + len(clean_tag) < 350:
                    valid_tags.append(clean_tag)
                    total_chars += len(clean_tag) + 1 

        timestamps_block = "\n".join(times) if times else ""
        lyrics_block     = lyrics if lyrics else ""

        if len(lyrics_block) > 3500:
            lyrics_block = lyrics_block[:3500] + "\n... [Lyrics Truncated]"

        desc_body = desc_template \
            .replace('[TIMESTAMPS]', timestamps_block) \
            .replace('[LYRICS]', lyrics_block)

        hashtag_line = (
            "#HindiRhymes #Balgeet #BachonKeGeet #HindiNurseryRhymes "
            "#KidsSongs #3DCartoon #BalGeet #HindiKids #NurseryRhymes "
            f"#KidsCartoon #Shorts #{topic_tag}"
        )

        desc = (
            f"{title}\n\n"
            f"{desc_body}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 CHAPTERS / TIMESTAMPS:\n{timestamps_block}\n\n"
            f"📝 LYRICS:\n{lyrics_block}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"LIKE 👍 | SUBSCRIBE 🔔 | SHARE ↗️\n"
            f"नई rhymes हर रोज़! New Hindi rhymes every day!\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{hashtag_line}"
        )

        body = {
            'snippet': {
                'title': (title[:97] + '...') if len(title) > 100 else title,
                'description': desc,
                'tags': valid_tags,        
                'categoryId': '24',            
                'defaultLanguage': 'hi',
                'defaultAudioLanguage': 'hi',
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': True,
            }
        }

        media = MediaFileUpload(vid, chunksize=-1, resumable=True)
        req = service.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        error_count = 0
        while response is None:
            try:
                status, response = req.next_chunk()
                if status:
                    print(f"Upload progress: {int(status.progress() * 100)}%")
                if response is not None:
                    print(f"✅ VIDEO UPLOADED! ID: {response['id']}")
            except (HttpError, ConnectionResetError, BrokenPipeError) as e:
                error_count += 1
                if error_count > 5:
                    print(f"Upload dropped 5 times. Aborting. {e}")
                    return False
                print(f"Connection dropped. Retrying {error_count}/5...")
                time.sleep(5)

        if not is_short:
            thumb = os.path.join(OUTPUT_DIR, "thumb.png")
            first_img = os.path.join(ASSETS_DIR, "i_l_0.jpg")
            create_thumbnail(content['title'], first_img, thumb, is_short)
            if os.path.exists(thumb):
                service.thumbnails().set(
                    videoId=response['id'],
                    media_body=MediaFileUpload(thumb)
                ).execute()
                print("✅ Thumbnail uploaded.")

        save_to_memory("used_rhymes.json", content['title'])
        return True

    except HttpError as e:
        print(f"YouTube API Error: {e.reason}")
        return False
    except Exception as e:
        print(f"Upload crash: {e}")
        return False

if __name__=="__main__":
    print("===== HINDI MASTI RHYMES - 2026 BROADCAST EDITION =====")
    total_successes=0
    # 🚀 SHORTS-ONLY MODE (4x a day schedule)
    for is_short,name in [(True,"SHORT")]:
        print(f"\n>>> GENERATING {name} <<<")
        data=generate_content("short" if is_short else "long")
        if data:
            vid,lyrics,times,desc=make_video(data,is_short)
            if vid:
                if upload_video(vid,data,lyrics,times,desc,is_short): total_successes+=1
            else: print(f"Render failed for {name}. Skipping upload.")
        else: print(f"Critical Failure: Could not generate content for {name}.")
    print("\nDaily broadcast workflow completed.")
    if total_successes==0:
        print("ALL PIPELINES FAILED. Throwing exit code 1.")
        sys.exit(1)
