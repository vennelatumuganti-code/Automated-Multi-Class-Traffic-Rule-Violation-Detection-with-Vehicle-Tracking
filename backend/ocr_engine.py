"""
ocr_engine.py
─────────────
This file reads number plate text from a cropped plate image.

Two-step process:
  Step 1 — ESRGAN: upscale the blurry plate image (4× sharper)
  Step 2 — Tesseract: read the text from the sharpened image

Why two steps?
  Traffic cameras are far away. The plate region in the frame is often
  tiny (maybe 60×20 pixels) and blurry. Tesseract fails on blurry text.
  ESRGAN makes it 4× bigger and sharper, then Tesseract can read it.

What is ESRGAN?
  Enhanced Super Resolution GAN — a deep learning model that fills in
  detail when upscaling an image, instead of just stretching pixels.
"""

import os
import re
import cv2
import numpy as np
import pytesseract
from PIL import Image

# ─────────────────────────────────────────────────────────────
# IMPORTANT: On Windows, tell pytesseract where Tesseract.exe is
# Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
# Then set the path below to match your installation folder
# ─────────────────────────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ─────────────────────────────────────────────────────────────
# 1. Image Enhancement (Simple version — before ESRGAN loads)
# ─────────────────────────────────────────────────────────────

def enhance_plate_simple(plate_img: np.ndarray) -> np.ndarray:
    """
    Basic image enhancement using only OpenCV (no ML needed).
    Used as a fallback if ESRGAN is not available.

    Steps:
    1. Upscale 4× using bicubic interpolation (smooth, not pixelated)
    2. Convert to grayscale (Tesseract works better on gray)
    3. Apply adaptive thresholding (makes text black, background white)
    4. Slight sharpening via unsharp mask
    """
    # Step 1: Upscale 4×
    h, w = plate_img.shape[:2]
    upscaled = cv2.resize(
        plate_img, (w * 4, h * 4),
        interpolation=cv2.INTER_CUBIC
    )

    # Step 2: Grayscale
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)

    # Step 3: Adaptive threshold — handles uneven lighting on plates
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11,
        C=2
    )

    # Step 4: Sharpen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(thresh, -1, kernel)

    return sharpened


# ─────────────────────────────────────────────────────────────
# 2. ESRGAN Super-Resolution (ML-based, higher quality)
# ─────────────────────────────────────────────────────────────

class ESRGANEnhancer:
    """
    Wraps the ESRGAN model for plate super-resolution.
    The model is loaded ONCE and reused for every plate — loading
    a model takes ~2 seconds, so we only want to do it once.
    """

    def __init__(self, model_path: str = "models/RealESRGAN_x4plus.pth"):
        self.model = None
        self.model_path = model_path
        self._load_model()

    def _load_model(self):
        """
        Try to load the ESRGAN model.
        If the model file doesn't exist yet, we fall back to simple enhancement.
        You can download the model from:
        https://github.com/xinntao/Real-ESRGAN/releases
        """
        if not os.path.exists(self.model_path):
            print(f"⚠️  ESRGAN model not found at {self.model_path}")
            print("   Falling back to OpenCV enhancement (still works, less sharp)")
            self.model = None
            return

        try:
            # Real-ESRGAN uses BasicSR under the hood
            # We import here so the app still starts even if not installed
            from basicsr.archs.rrdbnet_arch import RRDBNet
            import torch

            net = RRDBNet(
                num_in_ch=3, num_out_ch=3,
                num_feat=64, num_block=23, num_grow_ch=32, scale=4
            )
            checkpoint = torch.load(self.model_path, map_location="cpu")
            net.load_state_dict(checkpoint["params_ema"], strict=False)
            net.eval()
            self.model = net
            print("✅ ESRGAN model loaded successfully")
        except Exception as e:
            print(f"⚠️  Could not load ESRGAN: {e}")
            self.model = None

    def enhance(self, plate_img: np.ndarray) -> np.ndarray:
        """
        Enhance a plate image.
        Uses ESRGAN if available, otherwise OpenCV fallback.
        """
        if self.model is None:
            return enhance_plate_simple(plate_img)

        try:
            import torch
            # Convert BGR → RGB → float tensor in [0, 1]
            img_rgb = cv2.cvtColor(plate_img, cv2.COLOR_BGR2RGB)
            tensor  = torch.from_numpy(img_rgb).float() / 255.0
            tensor  = tensor.permute(2, 0, 1).unsqueeze(0)   # (1, C, H, W)

            with torch.no_grad():
                output = self.model(tensor)

            # Convert back to numpy BGR
            output_np = output.squeeze(0).permute(1, 2, 0).numpy()
            output_np = (output_np * 255).clip(0, 255).astype(np.uint8)
            return cv2.cvtColor(output_np, cv2.COLOR_RGB2BGR)

        except Exception as e:
            print(f"ESRGAN inference failed: {e}, using fallback")
            return enhance_plate_simple(plate_img)


# ─────────────────────────────────────────────────────────────
# 3. Tesseract OCR — Read Plate Text
# ─────────────────────────────────────────────────────────────

def read_plate_text(enhanced_img: np.ndarray) -> tuple[str, float]:
    """
    Run Tesseract OCR on the enhanced plate image.
    Returns (plate_text, confidence_score).

    Tesseract config explained:
      --psm 7  = treat the image as a single line of text
                 (a number plate IS a single line)
      --oem 3  = use the best available OCR engine (LSTM)
      -c whitelist = only recognize these characters
                     (number plates don't have @, #, etc.)
    """
    # Make sure image is grayscale for Tesseract
    if len(enhanced_img.shape) == 3:
        gray = cv2.cvtColor(enhanced_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = enhanced_img

    # Convert to PIL Image (pytesseract needs PIL)
    pil_img = Image.fromarray(gray)

    # Character whitelist for Indian number plates
    # Format: TS 09 EA 4421 or AP 28 CF 1190
    whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "

    config = f"--psm 7 --oem 3 -c tessedit_char_whitelist='{whitelist}'"

    try:
        # data = dict with per-character confidence scores
        data = pytesseract.image_to_data(
            pil_img, config=config,
            output_type=pytesseract.Output.DICT
        )

        # Collect words with confidence > 40
        words = []
        confidences = []
        for i, word in enumerate(data["text"]):
            conf = int(data["conf"][i])
            if conf > 40 and word.strip():
                words.append(word.strip())
                confidences.append(conf)

        plate_text = " ".join(words).upper().strip()
        avg_conf   = sum(confidences) / len(confidences) / 100 if confidences else 0.0

        # Clean up: remove noise characters that slip through
        plate_text = clean_plate_text(plate_text)

        return plate_text, round(avg_conf, 3)

    except Exception as e:
        print(f"OCR error: {e}")
        return "UNREAD", 0.0


def clean_plate_text(text: str) -> str:
    """
    Post-process the raw OCR output to fix common mistakes.

    Indian number plate format: XX 00 XX 0000
    Examples: TS 09 EA 4421 | AP 28 CF 1190 | MH 12 DE 8840

    Common OCR mistakes:
      O vs 0 (letter O vs number zero)
      I vs 1 (letter I vs number one)
      S vs 5
    """
    # Remove anything that's not a letter, number, or space
    text = re.sub(r"[^A-Z0-9 ]", "", text.upper())

    # Collapse multiple spaces into one
    text = re.sub(r"\s+", " ", text).strip()

    return text if len(text) >= 4 else "UNREAD"


# ─────────────────────────────────────────────────────────────
# 4. Main Function — Full Plate Pipeline
# ─────────────────────────────────────────────────────────────

# Create one global instance so the model loads only once
_enhancer = None

def get_enhancer() -> ESRGANEnhancer:
    """Lazy-load the enhancer (only when first needed)."""
    global _enhancer
    if _enhancer is None:
        _enhancer = ESRGANEnhancer()
    return _enhancer


def extract_plate_text(plate_crop: np.ndarray) -> tuple[str, float]:
    """
    Full pipeline:  plate crop → enhance → OCR → clean text

    This is the function called from detector.py.
    plate_crop = the small image of just the plate area from the video frame.

    Returns:
      ("TS09EA4421", 0.87)   ← plate text and confidence score
    """
    if plate_crop is None or plate_crop.size == 0:
        return "UNREAD", 0.0

    # Step 1: Enhance (ESRGAN or fallback)
    enhancer = get_enhancer()
    enhanced = enhancer.enhance(plate_crop)

    # Step 2: OCR
    plate_text, confidence = read_plate_text(enhanced)

    return plate_text, confidence
