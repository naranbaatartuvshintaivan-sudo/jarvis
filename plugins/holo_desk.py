"""
holo_desk — gesture-controlled holographic file desk for JARVIS.

Webcam-аар гарыг чинь дагаж (MediaPipe), файлуудыг голограф карт болгож
харуулна. Хуруугаараа удирдана:

    ☝  Долоовор хуруу   → курсор
    🤏 Чимхэх (pinch)    → карт барих / чирэх
    📥 PRINT бүс         → хэвлэх (3D файл бол slicer-т нээнэ)
    📂 OPEN бүс          → нээх
    ✋ Алгаа 1.5 сек     → desk хаах   (эсвэл Esc)

Байршуулах:  Documents\\Mark-L\\plugins\\holo_desk.py
Jarvis-д:    "Hey Jarvis, open holo desk"  /  "open holo desk on Downloads"

Нэг файл хоёр үүрэгтэй: Jarvis import хийхэд plugin, `python holo_desk.py <folder>`
гэж ажиллуулахад desk өөрөө. Plugin талд Qt/mediapipe import хийхгүй, тиймээс
Jarvis-ийн startup-д нөлөөлөхгүй.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")
DATA_DIR = Path.home() / ".jarvis_holo"
MODEL_PATH = DATA_DIR / "hand_landmarker.task"

PLUGIN = {
    "name": "holo_desk",
    "description": (
        "Open the holographic gesture desk: files from a folder float on screen as "
        "holographic cards the user controls with hand gestures through the webcam "
        "(pinch to grab, drag to PRINT to print, drag to OPEN to open). Use for "
        "'open holo desk', 'holo desk', 'hologram desk', 'gesture desk', "
        "'print with my hands'. Use action 'close' to close it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'open' (default) or 'close'."},
            "folder": {
                "type": "STRING",
                "description": "Folder to show: Desktop (default), Downloads, Documents, "
                               "or a full path.",
            },
        },
        "required": [],
    },
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
}

_proc: subprocess.Popen | None = None


# ══════════════════════════════════════════════════════════════════════════════
#  PLUGIN SIDE (Jarvis process)
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_folder(name: str) -> Path:
    home = Path.home()
    name = (name or "").strip()
    if name:
        p = Path(name).expanduser()
        if p.is_absolute() and p.is_dir():
            return p
        for base in (home, home / "OneDrive", home / "Documents"):
            for cand in (base / name, base / name.capitalize()):
                if cand.is_dir():
                    return cand
    for d in (home / "Desktop", home / "OneDrive" / "Desktop"):
        if d.is_dir():
            return d
    return home


def _ensure_deps(log) -> str | None:
    """mediapipe + hand model байхгүй бол суулгана. Алдаа бол мессеж буцаана."""
    if importlib.util.find_spec("mediapipe") is None:
        log("JARVIS: Holo desk — mediapipe суулгаж байна (нэг удаа, ~1 мин)…")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # mediapipe-г --no-deps-ээр: түүний opencv-contrib-python нь Jarvis-ийн
        # ажиллаж байгаа (түгжигдсэн) cv2-г дарж бичих гээд Windows дээр унадаг.
        # cv2, numpy, sounddevice Jarvis-д аль хэдийн бий — үлдсэн жижгийг нь суулгана.
        steps = [["mediapipe", "--no-deps"],
                 ["absl-py", "flatbuffers", "certifi", "matplotlib"]]
        with open(DATA_DIR / "pip.log", "w", encoding="utf-8") as pl:
            for args in steps:
                r = subprocess.run([sys.executable, "-m", "pip", "install", *args],
                                   capture_output=True, text=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                pl.write(f"$ pip install {' '.join(args)}\n{r.stdout}\n{r.stderr}\n")
                if r.returncode != 0:
                    first_err = next((ln for ln in (r.stderr or "").splitlines()
                                      if ln.startswith("ERROR")), r.stderr[-200:])
                    return (f"mediapipe суулгаж чадсангүй ({first_err.strip()[:200]}). "
                            f"Бүтэн log: {DATA_DIR / 'pip.log'}")
        importlib.invalidate_caches()
    if not MODEL_PATH.exists() or MODEL_PATH.stat().st_size < 1_000_000:
        log("JARVIS: Holo desk — гар таних model татаж байна (~8 MB)…")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = MODEL_PATH.with_suffix(".part")
        try:
            urllib.request.urlretrieve(MODEL_URL, tmp)
            tmp.replace(MODEL_PATH)
        except Exception as e:
            return f"гар таних model татаж чадсангүй: {e}"
    return None


def run(parameters: dict, player=None, session_memory=None) -> str:
    global _proc

    def log(msg: str):
        if player:
            try:
                player.write_log(msg)
            except Exception:
                pass

    action = str(parameters.get("action") or "open").strip().lower()

    if action == "close":
        if _proc and _proc.poll() is None:
            _proc.terminate()
            _proc = None
            return "Holo desk closed, sir."
        return "Holo desk is not open, sir."

    if _proc and _proc.poll() is None:
        return "Holo desk is already open, sir."

    err = _ensure_deps(log)
    if err:
        return f"Sir, holo desk-ийг нээж чадсангүй — {err}"

    folder = _resolve_folder(str(parameters.get("folder") or ""))
    try:
        _proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), str(folder)],
            cwd=str(Path(__file__).resolve().parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        return f"Sir, holo desk failed to launch: {e}"

    log(f"JARVIS: Holo desk → {folder}")
    return (f"Holo desk online with {folder.name}, sir. Pinch to grab a file, "
            f"drag it to PRINT or OPEN, and hold your open palm to close.")


# ══════════════════════════════════════════════════════════════════════════════
#  DESK SIDE (own process: python holo_desk.py <folder>)
# ══════════════════════════════════════════════════════════════════════════════

MODEL_EXT = {".stl", ".3mf", ".obj", ".gcode", ".step", ".stp", ".bgcode"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
DOC_EXT = {".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".md"}
SKIP_EXT = {".lnk", ".url", ".ini", ".exe", ".bat", ".cmd", ".ps1", ".tmp"}
MAX_CARDS = 18


def classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in MODEL_EXT:
        return "3D"
    if ext in IMAGE_EXT:
        return "IMG"
    if ext == ".pdf":
        return "PDF"
    if ext in DOC_EXT:
        return "DOC"
    return "FILE"


def list_files(folder: Path) -> list[Path]:
    try:
        files = [p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() not in SKIP_EXT
                 and not p.name.startswith(("~", "."))]
    except Exception:
        return []
    # 3D файлууд эхэнд, дараа нь шинэ нь эхэнд
    files.sort(key=lambda p: (classify(p) != "3D", -p.stat().st_mtime))
    return files[:MAX_CARDS]


class GestureState:
    """Landmark → курсор, pinch, open palm. Qt-гүй тул тест хийхэд амар."""

    PINCH_ON = 0.32     # hysteresis: барих
    PINCH_OFF = 0.45    # суллах
    SMOOTH = 0.35       # EMA жин (их = хурдан, бага = тогтвортой)

    def __init__(self):
        self.x = self.y = 0.5
        self.pinching = False
        self.palm_since: float | None = None
        self.visible = False

    @staticmethod
    def _dist(a, b) -> float:
        return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

    def update(self, lm, now: float) -> None:
        if lm is None:
            self.visible = False
            self.palm_since = None
            return
        self.visible = True
        # Толин тусгал: камер гарыг эсрэгээр харуулдаг
        tx, ty = 1.0 - lm[8].x, lm[8].y
        # Камерын захаас курсор хүрэхэд хэцүү тул голын 80%-ийг бүтэн дэлгэцэд сунгана
        tx = min(max((tx - 0.1) / 0.8, 0.0), 1.0)
        ty = min(max((ty - 0.1) / 0.8, 0.0), 1.0)
        self.x += (tx - self.x) * self.SMOOTH
        self.y += (ty - self.y) * self.SMOOTH

        hand = self._dist(lm[0], lm[9]) or 1e-6           # бугуй → дунд хурууны үндэс
        ratio = self._dist(lm[4], lm[8]) / hand           # эрхий ↔ долоовор
        if self.pinching:
            self.pinching = ratio < self.PINCH_OFF
        else:
            self.pinching = ratio < self.PINCH_ON

        # Дөрвөн хуруу бүгд тэнийсэн (үзүүр нь бугуйгаас үеэсээ хол) = нээлттэй алга
        extended = all(self._dist(lm[0], lm[t]) > self._dist(lm[0], lm[t - 2]) * 1.15
                       for t in (8, 12, 16, 20))
        if extended and not self.pinching and ratio > 0.6:
            self.palm_since = self.palm_since or now
        else:
            self.palm_since = None

    def palm_held(self, now: float, secs: float = 1.5) -> float:
        """0..1 — алгаа хэр удаан барьсан."""
        if self.palm_since is None:
            return 0.0
        return min((now - self.palm_since) / secs, 1.0)


def do_print(path: Path) -> str:
    if classify(path) == "3D":
        # 3D файлыг slicer (Bambu Studio / Cura / PrusaSlicer) шууд хэвлэдэг
        os.startfile(str(path))  # type: ignore[attr-defined]
        return f"{path.name} → slicer-т нээлээ"
    try:
        os.startfile(str(path), "print")  # type: ignore[attr-defined]
        return f"{path.name} → принтер рүү илгээлээ"
    except OSError:
        os.startfile(str(path))  # type: ignore[attr-defined]
        return f"{path.name} шууд хэвлэгдэхгүй файл — нээлээ"


def do_open(path: Path) -> str:
    os.startfile(str(path))  # type: ignore[attr-defined]
    return f"{path.name} нээлээ"


def main(folder_arg: str) -> None:
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                             QPixmap, QRadialGradient)
    from PyQt6.QtWidgets import QApplication, QWidget

    CYAN = QColor(0, 229, 255)
    ORANGE = QColor(255, 140, 40)
    GREEN = QColor(80, 255, 160)

    folder = Path(folder_arg)

    # ── Камер + гар таних thread ──────────────────────────────────────────────
    class HandThread(QThread):
        frame = pyqtSignal(object, object)   # (landmarks | None, preview QImage)
        failed = pyqtSignal(str)

        def run(self):
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)
            if not cap.isOpened():
                self.failed.emit("Камер олдсонгүй — webcam залгаатай эсэхийг шалгана уу.")
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            opts = vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            t0 = time.monotonic()
            last_ts = -1
            with vision.HandLandmarker.create_from_options(opts) as landmarker:
                while not self.isInterruptionRequested():
                    ok, bgr = cap.read()
                    if not ok:
                        time.sleep(0.01)
                        continue
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    ts = int((time.monotonic() - t0) * 1000)
                    if ts <= last_ts:
                        ts = last_ts + 1
                    last_ts = ts
                    res = landmarker.detect_for_video(
                        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                    lm = res.hand_landmarks[0] if res.hand_landmarks else None

                    # Жижиг preview: толин, cyan өнгөтэй, гарын цэгүүдтэй
                    small = cv2.flip(cv2.resize(rgb, (240, 180)), 1)
                    small = (small * [0.35, 0.85, 1.0]).astype("uint8")
                    if lm is not None:
                        for p in lm:
                            cv2.circle(small, (int((1 - p.x) * 240), int(p.y * 180)),
                                       2, (255, 255, 255), -1)
                    img = QImage(small.data, 240, 180, 240 * 3,
                                 QImage.Format.Format_RGB888).copy()
                    self.frame.emit(lm, img)
            cap.release()

    # ── Голограф карт ──────────────────────────────────────────────────────────
    class Card:
        W, H = 190, 150

        def __init__(self, path: Path, home: QPointF):
            self.path = path
            self.kind = classify(path)
            self.home = QPointF(home)
            self.pos = QPointF(home)
            self.thumb: QPixmap | None = None
            if self.kind == "IMG":
                pm = QPixmap(str(path))
                if not pm.isNull():
                    self.thumb = pm.scaled(self.W - 20, self.H - 52,
                                           Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)

        def rect(self) -> QRectF:
            return QRectF(self.pos.x() - self.W / 2, self.pos.y() - self.H / 2, self.W, self.H)

    # ── Desk цонх ─────────────────────────────────────────────────────────────
    class Desk(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("JARVIS — HOLO DESK")
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                                | Qt.WindowType.WindowStaysOnTopHint
                                | Qt.WindowType.Tool)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.g = GestureState()
            self.cards: list[Card] = []
            self.held: Card | None = None
            self.hover: Card | None = None
            self.zone_since: tuple[str, float] | None = None
            self.preview: QImage | None = None
            self.toast = ("HOLO DESK ONLINE — чимхэж барина уу", time.monotonic())
            self.error = ""
            self.phase = 0.0

            self.showFullScreen()
            self._layout_cards()

            self.cam = HandThread()
            self.cam.frame.connect(self._on_frame)
            self.cam.failed.connect(self._on_fail)
            self.cam.start()

            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)
            self.timer.start(16)

        # Layout: картуудыг нуман (arc) хэлбэрээр байрлуулна — голограф ширээ шиг
        def _layout_cards(self):
            files = list_files(folder)
            W, H = self.width(), self.height()
            cols = 6
            rows = max(1, (len(files) + cols - 1) // cols)
            gx, gy = 215, 175
            top = H * 0.22
            for i, f in enumerate(files):
                r, c = divmod(i, cols)
                n = min(cols, len(files) - r * cols)
                x = W / 2 + (c - (n - 1) / 2) * gx
                y = top + r * gy + abs(c - (n - 1) / 2) * 14   # зөөлөн нуман
                self.cards.append(Card(f, QPointF(x, y)))
            if not files:
                self.error = f"{folder} хоосон байна"
            self._rows = rows

        def zones(self) -> dict[str, QRectF]:
            W, H = self.width(), self.height()
            return {
                "PRINT": QRectF(W * 0.08, H - 210, W * 0.30, 150),
                "OPEN": QRectF(W * 0.62, H - 210, W * 0.30, 150),
            }

        def cursor(self) -> QPointF:
            return QPointF(self.g.x * self.width(), self.g.y * self.height())

        def _on_fail(self, msg: str):
            self.error = msg

        def _on_frame(self, lm, img):
            self.preview = img
            was = self.g.pinching
            self.g.update(lm, time.monotonic())
            cur = self.cursor()

            if self.g.pinching and not was:                      # барьж эхэлсэн
                for card in reversed(self.cards):
                    if card.rect().contains(cur):
                        self.held = card
                        self.cards.remove(card)
                        self.cards.append(card)                   # дээр нь гаргана
                        break
            elif was and not self.g.pinching and self.held:      # суллав
                self._drop(self.held)
                self.held = None

            if self.held:
                self.held.pos = QPointF(cur)

            self.hover = None
            if not self.held:
                for card in reversed(self.cards):
                    if card.rect().contains(cur):
                        self.hover = card
                        break

        def _armed_zone(self) -> str | None:
            """Карттай 0.6 сек бүс дээр байвал 'armed' — санамсаргүй хэвлэхээс сэргийлнэ."""
            if not self.held:
                self.zone_since = None
                return None
            now = time.monotonic()
            for name, r in self.zones().items():
                if r.contains(self.held.pos):
                    if not self.zone_since or self.zone_since[0] != name:
                        self.zone_since = (name, now)
                    return name if now - self.zone_since[1] >= 0.6 else None
            self.zone_since = None
            return None

        def _drop(self, card: Card):
            zone = self._armed_zone()
            try:
                if zone == "PRINT":
                    self.toast = (do_print(card.path), time.monotonic())
                elif zone == "OPEN":
                    self.toast = (do_open(card.path), time.monotonic())
            except Exception as e:
                self.toast = (f"Алдаа: {e}", time.monotonic())
            card.pos = QPointF(card.home)
            self.zone_since = None

        def _tick(self):
            self.phase += 0.016
            # Карт гэр лүүгээ зөөлөн буцна
            for card in self.cards:
                if card is not self.held:
                    card.pos += (card.home - card.pos) * 0.18
            if self.g.palm_held(time.monotonic()) >= 1.0 and not self.held:
                self.close()
            self.update()

        def keyPressEvent(self, e):
            if e.key() == Qt.Key.Key_Escape:
                self.close()

        def closeEvent(self, e):
            self.cam.requestInterruption()
            self.cam.wait(1500)
            e.accept()

        # ── Зурах ─────────────────────────────────────────────────────────────
        def paintEvent(self, _):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            W, H = self.width(), self.height()
            now = time.monotonic()

            p.fillRect(self.rect(), QColor(2, 10, 20, 215))

            # Голограф тор (перспектив шал)
            p.setPen(QPen(QColor(0, 229, 255, 28), 1))
            hy = H * 0.55
            for i in range(-12, 13):
                p.drawLine(QPointF(W / 2 + i * 40, hy), QPointF(W / 2 + i * 260, H))
            for k in range(1, 9):
                y = hy + (H - hy) * (k / 8) ** 1.6
                p.drawLine(QPointF(0, y), QPointF(W, y))
            # Scan line
            sy = (self.phase * 140) % H
            p.fillRect(QRectF(0, sy, W, 2), QColor(0, 229, 255, 35))

            # Гарчиг
            p.setPen(CYAN)
            p.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
            p.drawText(QRectF(0, 28, W, 40), Qt.AlignmentFlag.AlignHCenter, "J.A.R.V.I.S  ·  HOLO DESK")
            p.setFont(QFont("Consolas", 11))
            p.setPen(QColor(0, 229, 255, 160))
            p.drawText(QRectF(0, 70, W, 24), Qt.AlignmentFlag.AlignHCenter,
                       f"{folder}   ·   🤏 барих   ·   ✋ 1.5с хаах   ·   Esc")

            # Бүсүүд
            armed = self._armed_zone()
            for name, r in self.zones().items():
                col = ORANGE if name == "PRINT" else GREEN
                inside = self.held is not None and r.contains(self.held.pos)
                alpha = 200 if armed == name else (120 if inside else 55)
                p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), alpha), 2,
                              Qt.PenStyle.SolidLine if inside else Qt.PenStyle.DashLine))
                p.setBrush(QColor(col.red(), col.green(), col.blue(), alpha // 5))
                p.drawRoundedRect(r, 18, 18)
                if inside and self.zone_since and not armed:
                    prog = min((now - self.zone_since[1]) / 0.6, 1.0)
                    p.fillRect(QRectF(r.left() + 20, r.bottom() - 18, (r.width() - 40) * prog, 4), col)
                p.setPen(col)
                p.setFont(QFont("Consolas", 26, QFont.Weight.Bold))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter,
                           ("⎙  " if name == "PRINT" else "⤢  ") + name)

            # Картууд
            for card in self.cards:
                self._draw_card(p, card, card is self.held, card is self.hover)

            # Курсор
            if self.g.visible:
                c = self.cursor()
                rad = 26
                grad = QRadialGradient(c, rad * 2)
                grad.setColorAt(0, QColor(0, 229, 255, 120 if self.g.pinching else 50))
                grad.setColorAt(1, QColor(0, 229, 255, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(grad)
                p.drawEllipse(c, rad * 2, rad * 2)
                p.setPen(QPen(CYAN, 3))
                p.setBrush(QColor(0, 229, 255, 160) if self.g.pinching else Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, rad * (0.55 if self.g.pinching else 1.0),
                              rad * (0.55 if self.g.pinching else 1.0))
                held = self.g.palm_held(now)
                if held > 0:
                    p.setPen(QPen(ORANGE, 4))
                    p.drawArc(QRectF(c.x() - 40, c.y() - 40, 80, 80), 90 * 16, int(-360 * 16 * held))

            # Камерын preview
            if self.preview is not None:
                pr = QRectF(W - 270, 110, 240, 180)
                p.drawImage(pr, self.preview)
                p.setPen(QPen(QColor(0, 229, 255, 150), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(pr)
                p.setFont(QFont("Consolas", 9))
                p.drawText(QRectF(pr.left(), pr.bottom() + 4, 240, 16),
                           Qt.AlignmentFlag.AlignLeft,
                           "HAND: LOCKED" if self.g.visible else "HAND: SEARCHING…")

            # Toast / алдаа
            msg, at = self.toast
            if now - at < 4:
                p.setPen(QColor(255, 255, 255, int(255 * min(1, 4 - (now - at)))))
                p.setFont(QFont("Consolas", 15, QFont.Weight.Bold))
                p.drawText(QRectF(0, H - 50, W, 30), Qt.AlignmentFlag.AlignHCenter, msg)
            if self.error:
                p.setPen(QColor(255, 90, 90))
                p.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
                p.drawText(QRectF(0, H * 0.45, W, 40), Qt.AlignmentFlag.AlignHCenter, self.error)
            p.end()

        def _draw_card(self, p: QPainter, card: Card, held: bool, hover: bool):
            r = card.rect()
            if held:
                r = r.adjusted(-12, -10, 12, 10)
            col = {"3D": ORANGE, "IMG": GREEN}.get(card.kind, CYAN)
            glow = 200 if held else (150 if hover else 90)

            path = QPainterPath()
            cut = 16   # sci-fi өнцгийн тайралт
            path.moveTo(r.left() + cut, r.top())
            path.lineTo(r.right(), r.top())
            path.lineTo(r.right(), r.bottom() - cut)
            path.lineTo(r.right() - cut, r.bottom())
            path.lineTo(r.left(), r.bottom())
            path.lineTo(r.left(), r.top() + cut)
            path.closeSubpath()

            p.setBrush(QColor(0, 40, 60, 170 if held else 120))
            p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), glow), 2 if held else 1.5))
            p.drawPath(path)

            p.setPen(col)
            p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            p.drawText(QRectF(r.left() + 12, r.top() + 6, 60, 18), Qt.AlignmentFlag.AlignLeft, card.kind)

            body = QRectF(r.left() + 10, r.top() + 26, r.width() - 20, r.height() - 58)
            if card.thumb is not None:
                p.setOpacity(0.85)
                p.drawPixmap(QPointF(body.center().x() - card.thumb.width() / 2,
                                     body.center().y() - card.thumb.height() / 2), card.thumb)
                p.setOpacity(1.0)
            else:
                # 3D бол эргэлддэг wireframe куб, бусад нь том үсэг
                if card.kind == "3D":
                    self._wire_cube(p, body.center(), 30, col)
                else:
                    p.setFont(QFont("Consolas", 30, QFont.Weight.Bold))
                    p.setPen(QColor(col.red(), col.green(), col.blue(), 140))
                    p.drawText(body, Qt.AlignmentFlag.AlignCenter, card.path.suffix.upper()[1:5] or "?")

            name = card.path.name
            if len(name) > 22:
                name = name[:19] + "…"
            p.setPen(QColor(220, 250, 255))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(QRectF(r.left() + 8, r.bottom() - 28, r.width() - 16, 22),
                       Qt.AlignmentFlag.AlignCenter, name)

        def _wire_cube(self, p: QPainter, c: QPointF, s: float, col: QColor):
            import math
            a = self.phase * 0.9
            pts = []
            for x in (-1, 1):
                for y in (-1, 1):
                    for z in (-1, 1):
                        X = x * math.cos(a) - z * math.sin(a)
                        Z = x * math.sin(a) + z * math.cos(a)
                        Y = y * math.cos(0.5) - Z * math.sin(0.5)
                        pts.append(QPointF(c.x() + X * s, c.y() + Y * s))
            p.setPen(QPen(col, 1.5))
            for i in range(8):
                for j in range(i + 1, 8):
                    if bin(i ^ j).count("1") == 1:
                        p.drawLine(pts[i], pts[j])

    app = QApplication(sys.argv)
    desk = Desk()
    desk.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(_resolve_folder("")))
