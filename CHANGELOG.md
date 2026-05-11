# LighthouseOCR — Changelog

## Version convention

The app version is defined in a **single place**:

```python
# main_app_qt.py, line ~58
APP_VERSION = "v6.0"
```

This constant is automatically displayed in the bottom-left footer of the main window:

```python
lbl_version = QLabel(f"Phiên bản: {APP_VERSION}")
```

To bump the version, change `APP_VERSION` in `main_app_qt.py`. No other file needs to be updated for the UI to reflect it.

---

## [v6.0]

- Stable release: Gemini + PaddleOCR hybrid pipeline, PyQt5 UI.

## [v6.1] — 2026-05-11

### Added

- **Invoice image preview panel** (`post_process_dialog.py`): PNMH review dialog now
  displays a scrollable image of the source invoice alongside the data table. The panel
  appears in a resizable splitter (table/panel, ~72%/28% by default). Selecting any
  row auto-loads the corresponding image from the `DONE` folder.
- **Source filename persisted to Excel col 28** (`core_excel_mapper.py`): Each scanned
  row now records the originating image filename in column AB. Existing Excel files
  without col 28 open without error (backward compatible).

---

## [v6.0.1] — 2026-05-11

### Fixed

- **PaddleOCR subprocess hang** (`module_paddle_ocr.py`): Added a 120-second timeout (`OCR_SUBPROCESS_TIMEOUT`) to the subprocess polling loop. If the process does not complete within the limit, it is terminated (SIGTERM then SIGKILL fallback) and a clear error message is raised to the UI log. Previously the subprocess could run indefinitely (observed >1h 27min).
