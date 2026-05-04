# device_manager.py
import pyaudio

class DeviceManager:
    def __init__(self, pyaudio_instance: pyaudio.PyAudio, *, verbose=True):
        self.p = pyaudio_instance
        self.verbose = verbose

    def list_outputs(self):
        outs = []
        for i in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(i)
            if info.get("maxOutputChannels", 0) > 0:
                outs.append((i, info["name"]))
        return outs

    # def find_device_index(self, name):
    #     if self.verbose:
    #         print("\n=== OUTPUT DEVICES ===")
    #         for i, n in self.list_outputs():
    #             print(f"{i}: {n}")
    #         print("======================\n")

    #     if name is None:
    #         return None

    #     for i, n in self.list_outputs():
    #         if name.lower() in n.lower():
    #             return i  # FIRST match

        return None
