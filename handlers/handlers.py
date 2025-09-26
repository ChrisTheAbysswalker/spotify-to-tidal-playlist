import threading
import time
import traceback
from services.spotify_service import get_spotify_client, get_spotify_playlists, get_spotify_tracks
from services.tidal_service import search_tidal_track, create_tidal_playlist
from utils.utils import chunk_list

class Handlers:
    def __init__(self, sp_oauth, tidal_session):
        self.sp_oauth = sp_oauth
        self.tidal_session = tidal_session
        self.spotify_client = None
        self.tidal_logged_in = False

    # * ---------------- SPOTIFY ----------------
    def login_spotify_url(self):
        return self.sp_oauth.get_authorize_url()

    def spotify_callback(self, code: str):
        token_info = self.sp_oauth.get_access_token(code)
        self.spotify_client = get_spotify_client(token_info)
        return self.spotify_client

    # * ---------------- TIDAL ----------------
    def login_tidal_thread(self):
        def tidal_thread():
            try:
                self.tidal_session.login_oauth_simple()
                self.tidal_logged_in = self.tidal_session.user is not None
            except Exception:
                self.tidal_logged_in = False
                traceback.print_exc()
        threading.Thread(target=tidal_thread, daemon=True).start()

    # * ---------------- PLAYLISTS ----------------
    def get_playlists(self):
        if not self.spotify_client:
            return []
        return get_spotify_playlists(self.spotify_client)

    # * ---------------- MIGRACIÓN DE PLAYLISTS ----------------
    def migrar_playlists(self, playlist_ids=None):
        playlists = self.get_playlists()
        if playlist_ids:
            playlists = [p for p in playlists if p["id"] in playlist_ids]

        for playlist in playlists:
            print(f"\n🚀 Migrando playlist: {playlist['name']}")
            if not self.tidal_session.user:
                print("⚠️ No has iniciado sesión en Tidal")
                return

            tidal_playlist = create_tidal_playlist(self.tidal_session.user, playlist["name"])
            tracks = get_spotify_tracks(self.spotify_client, playlist["id"])
            tidal_track_ids = []

            for t in tracks:
                tidal_track = search_tidal_track(self.tidal_session, t["name"], t["artist"], t.get("isrc"))
                if tidal_track:
                    tidal_track_ids.append(tidal_track.id)
                else:
                    print(f"⚠️ No encontrada en Tidal: {t['name']} - {t['artist']}")
                time.sleep(0.1)

            if tidal_track_ids:
                for block in chunk_list(tidal_track_ids, 50):
                    tidal_playlist.add(block)
                print(f"✅ Agregadas {len(tidal_track_ids)} canciones a {playlist['name']}")
