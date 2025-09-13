import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import tidalapi
import time

load_dotenv()

# Acceder a las variables
SPOTIFY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SPOTIFY_SCOPE = os.getenv("SPOTIFY_SCOPE")

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SPOTIFY_SCOPE
))

# ---------- CONFIG TIDAL ----------
session = tidalapi.Session()
session.login_oauth_simple()  # Te pedirá logearte en navegador

# ---------- FUNCIONES ----------
def get_spotify_playlists():
    playlists = sp.current_user_playlists()
    return playlists["items"]

def get_spotify_tracks(playlist_id):
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

def search_tidal_track(name, artist):
    query = f"{name} {artist}"
    search = session.search(query, models=[tidalapi.media.Track])
    if search["tracks"]:
        return search["tracks"][0]
    return None

def create_tidal_playlist(name, description="Migrada de Spotify"):
    return session.user.create_playlist(name, description)

def chunk_list(lst, n):
    """Divide una lista en chunks de tamaño n"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ---------- MIGRACIÓN ----------
for playlist in get_spotify_playlists():
    print(f"\n🚀 Migrando playlist: {playlist['name']}")
    tidal_playlist = create_tidal_playlist(playlist["name"])

    tracks = get_spotify_tracks(playlist["id"])
    tidal_track_ids = []

    for t in tracks:
        tidal_track = search_tidal_track(t["name"], t["artist"])
        if tidal_track:
            tidal_track_ids.append(tidal_track.id)
        else:
            print(f"⚠️ No encontrada en Tidal: {t['name']} - {t['artist']}")
        time.sleep(0.1)  # Para no saturar la búsqueda

    # Agregar canciones en bloques de 50
    for block in chunk_list(tidal_track_ids, 50):
        tidal_playlist.add(block)
        print(f"✅ Agregadas {len(block)} canciones al playlist en Tidal")
