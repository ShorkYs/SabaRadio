import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
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

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma"}


class RadioState:
    def __init__(self, songs: list[str], volume: float, durations: dict[str, float] | None = None):
        self.lock = threading.Lock()
        self.songs = songs
        self.durations = durations or {}
        self.current_index = -1
        self.current_song: str | None = None
        self.current_started_at: float | None = None
        self.volume = volume
        self.skip_requested = False

    def snapshot(self) -> dict:
        with self.lock:
            previous_index = (self.current_index - 1) % len(self.songs) if self.songs and self.current_index >= 0 else None
            next_index = (self.current_index + 1) % len(self.songs) if self.songs and self.current_index >= 0 else None
            duration = self.durations.get(self.current_song or "", 0.0)
            elapsed = max(0.0, time.time() - self.current_started_at) if self.current_started_at else 0.0
            progress = min(1.0, elapsed / duration) if duration > 0 else 0.0
            queue_window = []
            if self.songs and self.current_index >= 0:
                queue_window = [
                    {
                        "index": (self.current_index + offset) % len(self.songs),
                        "song": self.songs[(self.current_index + offset) % len(self.songs)],
                    }
                    for offset in range(min(5, len(self.songs)))
                ]
            return {
                "current_song": self.current_song,
                "current_index": self.current_index,
                "current_started_at": self.current_started_at,
                "current_duration": duration,
                "current_elapsed": elapsed,
                "current_progress": progress,
                "total_songs": len(self.songs),
                "volume": self.volume,
                "previous_song": self.songs[previous_index] if previous_index is not None else None,
                "next_song": self.songs[next_index] if next_index is not None else None,
                "queue_window": queue_window,
                "stream_url": "/api/stream/current" if self.current_song else None,
            }

    def set_current(self, index: int, song: str):
        with self.lock:
            self.current_index = index
            self.current_song = song
            self.current_started_at = time.time()
            self.skip_requested = False

    def request_skip(self):
        with self.lock:
            self.skip_requested = True

    def consume_skip_request(self) -> bool:
        with self.lock:
            requested = self.skip_requested
            self.skip_requested = False
            return requested

    def wants_skip(self) -> bool:
        with self.lock:
            return self.skip_requested

    def set_volume(self, value: float):
        with self.lock:
            self.volume = max(0.0, min(1.0, value))

    def get_volume(self) -> float:
        with self.lock:
            return self.volume

    def get_duration(self, song: str) -> float:
        with self.lock:
            return self.durations.get(song, 0.0)


def display_name(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).stem.replace("_", " ").replace("-", " ")


def list_outputs(p: pyaudio.PyAudio) -> None:
    manager = DeviceManager(p)
    print("\n=== OUTPUT DEVICES ===")
    for i, name in manager.list_outputs():
        print(f"{i}: {name}")
    print("======================\n")


def open_output_stream(p: pyaudio.PyAudio, ffmpeg: OutFFMPEG, device_index: int | None):
    if device_index is None:
        return None
    return p.open(
        format=pyaudio.paInt16,
        channels=ffmpeg.out_ch,
        rate=ffmpeg.out_rate,
        output=True,
        output_device_index=device_index,
    )


def player_loop(state: RadioState, ffmpeg: OutFFMPEG, p: pyaudio.PyAudio, speaker_index: int | None, cable_index: int | None):
    outputs_enabled = speaker_index is not None or cable_index is not None
    if not outputs_enabled:
        print("No PyAudio output devices were selected; the Discord Activity browser stream is still available.")

    while True:
        for idx, song in enumerate(state.songs):
            state.set_current(idx, song)
            print(f"▶ Now playing: {os.path.basename(song)}")

            if not outputs_enabled:
                duration = state.get_duration(song)
                while not state.wants_skip():
                    if duration > 0 and state.snapshot()["current_elapsed"] >= duration:
                        break
                    time.sleep(0.2)
                state.consume_skip_request()
                continue

            stream_speaker = stream_cable = None
            try:
                stream_speaker = open_output_stream(p, ffmpeg, speaker_index)
                stream_cable = open_output_stream(p, ffmpeg, cable_index)
                for data in ffmpeg.stream(song):
                    if state.wants_skip():
                        break
                    ffmpeg.volume = state.get_volume()
                    data = ffmpeg._apply_volume_int16(data)
                    if stream_speaker:
                        stream_speaker.write(data)
                    if stream_cable:
                        stream_cable.write(data)
            except Exception as exc:
                print(f"Playback failed for {song}: {exc}")
            finally:
                if stream_cable:
                    stream_cable.close()
                if stream_speaker:
                    stream_speaker.close()
                state.consume_skip_request()


class RadioHandler(BaseHTTPRequestHandler):
    state: RadioState
    web_root: Path

    def log_message(self, format, *args):
        return

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".html":
            content_type = "text/html; charset=utf-8"

        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_audio(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")
        start = 0
        end = file_size - 1
        status = HTTPStatus.OK

        if range_header:
            units, _, range_spec = range_header.partition("=")
            if units == "bytes":
                first, _, last = range_spec.partition("-")
                start = int(first) if first else 0
                end = int(last) if last else end
                end = min(end, file_size - 1)
                status = HTTPStatus.PARTIAL_CONTENT

        if start > end or start >= file_size:
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            return

        length = end - start + 1
        content_type = mimetypes.guess_type(file_path.name)[0] or "audio/mpeg"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        with file_path.open("rb") as src:
            src.seek(start)
            remaining = length
            while remaining > 0:
                chunk = src.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

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
            self._send_json(
                HTTPStatus.OK,
                {
                    **snap,
                    "display_name": display_name(snap["current_song"]),
                    "file_name": os.path.basename(snap["current_song"]) if snap["current_song"] else None,
                    "previous_display_name": display_name(snap["previous_song"]),
                    "next_display_name": display_name(snap["next_song"]),
                    "queue_window": [
                        {**item, "display_name": display_name(item["song"]), "file_name": os.path.basename(item["song"])}
                        for item in snap["queue_window"]
                    ],
                },
            )
            return

        if path == "/api/queue":
            self._send_json(
                HTTPStatus.OK,
                {
                    "songs": [
                        {"file_name": os.path.basename(song), "display_name": display_name(song)}
                        for song in self.state.songs
                    ],
                    "count": len(self.state.songs),
                },
            )
            return

        if path == "/api/stream/current":
            current = self.state.snapshot()["current_song"]
            if not current:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._serve_audio(Path(current))
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
                    "redirect_uri": os.getenv("DISCORD_REDIRECT_URI", "https://127.0.0.1"),
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


def probe_duration_seconds(ffmpeg: OutFFMPEG, path: str) -> float:
    try:
        ffmpeg_path = Path(ffmpeg._find_ffmpeg())
        ffprobe = ffmpeg_path.with_name("ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe")
        ffprobe_cmd = str(ffprobe) if ffprobe.exists() else "ffprobe"
        output = subprocess.check_output(
            [
                ffprobe_cmd,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
        )
        return max(0.0, float(output.strip()))
    except Exception as exc:
        print(f"Could not probe duration for {os.path.basename(path)}: {exc}")
        return 0.0


def resolve_songs(music_folder: str, radio_file: str | None) -> list[str]:
    if radio_file:
        file_path = Path(radio_file).expanduser().resolve()
        if not file_path.is_file():
            raise RuntimeError(f"Radio file not found: {file_path}")
        if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise RuntimeError(f"Unsupported radio file extension: {file_path.suffix}")
        return [str(file_path)]

    fm = FileManager(
        music_folder=music_folder,
        allowed_extensions=AUDIO_EXTENSIONS,
        shuffle=True,
    )
    return fm.get_playlist(includeSubDirectories=True)


def main():
    parser = argparse.ArgumentParser(description="Local Saba Radio server for a Discord Activity")
    parser.add_argument("--music-folder", default="./music", help="Folder to scan when --radio-file is not set")
    parser.add_argument("--radio-file", help="Play one local audio file on loop instead of scanning a folder")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--speaker-index", type=int)
    parser.add_argument("--cable-index", type=int, help="Virtual cable output device index for piping audio into Discord")
    parser.add_argument("--ffmpeg-path", default=None)
    parser.add_argument("--volume", type=float, default=0.7)
    args = parser.parse_args()

    p = pyaudio.PyAudio()
    list_outputs(p)

    songs = resolve_songs(args.music_folder, args.radio_file)
    if not songs:
        raise RuntimeError(f"No songs found in {args.music_folder}")

    ffmpeg = OutFFMPEG(volume=args.volume, ffmpeg_path=args.ffmpeg_path)
    durations = {song: probe_duration_seconds(ffmpeg, song) for song in songs}
    state = RadioState(songs=songs, volume=args.volume, durations=durations)

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
    print("Use --radio-file path/to/song.mp3 for a single local radio file, or --music-folder for a playlist.")
    print("Set --cable-index to a virtual audio cable input if you want Discord voice to receive the same audio.")
    server.serve_forever()


if __name__ == "__main__":
    main()
