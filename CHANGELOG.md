# LighthouseOCR — Changelog

## Version convention

The app version is defined in a **single place**:

```python
# main_app_qt.py, line ~58
APP_VERSION = "v6.2"
```

This constant is automatically displayed in the bottom-left footer of the main window:

```python
lbl_version = QLabel(f"Phiên bản: {APP_VERSION}")
```

To bump the version, change `APP_VERSION` in `main_app_qt.py`. No other file needs to be updated for the UI to reflect it.

---

## [v7.1] — 2026-05-12

### Added / Fixed

- **Rotate buttons on image preview panel** (`post_process_dialog.py`): Rotate Left (↺) and Rotate Right (↻) buttons added to the top bar of the invoice image panel in both PNMH and Chi phí tabs.
- **Date logic fix** (`core_excel_mapper.py`, `post_process_dialog.py`): NGÀY GHI SỔ (PNMH col A, Chi phí col B) now uses the OCR invoice date. Empty if invoice has no date. `date.today()` logic removed entirely.
- **Image pipeline hardening** (`image_processor.py`): Geometric guards on contour detection (aspect ratio ≤3:1, warp area ≥25%), early resize before denoise (75% CPU gain), conditional denoise (Laplacian variance skip), denoise strength h=10→h=6.
- **PaddleOCR orientation** (`ocr_runner.py`): `use_doc_orientation_classify=True` — replaces Tesseract OSD, zero extra dependency.
- **Subprocess env fix** (`module_paddle_ocr.py`): Strip `PYTHONHOME`/`PYTHONPATH` before PaddleOCR subprocess to fix `python310.dll not found` error in PyInstaller builds.
- **Full error logging** (`ocr_pipeline.py`): Subprocess stderr now fully logged to UI instead of being truncated to first line.
- **Build system** (`Deploy_Build.ps1`, `.spec`): Added `-Full` flag for full build (includes Data structure). Default is Update build (code + python_env only).

---


### Added / Enhanced

- **Dialog opens maximized** (`post_process_dialog.py`): Review dialog now launches fullscreen for maximum working space. Window state (maximized or windowed + position) is saved across sessions using `QSettings`.
- **Image panel 35% width** (`post_process_dialog.py`): Splitter defaults to 65% table / 35% image panel. Both PNMH and Chi Phí splitter positions are persisted separately in settings.
- **Scroll-to-zoom on invoice image** (`post_process_dialog.py`): Mouse wheel over the image panel zooms in/out (15% per tick, range 0.2×–8×). Zoom resets when navigating to a new row.
- **Click-drag to pan** (`post_process_dialog.py`): Left-click and drag scrolls the image in any direction. Cursor changes to ClosedHand while panning.
- **Chi Phí tab image panel** (`post_process_dialog.py`): The Nhập Chi Phí tab now has the same invoice image panel (same zoom/pan/scroll mechanics) as PNMH. Source filename is stored in Chi Phí Excel col 16, populated by both OCR-routed rows and rows transferred from PNMH.
- **Processed image saved to DONE folder** (`main_app_qt.py`): After OCR, the enhanced (denoised + CLAHE + sharpened) PIL image is now saved to `DONE/` instead of moving the raw original. The review dialog therefore shows the processed version.
- **Source filename in Chi Phí Excel col 16** (`core_excel_mapper.py`): OCR-routed Chi Phí rows now record the source image filename in column P, consistent with PNMH col AB.

---

## [v6.1] — 2026-05-11

### Added

- **Invoice image preview panel** (`post_process_dialog.py`): PNMH review dialog now
  displays a scrollable image of the source invoice alongside the data table. The panel
  appears in a resizable splitter (table/panel, ~65%/35%). Selecting any row
  auto-loads the corresponding image from the `DONE` folder.
- **Source filename persisted to Excel col 28** (`core_excel_mapper.py`): Each scanned
  row now records the originating image filename in column AB. Existing Excel files
  without col 28 open without error (backward compatible).

---

## [v6.0.1] — 2026-05-11

### Fixed

- **PaddleOCR subprocess hang** (`module_paddle_ocr.py`): Added a 120-second timeout (`OCR_SUBPROCESS_TIMEOUT`) to the subprocess polling loop. If the process does not complete within the limit, it is terminated (SIGTERM then SIGKILL fallback) and a clear error message is raised to the UI log. Previously the subprocess could run indefinitely (observed >1h 27min).

---

## [v6.0]

- Stable release: Gemini + PaddleOCR hybrid pipeline, PyQt5 UI.
