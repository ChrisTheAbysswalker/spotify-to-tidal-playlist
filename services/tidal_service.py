import traceback
from utils.utils import normalize_track_name, fuzzy_match

def create_tidal_playlist(user, name, description="Migrada de Spotify"):
    return user.create_playlist(name, description)

def _match_track_conditional_live(name, artist, search_results, normalized=False, exclude_live=True):
    for t in search_results:
        t_name = normalize_track_name(t.name) if normalized else (t.name or "").lower()
        t_artists = [(a.name or "").lower() for a in getattr(t, "artists", [])]

        if exclude_live and "live" in t_name:
            continue

        if fuzzy_match(name, artist, t_name, t_artists):
            return t
    return None

def search_tidal_track(session, name, artist, spotify_isrc=None):
    try:
        # * BUSQUEDA POR ISRC 
        if spotify_isrc:
            search_results = session.search(name or artist or "", limit=50).get("tracks", [])
            for t in search_results:
                if getattr(t, "isrc", None) == spotify_isrc:
                    return t

        # * BUSQUEDA EXCLUYENDO LIVE
        query = f"{name} {artist}".strip()
        search_results = session.search(query, limit=50).get("tracks", [])
        track = _match_track_conditional_live(name, artist, search_results, exclude_live=True)
        if track:
            return track

        # * BUSQUEDA NORMALIZADA EXCLUYENDO LIVE
        norm_name = normalize_track_name(name)
        search_results = session.search(f"{norm_name} {artist}".strip(), limit=50).get("tracks", [])
        track = _match_track_conditional_live(norm_name, artist, search_results, normalized=True, exclude_live=True)
        if track:
            return track

        # * SI NINGUNO DE LOS ANTERIORES ES VALIDO, PERMITIR LIVE
        track = _match_track_conditional_live(name, artist, search_results, normalized=False, exclude_live=False)
        return track

    except Exception:
        print("Error en search_tidal_track:")
        traceback.print_exc()
    return None
