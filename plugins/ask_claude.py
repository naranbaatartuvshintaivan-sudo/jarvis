"""
ask_claude — Jarvis -> Claude Code bridge.

Jarvis-д дуугаар хэлсэн coding/research ажлыг Claude Code CLI (`claude -p`)
руу дамжуулж, үр дүнг нь Jarvis-аар уншуулна.

Байршуулах: Documents\\Mark-L\\plugins\\ask_claude.py
Шаардлага:  Claude Code CLI суусан, нэвтэрсэн байх (`claude` командыг терминалд шалга).
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

PLUGIN = {
    "name": "ask_claude",
    "description": (
        "Hand a coding, debugging, refactoring or code-explanation task to Claude Code "
        "(Anthropic's coding agent) running on this PC. Use when the user says things like "
        "'ask Claude', 'tell Claude to', 'Claude-аар хийлгэ', 'Claude-д хэл', or wants code "
        "written or fixed inside a project folder. Do NOT use for normal chat, web search "
        "or opening apps."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task": {
                "type": "STRING",
                "description": "The full instruction for Claude, in the user's own words.",
            },
            "project": {
                "type": "STRING",
                "description": (
                    "Optional project folder name or full path. A bare name is looked up "
                    "under Documents and Desktop. Empty = Documents."
                ),
            },
        },
        "required": ["task"],
    },
    "behavior": "NON_BLOCKING",   # Claude ажиллаж байхад Jarvis ярьсаар байна
    "scheduling": "WHEN_IDLE",    # дуусмагц чимээгүй үед хариугаа хэлнэ
}

TIMEOUT_S = 15 * 60
SPOKEN_LIMIT = 700


def _find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    # Native installer-ийн default байршил
    for p in (
        Path.home() / ".local" / "bin" / "claude.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
    ):
        if p.exists():
            return str(p)
    return None


def _resolve_project(project: str) -> Path:
    docs = Path.home() / "Documents"
    if not project:
        return docs
    p = Path(project).expanduser()
    if p.is_absolute() and p.is_dir():
        return p
    for base in (docs, Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        cand = base / project
        if cand.is_dir():
            return cand
    return docs


def run(parameters: dict, player=None, session_memory=None) -> str:
    task = str(parameters.get("task") or "").strip()
    if not task:
        return "Sir, Claude-д юу хийлгэхээ хэлээгүй байна."

    exe = _find_claude()
    if not exe:
        return ("Sir, Claude Code энэ компьютер дээр олдсонгүй. "
                "Эхлээд Claude Code суулгаад 'claude' командаар нэвтэрнэ үү.")

    cwd = _resolve_project(str(parameters.get("project") or "").strip())

    def log(msg: str):
        if player:
            try:
                player.write_log(msg)
            except Exception:
                pass

    log(f"JARVIS → Claude [{cwd.name}]: {task}")

    try:
        proc = subprocess.run(
            [exe, "-p", task,
             "--output-format", "text",
             # Файл засахыг зөвшөөрнө, shell команд ажиллуулахыг зөвшөөрөхгүй
             "--permission-mode", "acceptEdits"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return "Sir, Claude 15 минутад амжсангүй. Ажлыг жижиглээд дахин хэлнэ үү."
    except Exception as e:
        return f"Sir, Claude-г дуудаж чадсангүй: {e}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    # Бүтэн хариуг reports/ руу хадгална (дуугаар зөвхөн товчийг уншина)
    try:
        reports = Path(__file__).resolve().parent.parent / "reports"
        reports.mkdir(exist_ok=True)
        f = reports / f"claude_{time.strftime('%Y%m%d_%H%M%S')}.md"
        f.write_text(f"# Task\n{task}\n\n# Folder\n{cwd}\n\n# Claude\n{out}\n\n{err}",
                     encoding="utf-8")
        log(f"JARVIS: Claude-ийн бүтэн хариу → {f}")
    except Exception:
        pass

    if proc.returncode != 0 and not out:
        return f"Sir, Claude алдаа өглөө: {err[:300] or 'тодорхойгүй'}"

    spoken = out if len(out) <= SPOKEN_LIMIT else out[:SPOKEN_LIMIT] + "… (бүтэн хариу reports хавтсанд)"
    return f"Claude хэлж байна: {spoken}"
