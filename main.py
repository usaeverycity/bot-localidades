import os
import tweepy
import pandas as pd
import requests
import random
from dotenv import load_dotenv
from PIL import Image

# Cargar variables de entorno
load_dotenv()

# Leer claves
API_KEY = os.getenv("API_KEY")
API_KEY_SECRET = os.getenv("API_KEY_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")

# Log para verificar el token
print("✅ MAPBOX_TOKEN cargado:", MAPBOX_TOKEN[:10] + "..." if MAPBOX_TOKEN else "❌ No cargado")

# Inicializar cliente de Twitter (aunque no se usa en este paso)
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=API_KEY,
    consumer_secret=API_KEY_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

# Paths
CSV_PATH = "localidades_usa_filtrado_con_id.csv"
USED_IDS_PATH = "usados.txt"
IMAGEN_ORIGINAL = "mapa_raw.png"
IMAGEN_FINAL = "mapa.png"
IMAGEN_ZOOM = "mapa_zoom.png"

# Cargar CSV
df = pd.read_csv(CSV_PATH)

# Cargar IDs ya usados
if os.path.exists(USED_IDS_PATH):
    with open(USED_IDS_PATH, "r") as f:
        usados = set(map(int, f.read().splitlines()))
else:
    usados = set()

# Filtrar ciudades disponibles
df_disponibles = df[~df["id"].isin(usados)]

if df_disponibles.empty:
    raise Exception("🔥 Ya se usaron todas las ciudades disponibles.")

# Elegir ciudad random
ciudad = df_disponibles.sample(1).iloc[0]

# Guardar ID como usado
with open(USED_IDS_PATH, "a") as f:
    f.write(f"{ciudad['id']}\n")

# Extraer datos
lat = ciudad["latitude"]
lon = ciudad["longitude"]
nombre_ciudad = ciudad["name"]
estado = ciudad["state"]
county = ciudad["county"]

print(f"📍 Ciudad seleccionada: {nombre_ciudad}, {county} County, {estado}")

# Generar URL de Mapbox (zoom alejado para compensar crop)
zoom = 13.8
mapbox_url = f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom},0/800x800?access_token={MAPBOX_TOKEN}"
print(f"🌎 URL generada para la imagen: {mapbox_url}")

# Descargar imagen original
resp = requests.get(mapbox_url)
if resp.status_code == 200:
    with open(IMAGEN_ORIGINAL, "wb") as f:
        f.write(resp.content)
    print("📥 Imagen original descargada")

    # Abrir imagen y recortar centrado cuadrado
    img = Image.open(IMAGEN_ORIGINAL)
    w, h = img.size

    # Definir nuevo tamaño cuadrado seguro
    lado = 700

    # Calcular márgenes centrados
    left = (w - lado) // 2
    top = (h - lado) // 2
    right = left + lado
    bottom = top + lado

    crop_area = (left, top, right, bottom)
    img_cropped = img.crop(crop_area)

    # (Opcional) Escalar a 800x800 manteniendo proporción
    img_final = img_cropped.resize((800, 800), Image.LANCZOS)
    img_final.save(IMAGEN_FINAL)
    print(f"✅ Imagen recortada centrada y guardada como {IMAGEN_FINAL}")

    # 🔍 Generar imagen con zoom visual (recorte + resize)
    zoom_factor = 1.25  # acercamiento leve
    zoom_w = int(800 / zoom_factor)
    zoom_h = int(800 / zoom_factor)
    zoom_left = (800 - zoom_w) // 2
    zoom_top = (800 - zoom_h) // 2
    zoom_crop = (zoom_left, zoom_top, zoom_left + zoom_w, zoom_top + zoom_h)

    img_zoom = img_final.crop(zoom_crop).resize((800, 800), Image.LANCZOS)
    img_zoom.save(IMAGEN_ZOOM)
    print(f"🔎 Imagen con zoom generada como {IMAGEN_ZOOM}")

else:
    print(f"❌ Error al descargar imagen: {resp.status_code}")
    print("⚠️ Respuesta completa:", resp.text)

#
#
#

# Autenticación adicional para subir imágenes (v1.1)
auth = tweepy.OAuth1UserHandler(API_KEY, API_KEY_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api_v1 = tweepy.API(auth)

try:
    print("📤 Subiendo imagen principal...")
    media_main = api_v1.media_upload(filename=IMAGEN_FINAL)

    print("📤 Publicando tuit con imagen principal...")
    tweet_response = client.create_tweet(
        text=f"📍 {nombre_ciudad}, {county} County, {estado}",
        media_ids=[media_main.media_id]
    )
    tweet_id = tweet_response.data["id"]
    print(f"✅ Tuit publicado con ID: {tweet_id}")

    print("📤 Subiendo imagen con zoom...")
    media_zoom = api_v1.media_upload(filename=IMAGEN_ZOOM)

    print("📤 Publicando respuesta con imagen zoom...")
    reply = client.create_tweet(
        in_reply_to_tweet_id=tweet_id,
        media_ids=[media_zoom.media_id]
    )
    print(f"✅ Respuesta publicada con ID: {reply.data['id']}")

except Exception as e:
    print("❌ Error al tuitear:", e)

