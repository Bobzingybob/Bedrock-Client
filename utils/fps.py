"""PresentMon FPS overlay for Minecraft Bedrock."""
import collections
import ctypes
import subprocess
import threading
import time
from pathlib import Path


PROCESS_NAME = "Minecraft.Windows.exe"
SCRIPT_DIR = Path(__file__).resolve().parent.parent


class FrameMonitor:
    """Runs PresentMon as a child process and keeps a rolling frametime window."""

    def __init__(self, exe):
        self.frames = collections.deque(maxlen=60)
        self.ok = True
        self.error = ""
        self.raw = []
        self.proc = subprocess.Popen(
            [str(exe), "--process_name", PROCESS_NAME, "--output_stdout",
             "--v1_metrics", "--stop_existing_session", "--terminate_on_proc_exit"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        col = None
        for line in self.proc.stdout:
            line = line.lstrip("\ufeff").strip()
            if len(self.raw) < 8:
                self.raw.append(line)
            parts = [p.strip().strip('"') for p in line.split(",")]
            if col is None:
                low = [p.lower() for p in parts]
                for name in ("msbetweenpresents", "frametime"):
                    if name in low:
                        col = low.index(name)
                        break
                continue
            try:
                ms = float(parts[col])
                if ms > 0:
                    self.frames.append(ms)
            except (ValueError, IndexError):
                pass
        self.ok = False

    def dump_debug(self):
        """Write what PresentMon actually printed for debugging."""
        try:
            err = self.proc.stderr.read().strip() if self.proc.poll() is not None else "(still running)"
        except Exception:
            err = "(unreadable)"
        log = SCRIPT_DIR / "pm_debug.log"
        log.write_text(
            "PresentMon first output lines:\n" + "\n".join(self.raw or ["(nothing received)"])
            + f"\n\nstderr: {err}\nadmin: {bool(ctypes.windll.shell32.IsUserAnAdmin())}\n",
            encoding="utf-8")
        try:
            self.error = self.proc.stderr.read().strip()
        except Exception:
            pass

    def stats(self):
        """Return (avg_fps, avg_ms, 1%_low_fps) or None if not enough data."""
        if len(self.frames) < 5:
            return None
        data = list(self.frames)
        avg = sum(data) / len(data)
        worst = sorted(data)[-max(1, len(data) // 100 or 1):]
        return 1000.0 / avg, avg, 1000.0 / (sum(worst) / len(worst))

    def stop(self):
        """Terminate the PresentMon process."""
        if self.proc.poll() is None:
            self.proc.terminate()


def run_overlay(game, monitor):
    """Transparent, click-through, always-on-top FPS overlay in the top-left corner."""
    import tkinter as tk
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    key = "#010101"
    root.configure(bg=key)
    root.attributes("-transparentcolor", key)
    label = tk.Label(root, text="FPS --", fg="#39ff14", bg=key,
                     font=("Consolas", 16, "bold"), justify="left")
    label.pack(padx=6, pady=4)
    root.geometry("+10+10")
    root.update_idletasks()
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80)
    except Exception:
        pass

    start = time.time()
    dumped = [False]

    def tick():
        if not game.is_running():
            root.destroy()
            return
        s = monitor.stats() if monitor else None
        if s:
            label.config(text=f"{s[0]:.0f} FPS\n{s[1]:.1f} ms | 1% low {s[2]:.0f}")
        elif monitor and not monitor.ok:
            label.config(text="FPS counter off")
            if not dumped[0]:
                monitor.dump_debug()
                dumped[0] = True
        elif monitor and time.time() - start > 10:
            label.config(text="no frame data\nsee pm_debug.log")
            if not dumped[0]:
                monitor.dump_debug()
                dumped[0] = True
        root.after(250, tick)

    tick()
    root.mainloop()
