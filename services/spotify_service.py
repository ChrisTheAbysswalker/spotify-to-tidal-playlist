import spotipy

def get_spotify_client(token_info):
    return spotipy.Spotify(auth=token_info["access_token"])

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
