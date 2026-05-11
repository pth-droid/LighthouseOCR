import cv2
import numpy as np
from PIL import Image, ExifTags

MAX_LONG_SIDE = 2000

def apply_exif_rotation(image: Image.Image) -> Image.Image:
    try:
        exif = image._getexif()
        if exif is None:
            return image
        orient_key = next((k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None)
        if orient_key is None:
            return image
        orientation = exif.get(orient_key)
        rotation_map = {3: 180, 6: 270, 8: 90}
        degrees = rotation_map.get(orientation)
        if degrees:
            image = image.rotate(degrees, expand=True)
        return image
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
        
        # If the approximated contour has 4 points and covers a reasonably large area, assume it's a document
        if len(approx) == 4 and cv2.contourArea(approx) > 10000:
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

def prepare_image(image_path: str) -> Image.Image:
    try:
        # Step 1: Open and orient image via PIL
        with Image.open(image_path) as img:
            img = apply_exif_rotation(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.load()
            pil_img = img.copy()
            
        # Step 2: Convert to OpenCV format (BGR numpy array)
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
        # Step 3: Document Edge Detection & Perspective Transform
        doc_contour = get_document_contour(cv_img)
        
        if doc_contour is not None:
            print("  [Pre-process] Document contour found, applying perspective transform...")
            processed_cv = perspective_transform(cv_img, doc_contour)
        else:
            print("  [Pre-process] No document contour detected, using original image...")
            processed_cv = cv_img

        # Step 3b: Deskew — correct residual text-line tilt (up to ±15°)
        processed_cv = deskew_image(processed_cv)

        # Step 4: Denoising — remove phone photo noise/compression artifacts (BGR only)
        if len(processed_cv.shape) == 3 and processed_cv.shape[2] == 3:
            print("  [Pre-process] Denoising (fastNlMeansDenoisingColored)...")
            processed_cv = cv2.fastNlMeansDenoisingColored(
                processed_cv, None, h=10, hColor=10, templateWindowSize=7, searchWindowSize=21
            )
        else:
            print("  [Pre-process] Skipping denoising (grayscale image)...")

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

        # Step 7: Final resize to prevent memory/API overload
        return resize_if_needed(final_img)
        
    except Exception as e:
        raise RuntimeError(f"Lỗi tiền xử lý hình ảnh. File có thể bị hỏng: {e}") from e
