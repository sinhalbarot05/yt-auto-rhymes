import os, random, json, requests, time, numpy as np, re, math, subprocess, shutil, sys, io
import urllib.parse
from pathlib import Path
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (AudioFileClip, ImageClip, CompositeVideoClip,
                            concatenate_videoclips, CompositeAudioClip, ColorClip,
                            concatenate_audioclips)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ==========================================
# CORE 1: CONFIGURATION & STATE
# ==========================================
class Config:
    MEMORY_DIR = "memory/"
    OUTPUT_DIR = "videos/"
    ASSETS_DIR = "assets/"
    TOKEN_FILE = "youtube_token.pickle"
    FONT_FILE = os.path.join(ASSETS_DIR, "HindiFont.ttf")
    ENG_FONT_FILE = os.path.join(ASSETS_DIR, "EngFont.ttf")
    BRAND_COLORS = [(255, 204, 0), (65, 105, 225), (0, 139, 139)] # Mango Yellow, Royal Blue, Deep Turquoise
    CHANNEL_HANDLE = "@HindiMastiRhymes"

    @staticmethod
    def initialize():
        for d in [Config.MEMORY_DIR, Config.OUTPUT_DIR, Config.ASSETS_DIR]:
            Path(d).mkdir(exist_ok=True)
        
        # Ensure default files exist
        for f in ["used_topics.json", "used_rhymes.json"]:
            path = os.path.join(Config.MEMORY_DIR, f)
            if not os.path.exists(path):
                with open(path, "w", encoding='utf-8') as file:
                    json.dump([], file)

        # Download strict dependencies
        if not os.path.exists(Config.FONT_FILE):
            open(Config.FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf", timeout=20).content)
        if not os.path.exists(Config.ENG_FONT_FILE):
            open(Config.ENG_FONT_FILE, 'wb').write(requests.get("https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf", timeout=20).content)
        
        bg_music = os.path.join(Config.ASSETS_DIR, "bg_music_default.mp3")
        if not os.path.exists(bg_music):
            open(bg_music, 'wb').write(requests.get("https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3", timeout=30).content)

class StorageEngine:
    """Handles all persistent memory (so we don't repeat content)."""
    @staticmethod
    def load(filename):
        path = os.path.join(Config.MEMORY_DIR, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    @staticmethod
    def save(filename, item):
        data = StorageEngine.load(filename)
        if item not in data:
            data.append(item)
            with open(os.path.join(Config.MEMORY_DIR, filename), 'w', encoding='utf-8') as f:
                json.dump(data[-1000:], f, ensure_ascii=False, indent=2)

# ==========================================
# CORE 2: THE INTELLIGENCE (LLM)
# ==========================================
class IntelligenceEngine:
    """Handles Groq/OpenAI with strict JSON parsing and fallback logic."""
    @staticmethod
    def _call_api(url, key, model, prompt, max_tokens):
        if not key: return None
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"},
                              json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "max_tokens": max_tokens}, timeout=45)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception: pass
        return None

    @staticmethod
    def ask(prompt):
        # 1. Try OpenAI
        res = IntelligenceEngine._call_api("https://api.openai.com/v1/chat/completions", os.getenv('OPENAI_API_KEY'), "gpt-4o-mini", prompt, 2000)
        if res: return res
        # 2. Fallback to Groq
        return IntelligenceEngine._call_api("https://api.groq.com/openai/v1/chat/completions", os.getenv('GROQ_API_KEY'), "llama-3.3-70b-versatile", prompt, 3000)

    @staticmethod
    def extract_json(text):
        if not text: return None
        try:
            marker = '`' * 3
            if marker + 'json' in text:
                text = text.split(marker + 'json')[1].split(marker)[0]
            elif marker in text:
                text = text.split(marker)[1].split(marker)[0]
            
            text = text.strip()
            if text.startswith('['):
                return json.loads(text[text.find('['):text.rfind(']')+1])
            else:
                return json.loads(text[text.find('{'):text.rfind('}')+1])
        except Exception: return None

class ContentStrategist:
    """Generates the viral script using strict Hindi logic."""
    VIRAL_THEMES = [
        "Yellow JCB Excavator Digging Mud", "Red Tractor Driving in Village Farm", "Big Red Fire Truck Rescue", "Police Car Chasing Thieves",
        "Colorful Choo Choo Train on Tracks", "Giant Monster Truck Jumping", "Garbage Truck Cleaning the City", "Flying Helicopter Rescue",
        "Hathi Raja (King Elephant) Dancing", "Naughty Bandar Mama (Monkey) Eating Bananas", "Sher Khan (Lion King) Roaring loudly", "Chalak Lomdi (Clever Fox) Running",
        "Pyaasa Kauwa (Thirsty Crow) Drinking Water", "Dancing Mor (Colorful Peacock) in Rain", "Bhalu (Bear) Dancing in Jungle", "Kachhua (Slow Turtle) Winning Race",
        "Moti Kutta (Chubby Dog) Barking", "Billi Mausi (Aunt Cat) Drinking Milk", "Happy Baby Brushing Teeth Song", "Crying Baby Takes a Bubble Bath",
        "Toddler Eating Healthy Green Vegetables", "Baby Going to Sleep Lullaby", "Getting Dressed for School Morning", "Washing Hands with Soap Song",
        "Sharing Toys with Friends", "Funny Bhoot (Friendly Ghost) in House", "Naughty Baby Hiding from Mummy", "Five Little Monkeys Jumping on Bed",
        "Baby Falling Down and Crying loudly", "Magic Flying Carpet in Starry Sky", "Rainbow Unicorn Flying in Clouds", "Talking Colorful Ice Cream Cones",
        "Dancing Mangoes and Apples", "Beautiful Mermaid in Deep Blue Ocean", "Glowing Fireflies in Dark Forest", "Magic Wand Changing Colors",
        "Mummy and Papa Loving Baby", "Dada Dadi (Grandparents) Telling Story", "Playing with Little Sister", "Baby Helping Mummy in Kitchen"
    ]

    ARCHETYPES = [
        "adorable little Indian girl, big brown eyes, bright pink lehenga", "cute chubby Indian baby boy, curly hair, yellow kurta",
        "friendly baby animal matching the theme, cute costume", "magical glowing fairy, tiny wings, pastel purple and gold",
        "cute funny round robot, blinking LED eyes, colorful buttons", "brave little Indian superhero toddler, tiny cape and mask",
        "cheerful baby alien, big blue eyes, shiny silver suit", "playful little Indian boy, chef outfit, tiny white hat",
        "energetic baby girl, astronaut white and orange suit", "tiny talking animal sidekick duo, one big, one small"
    ]

    @staticmethod
    def get_theme(used_topics):
        available = [t for t in ContentStrategist.VIRAL_THEMES if t not in used_topics[-100:]]
        if len(available) < 5:
            print("🧠 Expanding brain: Generating new viral themes...")
            prompt = "You are a YouTube India Kids strategist. Generate 15 BRAND NEW, highly viral Hindi toddler video topics (like JCBs, animals, magic). Output ONLY a valid JSON list of 15 English strings."
            raw = IntelligenceEngine.ask(prompt)
            new_themes = IntelligenceEngine.extract_json(raw)
            if isinstance(new_themes, list) and len(new_themes) > 5:
                available.extend(new_themes)
        return random.choice(available) if available else random.choice(ContentStrategist.VIRAL_THEMES)

    @staticmethod
    def create_script():
        used = StorageEngine.load("used_topics.json")
        theme = ContentStrategist.get_theme(used)
        archetype = random.choice(ContentStrategist.ARCHETYPES)
        
        topic_prompt = f"Output ONLY a 3-to-4 word English topic for a Hindi kids rhyme about: {theme}. No rabbits, cakes, sweets. Avoid: {', '.join(used[-20:])}."
        topic = IntelligenceEngine.ask(topic_prompt) or f"Cute {theme}"
        
        prompt = f"""You are a native Hindi children's poet and a YouTube India SEO expert.
Topic: "{topic}"
Archetype: [{archetype}]

━━ STRICT HINDI LINGUISTIC RULES ━━
1. Write EXACTLY 14 scenes/lines.
2. PERFECT HINDI GRAMMAR & GENDER (लिंग): Ensure masculine/feminine words match perfectly.
3. PURE DEVANAGARI STRICT LOCK: MUST use ONLY standard Devanagari. NO Emojis. NO English/Roman letters mixed inside Hindi words. DO NOT transliterate English words into Hindi script (e.g., do NOT write "मिश्चिव" for mischievous, use "नटखट").
4. RHYTHM & RHYME: 4 to 8 words per line. Bouncy meter. AABB rhyme scheme. NEVER force a rhyme over good grammar.
5. NO LITERAL TRANSLATIONS: Write naturally like an Indian mother.

━━ VISUAL & SEO RULES ━━
6. Protagonist: Describe in 12-15 English words using Mango Yellow, Royal Blue, or Deep Turquoise. EVERY image_prompt MUST start with this exact description.
7. TITLE: Create a SHORT, natural Hindi catchphrase (2 to 4 words). Format EXACTLY: "Short Hindi Catchphrase | English | 3D बालगीत 2026 | हिंदी राइम्स फॉर किड्स" (Note correct spelling of बालगीत).
8. Generate 30 SEO tags and a 250-word description with [TIMESTAMPS] and [LYRICS] placeholders.

Output ONLY valid JSON:
{{
  "title": "Short Hindi | English | 3D बालगीत 2026 | हिंदी राइम्स फॉर किड्स",
  "keyword": "searchable english word",
  "seo_tags": ["tag1","tag2"],
  "seo_description": "...",
  "main_character": "12-15 word English description",
  "scenes": [{{"line": "4-8 word pure Devanagari sentence", "image_prompt": "character description + action"}}]
}}"""
        for _ in range(4):
            raw = IntelligenceEngine.ask(prompt)
            data = IntelligenceEngine.extract_json(raw)
            if data and "scenes" in data and len(data["scenes"]) >= 12:
                StorageEngine.save("used_topics.json", topic)
                print(f"✅ Script Generated: {data['title']}")
                return data
            time.sleep(4)
        return None

# ==========================================
# CORE 3: ASSET FACTORY (Hydra Image + Edge TTS + Audio)
# ==========================================
class AssetEngine:
    """Handles robust file downloading, image generation, and voice synthesis."""
    
    @staticmethod
    def _download(url, filepath):
        session = requests.Session()
        retry = Retry(total=4, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods={"GET"})
        session.mount('https://', HTTPAdapter(max_retries=retry))
        try:
            r = session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=35)
            r.raise_for_status()
            if 'image' not in r.headers.get('Content-Type', '').lower(): return False
            try: Image.open(io.BytesIO(r.content)).verify()
            except Exception: return False
            with open(filepath, 'wb') as f: f.write(r.content)
            return True
        except Exception: return False

    @staticmethod
    def fetch_dynamic_background_music(out_path):
        print("🎵 Fetching dynamic background track...")
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
            shutil.copyfile(os.path.join(Config.ASSETS_DIR, "bg_music_default.mp3"), out_path)
            return False

    @staticmethod
    def generate_image(prompt, filepath, fallback_kw, seed):
        w, h = 1080, 1920
        scene_seed = seed + random.randint(1, 100)
        clean_prompt = urllib.parse.quote(f"{prompt}, Mango Yellow, Royal Blue, Deep Turquoise, 3D Pixar Cocomelon style kids cartoon vibrant masterpiece 8k")
        api = os.getenv('POLLINATIONS_API_KEY')
        
        # Layer 1 & 2: Pollinations (Auth -> Public)
        urls = []
        if api: urls.append(f"https://gen.pollinations.ai/image/{clean_prompt}?model=flux&width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true")
        urls.append(f"https://image.pollinations.ai/prompt/{clean_prompt}?width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true")
        # Layer 3: LoremFlickr Stock
        urls.append(f"https://loremflickr.com/{w}/{h}/{urllib.parse.quote(fallback_kw or 'cartoon kids')}?lock={scene_seed}")

        success = False
        for url in urls:
            if AssetEngine._download(url, filepath):
                success = True
                break
        
        # Enhance or Layer 4 (Color Block)
        if success:
            try:
                with Image.open(filepath) as im:
                    im = im.convert("RGB").resize((w, h), Image.LANCZOS)
                    im = ImageEnhance.Color(im).enhance(1.15)
                    im = ImageEnhance.Contrast(im).enhance(1.10)
                    im.save(filepath, "JPEG", quality=98, optimize=True)
            except Exception: pass
        else:
            print("🚨 All image layers failed. Generating brand block.")
            Image.new('RGB', (w, h), random.choice(Config.BRAND_COLORS)).save(filepath)

    @staticmethod
    def generate_voice(text, filepath):
        # Strict fallback sanitization to protect edge-tts from symbols
        clean_speech = re.sub(r'[^\u0900-\u097F\s\,\.\!\?]', '', text).strip()
        if len(clean_speech) < 2: clean_speech = "मस्ती"
        
        for _ in range(5):
            try:
                subprocess.run(["edge-tts", "--voice", "hi-IN-SwaraNeural", "--rate=-10%", "--pitch=+10Hz", "--text", clean_speech, "--write-media", filepath], capture_output=True, timeout=15)
                if os.path.exists(filepath) and os.path.getsize(filepath) > 1000: return True
            except Exception: pass
            time.sleep(random.uniform(1, 3))
        return False

# ==========================================
# CORE 4: VIDEO STUDIO (MoviePy)
# ==========================================
class VideoStudio:
    """Assembles the final video using dynamic camera moves and text overlays."""
    
    @staticmethod
    def _create_text_overlay(text, w, h, size, dur, color='#FFFF00', y_pos=None, is_eng=False):
        clean_text = re.sub(r'[^\w\s\,\.\!\?\-\@]', '', text).strip() if is_eng else re.sub(r'[^\u0900-\u097F\s\,\.\!\?]', '', text).strip()
        img = Image.new('RGBA', (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        font_path = Config.ENG_FONT_FILE if is_eng else Config.FONT_FILE
        
        font = ImageFont.truetype(font_path, size) if os.path.exists(font_path) else ImageFont.load_default()
        
        # Simple word wrap
        max_w = w - 120
        words = clean_text.split()
        lines, curr = [], ""
        for word in words:
            test = curr + " " + word if curr else word
            if draw.textbbox((0,0), test, font=font)[2] <= max_w: curr = test
            else:
                if curr: lines.append(curr)
                curr = word
        if curr: lines.append(curr)
        wrapped = "\n".join(lines)
        
        # Scale down if too tall
        bbox = draw.multiline_textbbox((0,0), wrapped, font=font, align="center")
        while (bbox[2]-bbox[0] > max_w) and size > 40:
            size -= 4
            font = ImageFont.truetype(font_path, size)
            bbox = draw.multiline_textbbox((0,0), wrapped, font=font, align="center")

        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        x = (w - tw) // 2
        y = y_pos if y_pos is not None else (h - th - 340)

        # Draw stroke then text
        stroke = 8
        draw.multiline_text((x+6, y+6), wrapped, font=font, fill=(0,0,0,160), align="center")
        for dx in range(-stroke, stroke+1, 2):
            for dy in range(-stroke, stroke+1, 2):
                draw.multiline_text((x+dx, y+dy), wrapped, font=font, fill='black', align="center")
        draw.multiline_text((x,y), wrapped, font=font, fill=color, align="center")
        return ImageClip(np.array(img)).set_duration(dur)

    @staticmethod
    def render_short(script_data):
        print("🎬 Assembling Studio Short...")
        master_seed = random.randint(1000, 999999)
        kw = script_data.get('keyword', 'kids')
        
        bgm_path = os.path.join(Config.ASSETS_DIR, "bg_music_dynamic.mp3")
        AssetEngine.fetch_dynamic_background_music(bgm_path)

        # Parallel Generation
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = []
            for i, scene in enumerate(script_data['scenes']):
                img_path = os.path.join(Config.ASSETS_DIR, f"img_{i}.jpg")
                aud_path = os.path.join(Config.ASSETS_DIR, f"aud_{i}.mp3")
                futures.append(ex.submit(AssetEngine.generate_image, scene.get('image_prompt', 'cartoon'), img_path, kw, master_seed))
                futures.append(ex.submit(AssetEngine.generate_voice, scene['line'], aud_path))
            for f in as_completed(futures): f.result()

        clips = []
        timestamps = []
        current_time = 0.0
        w, h = 1080, 1920

        for i, scene in enumerate(script_data['scenes']):
            img_path = os.path.join(Config.ASSETS_DIR, f"img_{i}.jpg")
            aud_path = os.path.join(Config.ASSETS_DIR, f"aud_{i}.mp3")
            if not os.path.exists(aud_path): return None, None, None # Fail safe
            
            # Audio mix (Voice + Reverb + BGM)
            voice = AudioFileClip(aud_path)
            echo = voice.volumex(0.25).set_start(0.18)
            enhanced_voice = CompositeAudioClip([voice, echo]).set_duration(voice.duration + 0.3)
            dur = enhanced_voice.duration
            
            bgm = AudioFileClip(bgm_path).volumex(0.085).audio_fadein(2.0)
            bg_looped = concatenate_audioclips([bgm] * int(math.ceil(dur/bgm.duration))).subclip(0, dur) if bgm.duration > 0 else bgm
            
            # Video mix (Camera Pan + Text)
            img = ImageClip(img_path).resize(1.15)
            ex_x, ex_y = img.w - w, img.h - h
            move = random.choice(['zoom_in','zoom_out','pan_left','pan_right','pan_up','pan_down'])
            
            if move=='zoom_in': anim = img.resize(lambda t: 1.0 + 0.15*(t/dur)).set_position('center')
            elif move=='zoom_out': anim = img.resize(lambda t: 1.15 - 0.15*(t/dur)).set_position('center')
            elif move=='pan_left': anim = img.set_position(lambda t: (-ex_x*(t/dur), 'center'))
            elif move=='pan_right': anim = img.set_position(lambda t: (-ex_x + (ex_x*(t/dur)), 'center'))
            elif move=='pan_up': anim = img.set_position(lambda t: ('center', -ex_y*(t/dur)))
            else: anim = img.set_position(lambda t: ('center', -ex_y + (ex_y*(t/dur))))
            
            anim = anim.set_duration(dur)
            txt = VideoStudio._create_text_overlay(scene['line'], w, h, 118, dur).crossfadein(0.4)
            wm = VideoStudio._create_text_overlay(Config.CHANNEL_HANDLE, w, h, 38, dur, color='white', y_pos=40, is_eng=True).set_opacity(0.6)
            
            clip = CompositeVideoClip([anim, txt, wm], size=(w,h)).set_audio(CompositeAudioClip([enhanced_voice, bg_looped])).set_duration(dur)
            if i > 0: clip = clip.crossfadein(0.4)
            
            clips.append(clip)
            timestamps.append(f"{time.strftime('%M:%S', time.gmtime(current_time))} - {scene['line'][:55]}...")
            current_time += dur

        out_path = os.path.join(Config.OUTPUT_DIR, "final_short.mp4")
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(out_path, fps=24, codec='libx264', audio_codec='aac', threads=2, preset='medium', ffmpeg_params=['-crf','19','-pix_fmt','yuv420p'])
        
        lyrics = "\n".join([s['line'] for s in script_data['scenes']])
        return out_path, lyrics, timestamps

# ==========================================
# CORE 5: BROADCASTER (YouTube Upload)
# ==========================================
class Broadcaster:
    """Handles safe YouTube metadata truncation and API uploading."""
    
    @staticmethod
    def upload(video_path, script_data, lyrics, timestamps):
        try:
            print(f"🚀 Broadcaster Authenticating...")
            with open(Config.TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
            service = build('youtube', 'v3', credentials=creds)

            # Metadata Sanitization
            title = script_data.get('title', "Hindi Nursery Rhymes for Kids 2026")
            if len(title) > 97: title = title[:97] + "..."
            
            ai_tags = script_data.get('seo_tags', [])
            base_tags = ["hindi nursery rhymes", "balgeet", "bachon ke geet", "3d hindi rhymes", "shorts"]
            valid_tags, char_count = [], 0
            for tag in list(dict.fromkeys(ai_tags + base_tags)):
                clean = re.sub(r'[<>",#|\[\]{}\n\r]', '', str(tag)).strip()
                if 2 < len(clean) < 40 and char_count + len(clean) < 350:
                    valid_tags.append(clean)
                    char_count += len(clean) + 1

            lyrics_block = lyrics[:3500] + "\n... [Truncated]" if len(lyrics) > 3500 else lyrics
            time_block = "\n".join(timestamps)
            
            desc_template = script_data.get('seo_description', '')
            desc_body = desc_template.replace('[TIMESTAMPS]', time_block).replace('[LYRICS]', lyrics_block)
            
            desc = (f"{title}\n\n{desc_body}\n\n"
                    f"📌 TIMESTAMPS:\n{time_block}\n\n"
                    f"📝 LYRICS:\n{lyrics_block}\n\n"
                    f"👍 LIKE | SUBSCRIBE | SHARE ↗️\n"
                    f"#HindiRhymes #Balgeet #Shorts #KidsCartoon")

            body = {
                'snippet': {
                    'title': title, 'description': desc, 'tags': valid_tags,
                    'categoryId': '24', 'defaultLanguage': 'hi', 'defaultAudioLanguage': 'hi'
                },
                'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': True}
            }

            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            req = service.videos().insert(part="snippet,status", body=body, media_body=media)

            response, errors = None, 0
            while response is None:
                try:
                    status, response = req.next_chunk()
                    if status: print(f"Upload: {int(status.progress() * 100)}%")
                except (HttpError, ConnectionResetError, BrokenPipeError) as e:
                    errors += 1
                    if errors > 5: return False
                    print(f"Connection dropped. Retrying {errors}/5...")
                    time.sleep(5)

            print(f"✅ UPLOAD SUCCESS! ID: {response['id']}")
            StorageEngine.save("used_rhymes.json", title)
            return True
        except Exception as e:
            print(f"🚨 Broadcaster Crash: {e}")
            return False

def system_cleanup():
    print("🧹 First Principles Cleanup: Purging temporary assets...")
    for f in os.listdir(Config.ASSETS_DIR):
        if not f.endswith(('.ttf', 'default.mp3')):
            try: os.unlink(os.path.join(Config.ASSETS_DIR, f))
            except Exception: pass

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__=="__main__":
    print(f"===== {Config.CHANNEL_HANDLE} - FIRST PRINCIPLES ENGINE =====")
    Config.initialize()
    
    script_data = ContentStrategist.create_script()
    if script_data:
        vid_path, lyrics, times = VideoStudio.render_short(script_data)
        if vid_path:
            success = Broadcaster.upload(vid_path, script_data, lyrics, times)
            if not success: sys.exit(1)
        else:
            print("❌ Video Assembly Failed.")
            sys.exit(1)
    else:
        print("❌ Intelligence Engine Failed.")
        sys.exit(1)
        
    system_cleanup()
    print("🏁 Pipeline execution perfect.")
