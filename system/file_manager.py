import os
import random

class FileManager:
    def __init__(self, music_folder, allowed_extensions, shuffle=True):
        self.MUSIC_FOLDER = music_folder
        self.ALLOWED_EXTENSIONS = set(e.lower() for e in allowed_extensions)
        self.SHUFFLE = shuffle

    def get_playlist(self, includeSubDirectories=False):
        songs = []
        print("MUSIC_FOLDER abs:", os.path.abspath(self.MUSIC_FOLDER))

        try:
            print("Top-level files:", os.listdir(self.MUSIC_FOLDER))
        except Exception as e:
            print("Cannot list MUSIC_FOLDER:", e)

        if includeSubDirectories:
            for root, _, files in os.walk(self.MUSIC_FOLDER):
               for f in files:
                   if os.path.splitext(f)[1].lower() in self.ALLOWED_EXTENSIONS:
                        songs.append(os.path.join(root, f))
        else:
            for f in os.listdir(self.MUSIC_FOLDER):
                full = os.path.join(self.MUSIC_FOLDER, f)
                if os.path.isfile(full) and os.path.splitext(f)[1].lower() in self.ALLOWED_EXTENSIONS:
                    songs.append(full)

        if self.SHUFFLE:
            random.shuffle(songs)

        return songs