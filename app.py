from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import threading

from utils.config import sp_oauth, tidal_session
from handlers.handlers import Handlers

templates = Jinja2Templates(directory="templates")
app = FastAPI()
handlers = Handlers(sp_oauth, tidal_session)

from fastapi.middleware.cors import CORSMiddleware


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {"request": request,
         "spotify_connected": handlers.spotify_client is not None,
         "tidal_connected": handlers.tidal_logged_in}
    )

@app.get("/login_spotify")
def login_spotify():
    return RedirectResponse(handlers.login_spotify_url())

@app.get("/callback/")
def spotify_callback(code: str):
    handlers.spotify_callback(code)
    return RedirectResponse("/playlists")

@app.get("/login_tidal")
def login_tidal():
    handlers.login_tidal_thread()
    return RedirectResponse("/", status_code=303)

@app.get("/playlists", response_class=HTMLResponse)
def playlists(request: Request):
    playlists = handlers.get_playlists()
    if not playlists or not handlers.tidal_logged_in:
        return RedirectResponse("/")
    return templates.TemplateResponse("playlists.html", {"request": request, "playlists": playlists})

@app.post("/migrar", response_class=HTMLResponse)
def migrar(request: Request, playlist_ids: list[str] = Form(...)):
    response = templates.TemplateResponse("migrar.html", {"request": request})
    threading.Thread(target=lambda: handlers.migrar_playlists(playlist_ids), daemon=True).start()
    return response
