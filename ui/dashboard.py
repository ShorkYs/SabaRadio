import json
import os
import random
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk

CONFIG_PATH = "radio_settings.json"


class Dashboard:
    def __init__(self, controller):
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("📻 Saba Radio")
        self.root.geometry("1200x760")
        self.root.configure(bg="#050b1d")

        self.background_presets = []
        self.current_preset_idx = -1
        self.current_theme = "day"
        self.bg_frames = []
        self.bg_after_id = None
        self.bg_frame_idx = 0

        self.soundboard_clips = []
        self.output_map = {"Default": None}
        self.mic_map = {"None": None}

        self.build_ui()
        self.bind_hotkeys()
        self.load_devices()
        self.load_settings()
        self.update_loop()

    def build_ui(self):
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg="#050b1d")
        self.canvas.pack(fill="both", expand=True)
        self.bg_rect = self.canvas.create_rectangle(0, 0, 1, 1, fill="#0f2559", outline="")
        self.bg_img = self.canvas.create_image(0, 0, anchor="nw")

        self.card = tk.Frame(self.canvas, bg="#0c1328")
        self.canvas_card = self.canvas.create_window(0, 0, window=self.card)

        self.time_label = tk.Label(self.card, text="", font=("Segoe UI", 48, "bold"), fg="#f8fafc", bg="#0c1328")
        self.time_label.pack(pady=(18, 8))

        self.song_label = tk.Label(self.card, text="No song", font=("Segoe UI", 16, "bold"), fg="#f8fafc", bg="#0c1328")
        self.song_label.pack()
        self.state_label = tk.Label(self.card, text="Idle", font=("Segoe UI", 11), fg="#cbd5e1", bg="#0c1328")
        self.state_label.pack(pady=(0, 10))

        self.wave_canvas = tk.Canvas(self.card, height=74, bg="#0b1020", highlightthickness=0)
        self.wave_canvas.pack(fill="x", padx=18)

        self.progress = ttk.Progressbar(self.card, maximum=100)
        self.progress.pack(fill="x", padx=18, pady=(12, 14))

        dock = tk.Frame(self.card, bg="#111827")
        dock.pack(fill="x", padx=18, pady=(0, 18))

        left = tk.Frame(dock, bg="#111827")
        left.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        tk.Label(left, text="Now Playing", fg="#e2e8f0", bg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(left, text="Saba Radio", fg="#94a3b8", bg="#111827", font=("Segoe UI", 10)).pack(anchor="w")

        controls = tk.Frame(dock, bg="#111827")
        controls.pack(side="left", padx=12)
        for t, fn in [("⏮", self.skip), ("⏯", self.toggle_play_pause), ("⏭", self.skip)]:
            tk.Button(controls, text=t, command=fn, width=3).pack(side="left", padx=3)

        right = tk.Frame(dock, bg="#111827")
        right.pack(side="right", padx=8)
        tk.Button(right, text="🌗", command=self.toggle_theme).pack(side="left", padx=3)
        tk.Button(right, text="💾", command=self.save_settings).pack(side="left", padx=3)

        panel = tk.Frame(self.card, bg="#0c1328")
        panel.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        tk.Button(panel, text="Play", command=self.play).grid(row=0, column=0, padx=4, pady=4)
        tk.Button(panel, text="Pause", command=self.pause).grid(row=0, column=1, padx=4, pady=4)
        tk.Button(panel, text="Shuffle", command=self.shuffle).grid(row=0, column=2, padx=4, pady=4)
        tk.Button(panel, text="Add Songs", command=self.add_songs).grid(row=0, column=3, padx=4, pady=4)
        tk.Button(panel, text="Add Soundboard", command=self.add_soundboard_clip).grid(row=0, column=4, padx=4, pady=4)

        tk.Scale(panel, from_=0, to=1, resolution=0.01, command=lambda v: self.controller.set_volume(float(v)), label="Volume", orient="horizontal", length=130).grid(row=0, column=5, padx=4)
        tk.Scale(panel, from_=0, to=1, resolution=0.01, command=lambda v: self.controller.set_mic_mix(float(v)), label="Mic Mix", orient="horizontal", length=130).grid(row=0, column=6, padx=4)

        tk.Label(panel, text="Output", bg="#0c1328", fg="#cbd5e1").grid(row=1, column=0, sticky="e")
        self.output_var = tk.StringVar(value="Default")
        self.output_combo = ttk.Combobox(panel, textvariable=self.output_var, width=32, state="readonly")
        self.output_combo.grid(row=1, column=1, columnspan=3, sticky="we", padx=3)
        self.output_combo.bind("<<ComboboxSelected>>", lambda _e: self.controller.set_output_device(self.output_map.get(self.output_var.get())))

        tk.Label(panel, text="Microphone", bg="#0c1328", fg="#cbd5e1").grid(row=1, column=4, sticky="e")
        self.mic_var = tk.StringVar(value="None")
        self.mic_combo = ttk.Combobox(panel, textvariable=self.mic_var, width=28, state="readonly")
        self.mic_combo.grid(row=1, column=5, columnspan=2, sticky="we", padx=3)
        self.mic_combo.bind("<<ComboboxSelected>>", lambda _e: self.controller.set_mic_input_device(self.mic_map.get(self.mic_var.get())))

        tk.Label(panel, text="Background Preset", bg="#0c1328", fg="#cbd5e1").grid(row=2, column=0, sticky="e")
        self.preset_var = tk.StringVar(value="None")
        self.preset_combo = ttk.Combobox(panel, textvariable=self.preset_var, width=32, state="readonly")
        self.preset_combo.grid(row=2, column=1, columnspan=3, sticky="we", padx=3, pady=4)
        self.preset_combo.bind("<<ComboboxSelected>>", self.select_preset)
        tk.Button(panel, text="Add BG Preset", command=self.add_background_preset).grid(row=2, column=4, padx=3)

        self.queue_list = tk.Listbox(panel, height=6)
        self.queue_list.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=6)
        self.soundboard_list = tk.Listbox(panel, height=6)
        self.soundboard_list.grid(row=3, column=4, columnspan=3, sticky="nsew", pady=6)
        tk.Button(panel, text="Play Clip", command=self.play_soundboard_clip).grid(row=4, column=4, pady=4)

        self.root.bind("<Configure>", self.on_resize)

    def bind_hotkeys(self):
        self.root.bind("<space>", lambda _e: self.toggle_play_pause())
        self.root.bind("n", lambda _e: self.skip())

    def toggle_play_pause(self):
        self.pause() if self.controller.playing else self.play()

    def load_devices(self):
        p = getattr(self.controller, "pyaudio_instance", None)
        outputs, mics = ["Default"], ["None"]
        if p:
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxOutputChannels", 0) > 0:
                    label = f"{i}: {info['name']}"
                    outputs.append(label)
                    self.output_map[label] = i
                if info.get("maxInputChannels", 0) > 0:
                    label = f"{i}: {info['name']}"
                    mics.append(label)
                    self.mic_map[label] = i
        self.output_combo["values"] = outputs
        self.output_combo.set(outputs[0])
        self.mic_combo["values"] = mics
        self.mic_combo.set(mics[0])

    def add_songs(self):
        for s in filedialog.askopenfilenames(filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.opus *.wma")]):
            self.controller.add_to_queue(s)

    def add_soundboard_clip(self):
        clip = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg")])
        if clip:
            self.soundboard_clips.append(clip)
            self.soundboard_list.insert(tk.END, os.path.basename(clip))

    def play_soundboard_clip(self):
        idx = self.soundboard_list.curselection()
        if idx:
            self.controller.queue.insert(0, self.soundboard_clips[idx[0]])

    def add_background_preset(self):
        day = filedialog.askopenfilename(title="Day background", filetypes=[("Media", "*.gif *.png")])
        if not day:
            return
        night = filedialog.askopenfilename(title="Night background", filetypes=[("Media", "*.gif *.png")])
        preset = {"name": f"Preset {len(self.background_presets)+1}", "day": day or None, "night": night or None}
        self.background_presets.append(preset)
        self.refresh_preset_combo()
        self.current_preset_idx = len(self.background_presets) - 1
        self.preset_combo.current(self.current_preset_idx)
        self.apply_background(self.current_theme)

    def refresh_preset_combo(self):
        names = [p["name"] for p in self.background_presets] or ["None"]
        self.preset_combo["values"] = names
        if not self.background_presets:
            self.preset_combo.set("None")

    def select_preset(self, _e=None):
        if not self.background_presets:
            return
        self.current_preset_idx = self.preset_combo.current()
        self.apply_background(self.current_theme)

    def _current_bg_path(self, theme):
        if self.current_preset_idx < 0 or self.current_preset_idx >= len(self.background_presets):
            return None
        return self.background_presets[self.current_preset_idx].get(theme)

    def toggle_theme(self):
        self.current_theme = "night" if self.current_theme == "day" else "day"
        self.apply_background(self.current_theme)

    def apply_background(self, theme):
        path = self._current_bg_path(theme)
        if self.bg_after_id:
            self.root.after_cancel(self.bg_after_id)
            self.bg_after_id = None
        self.bg_frames = []
        if not path or not os.path.exists(path):
            self.canvas.itemconfig(self.bg_rect, fill="#173d7a" if theme == "day" else "#07122b")
            self.canvas.itemconfig(self.bg_img, image="")
            return
        if path.lower().endswith(".gif"):
            i = 0
            while True:
                try:
                    self.bg_frames.append(tk.PhotoImage(file=path, format=f"gif -index {i}")); i += 1
                except tk.TclError:
                    break
        else:
            self.bg_frames = [tk.PhotoImage(file=path)]
        self._animate_bg()

    def _animate_bg(self):
        if not self.bg_frames:
            return
        frame = self.bg_frames[self.bg_frame_idx % len(self.bg_frames)]
        self.canvas.itemconfig(self.bg_img, image=frame)
        self.bg_frame_idx += 1
        self.bg_after_id = self.root.after(90, self._animate_bg)

    def save_settings(self):
        data = {
            "background_presets": self.background_presets,
            "current_preset_idx": self.current_preset_idx,
            "theme": self.current_theme,
            "output": self.output_var.get(),
            "microphone": self.mic_var.get(),
            "soundboard": self.soundboard_clips,
            "volume": self.controller.volume,
            "mic_mix": self.controller.mic_mix,
            "crossfade": self.controller.crossfade_seconds,
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_settings(self):
        if not os.path.exists(CONFIG_PATH):
            return
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.background_presets = data.get("background_presets", [])
        self.current_preset_idx = data.get("current_preset_idx", -1)
        self.current_theme = data.get("theme", "day")
        self.soundboard_clips = [c for c in data.get("soundboard", []) if os.path.exists(c)]
        self.soundboard_list.delete(0, tk.END)
        for c in self.soundboard_clips:
            self.soundboard_list.insert(tk.END, os.path.basename(c))
        self.refresh_preset_combo()
        if self.background_presets and 0 <= self.current_preset_idx < len(self.background_presets):
            self.preset_combo.current(self.current_preset_idx)
        if data.get("output") in self.output_map:
            self.output_var.set(data["output"])
        if data.get("microphone") in self.mic_map:
            self.mic_var.set(data["microphone"])
            self.controller.set_mic_input_device(self.mic_map[self.mic_var.get()])
        self.controller.set_volume(data.get("volume", self.controller.volume))
        self.controller.set_mic_mix(data.get("mic_mix", self.controller.mic_mix))
        self.controller.set_crossfade(data.get("crossfade", self.controller.crossfade_seconds))

    def on_resize(self, _e=None):
        w, h = self.root.winfo_width(), self.root.winfo_height()
        self.canvas.coords(self.bg_rect, 0, 0, w, h)
        self.canvas.coords(self.bg_img, 0, 0)
        self.canvas.coords(self.canvas_card, w // 2, h // 2)

    def play(self): self.controller.play()
    def pause(self): self.controller.pause()
    def skip(self): self.controller.skip()
    def shuffle(self): self.controller.toggle_shuffle()

    def animate_waveform(self):
        self.wave_canvas.delete("all")
        width = max(self.wave_canvas.winfo_width(), 100)
        bar_w = width / 40
        for i in range(40):
            amp = random.randint(10, 58) if self.controller.playing else 8
            self.wave_canvas.create_rectangle(i * bar_w, 65 - amp, i * bar_w + bar_w - 2, 65, fill="#38bdf8", outline="")

    def update_loop(self):
        now = datetime.now().strftime("%-I:%M %p") if os.name != "nt" else datetime.now().strftime("%I:%M %p").lstrip("0")
        self.time_label.config(text=now)
        song = self.controller.current_song
        self.song_label.config(text=os.path.basename(song) if song else "No song")
        self.state_label.config(text="Playing" if song else "Idle")
        self.progress["value"] = (self.progress["value"] + (2 if song else 0.3)) % 100
        self.queue_list.delete(0, tk.END)
        for q in self.controller.queue[:80]:
            self.queue_list.insert(tk.END, os.path.basename(q))
        self.animate_waveform()
        self.root.after(200, self.update_loop)

    def run(self):
        self.apply_background(self.current_theme)
        self.on_resize()
        self.root.mainloop()
