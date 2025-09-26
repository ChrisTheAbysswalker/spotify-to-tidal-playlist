import threading
import time
from utils import chunk_list
from services.tidal_service import search_tidal_track, create_tidal_playlist
from services.spotify_service import get_spotify_tracks

def migrar_playlists(spotify_client, tidal_session):
    playlists = spotify_client.current_user_playlists()["items"]
    for playlist in playlists:
        print(f"\n🚀 Migrando playlist: {playlist['name']}")
        if not tidal_session.user:
            print("⚠️ No has iniciado sesión en Tidal")
            return

        tidal_playlist = create_tidal_playlist(tidal_session.user, playlist["name"])
        tracks = get_spotify_tracks(spotify_client, playlist["id"])
        tidal_track_ids = []

        for t in tracks:
            tidal_track = search_tidal_track(tidal_session, t["name"], t["artist"], t.get("isrc"))
            if tidal_track:
                tidal_track_ids.append(tidal_track.id)
            else:
                print(f"⚠️ No encontrada en Tidal: {t['name']} - {t['artist']}")
            time.sleep(0.1)

        if tidal_track_ids:
            for block in chunk_list(tidal_track_ids, 50):
                tidal_playlist.add(block)
            print(f"✅ Agregadas {len(tidal_track_ids)} canciones a {playlist['name']}")
