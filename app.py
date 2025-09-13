from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import tidalapi
import threading
import os
from dotenv import load_dotenv
import time

load_dotenv()

# ---------- TEMPLATES ----------
templates = Jinja2Templates(directory="templates")

# ---------- APP ----------
app = FastAPI()

# ---------- CONFIG SPOTIFY ----------
SPOTIFY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SPOTIFY_SCOPE = os.getenv("SPOTIFY_SCOPE")

sp_oauth = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SPOTIFY_SCOPE,
    cache_path=".cache-spotify"
)

spotify_client = None

# ---------- CONFIG TIDAL ----------
tidal_session = tidalapi.Session()
tidal_logged_in = False

def tidal_login_thread():
    """Inicia login OAuth de Tidal en un hilo aparte"""
    global tidal_logged_in
    tidal_session.login_oauth_simple()
    tidal_logged_in = tidal_session.user is not None

# ---------- FUNCIONES ----------
def get_spotify_client():
    global spotify_client
    return spotify_client

def get_spotify_playlists(sp):
    return sp.current_user_playlists()["items"]

def get_spotify_tracks(sp, playlist_id):
    tracks = []
    offset = 0
    while True:
        results = sp.playlist_items(playlist_id, offset=offset, limit=100)
        for item in results["items"]:
            track = item["track"]
            tracks.append({
                "name": track["name"],
                "artist": track["artists"][0]["name"]
            })
        if results["next"]:
            offset += 100
        else:
            break
    return tracks


def create_tidal_playlist(name, description="Migrada de Spotify"):
    return tidal_session.user.create_playlist(name, description)

def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ---------- ROUTES ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    global spotify_client, tidal_logged_in
    spotify_connected = spotify_client is not None
    return templates.TemplateResponse(
        "home.html",
        {"request": request,
         "spotify_connected": spotify_connected,
         "tidal_connected": tidal_logged_in}
    )

# ---------------- SPOTIFY ----------------
@app.get("/login_spotify")
def login_spotify():
    auth_url = sp_oauth.get_authorize_url()
    return RedirectResponse(auth_url)

@app.get("/callback/")
def spotify_callback(code: str):
    global spotify_client
    token_info = sp_oauth.get_access_token(code)
    spotify_client = spotipy.Spotify(auth=token_info["access_token"])
    return RedirectResponse("/playlists")

# ---------------- TIDAL ----------------
@app.get("/login_tidal")
def login_tidal():
    threading.Thread(target=tidal_login_thread, daemon=True).start()
    return RedirectResponse("/", status_code=303)

# ---------------- PLAYLISTS ----------------
@app.get("/playlists", response_class=HTMLResponse)
def playlists(request: Request):
    if not spotify_client or not tidal_logged_in:
        return RedirectResponse("/")
    playlists = get_spotify_playlists(spotify_client)
    return templates.TemplateResponse(
        "playlists.html",
        {"request": request, "playlists": playlists}
    )

# ---------------- MIGRAR ----------------
def search_tidal_track(name, artist):
    """Busca un track en Tidal y devuelve el objeto Track si se encuentra"""
    search_results = tidal_session.search(name, limit=50)  # devuelve dict

    for t in search_results.get("tracks", []):
        if t.name.lower() == name.lower() and artist.lower() in [a.name.lower() for a in t.artists]:
            return t
    return None

def migrar_playlists():
    """Ejemplo de migración usando tidalapi directamente"""
    playlists = get_spotify_playlists(spotify_client)  # tu cliente de Spotify
    for playlist in playlists:
        print(f"\n🚀 Migrando playlist: {playlist['name']}")

        if not tidal_session.user:
            print("⚠️ No has iniciado sesión en Tidal")
            return

        tidal_playlist = create_tidal_playlist(playlist["name"])
        tracks = get_spotify_tracks(spotify_client, playlist["id"])
        tidal_track_ids = []

        for t in tracks:
            tidal_track = search_tidal_track(t["name"], t["artist"])
            if tidal_track:
                tidal_track_ids.append(tidal_track.id)
            else:
                print(f"⚠️ No encontrada en Tidal: {t['name']} - {t['artist']}")
            time.sleep(0.1)  # evitar saturar la API

        if tidal_track_ids:
            for block in chunk_list(tidal_track_ids, 50):
                tidal_playlist.add(block)
            print(f"✅ Agregadas {len(tidal_track_ids)} canciones a {playlist['name']}")
@app.post("/migrar", response_class=HTMLResponse)
def migrar(request: Request, playlist_ids: list[str] = Form(...)):
    """Muestra template de progreso y lanza migración en un hilo"""
    response = templates.TemplateResponse("migrar.html", {"request": request})

    def migracion_thread():
        for playlist_id in playlist_ids:
            playlist = spotify_client.playlist(playlist_id)
            print(f"\n🚀 Migrando playlist: {playlist['name']}")

            if not tidal_session.user:
                print("⚠️ No has iniciado sesión en Tidal")
                return

            tidal_playlist = create_tidal_playlist(playlist["name"])
            tracks = get_spotify_tracks(spotify_client, playlist_id)
            tidal_track_ids = []

            for t in tracks:
                # Usamos la nueva función que busca directamente en tidalapi
                tidal_track = search_tidal_track(t["name"], t["artist"])
                if tidal_track:
                    tidal_track_ids.append(tidal_track.id)
                else:
                    print(f"⚠️ No encontrada en Tidal: {t['name']} - {t['artist']}")
                time.sleep(0.1)  # evitar saturar la API

            if tidal_track_ids:
                for block in chunk_list(tidal_track_ids, 50):
                    tidal_playlist.add(block)
                print(f"✅ Agregadas {len(tidal_track_ids)} canciones a {playlist['name']}")
            else:
                print("⚠️ Ninguna canción migrada para esta playlist")

    threading.Thread(target=migracion_thread, daemon=True).start()
    return response
