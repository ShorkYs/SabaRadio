import numpy as np


class CrossfadePlayer:

    def __init__(self, p, speaker_index, cable_index, rate, channels):

        self.p = p
        self.rate = rate
        self.channels = channels

        self.stream_speaker = None
        self.stream_cable = None

        if speaker_index is not None:
            self.stream_speaker = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                output=True,
                output_device_index=speaker_index
            )

        if cable_index is not None:
            self.stream_cable = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                output=True,
                output_device_index=cable_index
            )

    def write(self, data):

        if self.stream_speaker:
            self.stream_speaker.write(data)

        if self.stream_cable:
            self.stream_cable.write(data)

    def close(self):

        if self.stream_speaker:
            self.stream_speaker.close()

        if self.stream_cable:
            self.stream_cable.close()


def mix(a, b, fade):

    a = np.frombuffer(a, dtype=np.int16).astype(np.float32)
    b = np.frombuffer(b, dtype=np.int16).astype(np.float32)

    mixed = a * (1 - fade) + b * fade

    mixed = np.clip(mixed, -32768, 32767)

    return mixed.astype(np.int16).tobytes()