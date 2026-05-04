import threading
import time
import os

from audio.output_ffmpeg import OutFFMPEG

CROSSFADE_SECONDS = 5

class RadioEngine(threading.Thread):

    def __init__(self, controller, pyaudio_instance, speaker_index, cable_index):
        super().__init__(daemon=True)

        self.controller = controller
        self.p = pyaudio_instance
        self.speaker_index = speaker_index
        self.cable_index = cable_index

        self.ffmpeg = OutFFMPEG()

        self.running = True

    def run(self):

        while self.running:

            if not self.controller.playing:
                time.sleep(0.2)
                continue

            song = self.controller.get_next_song()

            if not song:
                time.sleep(1)
                continue

            self.controller.current_song = song

            try:

                self.ffmpeg.volume = self.controller.volume

                self.ffmpeg.play(
                    path=song,
                    p=self.p,
                    speaker_index=self.speaker_index,
                    cable_index=self.cable_index
                )

            except Exception as e:
                print("Song failed:", e)

            self.controller.current_song = None

    def stop(self):
        self.running = False