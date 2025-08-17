import os
import tweepy
import pandas as pd
import requests
from io import BytesIO
from dotenv import load_dotenv
from PIL import Image, ImageFilter, ImageEnhance

# -------------------------
# Load environment variables
# -------------------------
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_KEY_SECRET = os.getenv("API_KEY_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

# -------------------------
# Twitter client (v2) + v1.1
# -------------------------
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=API_KEY,
    consumer_secret=API_KEY_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

auth = tweepy.OAuth1UserHandler(API_KEY, API_KEY_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api_v1 = tweepy.API(auth)

# -------------------------
# Paths
# -------------------------
CSV_PATH = "localidades_usa_filtrado_con_id.csv"
USED_IDS_PATH = "usados.txt"
IMAGEN_FINAL = "mapa.jpg"     # main image (high-quality JPEG)
IMAGEN_ZOOM = "mapa_zoom.jpg" # reply image (derived from HD base)

# -------------------------
# Load CSV and pick city
# -------------------------
df = pd.read_csv(CSV_PATH)

if os.path.exists(USED_IDS_PATH):
    with open(USED_IDS_PATH, "r") as f:
        usados = set(int(line) for line in f.read().splitlines() if line.strip())
else:
    usados = set()

df_disponibles = df[~df["id"].isin(usados)]
if df_disponibles.empty:
    raise Exception("All cities were already used.")

ciudad = df_disponibles.sample(1).iloc[0]

lat = float(ciudad["latitude"])
lon = float(ciudad["longitude"])
nombre_ciudad = str(ciudad["name"])
estado = str(ciudad["state"])
county = str(ciudad["county"]) if not pd.isna(ciudad["county"]) else ""

print(f"📍 Selected: {nombre_ciudad}, {county} County, {estado}")

# -------------------------
# Build Mapbox Static URL (HD base, no aggressive crop)
# -------------------------
zoom = 13.8
# 1280x1280@2x renders ~2560x2560; great source for downscaling once
size = "1280x1280@2x"
mapbox_url = (
    f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
    f"{lon},{lat},{zoom},0/{size}?access_token={MAPBOX_TOKEN}"
)
print(f"🌎 Mapbox URL: {mapbox_url}")

# -------------------------
# Download HD image
# -------------------------
resp = requests.get(mapbox_url, timeout=20)
if resp.status_code != 200:
    print(f"❌ Mapbox error: {resp.status_code}")
    print("⚠️ Response:", resp.text)
    raise SystemExit(1)

# -------------------------
# Process HD base image (best quality)
# -------------------------
# Open from memory and force RGB
img = Image.open(BytesIO(resp.content)).convert("RGB")

# Small centered micro-crop (~4%) to avoid any edge artifacts
w, h = img.size
m = int(min(w, h) * 0.04)
img = img.crop((m, m, w - m, h - m))

# Single high-quality resize to 2048x2048
img = img.resize((2048, 2048), Image.LANCZOS)

# Gentle clarity: unsharp + slight contrast
img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=3))
img = ImageEnhance.Contrast(img).enhance(1.05)

# Save main image as high-quality JPEG (Twitter-friendly)
img.save(
    IMAGEN_FINAL,
    format="JPEG",
    quality=92,
    subsampling=1,   # 4:2:2 keeps sharpness with reasonable size
    optimize=True,
    progressive=True
)
print(f"✅ Main image saved: {IMAGEN_FINAL} ({img.size[0]}x{img.size[1]})")

# -------------------------
# Create zoom image from HD base (so it does not pixelate)
# -------------------------
# Crop a centered box (≈1.35x zoom) from the 2048 base, then resize back to 2048
zoom_factor = 1.35
zw = int(2048 / zoom_factor)
zh = int(2048 / zoom_factor)
zl = (2048 - zw) // 2
zt = (2048 - zh) // 2
img_zoom = img.crop((zl, zt, zl + zw, zt + zh)).resize((2048, 2048), Image.LANCZOS)

# Apply a slightly softer unsharp for the zoomed version
img_zoom = img_zoom.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=3))
img_zoom = ImageEnhance.Contrast(img_zoom).enhance(1.05)

img_zoom.save(
    IMAGEN_ZOOM,
    format="JPEG",
    quality=92,
    subsampling=1,
    optimize=True,
    progressive=True
)
print(f"🔎 Zoom image saved: {IMAGEN_ZOOM} ({img_zoom.size[0]}x{img_zoom.size[1]})")

# -------------------------
# Mark ID as used only after images are generated successfully
# -------------------------
with open(USED_IDS_PATH, "a") as f:
    f.write(f"{int(ciudad['id'])}\n")

# -------------------------
# Post to Twitter (main + reply with zoom)
# -------------------------
try:
    print("📤 Uploading main image...")
    media_main = api_v1.media_upload(filename=IMAGEN_FINAL)

    print("🐦 Tweeting main image...")
    caption = f"📍 {nombre_ciudad}, {county} County, {estado}" if county.strip() else f"📍 {nombre_ciudad}, {estado}"
    tweet_response = client.create_tweet(text=caption, media_ids=[media_main.media_id])
    tweet_id = tweet_response.data["id"]
    print(f"✅ Tweet ID: {tweet_id}")

    print("📤 Uploading zoom image...")
    media_zoom = api_v1.media_upload(filename=IMAGEN_ZOOM)

    print("↩️ Replying with zoom image...")
    reply = client.create_tweet(in_reply_to_tweet_id=tweet_id, media_ids=[media_zoom.media_id])
    print(f"✅ Reply ID: {reply.data['id']}")

except Exception as e:
    print("❌ Twitter error:", e)
