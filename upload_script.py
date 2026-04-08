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

from moviepy.editor import (AudioFileClip, ImageClip, VideoFileClip, CompositeVideoClip,
                            concatenate_videoclips, CompositeAudioClip, ColorClip,
                            concatenate_audioclips)
import moviepy.video.fx.all as vfx
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
        
        for f in ["used_topics.json", "used_rhymes.json"]:
            path = os.path.join(Config.MEMORY_DIR, f)
            if not os.path.exists(path):
                with open(path, "w", encoding='utf-8') as file:
                    json.dump([], file)

        if not os.path.exists(Config.FONT_FILE):
            open(Config.FONT_FILE, 'wb').write(requests.get("[https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf](https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf)", timeout=20).content)
        if not os.path.exists(Config.ENG_FONT_FILE):
            open(Config.ENG_FONT_FILE, 'wb').write(requests.get("[https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf](https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf)", timeout=20).content)
        
        bg_music = os.path.join(Config.ASSETS_DIR, "bg_music_default.mp3")
        if not os.path.exists(bg_music):
            open(bg_music, 'wb').write(requests.get("[https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3](https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3)", timeout=30).content)

class StorageEngine:
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
# CORE 2: THE INTELLIGENCE (HIT SONGWRITER)
# ==========================================
class IntelligenceEngine:
    @staticmethod
    def _call_api(name, url, key, model, prompt, max_tokens):
        if not key: 
            return None
        try:
            payload = {
                "model": model, 
                "messages": [{"role": "user", "content": prompt}], 
                "temperature": 0.95, 
                "top_p": 0.95,
                "max_tokens": max_tokens
            }
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=45)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            pass
        return None

    @staticmethod
    def ask(prompt):
        print("🧠 Engaging Omni-Fallback Intelligence Engine (Songwriter Mode)...")
        res = IntelligenceEngine._call_api("OpenAI", "[https://api.openai.com/v1/chat/completions](https://api.openai.com/v1/chat/completions)", os.getenv('OPENAI_API_KEY'), "gpt-4o-mini", prompt, 2000)
        if res: return res
        
        print("   ↳ 🔄 Falling back to Groq...")
        res = IntelligenceEngine._call_api("Groq", "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)", os.getenv('GROQ_API_KEY'), "llama-3.3-70b-versatile", prompt, 3000)
        if res: return res
        
        print("   ↳ 🔄 Falling back to WaveSpeed...")
        res = IntelligenceEngine._call_api("WaveSpeed", "[https://api.wavespeed.ai/v1/chat/completions](https://api.wavespeed.ai/v1/chat/completions)", os.getenv('WAVESPEED_API_KEY'), "llama-3-70b", prompt, 3000) 
        if res: return res
        return None

    @staticmethod
    def extract_json(text):
        if not text: return None
        try:
            # BUGFIX: Using chr(96) to generate backticks dynamically so it doesn't break the UI markdown
            marker = chr(96) * 3 
            if marker + 'json' in text: text = text.split(marker + 'json')[1].split(marker)[0]
            elif marker in text: text = text.split(marker)[1].split(marker)[0]
            text = text.strip()
            if text.startswith('['): return json.loads(text[text.find('['):text.rfind(']')+1])
            else: return json.loads(text[text.find('{'):text.rfind('}')+1])
        except Exception: return None

class ContentStrategist:
    VIRAL_THEMES = [
        "Chote Bachon Ka Khilona (Small Kids Colorful Toys) Playing",
        "Giant Green T-Rex Dinosaur Roaring loudly",
        "Cute Baby Dinosaur Hatching from Egg",
        "Toy Train and Building Blocks for Kids",
        "Mango Yellow JCB Excavator Digging Mud", 
        "Red Toy Tractor Driving in Village Farm", 
        "Big Red Toy Fire Truck Rescue", 
        "Police Car Toy Chasing Thieves",
        "Colorful Choo Choo Toy Train on Tracks", 
        "Giant Monster Truck Toy Jumping", 
        "Garbage Truck Toy Cleaning the City", 
        "Flying Helicopter Toy Rescue",
        "Remote Control Racing Car Zooming",
        "Naughty Toy Robot Driving a Tractor",
        "Cute Plush Dinosaur Riding a Train"
    ]

    ARCHETYPES = [
        "premium 3D plastic Mango Yellow toy robot with glowing eyes", 
        "cute plush Deep Turquoise baby dinosaur toy",
        "glossy Royal Blue plastic toy tractor with big wheels", 
        "vibrant 3D plastic toy train engine",
        "cute chunky Mango Yellow toy JCB excavator"
    ]

    @staticmethod
    def get_theme(used_topics):
        available = [t for t in ContentStrategist.VIRAL_THEMES if t not in used_topics[-100:]]
        return random.choice(available) if available else random.choice(ContentStrategist.VIRAL_THEMES)

    @staticmethod
    def create_script():
        used = StorageEngine.load("used_topics.json")
        theme = ContentStrategist.get_theme(used)
        archetype = random.choice(ContentStrategist.ARCHETYPES)
        topic_prompt = f"Output ONLY a 3-to-4 word English topic for a Hindi kids rhyme about: {theme}. Focus on toys/vehicles. Avoid: {', '.join(used[-20:])}."
        topic = IntelligenceEngine.ask(topic_prompt) or f"Cute Toy {theme}"
        
        prompt = f"""You are a top YouTube India Kids SEO expert and a HIT CHILDREN'S SONGWRITER.
Topic: "{topic}"
Archetype: [{archetype}]

━━ VIRAL SONG & RETENTION RULES ━━
1. Write EXACTLY 14 scenes. 
2. MAKE IT MUSICAL: Use a highly repetitive, catchy chorus rhythm. It MUST be easy to sing-along for 2-5 year olds.
3. THE INFINITE LOOP: The rhyme must be a perfect loop. Line 14 MUST seamlessly lead right back into Line 1.

━━ HINDI RULES (CRITICAL) ━━
4. PERFECT HINDI GRAMMAR. Keep it to 5-7 simple words per line. AABB rhyme scheme.
5. PURE DEVANAGARI STRICT LOCK FOR ON-SCREEN LYRICS. NO emojis in the 'line' field.

━━ VISUAL & METADATA RULES ━━
6. Image Prompt: Start EVERY prompt with: "{archetype}. High-contrast, hyper-vibrant, bright lighting, plastic toy store aesthetic. [Action]"
7. TITLE: Create a HIGH-CTR clickbait title. Format: "Short Catchy Hindi | English + 2 Emojis | 3D बालगीत 2026 | हिंदी राइम्स फॉर किड्स"

━━ FEW-SHOT EXAMPLE OF A PERFECT MUSICAL RHYTHM ━━
Scene 1: "लाल ट्रैक्टर चला भई चला"
Scene 2: "गांव की सैर को यह निकला"
Scene 3: "पीले पहिए घूमते जाएं"
Scene 4: "सब बच्चों को यह हंसाएं"

Output ONLY valid JSON:
{{
  "title": "Hindi | English [emojis] | 3D बालगीत 2026 | हिंदी राइम्स फॉर किड्स",
  "keyword": "searchable english word",
  "seo_tags": ["tag1","tag2"],
  "seo_description": "...",
  "main_character": "archetype description",
  "scenes": [{{"line": "Pure Devanagari sentence", "image_prompt": "character description + toy aesthetic + action"}}]
}}"""
        for _ in range(4):
            raw = IntelligenceEngine.ask(prompt)
            data = IntelligenceEngine.extract_json(raw)
            if data and "scenes" in data and len(data["scenes"]) >= 12:
                StorageEngine.save("used_topics.json", topic)
                print(f"✅ Hit Song Script Generated: {data['title']}")
                return data
            time.sleep(4)
        return None

# ==========================================
# CORE 3: ASSET FACTORY (ARMOR-PLATED HYDRA)
# ==========================================
class AssetEngine:
    @staticmethod
    def _get_pollinations_keys():
        """ARMOR-PLATED KEY EXTRACTOR: Ignores brackets, quotes, and whitespace."""
        raw_keys = os.getenv('POLLINATIONS_API_KEY', '')
        if not raw_keys: return []
        
        valid_keys = re.findall(r'(sk_[a-zA-Z0-9_-]+)', raw_keys)
        if valid_keys: return valid_keys
        
        cleaned = re.sub(r'[\[\]\"\'\s]', '', raw_keys)
        return [k for k in cleaned.split(',') if k]

    @staticmethod
    def _download_with_rotation(url, filepath, custom_timeout=60, type_label="Asset"):
        keys = AssetEngine._get_pollinations_keys()
        
        if not keys:
            print(f"   ↳ ⚠️ No keys found. Trying {type_label} on public tier...")
            return AssetEngine._execute_download(url, filepath, None, custom_timeout, type_label)

        for index, key in enumerate(keys):
            headers = {"Authorization": f"Bearer {key}", "User-Agent": "Mozilla/5.0"}
            print(f"   ↳ Attempting {type_label} with Key #{index + 1}...")
            
            success = AssetEngine._execute_download(url, filepath, headers, custom_timeout, type_label)
            if success: return True
            else: print(f"   ↳ ⚠️ Key #{index + 1} failed. Rotating...")
        
        print(f"   ↳ ❌ All available Pollinations keys failed for {type_label}.")
        return False

    @staticmethod
    def _execute_download(url, filepath, headers, custom_timeout, type_label):
        session = requests.Session()
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retry))
        try:
            r = session.get(url, headers=headers, timeout=custom_timeout, proxies={"http": None, "https": None})
            
            if r.status_code == 200:
                content_type = r.headers.get('Content-Type', '').lower()
                is_image = 'image' in content_type
                is_media = 'video' in content_type or 'audio' in content_type or 'mpeg' in content_type or 'mp4' in content_type
                
                if not (is_image or is_media): return False
                if is_image:
                    try: Image.open(io.BytesIO(r.content)).verify()
                    except Exception: return False
                if is_media and len(r.content) < 5000: return False
                    
                with open(filepath, 'wb') as f: f.write(r.content)
                return True
            else:
                print(f"      ↳ API Error {r.status_code}: {r.text[:50]}")
                return False
        except Exception as e:
            print(f"      ↳ Network Error: {str(e)[:40]}")
            return False

    @staticmethod
    def generate_pollinations_audio(text, filepath):
        encoded = urllib.parse.quote(text)
        url = f"[https://gen.pollinations.ai/audio/](https://gen.pollinations.ai/audio/){encoded}?model=music"
        return AssetEngine._download_with_rotation(url, filepath, custom_timeout=90, type_label="Audio")

    @staticmethod
    def generate_pollinations_video(prompt, filepath):
        clean_prompt = urllib.parse.quote(f"{prompt}, Mango Yellow, Royal Blue, Deep Turquoise, 3D Pixar Cocomelon style kids cartoon vibrant masterpiece 8k")
        url = f"[https://gen.pollinations.ai/video/](https://gen.pollinations.ai/video/){clean_prompt}?duration=4&fps=24"
        return AssetEngine._download_with_rotation(url, filepath, custom_timeout=150, type_label="Video")

    @staticmethod
    def generate_image(prompt, filepath, fallback_kw, seed):
        w, h = 1080, 1920
        scene_seed = seed + random.randint(1, 100)
        clean_prompt = urllib.parse.quote(f"{prompt}, Mango Yellow, Royal Blue, Deep Turquoise, 3D Pixar Cocomelon style kids cartoon vibrant masterpiece 8k")
        
        url_premium = f"[https://gen.pollinations.ai/image/](https://gen.pollinations.ai/image/){clean_prompt}?model=flux&width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true"
        url_public = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){clean_prompt}?width={w}&height={h}&nologo=true&seed={scene_seed}&enhance=true"
        
        if AssetEngine._download_with_rotation(url_premium, filepath, custom_timeout=60, type_label="Image"):
            pass 
        elif AssetEngine._execute_download(url_public, filepath, None, 45, "Image Fallback"):
            pass 
        else:
            Image.new('RGB', (w, h), random.choice(Config.BRAND_COLORS)).save(filepath)
            return

        try:
            with Image.open(filepath) as im:
                im = im.convert("RGB").resize((w, h), Image.LANCZOS)
                im = ImageEnhance.Color(im).enhance(1.15)
                im = ImageEnhance.Contrast(im).enhance(1.10)
                im.save(filepath, "JPEG", quality=98, optimize=True)
        except Exception: pass

    @staticmethod
    def generate_voice(text, filepath):
        clean_speech = re.sub(r'[^\u0900-\u097F\s\,\.\!\?]', '', text).strip()
        if len(clean_speech) < 2: clean_speech = "मस्ती"
        for _ in range(5):
            try:
                subprocess.run(["edge-tts", "--voice", "hi-IN-SwaraNeural", "--rate=+5%", "--pitch=+20Hz", "--text", clean_speech, "--write-media", filepath], capture_output=True, timeout=15)
                if os.path.exists(filepath) and os.path.getsize(filepath) > 1000: return True
            except Exception: pass
            time.sleep(random.uniform(1, 3))
        return False

    @staticmethod
    def fetch_dynamic_background_music(out_path):
        print("🎵 Fetching dynamic background track...")
        safe_audio_tracks = [
            "[https://ia800408.us.archive.org/27/items/UpbeatKidsMusic/Upbeat_Kids_Music.mp3](https://ia800408.us.archive.org/27/items/UpbeatKidsMusic/Upbeat_Kids_Music.mp3)",
            "[https://ia801402.us.archive.org/16/items/happy-upbeat-background-music/Happy%20Upbeat.mp3](https://ia801402.us.archive.org/16/items/happy-upbeat-background-music/Happy%20Upbeat.mp3)",
            "[https://ia600504.us.archive.org/33/items/bensound-music/bensound-ukulele.mp3](https://ia600504.us.archive.org/33/items/bensound-music/bensound-ukulele.mp3)",
            "[https://ia800504.us.archive.org/33/items/bensound-music/bensound-buddy.mp3](https://ia800504.us.archive.org/33/items/bensound-music/bensound-buddy.mp3)",
            "[https://ia801509.us.archive.org/13/items/bensound-music/bensound-clearday.mp3](https://ia801509.us.archive.org/13/items/bensound-music/bensound-clearday.mp3)",
            "[https://ia801509.us.archive.org/13/items/bensound-music/bensound-littleidea.mp3](https://ia801509.us.archive.org/13/items/bensound-music/bensound-littleidea.mp3)",
            "[https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3](https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3)"
        ]
        try:
            r = requests.get(random.choice(safe_audio_tracks), timeout=30, proxies={"http": None, "https": None})
            r.raise_for_status()
            with open(out_path, 'wb') as f:
                f.write(r.content)
            return True
        except Exception:
            shutil.copyfile(os.path.join(Config.ASSETS_DIR, "bg_music_default.mp3"), out_path)
            return False

# ==========================================
# CORE 4: VIDEO STUDIO 
# ==========================================
class VideoStudio:
    @staticmethod
    def _create_text_overlay(text, w, h, size, dur, color='#FFFF00', y_pos=None, is_eng=False):
        clean_text = re.sub(r'[^\w\s\,\.\!\?\-\@]', '', text).strip() if is_eng else re.sub(r'[^\u0900-\u097F\s\,\.\!\?]', '', text).strip()
        img = Image.new('RGBA', (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        font_path = Config.ENG_FONT_FILE if is_eng else Config.FONT_FILE
        font = ImageFont.truetype(font_path, size) if os.path.exists(font_path) else ImageFont.load_default()
        
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
        
        bbox = draw.multiline_textbbox((0,0), wrapped, font=font, align="center")
        while (bbox[2]-bbox[0] > max_w) and size > 40:
            size -= 4
            font = ImageFont.truetype(font_path, size)
            bbox = draw.multiline_textbbox((0,0), wrapped, font=font, align="center")

        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        x = (w - tw) // 2
        y = y_pos if y_pos is not None else (h - th - 340)

        stroke = 8
        draw.multiline_text((x+6, y+6), wrapped, font=font, fill=(0,0,0,160), align="center")
        for dx in range(-stroke, stroke+1, 2):
            for dy in range(-stroke, stroke+1, 2):
                draw.multiline_text((x+dx, y+dy), wrapped, font=font, fill='black', align="center")
        draw.multiline_text((x,y), wrapped, font=font, fill=color, align="center")
        return ImageClip(np.array(img)).set_duration(dur)

    @staticmethod
    def render_short(script_data):
        print("🎬 Assembling Studio Short with AI Audio/Video Fallbacks...")
        master_seed = random.randint(1000, 999999)
        kw = script_data.get('keyword', 'kids')

        def build_scene_assets(i, scene):
            img_path = os.path.join(Config.ASSETS_DIR, f"img_{i}.jpg")
            vid_path = os.path.join(Config.ASSETS_DIR, f"vid_{i}.mp4")
            aud_path = os.path.join(Config.ASSETS_DIR, f"aud_{i}.mp3")
            
            if not AssetEngine.generate_pollinations_audio(scene['line'], aud_path):
                print(f"   ↳ Scene {i}: Audio fallback to TTS")
                AssetEngine.generate_voice(scene['line'], aud_path)
                
            if not AssetEngine.generate_pollinations_video(scene.get('image_prompt', 'cartoon'), vid_path):
                print(f"   ↳ Scene {i}: Video fallback to Image")
                AssetEngine.generate_image(scene.get('image_prompt', 'cartoon'), img_path, kw, master_seed)

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [ex.submit(build_scene_assets, i, scene) for i, scene in enumerate(script_data['scenes'])]
            for f in as_completed(futures): f.result()

        clips = []
        timestamps = []
        current_time = 0.0
        w, h = 1080, 1920
        
        bgm_path = os.path.join(Config.ASSETS_DIR, "bg_music_dynamic.mp3")
        AssetEngine.fetch_dynamic_background_music(bgm_path)

        for i, scene in enumerate(script_data['scenes']):
            img_path = os.path.join(Config.ASSETS_DIR, f"img_{i}.jpg")
            vid_path = os.path.join(Config.ASSETS_DIR, f"vid_{i}.mp4")
            aud_path = os.path.join(Config.ASSETS_DIR, f"aud_{i}.mp3")
            
            if not os.path.exists(aud_path): return None, None, None 
            
            voice = AudioFileClip(aud_path)
            if voice.duration > 4.5: voice = voice.subclip(0, 4.5)
            
            if voice.duration < 2.5:
                echo = voice.volumex(0.25).set_start(0.18)
                enhanced_voice = CompositeAudioClip([voice, echo]).set_duration(voice.duration + 0.3)
                
                bgm = AudioFileClip(bgm_path).volumex(0.085).audio_fadein(2.0)
                bg_looped = concatenate_audioclips([bgm] * int(math.ceil(enhanced_voice.duration/bgm.duration))).subclip(0, enhanced_voice.duration) if bgm.duration > 0 else bgm
                final_audio = CompositeAudioClip([enhanced_voice, bg_looped])
                dur = enhanced_voice.duration
            else:
                final_audio = voice
                dur = voice.duration
            
            if os.path.exists(vid_path):
                base_clip = VideoFileClip(vid_path)
                if base_clip.duration < dur:
                    base_clip = base_clip.fx(vfx.loop, duration=dur)
                else:
                    base_clip = base_clip.subclip(0, dur)
                
                resized_clip = base_clip.resize(height=h)
                anim = resized_clip.crop(x_center=resized_clip.w/2, width=w).set_duration(dur)
            else:
                img = ImageClip(img_path).resize(1.15)
                ex_x, ex_y = img.w - w, img.h - h
                move = random.choice(['zoom_in','zoom_out','pan_left','pan_right','pan_up','pan_down'])
                speed = 0.25 if i == 0 else 0.12 
                
                if move=='zoom_in': anim = img.resize(lambda t: 1.0 + speed*(t/dur)).set_position('center')
                elif move=='zoom_out': anim = img.resize(lambda t: 1.15 - speed*(t/dur)).set_position('center')
                elif move=='pan_left': anim = img.set_position(lambda t: (-ex_x*(t/dur), 'center'))
                elif move=='pan_right': anim = img.set_position(lambda t: (-ex_x + (ex_x*(t/dur)), 'center'))
                elif move=='pan_up': anim = img.set_position(lambda t: ('center', -ex_y*(t/dur)))
                else: anim = img.set_position(lambda t: ('center', -ex_y + (ex_y*(t/dur))))
                anim = anim.set_duration(dur)

            txt = VideoStudio._create_text_overlay(scene['line'], w, h, 118, dur).crossfadein(0.4)
            wm = VideoStudio._create_text_overlay(Config.CHANNEL_HANDLE, w, h, 38, dur, color='white', y_pos=40, is_eng=True).set_opacity(0.6)
            
            clip = CompositeVideoClip([anim, txt, wm], size=(w,h)).set_audio(final_audio).set_duration(dur)
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
# CORE 5: BROADCASTER (Weaponized Metadata)
# ==========================================
class Broadcaster:
    @staticmethod
    def upload(video_path, script_data, lyrics, timestamps):
        try:
            print(f"🚀 Broadcaster Authenticating...")
            with open(Config.TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
            service = build('youtube', 'v3', credentials=creds)

            title = script_data.get('title', "Hindi Nursery Rhymes for Kids 2026")
            if len(title) > 97: title = title[:97] + "..."
            
            ai_tags = script_data.get('seo_tags', [])
            
            base_tags = [
                "छोटे बच्चों का खिलौना", "dinosaur poem in hindi", "rems hindi", "reams hindi", 
                "tractor cartoon", "khilona wala cartoon", "hindi nursery rhymes", "balgeet", 
                "bachon ke geet", "3d hindi rhymes", "shorts"
            ]
            
            valid_tags, char_count = [], 0
            for tag in list(dict.fromkeys(base_tags + ai_tags)):
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
                    f"#HindiRhymes #छोटेबच्चोंकाखिलौना #TractorCartoon #Balgeet #Shorts #KidsToys")

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
    print(f"===== {Config.CHANNEL_HANDLE} - TOY FACTORY V4.6 (OMNI-HYDRA) =====")
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
