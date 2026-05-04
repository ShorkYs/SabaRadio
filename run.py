import pyaudio

from system.file_manager import FileManager
from system.device_manager import DeviceManager

from radio_controller import RadioController
from radio_engine import RadioEngine
from ui.dashboard import Dashboard


MUSIC_FOLDER = "music"

ALLOWED_EXTENSIONS = [
".wav",".mp3",".flac",".m4a",".aac",".ogg",".opus",".wma"
]

CABLE_DEVICE = "CABLE Input"

p = pyaudio.PyAudio()

device_manager = DeviceManager(p)

print("\nAvailable Audio Outputs:\n")

for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)

    if info["maxOutputChannels"] > 0:
        print(i, ":", info["name"])

def find_device(name):

    if name is None:
        return None

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)

        if info["maxOutputChannels"] > 0:
            if name.lower() in info["name"].lower():
                return i

    return None


cable_index = find_device(CABLE_DEVICE)
speaker_index = None


controller = RadioController()
controller.pyaudio_instance = p

file_manager = FileManager(
    MUSIC_FOLDER,
    ALLOWED_EXTENSIONS,
    shuffle=True
)

controller.playlist = file_manager.get_playlist()


engine = RadioEngine(
    controller,
    p,
    speaker_index,
    cable_index
)

engine.start()


dashboard = Dashboard(controller)

dashboard.run()