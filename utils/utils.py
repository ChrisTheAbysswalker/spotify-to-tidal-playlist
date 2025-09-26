import re
from rapidfuzz import fuzz

def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def normalize_track_name(name: str) -> str:
    # ? MORMALIZA EL NOMBRE DE LA CANCION EXCLUYENDO SIMBOLOS Y SUFIJOS COMUNES
    
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(
        r"-\s*((\d{4})?\s*Remaster(ed)?|Single Version|Version|Live|Radio Edit|Mono|Stereo|Acoustic|Demo|Edit)",
        "",
        name,
        flags=re.IGNORECASE
    )
    name = re.sub(r"Remaster(ed)?\s*\d{4}?", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip().lower()

def fuzzy_match(name, artist, t_name, t_artists):
    score_name = fuzz.partial_ratio(name.lower(), t_name.lower())
    score_artist = max(fuzz.partial_ratio(artist.lower(), a.lower()) for a in t_artists) if artist else 0
    return score_name > 80 and score_artist > 80
