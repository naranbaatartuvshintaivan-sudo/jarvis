# jarvis

[FatihMakes/Mark-L](https://github.com/FatihMakes/Mark-L) (JARVIS) voice assistant-д зориулсан нэмэлт plugin-ууд болон Windows installer.

> Mark-L өөрөө энэ repo-д ороогүй — FatihMakes-ийн код (CC BY-NC 4.0). Эндээс зөвхөн өөрсдийн бичсэн plugin-ууд.

## Юу байгаа вэ

| Файл | Юу хийдэг |
|---|---|
| `install_jarvis.bat` | Git + Python 3.12 (winget), Mark-L clone, `.venv`, dependencies, Desktop launcher — нэг товшилтоор |
| `plugins/ask_claude.py` | Jarvis → **Claude Code** bridge. *"Hey Jarvis, ask Claude to …"* гэхэд `claude -p`-ээр төсөл дотор ажил хийлгэж, хариуг уншина |
| `plugins/holo_desk.py` | **Gesture holo desk** — webcam + MediaPipe hand tracking. Файлууд голограф карт болж, чимхээд PRINT / OPEN бүс рүү чирнэ |

## Суулгах

1. `install_jarvis.bat`-ийг ажиллуул → `Documents\Mark-L` суусан байна.
2. `plugins/*.py`-г `Documents\Mark-L\plugins\` руу хуул.
3. Jarvis-ийг restart → Plugin Manager-т `ask_claude`, `holo_desk` харагдана.

### ask_claude
- [Claude Code](https://docs.claude.com/en/docs/claude-code) суулгаж нэвтэрсэн байх (`claude` командаар шалга).
- `--permission-mode acceptEdits`: файл засна, shell команд ажиллуулахгүй.
- Бүтэн хариу `Mark-L\reports\claude_*.md`-д хадгалагдана.

### holo_desk
- Webcam хэрэгтэй. Анх нээхэд `mediapipe` (`--no-deps`, Jarvis-ийн `cv2`-д хүрэхгүй) болон ~8 MB hand model автоматаар суулгана.
- Gestures:
  - ☝ долоовор хуруу → курсор
  - 🤏 pinch → карт барих
  - PRINT бүс (0.6с барих) → хэвлэх; `.stl/.3mf/.gcode` бол slicer-т нээнэ
  - OPEN бүс → нээх
  - ✋ алгаа 1.5с → хаах (эсвэл `Esc`)
- Jarvis: *"open holo desk"*, *"open holo desk on Downloads"*
- Алдаа гарвал: `%USERPROFILE%\.jarvis_holo\pip.log`
