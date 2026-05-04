# ffmpeg_player.py
import os
import subprocess
import numpy as np
import pyaudio

class OutFFMPEG:
    def __init__(self, *, volume=1.0, chunk_frames=1024, out_rate=48000, out_ch=2, ffmpeg_path=None):
        self.volume = float(volume)
        self.chunk_frames = int(chunk_frames)
        self.out_rate = int(out_rate)
        self.out_ch = int(out_ch)
        self.ffmpeg_path = ffmpeg_path  # optional override

    def _find_ffmpeg(self) -> str:
        if self.ffmpeg_path:
            if not os.path.exists(self.ffmpeg_path):
                raise RuntimeError(f"ffmpeg.exe not found at: {self.ffmpeg_path}")
            return self.ffmpeg_path

        # default: ../ffmpeg/ffmpeg.exe relative to this file
        here = os.path.dirname(os.path.abspath(__file__))
        ff = os.path.abspath(os.path.join(here, "..", "ffmpeg", "ffmpeg.exe"))
        if not os.path.exists(ff):
            raise RuntimeError(f"ffmpeg.exe not found at: {ff}")
        return ff

    def _apply_volume_int16(self, pcm_bytes: bytes) -> bytes:
        if self.volume >= 0.999:
            return pcm_bytes
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        audio = np.clip(audio * self.volume, -32768, 32767)
        return audio.astype(np.int16).tobytes()

    def stream(self, path):

        ffmpeg = self._find_ffmpeg()

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-vn", "-sn",
            "-i", path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ac", str(self.out_ch),
            "-ar", str(self.out_rate),
            "pipe:1",
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)

        chunk_bytes = self.chunk_frames * self.out_ch * 2

        while True:

            data = proc.stdout.read(chunk_bytes)

            if not data:
                break

            yield data

        proc.stdout.close()
        proc.wait()

    def play(self, *, path: str, p: pyaudio.PyAudio, speaker_index=None, cable_index=None):
        print(f"▶ FFMPEG Now playing: {os.path.basename(path)}")

        ffmpeg = self._find_ffmpeg()
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-vn", "-sn",
            "-i", path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ac", str(self.out_ch),
            "-ar", str(self.out_rate),
            "pipe:1",
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stream_speaker = None
        if speaker_index is not None:
            stream_speaker = p.open(
                format=pyaudio.paInt16,
                channels=self.out_ch,
                rate=self.out_rate,
                output=True,
                output_device_index=speaker_index
            )

        stream_cable = None
        if cable_index is not None:
            stream_cable = p.open(
                format=pyaudio.paInt16,
                channels=self.out_ch,
                rate=self.out_rate,
                output=True,
                output_device_index=cable_index
            )

        if stream_speaker is None and stream_cable is None:
            proc.kill()
            raise ValueError("No outputs configured: set speaker_index and/or cable_index")

        chunk_bytes = self.chunk_frames * self.out_ch * 2  # int16

        try:
            while True:
                data = proc.stdout.read(chunk_bytes)
                if not data:
                    break

                data = self._apply_volume_int16(data)

                if stream_speaker:
                    stream_speaker.write(data)
                if stream_cable:
                    stream_cable.write(data)

        finally:
            if stream_cable:
                stream_cable.close()
            if stream_speaker:
                stream_speaker.close()

            if proc.stdout:
                proc.stdout.close()

            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            ret = proc.wait()
            if ret != 0:
                raise RuntimeError(f"ffmpeg failed (exit {ret}): {stderr.strip()}")
