from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk


class VideoPlayer(tk.Frame):
    """Silent in-app preview player for NewsFlow's short footage clips."""

    def __init__(self, parent, colors: dict[str, str]):
        super().__init__(parent, bg=colors["card"])
        self.colors = colors
        self.capture = None
        self.path = ""
        self.playing = False
        self.fps = 25.0
        self.frame_count = 1
        self._photo = None
        self._after_id = None
        self.canvas = tk.Canvas(self, bg="#02070D", highlightthickness=1,
                                highlightbackground=colors["border"], height=360)
        self.canvas.pack(fill="both", expand=True)
        controls = tk.Frame(self, bg=colors["card"])
        controls.pack(fill="x", pady=(8, 0))
        self.play_button = tk.Button(
            controls, text="▶", command=self.toggle, bg=colors["active"], fg=colors["text"],
            activebackground=colors["blue"], activeforeground="white", relief="flat", width=5,
        )
        self.play_button.pack(side="left")
        self.position = tk.DoubleVar(value=0)
        self.slider = ttk.Scale(controls, from_=0, to=1, variable=self.position, command=self._seek)
        self.slider.pack(side="left", fill="x", expand=True, padx=10)
        self.time_label = tk.Label(controls, text="00:00 / 00:00", bg=colors["card"],
                                   fg=colors["muted"], font=("Segoe UI", 9))
        self.time_label.pack(side="right")

    def load(self, path: str):
        import cv2
        self.stop()
        if self.capture is not None:
            self.capture.release()
        self.path = path
        self.capture = cv2.VideoCapture(path)
        if not self.capture.isOpened():
            self.capture = None
            raise ValueError(f"Не удалось открыть видео: {Path(path).name}")
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS) or 25.0)
        self.frame_count = max(1, int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.slider.configure(to=max(0, self.frame_count - 1))
        self.position.set(0)
        self._read_frame(0)

    def _read_frame(self, frame_number: int | None = None):
        if self.capture is None:
            return False
        import cv2
        from PIL import Image, ImageTk
        if frame_number is not None:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(self.frame_count - 1, frame_number)))
        ok, frame = self.capture.read()
        if not ok:
            return False
        frame_number = int(self.capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        width = max(320, self.canvas.winfo_width())
        height = max(180, self.canvas.winfo_height())
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(width // 2, height // 2, image=self._photo, anchor="center")
        self.position.set(frame_number)
        elapsed, total = frame_number / self.fps, self.frame_count / self.fps
        self.time_label.config(text=f"{self._format_time(elapsed)} / {self._format_time(total)}")
        return True

    @staticmethod
    def _format_time(seconds: float) -> str:
        value = max(0, int(seconds))
        return f"{value // 60:02d}:{value % 60:02d}"

    def _seek(self, value):
        if self.capture is not None and not self.playing:
            self._read_frame(int(float(value)))

    def toggle(self):
        if self.capture is None:
            return
        self.playing = not self.playing
        self.play_button.config(text="Ⅱ" if self.playing else "▶")
        if self.playing:
            self._tick()
        elif self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

    def _tick(self):
        if not self.playing or self.capture is None:
            return
        if not self._read_frame():
            self.capture.set(1, 0)
            self._read_frame(0)
            self.playing = False
            self.play_button.config(text="▶")
            return
        self._after_id = self.after(max(15, int(1000 / self.fps)), self._tick)

    def stop(self):
        self.playing = False
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self._after_id = None
        if hasattr(self, "play_button") and self.play_button.winfo_exists():
            self.play_button.config(text="▶")

    def close(self):
        self.stop()
        if self.capture is not None:
            self.capture.release()
            self.capture = None
