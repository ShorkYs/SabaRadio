import argparse
import json
import os
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pyaudio
from audio.output_ffmpeg import OutFFMPEG
from system.device_manager import DeviceManager
from system.file_manager import FileManager


class RadioState:
    def __init__(self, songs: list[str], volume: float):
        self.lock = threading.Lock()
        self.songs = songs
        self.current_index = -1
        self.current_song: str | None = None
        self.volume = volume
        self.skip_requested = False

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "current_song": self.current_song,
                "current_index": self.current_index,
                "total_songs": len(self.songs),
                "volume": self.volume,
            }

    def request_skip(self):
        with self.lock:
            self.skip_requested = True

    def consume_skip_request(self) -> bool:
        with self.lock:
            requested = self.skip_requested
            self.skip_requested = False
            return requested

    def set_volume(self, value: float):
        with self.lock:
            self.volume = max(0.0, min(1.0, value))


def list_outputs(p: pyaudio.PyAudio) -> None:
    manager = DeviceManager(p)
    print("\n=== OUTPUT DEVICES ===")
    for i, name in manager.list_outputs():
        print(f"{i}: {name}")
    print("======================\n")


def player_loop(state: RadioState, ffmpeg: OutFFMPEG, p: pyaudio.PyAudio, speaker_index: int | None, cable_index: int | None):
    while True:
        for idx, song in enumerate(state.songs):
            with state.lock:
                state.current_index = idx
                state.current_song = song
                ffmpeg.volume = state.volume

            print(f"▶ Now playing: {os.path.basename(song)}")
            try:
                ffmpeg.play(path=song, p=p, speaker_index=speaker_index, cable_index=cable_index)
            except Exception as exc:
                print(f"Playback failed for {song}: {exc}")

            if state.consume_skip_request():
                continue


class RadioHandler(BaseHTTPRequestHandler):
    state: RadioState
    web_root: Path

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if file_path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif file_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            content_type = f"image/{file_path.suffix.lstrip('.')}"
        else:
            content_type = "application/octet-stream"

        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/now-playing":
            snap = self.state.snapshot()
            song_name = os.path.basename(snap["current_song"]) if snap["current_song"] else None
            self._send_json(HTTPStatus.OK, {**snap, "display_name": song_name})
            return

        if path == "/api/queue":
            self._send_json(
                HTTPStatus.OK,
                {
                    "songs": [os.path.basename(s) for s in self.state.songs],
                    "count": len(self.state.songs),
                },
            )
            return

        if path in {"/", "/index.html"}:
            self._serve_file(self.web_root / "index.html")
            return

        static_file = (self.web_root / path.lstrip("/")).resolve()
        if self.web_root in static_file.parents or static_file == self.web_root:
            self._serve_file(static_file)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/skip":
            self.state.request_skip()
            self._send_json(HTTPStatus.OK, {"ok": True})
            return

        if parsed.path == "/api/volume":
            params = parse_qs(parsed.query)
            try:
                value = float(params.get("value", [""])[0])
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid value"})
                return
            self.state.set_volume(value)
            self._send_json(HTTPStatus.OK, {"ok": True, "volume": value})
            return

        if parsed.path == "/api/discord/token":
            body = self._read_json_body()
            code = body.get("code")
            client_id = os.getenv("DISCORD_CLIENT_ID")
            client_secret = os.getenv("DISCORD_CLIENT_SECRET")
            if not code or not client_id or not client_secret:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Missing code or DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET"},
                )
                return

            payload = urlencode(
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": "https://127.0.0.1",
                }
            ).encode("utf-8")

            req = Request(
                "https://discord.com/api/oauth2/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urlopen(req) as response:
                    token_data = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_GATEWAY, {"error": f"token exchange failed: {exc}"})
                return

            self._send_json(HTTPStatus.OK, token_data)
            return

        self.send_error(HTTPStatus.NOT_FOUND)


def main():
    parser = argparse.ArgumentParser(description="Discord Activity style local radio server")
    parser.add_argument("--music-folder", default="./music")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--speaker-index", type=int)
    parser.add_argument("--cable-index", type=int)
    parser.add_argument("--ffmpeg-path", default=None)
    parser.add_argument("--volume", type=float, default=0.7)
    args = parser.parse_args()

    p = pyaudio.PyAudio()
    list_outputs(p)

    fm = FileManager(
        music_folder=args.music_folder,
        allowed_extensions={".mp3", ".wav", ".flac", ".ogg", ".m4a"},
        shuffle=True,
    )
    songs = fm.get_playlist(includeSubDirectories=True)
    if not songs:
        raise RuntimeError(f"No songs found in {args.music_folder}")

    ffmpeg = OutFFMPEG(volume=args.volume, ffmpeg_path=args.ffmpeg_path)
    state = RadioState(songs=songs, volume=args.volume)

    thread = threading.Thread(
        target=player_loop,
        args=(state, ffmpeg, p, args.speaker_index, args.cable_index),
        daemon=True,
    )
    thread.start()

    RadioHandler.state = state
    RadioHandler.web_root = Path(__file__).parent / "web"

    server = ThreadingHTTPServer((args.host, args.port), RadioHandler)
    print(f"Activity UI: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
