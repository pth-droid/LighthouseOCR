import cv2
import numpy as np
from PIL import Image, ImageOps

MAX_LONG_SIDE = 2000

def apply_exif_rotation(image: Image.Image) -> Image.Image:
    """Correct camera orientation using EXIF data (all 8 orientations, including mirrored)."""
    try:
        return ImageOps.exif_transpose(image)
    except Exception:
        return image



def order_points(pts):
    """Sorts points into: top-left, top-right, bottom-right, bottom-left"""
    rect = np.zeros((4, 2), dtype="float32")
    
    # the top-left point will have the smallest sum, whereas
    # the bottom-right point will have the largest sum
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    
    # now, compute the difference between the points, the
    # top-right point will have the smallest difference,
    # whereas the bottom-left will have the largest difference
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    
    return rect

def perspective_transform(image, pts):
    """Warps the image to a top-down view based on the 4 provided points"""
    rect = order_points(pts)
    (tl, tr, br, bl) = rect
    
    # Compute widths
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))
    
    # Compute heights
    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))
    
    # Destination points for top-down view
    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")
    
    # Perspective transform matrix
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    return warped

def get_document_contour(image_cv):
    """Detects the document contour using OpenCV edge detection"""
    # Resize for faster and more reliable edge detection while keeping aspect ratio
    ratio = image_cv.shape[0] / 500.0
    image = cv2.resize(image_cv, (int(image_cv.shape[1] / ratio), 500))
    
    # Convert to grayscale, blur, edge detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Using adaptive Canny based on median pixel intensity
    v = np.median(gray)
    lower = int(max(0, (1.0 - 0.33) * v))
    upper = int(min(255, (1.0 + 0.33) * v))
    edged = cv2.Canny(gray, lower, upper)
    
    # Morphological transformations to close gaps in edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)
    
    # Find contours
    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    
    document_contour = None
    for c in contours:
        # Approximate the contour
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        
        # Must be a quadrilateral with reasonable area
        if len(approx) != 4 or cv2.contourArea(approx) <= 10000:
            continue
        # Guard: reject contours with extreme aspect ratio (> 3:1)
        rect = cv2.minAreaRect(approx)
        (w_rect, h_rect) = rect[1]
        if w_rect > 0 and h_rect > 0:
            ar = max(w_rect, h_rect) / min(w_rect, h_rect)
            if ar > 3.0:
                continue
        document_contour = approx
        break
            
    if document_contour is not None:
        # Scale the contour back to the original image size
        return document_contour.reshape(4, 2) * ratio
    return None

def deskew_image(cv_img: np.ndarray) -> np.ndarray:
    """Detect dominant text-line angle and rotate to correct skew up to ±15°."""
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # Dilate horizontally to merge characters into text-line blobs
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 3))
    dilated = cv2.dilate(thresh, kernel)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles = []
    for c in contours:
        if cv2.contourArea(c) < 500:
            continue
        rect = cv2.minAreaRect(c)
        angle = rect[-1]
        if angle < -45:
            angle += 90
        angles.append(angle)
    if not angles:
        return cv_img
    skew = float(np.median(angles))
    if abs(skew) < 0.5 or abs(skew) > 15:
        return cv_img
    print(f"  [Pre-process] Deskew: correcting {skew:.2f}°...")
    (h, w) = cv_img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), skew, 1.0)
    return cv2.warpAffine(cv_img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def resize_if_needed(img: Image.Image) -> Image.Image:
    w, h = img.size
    long_side = max(w, h)
    if long_side <= MAX_LONG_SIDE:
        return img
    scale = MAX_LONG_SIDE / long_side
    resample_method = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
    return img.resize((int(w * scale), int(h * scale)), resample_method)

def resize_cv_if_needed(cv_img: np.ndarray) -> np.ndarray:
    """Resize OpenCV BGR image so long side <= MAX_LONG_SIDE. Uses INTER_AREA for downscale."""
    h, w = cv_img.shape[:2]
    long_side = max(w, h)
    if long_side <= MAX_LONG_SIDE:
        return cv_img
    scale = MAX_LONG_SIDE / long_side
    new_w, new_h = int(w * scale), int(h * scale)
    print(f"  [Pre-process] Resize: {w}×{h} → {new_w}×{new_h} (trước denoise)")
    return cv2.resize(cv_img, (new_w, new_h), interpolation=cv2.INTER_AREA)

def prepare_image(image_path: str) -> Image.Image:
    try:
        # Step 1: Open and orient image via PIL (EXIF — handles all 8 orientations)
        with Image.open(image_path) as img:
            img = apply_exif_rotation(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.load()
            pil_img = img.copy()

        # Step 1b: 90°/180°/270° orientation is handled by PaddleOCR's
        # use_doc_orientation_classify (enabled in ocr_runner.py).

        # Step 2: Convert to OpenCV format (BGR numpy array)
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
        # Step 3: Document Edge Detection & Perspective Transform
        doc_contour = get_document_contour(cv_img)
        
        if doc_contour is not None:
            warped = perspective_transform(cv_img, doc_contour)
            # Quality check: warped result must retain at least 25% of original area
            orig_area = cv_img.shape[0] * cv_img.shape[1]
            warp_area = warped.shape[0] * warped.shape[1]
            if warp_area < orig_area * 0.25:
                print(f"  [Pre-process] Warp quá nhỏ ({warp_area/orig_area:.0%} diện tích gốc), bỏ qua perspective transform.")
                processed_cv = cv_img
            else:
                print("  [Pre-process] Document contour found, applying perspective transform...")
                processed_cv = warped
        else:
            print("  [Pre-process] No document contour detected, using original image...")
            processed_cv = cv_img

        # Step 3b: Deskew — correct residual text-line tilt (up to ±15°)
        processed_cv = deskew_image(processed_cv)

        # Step 4a: Resize early — denoise/enhance at ≤2000px for performance
        processed_cv = resize_cv_if_needed(processed_cv)

        # Step 4b: Denoising — skip if image is already sharp (clean scan)
        gray_check = cv2.cvtColor(processed_cv, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray_check, cv2.CV_64F).var()
        if laplacian_var > 500:
            print(f"  [Pre-process] Denoising: Bỏ qua — ảnh đã sắc nét (laplacian={laplacian_var:.0f}).")
        else:
            print(f"  [Pre-process] Denoising (h=6, laplacian={laplacian_var:.0f})...")
            processed_cv = cv2.fastNlMeansDenoisingColored(
                processed_cv, None, h=6, hColor=6, templateWindowSize=7, searchWindowSize=21
            )

        # Step 5: CLAHE contrast enhancement — applied only to L channel in LAB space
        print("  [Pre-process] CLAHE contrast enhancement...")
        lab = cv2.cvtColor(processed_cv, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge((l, a, b))
        processed_cv = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # Step 6: Sharpening via unsharp mask — restores text edges softened by CLAHE
        print("  [Pre-process] Sharpening (unsharp mask)...")
        blurred = cv2.GaussianBlur(processed_cv, (0, 0), sigmaX=1.0)
        processed_cv = cv2.addWeighted(processed_cv, 1.5, blurred, -0.5, 0)

        # Convert enhanced BGR array back to PIL Image
        final_rgb = cv2.cvtColor(processed_cv, cv2.COLOR_BGR2RGB)
        final_img = Image.fromarray(final_rgb)

        # Step 7: Final PIL resize (safety — already resized at Step 4a in CV space)
        return resize_if_needed(final_img)
        
    except Exception as e:
        raise RuntimeError(f"Lỗi tiền xử lý hình ảnh. File có thể bị hỏng: {e}") from e
