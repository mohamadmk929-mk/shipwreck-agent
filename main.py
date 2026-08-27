"""
Shipwreck Hunters — Autonomous Video Agent
يشتغل تلقائيًا: يختار موضوع -> يكتب سكريبت -> يولد صوت وصور -> يركب فيديو -> يحفظه كمخرج جاهز للمراجعة
لا ينشر على يوتيوب تلقائيًا — فقط يجهز الفيديو.
"""
import os, json, random, asyncio, requests, urllib.parse
import edge_tts
from moviepy import (ImageClip, AudioFileClip, CompositeVideoClip,
                             concatenate_videoclips, vfx)

OUTPUT_DIR = "output"
ASSETS_DIR = "assets"
os.makedirs(f"{OUTPUT_DIR}", exist_ok=True)
os.makedirs(f"{ASSETS_DIR}/audio", exist_ok=True)
os.makedirs(f"{ASSETS_DIR}/images", exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VOICE = "en-US-GuyNeural"
TARGET_SCENES = 20  # ~3-4 دقائق

TOPIC_BANK = [
    "The Lost Nazi U-Boat Convoy That Vanished With Gold Reserves",
    "USS Cyclops: The Warship That Disappeared Without a Trace",
    "The Experimental Stealth Submarine Buried in Arctic Ice",
    "HMS Erebus and Terror: The Warships Lost in the Frozen Northwest Passage",
    "The Ghost Fleet of Truk Lagoon: Japan's Sunken Naval Armada",
    "The Confederate Ironclad That Sank on Its First Voyage",
    "Operation Habakkuk: The Secret WWII Ice Aircraft Carrier",
    "The Ottoman Battleship Lost in the Black Sea Depths",
    "The Soviet Golf-Class Submarine and the CIA's Secret Recovery",
    "The Sunken Prototype Torpedo Boat of the Russo-Japanese War",
    "USS Indianapolis: The Warship That Delivered a Secret Weapon",
    "The Buried Railway Gun Never Deployed in WWII",
]

USED_TOPICS_FILE = f"{OUTPUT_DIR}/used_topics.json"


def pick_topic():
    used = []
    if os.path.exists(USED_TOPICS_FILE):
        used = json.load(open(USED_TOPICS_FILE))
    available = [t for t in TOPIC_BANK if t not in used] or TOPIC_BANK
    topic = random.choice(available)
    used.append(topic)
    json.dump(used[-len(TOPIC_BANK):], open(USED_TOPICS_FILE, "w"))
    return topic


def write_script_with_gemini(topic):
    """يستخدم Gemini المجاني لكتابة سكريبت مقسّم لمشاهد. لو ما فيه مفتاح، يرجع خطأ واضح."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY غير موجود — راجع تعليمات إعداد الـ Secret")

    prompt = f"""Write a suspenseful documentary-style YouTube narration script about: "{topic}"
Split it into exactly {TARGET_SCENES} scenes. Each scene should be 2-3 sentences of narration
(dramatic, factual, engaging tone, suitable for a mystery/history channel about lost warships).
Return ONLY valid JSON, no markdown, no explanation, in this exact format:
[
  {{"id": 1, "narration": "...", "image_prompt": "cinematic description in English for AI image generation", "motion": "zoom_in"}},
  ...
]
motion must be one of: zoom_in, zoom_out, pan_left, pan_right (vary them across scenes).
image_prompt must be a vivid cinematic visual description, no text/words in the image, no real identifiable people.
"""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=120)                           

                                 
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


async def generate_voice(text, filename):
    communicate = edge_tts.Communicate(text, VOICE, rate="-5%")
    await communicate.save(filename)


def generate_image(prompt, filename, width=1024, height=1024):
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true"
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    with open(filename, "wb") as f:
        f.write(r.content)


def image_to_clip(image_path, duration, motion):
    """يحوّل صورة ثابتة لكليب متحرك (Ken Burns) بمدة تساوي الصوت المطابق له."""
    clip = ImageClip(image_path).set_duration(duration)
    w, h = clip.size
    zoom_ratio = 1.15

    if motion == "zoom_in":
        clip = clip.resize(lambda t: 1 + (zoom_ratio - 1) * (t / duration))
    elif motion == "zoom_out":
        clip = clip.resize(lambda t: zoom_ratio - (zoom_ratio - 1) * (t / duration))
    elif motion == "pan_left":
        clip = clip.resize(1.15).set_position(lambda t: (-40 * (t / duration), "center"))
    elif motion == "pan_right":
        clip = clip.resize(1.15).set_position(lambda t: (-40 * (1 - t / duration), "center"))

    clip = clip.set_position("center")
    bg = ImageClip(image_path).set_duration(duration).resize(width=w, height=h)
    composite = CompositeVideoClip([bg, clip], size=(w, h))
    return composite.fx(vfx.fadein, 0.4).fx(vfx.fadeout, 0.4)


def build_video(scenes, output_path):
    clips = []
    for s in scenes:
        audio = AudioFileClip(s["audio_path"])
        img_clip = image_to_clip(s["image_path"], audio.duration, s["motion"])
        img_clip = img_clip.set_audio(audio)
        clips.append(img_clip)
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")


def main():
    print("== 1) اختيار الموضوع ==")
    topic = pick_topic()
    print(f"الموضوع: {topic}")

    print("== 2) كتابة السكريبت (Gemini) ==")
    scenes = write_script_with_gemini(topic)
    print(f"عدد المشاهد: {len(scenes)}")

    print("== 3) توليد الصوت ==")
    for s in scenes:
        path = f"{ASSETS_DIR}/audio/scene_{s['id']}.mp3"
        asyncio.run(generate_voice(s["narration"], path))
        s["audio_path"] = path
    print("تم توليد كل الأصوات")

    print("== 4) توليد الصور ==")
    for s in scenes:
        path = f"{ASSETS_DIR}/images/scene_{s['id']}.jpg"
        generate_image(s["image_prompt"], path)
        s["image_path"] = path
    print("تم توليد كل الصور")

    print("== 5) بناء الفيديو ==")
    safe_name = "".join(c if c.isalnum() else "_" for c in topic)[:50]
    video_path = f"{OUTPUT_DIR}/{safe_name}.mp4"
    build_video(scenes, video_path)

    # ملف وصف جاهز للنشر (يذكر أنه AI-generated حسب سياسة يوتيوب)
    description = (
        f"{topic}\n\n"
        "This video was created using AI tools (script, narration, visuals) "
        "to explore historical naval mysteries.\n\n"
        "#ShipwreckHunters #Warship #NavalHistory #GhostShips #DeepSeaMystery"
    )
    with open(f"{OUTPUT_DIR}/{safe_name}_description.txt", "w", encoding="utf-8") as f:
        f.write(description)

    print(f"\n✅ الفيديو جاهز: {video_path}")
    print("راجعه ووافق قبل أي رفع على يوتيوب.")


if __name__ == "__main__":
    main()
