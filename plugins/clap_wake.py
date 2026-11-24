"""
clap_wake — 👏👏 хоёр удаа алга ташихад JARVIS сэрнэ.

Wake word (Hey Jarvis) горимтой зэрэгцэж ажиллана: Jarvis унтаж байхад
хоёр удаа алга ташвал сэрнэ. Сэрүүн үед юу ч хийхгүй.

Байршуулах:  Documents\\Mark-L\\plugins\\clap_wake.py
Шаардлага:   🎛 CONTROLS → WAKE WORD: ON  (унтах/сэрэх горим идэвхтэй байх)
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
        "Control clap-to-wake: two claps wake JARVIS while it is asleep. "
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

_state = {"enabled": True, "level": "medium", "jarvis": None, "error": "", "started": False}
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


def _worker() -> None:
    import numpy as np
    import sounddevice as sd

    # Jarvis бүрэн ачаалагдахыг хүлээнэ
    for _ in range(120):
        jarvis = _find_jarvis()
        if jarvis is not None:
            _state["jarvis"] = jarvis
            break
        time.sleep(1.0)
    else:
        _state["error"] = "JarvisLive олдсонгүй"
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
        # Зөвхөн унтаж байхад сонсоно — сэрүүн үед CPU зарцуулахгүй
        if not (getattr(j, "_wake_enabled", False) and not getattr(j, "_awake", True)):
            return
        block = indata[:, 0].astype(np.float32) / 32768.0
        with _lock:
            fired = _detector.feed(block)
        if fired:
            _log("👏👏 detected — waking JARVIS")
            try:
                j.wake(reason="double clap")
            except Exception as e:
                _log(f"wake failed: {e}")

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
        return "Clap wake is on, sir. Two claps will wake me when I'm asleep."
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

    j = _state["jarvis"]
    wake_mode = bool(j and getattr(j, "_wake_enabled", False))
    parts = [f"Clap wake is {'on' if _state['enabled'] else 'off'}",
             f"sensitivity {_state['level']}"]
    if not wake_mode:
        parts.append("but wake word mode is off, so I never sleep — turn WAKE WORD on in Controls")
    if _state["error"]:
        parts.append(f"microphone error: {_state['error']}")
    return ", ".join(parts) + ", sir."
