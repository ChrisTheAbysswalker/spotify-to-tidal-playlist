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
from rapidfuzz import fuzz
import re
import traceback

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
    try:
        tidal_session.login_oauth_simple()
        tidal_logged_in = tidal_session.user is not None
    except Exception:
        tidal_logged_in = False
        print("Error en login Tidal:")
        traceback.print_exc()

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
            track = item.get("track")
            if not track:
                continue
            tracks.append({
                "name": track["name"],
                "artist": track["artists"][0]["name"] if track.get("artists") else "",
                "isrc": track.get("external_ids", {}).get("isrc")
            })
        if results.get("next"):
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

@app.get("/login_tidal")
def login_tidal():
    threading.Thread(target=tidal_login_thread, daemon=True).start()
    return RedirectResponse("/", status_code=303)

@app.get("/playlists", response_class=HTMLResponse)
def playlists(request: Request):
    if not spotify_client or not tidal_logged_in:
        return RedirectResponse("/")
    playlists = get_spotify_playlists(spotify_client)
    return templates.TemplateResponse(
        "playlists.html",
        {"request": request, "playlists": playlists}
    )

# ---------- MIGRAR ----------

def normalize_track_name(name: str) -> str:
    """Normaliza el nombre eliminando paréntesis y sufijos comunes"""
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(
        r"-\s*((\d{4})?\s*Remaster(ed)?|Single Version|Version|Live|Radio Edit|Mono|Stereo|Acoustic|Demo|Edit)",
        "",
        name,
        flags=re.IGNORECASE
    )
    name = re.sub(r"Remaster(ed)?\s*\d{4}?", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip().lower()


def _match_track_conditional_live(name, artist, search_results, normalized=False, exclude_live=True):
    """Busca la mejor coincidencia en search_results, excluyendo Live si exclude_live=True"""
    for t in search_results:
        t_name = normalize_track_name(t.name) if normalized else (t.name or "").lower()
        t_artists = [(a.name or "").lower() for a in getattr(t, "artists", [])]

        # Excluir Live si corresponde
        if exclude_live and "live" in t_name:
            continue

        score_name = fuzz.partial_ratio(name.lower(), t_name)
        score_artist = max(fuzz.partial_ratio(artist.lower(), a) for a in t_artists) if artist else 0

        if score_name > 80 and score_artist > 80:
            return t
    return None


def search_tidal_track(name, artist, spotify_isrc=None):
    """Busca un track en Tidal con ISRC, búsqueda difusa y filtro Live condicional"""
    try:
        # 1) Por ISRC exacto
        if spotify_isrc:
            search_results = tidal_session.search(name or artist or "", limit=50).get("tracks", [])
            for t in search_results:
                if getattr(t, "isrc", None) == spotify_isrc:
                    return t

        # 2) Búsqueda difusa excluyendo Live
        query = f"{name} {artist}".strip()
        search_results = tidal_session.search(query, limit=50).get("tracks", [])
        track = _match_track_conditional_live(name, artist, search_results, exclude_live=True)
        if track:
            return track

        # 3) Búsqueda normalizada excluyendo Live
        norm_name = normalize_track_name(name)
        if norm_name and artist:
            search_results = tidal_session.search(f"{norm_name} {artist}".strip(), limit=50).get("tracks", [])
            track = _match_track_conditional_live(norm_name, artist, search_results, normalized=True, exclude_live=True)
            if track:
                return track

        # 4) Último recurso: permitir Live
        track = _match_track_conditional_live(name, artist, search_results, normalized=False, exclude_live=False)
        if track:
            return track

    except Exception:
        print("Error en search_tidal_track:")
        traceback.print_exc()

    return None


def migrar_playlists():
    playlists = get_spotify_playlists(spotify_client)
    for playlist in playlists:
        print(f"\n🚀 Migrando playlist: {playlist['name']}")

        if not tidal_session.user:
            print("⚠️ No has iniciado sesión en Tidal")
            return

        tidal_playlist = create_tidal_playlist(playlist["name"])
        tracks = get_spotify_tracks(spotify_client, playlist["id"])
        tidal_track_ids = []

        for t in tracks:
            tidal_track = search_tidal_track(t["name"], t["artist"], t.get("isrc"))
            if tidal_track:
                tidal_track_ids.append(tidal_track.id)
            else:
                print(f"⚠️ No encontrada en Tidal: {t['name']} - {t['artist']}")
            time.sleep(0.1)

        if tidal_track_ids:
            for block in chunk_list(tidal_track_ids, 50):
                tidal_playlist.add(block)
            print(f"✅ Agregadas {len(tidal_track_ids)} canciones a {playlist['name']}")
        else:
            print(f"⚠️ Ninguna canción migrada para la playlist: {playlist['name']}")


@app.post("/migrar", response_class=HTMLResponse)
def migrar(request: Request, playlist_ids: list[str] = Form(...)):
    response = templates.TemplateResponse("migrar.html", {"request": request})

    def migracion_thread():
        try:
            for playlist_id in playlist_ids:
                try:
                    playlist = spotify_client.playlist(playlist_id)
                    print(f"\n🚀 Migrando playlist: {playlist['name']}")

                    if not tidal_session.user:
                        print("⚠️ No has iniciado sesión en Tidal")
                        return

                    tidal_playlist = create_tidal_playlist(playlist["name"])
                    tracks = get_spotify_tracks(spotify_client, playlist_id)
                    tidal_track_ids = []

                    for t in tracks:
                        tidal_track = search_tidal_track(t["name"], t["artist"], t.get("isrc"))
                        if tidal_track:
                            tidal_track_ids.append(tidal_track.id)
                        else:
                            print(f"⚠️ No encontrada en Tidal: {t['name']} - {t['artist']}")
                        time.sleep(0.1)

                    if tidal_track_ids:
                        for block in chunk_list(tidal_track_ids, 50):
                            tidal_playlist.add(block)
                        print(f"✅ Agregadas {len(tidal_track_ids)} canciones a {playlist['name']}")
                    else:
                        print(f"⚠️ Ninguna canción migrada para esta playlist: {playlist['name']}")

                except Exception:
                    print(f"Error migrando playlist id={playlist_id}:")
                    traceback.print_exc()
                    continue
        except Exception:
            print("Error en el hilo de migración:")
            traceback.print_exc()

    threading.Thread(target=migracion_thread, daemon=True).start()
    return response
