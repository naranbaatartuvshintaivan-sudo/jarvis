"""
clap_wake — 👏👏 хоёр удаа алга ташихад JARVIS сэрнэ.

Хоёр удаа алга ташихад:
  • Jarvis-ийн цонх дэлгэцийн урд гарч ирнэ (minimize хийсэн ч)
  • Mic mute-тэй бол нээнэ
  • Wake word горимд унтаж байвал сэрнэ

Байршуулах:  Documents\\Mark-L\\plugins\\clap_wake.py
Jarvis-д:    "turn off clap wake" / "clap sensitivity high" / "clap wake status"

Яаж ажилладаг вэ:
  • Өөрийн жижиг mic stream (Jarvis-ийн mic-тэй зэрэгцээ, Windows shared mode).
  • 10 ms block бүрийн оргил (peak) + энерги → алга ташилт = маш огцом өсөлт,
    ~60 ms дотор унтардаг богино импульс. Яриа, хөгжим удаан үргэлжилдэг тул
    "decay" шалгалтаар хасагдана.
  • Хоёр импульс 0.12–0.8 сек зайтай → wake. Гурав дахь нь 0.8 сек дотор ирвэл
    (хөгжмийн бөмбөр, хаалга тогших) цуцлагдана.
  • Jarvis-ийн core кодыг өөрчлөхгүй — `git pull` хийхэд зөрчил гарахгүй.
"""
from __future__ import annotations

import gc
import threading
import time

PLUGIN = {
    "name": "clap_wake",
    "description": (
        "Control clap-to-wake: two claps bring the JARVIS window to the front, "
        "unmute the mic and wake it if asleep. "
        "action 'on' / 'off' / 'status', or 'sensitivity' with level low|medium|high. "
        "Use for 'turn off clap wake', 'clap sensitivity high', 'is clap wake on'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "on | off | status | sensitivity"},
            "level": {"type": "STRING", "description": "low | medium | high (for sensitivity)"},
        },
        "required": ["action"],
    },
}

RATE = 16000
BLOCK = 160                      # 10 ms
SENSITIVITY = {                  # (абсолют оргил босго, шуугианаас хэд дахин)
    "low":    (0.45, 14.0),
    "medium": (0.30, 9.0),
    "high":   (0.18, 6.0),
}


class ClapDetector:
    """Цэвэр numpy логик — mic-гүйгээр тестлэх боломжтой.

    feed(block) → True бол "хоёр удаа алга ташлаа" гэсэн үг.
    block: float32 [-1, 1] mono, 10 ms.
    """

    MIN_GAP, MAX_GAP = 0.12, 0.80   # хоёр ташилтын хоорондох зай (сек)
    DECAY_WINDOW = 0.07             # импульс энэ хугацаанд унтрах ёстой
    DECAY_RATIO = 0.30              # оргилын 30%-иас доош буух ёстой
    COOLDOWN = 2.0

    def __init__(self, level: str = "medium"):
        self.set_level(level)
        self.noise = 0.01            # шуугианы түвшин (RMS, адаптив)
        self.t = 0.0                 # дотоод цаг (сек) — block тоолж явна
        self.prev_rms = 0.0
        self.candidate: tuple[float, float] | None = None   # (эхэлсэн цаг, оргил rms)
        self.claps: list[float] = []
        self.last_fire = -99.0
        self.pending_fire: float | None = None

    def set_level(self, level: str) -> None:
        self.level = level if level in SENSITIVITY else "medium"
        self.abs_peak, self.rel = SENSITIVITY[self.level]

    def feed(self, block) -> bool:
        import numpy as np
        b = np.asarray(block, dtype=np.float32)
        peak = float(np.max(np.abs(b))) if b.size else 0.0
        rms = float(np.sqrt(np.mean(b * b))) if b.size else 0.0
        self.t += len(b) / RATE
        fired = False

        # 1) Нэр дэвшигч импульс унтарсан эсэх (decay шалгалт)
        if self.candidate is not None:
            start, cpeak = self.candidate
            if rms < cpeak * self.DECAY_RATIO:
                self.candidate = None
                self._on_clap(start)
            elif self.t - start > self.DECAY_WINDOW:
                self.candidate = None    # удаан үргэлжилсэн → яриа/хөгжим

        # 2) Шинэ огцом өсөлт
        elif (peak >= self.abs_peak and rms > self.noise * self.rel
              and rms > self.prev_rms * 3.0):
            self.candidate = (self.t, rms)

        # 3) Гурав дахь ташилт ирээгүй бол wake
        if self.pending_fire is not None and self.t - self.pending_fire > self.MAX_GAP:
            self.pending_fire = None
            if self.t - self.last_fire > self.COOLDOWN:
                self.last_fire = self.t
                fired = True

        # 4) Шуугианы түвшинг зөвхөн чимээгүй үед шинэчилнэ
        if self.candidate is None and rms < self.noise * 3.0:
            self.noise = max(0.002, self.noise * 0.995 + rms * 0.005)

        self.prev_rms = rms
        return fired

    def _on_clap(self, at: float) -> None:
        self.claps = [c for c in self.claps if at - c <= self.MAX_GAP * 2] + [at]
        if self.pending_fire is not None:
            # Гурав дахь ташилт → хоёр ташилт биш, цуцална
            self.pending_fire = None
            self.claps = []
            return
        if len(self.claps) >= 2:
            gap = self.claps[-1] - self.claps[-2]
            if self.MIN_GAP <= gap <= self.MAX_GAP:
                self.pending_fire = at
                self.claps = []


# ══════════════════════════════════════════════════════════════════════════════
#  Jarvis-тэй холбох хэсэг
# ══════════════════════════════════════════════════════════════════════════════

_state = {"enabled": True, "level": "medium", "jarvis": None, "error": "",
          "started": False, "bridge": None}
_detector = ClapDetector()
_lock = threading.Lock()


def _find_jarvis():
    """Ажиллаж байгаа JarvisLive объектыг олно (core-д hook байхгүй тул)."""
    for obj in gc.get_objects():
        try:
            if type(obj).__name__ == "JarvisLive" and hasattr(obj, "wake"):
                return obj
        except Exception:
            continue
    return None


def _log(msg: str) -> None:
    print(f"[Clap] {msg}")


def _bring_to_front(win) -> None:
    """Jarvis-ийн цонхыг дэлгэцийн урд гаргана (Qt main thread дээр дуудагдана)."""
    try:
        if win.isMinimized() or not win.isVisible():
            win.showNormal()
        win.raise_()
        win.activateWindow()
    except Exception:
        pass
    # Windows өөр програм идэвхтэй үед цонхыг урд гаргахыг хориглодог —
    # foreground thread-тэй түр холбогдож зөвшөөрөл авна.
    try:
        import ctypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = int(win.winId())
        fg = u32.GetForegroundWindow()
        fg_tid = u32.GetWindowThreadProcessId(fg, None)
        me = k32.GetCurrentThreadId()
        u32.AttachThreadInput(me, fg_tid, True)
        u32.ShowWindow(hwnd, 9)              # SW_RESTORE
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
        u32.AttachThreadInput(me, fg_tid, False)
    except Exception:
        pass


def _on_double_clap() -> None:
    """Qt main thread дээр ажиллана: цонх урд гаргах + mic нээх + сэрээх."""
    j = _state["jarvis"]
    if j is None:
        return
    ui = getattr(j, "ui", None)
    done = []
    win = getattr(ui, "_win", None)
    if win is not None:
        _bring_to_front(win)
        done.append("window up")
    try:
        if ui is not None and ui.muted:
            ui.muted = False
            done.append("mic on")
    except Exception:
        pass
    if getattr(j, "_wake_enabled", False) and not getattr(j, "_awake", True):
        try:
            j.wake(reason="double clap")
            done.append("awake")
        except Exception as e:
            _log(f"wake failed: {e}")
    _log("👏👏 → " + (", ".join(done) or "nothing to do"))
    try:
        ui.write_log("SYS: 👏👏 Clap — " + (", ".join(done) or "ready") + ".")
    except Exception:
        pass


def _make_bridge():
    """Mic thread-ээс Qt main thread руу дохио дамжуулах QObject."""
    from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal, pyqtSlot

    class _Bridge(QObject):
        clapped = pyqtSignal()

        def __init__(self):
            super().__init__()
            self.clapped.connect(self._handle)

        @pyqtSlot()          # жинхэнэ slot → main thread дээр дуудагдана
        def _handle(self):
            _on_double_clap()

    app = QCoreApplication.instance()
    if app is None:
        return None
    b = _Bridge()
    b.moveToThread(app.thread())
    # Холболтыг main thread-д шилжүүлсний дараа дахин хийнэ (Queued)
    from PyQt6.QtCore import Qt
    b.clapped.disconnect()
    b.clapped.connect(b._handle, Qt.ConnectionType.QueuedConnection)
    return b


def _worker() -> None:
    import numpy as np
    import sounddevice as sd

    # Jarvis бүрэн ачаалагдахыг хүлээнэ
    for _ in range(120):
        jarvis = _find_jarvis()
        if jarvis is not None and getattr(jarvis, "ui", None) is not None:
            _state["jarvis"] = jarvis
            break
        time.sleep(1.0)
    else:
        _state["error"] = "JarvisLive олдсонгүй"
        _log(_state["error"])
        return

    _state["bridge"] = _make_bridge()
    if _state["bridge"] is None:
        _state["error"] = "Qt app олдсонгүй"
        _log(_state["error"])
        return

    device = None
    try:
        from core import audio_devices
        from memory.config_manager import get_input_device
        name = get_input_device()
        device = audio_devices.resolve(name, "input") if name else None
    except Exception:
        device = None

    def callback(indata, frames, time_info, status):
        if not _state["enabled"]:
            return
        j = _state["jarvis"]
        # Jarvis өөрөө ярьж байх үед алгасна (өөрийнх нь дуу)
        if getattr(j, "_is_speaking", False):
            return
        block = indata[:, 0].astype(np.float32) / 32768.0
        with _lock:
            fired = _detector.feed(block)
        if fired:
            _state["bridge"].clapped.emit()

    while True:
        try:
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                                blocksize=BLOCK, device=device, callback=callback):
                _log(f"listening for 👏👏 (sensitivity {_state['level']})")
                _state["error"] = ""
                while True:
                    time.sleep(1.0)
        except Exception as e:
            _state["error"] = str(e)
            _log(f"mic error — {e}; 5 сек дараа дахин оролдоно")
            time.sleep(5.0)


def _start_once() -> None:
    if _state["started"]:
        return
    _state["started"] = True
    threading.Thread(target=_worker, daemon=True, name="ClapWakeThread").start()


# Plugin ачаалагдмагц арын thread эхэлнэ
_start_once()


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "status").strip().lower()

    if action == "on":
        _state["enabled"] = True
        return "Clap wake is on, sir. Two claps bring me up."
    if action == "off":
        _state["enabled"] = False
        return "Clap wake is off, sir."
    if action == "sensitivity":
        level = str(parameters.get("level") or "medium").strip().lower()
        if level not in SENSITIVITY:
            return "Sensitivity must be low, medium or high, sir."
        with _lock:
            _detector.set_level(level)
        _state["level"] = level
        return f"Clap sensitivity set to {level}, sir."

    parts = [f"Clap wake is {'on' if _state['enabled'] else 'off'}",
             f"sensitivity {_state['level']}"]
    if _state["error"]:
        parts.append(f"error: {_state['error']}")
    return ", ".join(parts) + ", sir."
