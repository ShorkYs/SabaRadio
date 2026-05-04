import threading

class RadioController:

    def __init__(self):
        self.lock = threading.Lock()

        self.current_song = None
        self.queue = []
        self.playlist = []

        self.playing = False
        self.shuffle = True
        self.loop = True

        self.volume = 0.2

        self.song_position = 0
        self.song_length = 0

        self.crossfade_seconds = 5
        self.output_device_index = None
        self.mic_mix = 0.0
        self.mic_input_device_index = None

    def play(self):
        with self.lock:
            self.playing = True

    def pause(self):
        with self.lock:
            self.playing = False

    def skip(self):
        with self.lock:
            self.current_song = None

    def toggle_shuffle(self):
        with self.lock:
            self.shuffle = not self.shuffle

    def set_volume(self, v):
        with self.lock:
            self.volume = v

    def add_to_queue(self, song):
        with self.lock:
            self.queue.append(song)

    def get_next_song(self):

        with self.lock:

            if self.queue:
                return self.queue.pop(0)

            if not self.playlist:
                return None

            import random

            if self.shuffle:
                return random.choice(self.playlist)

            return self.playlist.pop(0)

    def set_output_device(self, index):
        with self.lock:
            self.output_device_index = index

    def set_crossfade(self, seconds):
        with self.lock:
            self.crossfade_seconds = max(0, int(float(seconds)))

    def set_mic_mix(self, value):
        with self.lock:
            self.mic_mix = max(0.0, min(1.0, float(value)))


    def set_mic_input_device(self, index):
        with self.lock:
            self.mic_input_device_index = index
