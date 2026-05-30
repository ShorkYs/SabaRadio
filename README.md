# Saba_Radio

## Local Discord Activity radio

Run a single local radio file and expose the Saba Radio Activity UI from the built-in Python server:

```bash
python activity/discord_activity_radio.py --radio-file ./music/song.mp3 --host 127.0.0.1 --port 8787
```

Or scan a folder recursively:

```bash
python activity/discord_activity_radio.py --music-folder ./music --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787` to use the Figma-style Saba Radio layout. The Activity includes a play button that streams the current local file through `/api/stream/current`, skip/refresh controls, queue labels, clock, progress, and volume sync.

To send the same local playback into Discord voice, route a virtual audio cable and pass its PyAudio output device index:

```bash
python activity/discord_activity_radio.py --radio-file ./music/song.mp3 --cable-index 12 --speaker-index 5
```

The server prints available output devices on startup. Use `--cable-index` for the virtual cable input that Discord can use as a microphone/input source, and optionally `--speaker-index` for local monitoring.

If `ffmpeg` is not bundled in `./ffmpeg/ffmpeg.exe`, install it on your `PATH` or pass `--ffmpeg-path /path/to/ffmpeg`.

For Discord Activity OAuth, set `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` on the Python server. When developing through Vite, set `VITE_DISCORD_CLIENT_ID` for the web client.

### Background switcher config

Edit `activity/web/backgrounds.config.js` to assign the Activity backgrounds. Each entry has:

- `title`: label shown in the background switcher.
- `image`: thumbnail/card image used by the switcher.
- `background`: full-screen background image applied when that entry is active.

The middle card is the active background. Click either side card to rotate to that configured background.
