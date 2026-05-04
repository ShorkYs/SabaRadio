# output_pyaudio.py
import os
import wave
import math
import numpy as np
import pyaudio

class OutPyAudio:
    def __init__(self, *, volume=1.0, chunk_frames=1024):
        self.volume = float(volume)
        self.chunk_frames = int(chunk_frames)

    def _apply_volume_int16(self, pcm_bytes: bytes) -> bytes:
        if self.volume >= 0.999:
            return pcm_bytes
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        audio = np.clip(audio * self.volume, -32768, 32767)
        return audio.astype(np.int16).tobytes()

    def play(self, *, path: str, p: pyaudio.PyAudio, speaker_index=None, cable_index=None):
        """
        WAV/PCM playback using Python's wave module.
        Only reliable for PCM WAVs. (FFmpeg backend handles the weird WAVs.)
        """
        wf = wave.open(path, "rb")

        streams = []
        try:
            fmt = p.get_format_from_width(wf.getsampwidth())
            ch = wf.getnchannels()
            rate = wf.getframerate()

            if speaker_index is not None:
                streams.append(p.open(format=fmt, channels=ch, rate=rate, output=True,
                                      output_device_index=speaker_index))
            if cable_index is not None:
                streams.append(p.open(format=fmt, channels=ch, rate=rate, output=True,
                                      output_device_index=cable_index))

            if not streams:
                raise ValueError("No outputs configured: set speaker_index and/or cable_index")

            print(f"▶ WAV Now playing: {os.path.basename(path)}  ({ch}ch {rate}Hz {wf.getsampwidth()*8}-bit)")

            data = wf.readframes(self.chunk_frames)
            while data:
                # only apply volume safely for 16-bit PCM
                if wf.getsampwidth() == 2:
                    data = self._apply_volume_int16(data)

                for s in streams:
                    s.write(data)

                data = wf.readframes(self.chunk_frames)

        finally:
            for s in streams:
                try: s.close()
                except Exception: pass
            wf.close()

    def test_device_output(self, *, p: pyaudio.PyAudio, device_index, seconds=0.6, rate=44100):
        stream = p.open(
            format=pyaudio.paInt16,
            channels=2,
            rate=rate,
            output=True,
            output_device_index=device_index
        )
        t = np.arange(int(rate * seconds))
        tone = (0.2 * 32767 * np.sin(2 * math.pi * 440 * t / rate)).astype(np.int16)
        stereo = np.repeat(tone[:, None], 2, axis=1).reshape(-1)
        stream.write(stereo.tobytes())
        stream.close()
