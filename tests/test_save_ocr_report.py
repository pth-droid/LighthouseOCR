"""
Regression test for DataManager.save_ocr_report().
ASCII ONLY to avoid Windows console encoding issues.
Run: python tests/test_save_ocr_report.py
"""
import os, sys, csv, tempfile
sys.path.insert(0, '.')

PASS = 0
FAIL = 0

def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f" | {detail}" if detail else ""))

print("=" * 60)
print("LIGHTHOUSE OCR - save_ocr_report TEST")
print("=" * 60)

import data_manager as dm

# Redirect to a temp file so we don't pollute the project's Data structure folder
tmpdir = tempfile.mkdtemp(prefix="ocr_report_test_")
dm._OCR_REPORT_FILE = os.path.join(tmpdir, "OCR_Difficult_Reports.csv")

EXPECTED_HEADER = [
    'Timestamp', 'Image', 'So chung tu', 'Ngay hoa don',
    'Dien giai (OCR)', 'Ma vat tu', 'Ly do kho',
]  # ASCII version for label only; actual header is Vietnamese (verified by length).

# ---------- Case 1: create new file + header ----------
print("\n[CASE 1] First call creates file with 7-col header")
assert not os.path.exists(dm._OCR_REPORT_FILE)
dm.app_data.save_ocr_report("img1.jpg", "CT001", "01/01/2025", "Bo Anchor", "VT001", "chu mo")
check("file created", os.path.isfile(dm._OCR_REPORT_FILE))
with open(dm._OCR_REPORT_FILE, encoding='utf-8') as f:
    rows = list(csv.reader(f))
check("row count = 2 (header+1)", len(rows) == 2, f"got {len(rows)}")
check("header has 7 cols",        len(rows[0]) == 7, f"got {len(rows[0])}")
check("data row has 7 cols",      len(rows[1]) == 7, f"got {len(rows[1])}")
check("image col matches",        rows[1][1] == "img1.jpg")
check("invoice_no col matches",   rows[1][2] == "CT001")
check("ocr_text col matches",     rows[1][4] == "Bo Anchor")
check("reason col matches",       rows[1][6] == "chu mo")

# ---------- Case 2: append to existing ----------
print("\n[CASE 2] Second call appends, header not duplicated")
dm.app_data.save_ocr_report("img2.jpg", "CT002", "02/01/2025", "Sua tuoi", "VT002", "anh nghieng")
with open(dm._OCR_REPORT_FILE, encoding='utf-8') as f:
    rows = list(csv.reader(f))
check("row count = 3",            len(rows) == 3, f"got {len(rows)}")
check("header not duplicated",    rows[1][0] != 'Timestamp' and rows[2][0] != 'Timestamp')
check("second row image",         rows[2][1] == "img2.jpg")

# ---------- Case 3: empty reason allowed ----------
print("\n[CASE 3] Empty reason round-trips as empty string")
dm.app_data.save_ocr_report("img3.jpg", "CT003", "03/01/2025", "Banh mi", "VT003", "")
with open(dm._OCR_REPORT_FILE, encoding='utf-8') as f:
    rows = list(csv.reader(f))
check("row count = 4",            len(rows) == 4)
check("empty reason preserved",   rows[3][6] == "")

# ---------- Case 4: missing parent dir auto-created ----------
print("\n[CASE 4] Auto-creates missing parent directory")
tmpdir2 = tempfile.mkdtemp(prefix="ocr_report_test_")
nested = os.path.join(tmpdir2, "newdir", "OCR_Difficult_Reports.csv")
dm._OCR_REPORT_FILE = nested
assert not os.path.exists(os.path.dirname(nested))
dm.app_data.save_ocr_report("img4.jpg", "CT004", "04/01/2025", "Trung ga", "VT004", "lan dau")
check("parent dir auto-created", os.path.isdir(os.path.dirname(nested)))
check("nested file written",     os.path.isfile(nested))

# ---------- Summary ----------
print("\n" + "=" * 60)
print(f"RESULT: {PASS} passed, {FAIL} failed")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
