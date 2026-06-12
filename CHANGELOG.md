# LighthouseOCR — Changelog

## Version convention

The app version is defined in a **single place**:

```python
# main_app_qt.py, line ~58
APP_VERSION = "v7.4"
```

This constant is automatically displayed in the bottom-left footer of the main window:

```python
lbl_version = QLabel(f"Phiên bản: {APP_VERSION}")
```

To bump the version, change `APP_VERSION` in `main_app_qt.py`.  
`Deploy_Build.ps1` now reads this value automatically, so build metadata stays in sync.

---

## [v7.4] — 2026-06-04

### Added / Fixed

- **Version bump** (`main_app_qt.py`, `claude.md`): Updated runtime metadata to `v7.4`.
- **Model discovery price labels** (`data_manager.py`, `main_app_qt.py`, `admin_dialogs.py`): Dynamic Gemini model discovery now shows known input/output token prices beside model names while saving only the clean model id to config.
- **Retired model guard** (`data_manager.py`, `Deploy_Build.ps1`): Release defaults and loaded config now replace retired/unsafe preview defaults such as `gemini-2.5-flash-preview-04-17`.
- **Dist logo packaging fix** (`LighthouseOCR.spec`): `app_logo.png` is now bundled so the main UI logo appears in packaged builds.
- **Post-process image preview fix** (`post_process_dialog.py`): Review dialog resolves images from the Excel folder or sibling `DONE` folder, auto-selects the first row with an image, and falls back to Pillow image loading when Qt `QPixmap` cannot decode client JPEG files.
- **PP-StructureV3 worker reuse** (`ocr_structure_runner.py`, `module_paddle_structure_ocr.py`): The default structure pipeline now keeps one isolated PP-StructureV3 worker process alive for a folder run, so the heavy Paddle model is not reloaded for every invoice image. Set `OCR_STRUCTURE_DISABLE_WORKER=1` only for diagnostics to force the older one-shot subprocess mode.
- **Runtime cache control** (`ocr_structure_runner.py`, `module_paddle_structure_ocr.py`, `module_paddle_ocr.py`): OCR subprocesses now run with Python bytecode writing disabled, preventing repeated `__pycache__`/`.pyc` growth inside the portable runtime during normal app use.
- **Deploy build hardening** (`Deploy_Build.ps1`, `LighthouseOCR.spec`): PP-StructureV3 preflight now captures noisy Paddle stderr without treating it as a failed build, PyInstaller retries with fresh work folders, and builds can fall back when Windows blocks EXE resource updates. Env copy now excludes `__pycache__`/`.pyc` files and no longer deletes the old runtime env before refresh, reducing file count and avoiding locked-cache failures. If an existing `dist/LighthouseOCR/LighthouseOCR.exe` is locked, the build writes to a timestamped `dist/LighthouseOCR_locked_*` folder instead of failing. In the resource fallback case the app UI logo remains bundled, but the Windows EXE icon/manifest resource embedding may be skipped.
- **Hard-case Vision fallback** (`ocr_pipeline_structure.py`): When PP-StructureV3/local KIE is very weak or the light fallback still returns no items/total, the default pipeline escalates to the Pro Vision model instead of sending an empty invoice to review.
- **Empty-review guard** (`ocr_pipeline_structure.py`): If all fallback layers still produce no line items, the invoice is treated as not processed so the app does not open a blank post-process review.
- **Structure validation hardening** (`invoice_validation.py`, `business_kie.py`): Local PP-StructureV3 results now require item pricing before being accepted, and total parsing ignores phone/portal/document numbers.
- **OCR item matching hardening** (`core_excel_mapper.py`, `item_matcher.py`): Common OCR typo `dura` is normalized to `dua`, long item names can match by meaningful partial tokens, and short generic names no longer get unsafe token-set matches.
- **Local supplier evidence rescue** (`local_evidence_rescue.py`, `ocr_pipeline_structure.py`, `supplier_enrichment.py`): Supplier values that look like salesperson/NVBH/HRC lines are treated as suspicious. The structure pipeline now checks local structure text and focused header crops for supplier/header evidence before accepting NCC. If no strong local evidence exists, NCC is left empty instead of escalating to Pro Vision only because of a suspicious staff line.
- **Mixed invoice routing fix** (`core_excel_mapper.py`): Unmapped items stay in PNMH when the same invoice already has mapped inventory items, preventing product rows from being moved to Chi phí just because one item is missing from the master list.

---

## [v7.3] — 2026-05-30

### Added / Fixed

- **Version bump** (`main_app_qt.py`, `claude.md`): Updated runtime metadata to `v7.3`.
- **Single source-of-truth enforcement** (`Deploy_Build.ps1`): Deployment banner now reads `APP_VERSION` from `main_app_qt.py` instead of hardcoded script version text.
- **Client dependency self-heal** (`Deploy_Build.ps1`): Build output now includes `Setup_Moi_Truong.bat` and a generated launcher `LighthouseOCR_Start.bat` that preflights `env\\python.exe` and can trigger setup when runtime dependencies are missing.
- **PaddleOCR stack update** (`README.md`, `Setup_Moi_Truong.bat`, `Setup_Nguon.bat`, runtime env): Updated target stack to `paddleocr[doc-parser]==3.6.0`, `paddlex[ocr]==3.6.1`, and Windows CPU-safe `paddlepaddle==3.2.0`.

---

## [v7.2] — 2026-05-21

### Added / Fixed

- **Version bump** (`main_app_qt.py`, `Deploy_Build.ps1`, `claude.md`): Updated runtime/build metadata to `v7.2`.
- **Build hierarchy alignment** (`Deploy_Build.ps1`): Deployment script now uses `LighthouseOCR.spec` and copies OCR runtime to `dist/LighthouseOCR/env` (compatible with app runtime path resolution).
- **Legacy compatibility in deploy** (`Deploy_Build.ps1`): If `env/` is missing, script falls back to `python_env/` as source during copy.
- **Build stability improvement** (`Deploy_Build.ps1`): PyInstaller now uses a timestamped `--workpath` per run to reduce collisions with stale/locked build artifacts.
- **OpenCV packaging fix** (`LighthouseOCR.spec`): `cv2` is now bundled with the main app because image preprocessing runs before the PaddleOCR subprocess.
- **Prompt asset packaging fix** (`LighthouseOCR.spec`, `module_*_ocr.py`, `module_calculator.py`): Runtime skill prompt Markdown files are now bundled and resolved through `path_utils` for PyInstaller builds.

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

### Added / Enhanced

- **Dialog opens maximized** (`post_process_dialog.py`): Review dialog now launches fullscreen for maximum working space. Window state (maximized or windowed + position) is saved across sessions using `QSettings`.
- **Image panel 35% width** (`post_process_dialog.py`): Splitter defaults to 65% table / 35% image panel. Both PNMH and Chi phí splitter positions are persisted separately in settings.
- **Scroll-to-zoom on invoice image** (`post_process_dialog.py`): Mouse wheel over the image panel zooms in/out (15% per tick, range 0.2×–8×). Zoom resets when navigating to a new row.
- **Click-drag to pan** (`post_process_dialog.py`): Left-click and drag scrolls the image in any direction. Cursor changes to ClosedHand while panning.
- **Chi phí tab image panel** (`post_process_dialog.py`): The Nhập Chi phí tab now has the same invoice image panel (same zoom/pan/scroll mechanics) as PNMH. Source filename is stored in Chi phí Excel col 16, populated by both OCR-routed rows and rows transferred from PNMH.
- **Processed image saved to DONE folder** (`main_app_qt.py`): After OCR, the enhanced (denoised + CLAHE + sharpened) PIL image is now saved to `DONE/` instead of moving the raw original. The review dialog therefore shows the processed version.
- **Source filename in Chi phí Excel col 16** (`core_excel_mapper.py`): OCR-routed Chi phí rows now record the source image filename in column P, consistent with PNMH col AB.

---

## [v6.1] — 2026-05-11

### Added

- **Invoice image preview panel** (`post_process_dialog.py`): PNMH review dialog now displays a scrollable image of the source invoice alongside the data table. The panel appears in a resizable splitter (table/panel, ~65%/35%). Selecting any row auto-loads the corresponding image from the `DONE` folder.
- **Source filename persisted to Excel col 28** (`core_excel_mapper.py`): Each scanned row now records the originating image filename in column AB. Existing Excel files without col 28 open without error (backward compatible).

---

## [v6.0.1] — 2026-05-11

### Fixed

- **PaddleOCR subprocess hang** (`module_paddle_ocr.py`): Added a 120-second timeout (`OCR_SUBPROCESS_TIMEOUT`) to the subprocess polling loop. If the process does not complete within the limit, it is terminated (SIGTERM then SIGKILL fallback) and a clear error message is raised to the UI log. Previously the subprocess could run indefinitely (observed >1h 27min).

---

## [v6.0]

- Stable release: Gemini + PaddleOCR hybrid pipeline, PyQt5 UI.
