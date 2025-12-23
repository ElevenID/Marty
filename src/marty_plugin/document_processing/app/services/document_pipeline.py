"""
Lightweight document layout pipeline for self-hosted processing.

This module provides placeholders for:
- Detecting and rectifying the document (deskew)
- Estimating regions (MRZ, portrait, text blocks)
- Watermark/surface checks (stubbed)

It is designed to be replaced with OpenCV/Tesseract backed implementations
while keeping the call sites stable.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Optional OpenCV/numpy
try:  # pragma: no cover - optional dependency path
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency path
    cv2 = None
    np = None


@dataclass
class DocumentRegions:
    """Detected regions on a document page."""

    mrz: Optional[Image.Image]
    portrait: Optional[Image.Image]
    text_block: Optional[Image.Image]
    layout_size: Tuple[int, int]


class DocumentPipeline:
    """Hexagonal adapter-friendly document pipeline (placeholder implementation)."""

    def decode_image(self, base64_data: str) -> Image.Image:
        """Decode base64 image data into a PIL image."""
        if "," in base64_data and base64_data.startswith("data:"):
            base64_data = base64_data.split(",", 1)[1]
        image_data = base64.b64decode(base64_data)
        return Image.open(BytesIO(image_data))

    def deskew(self, image: Image.Image) -> Image.Image:
        """
        Deskew using OpenCV if available: find largest quadrilateral and warp to top-down.
        Falls back to the original image if OpenCV is unavailable or no quad found.
        """
        if cv2 is None or np is None:
            logger.debug("OpenCV not available; returning original image")
            return image

        try:
            img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 75, 200)
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

            doc_quad = None
            for c in contours:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) == 4:
                    doc_quad = approx
                    break

            if doc_quad is None:
                logger.debug("No quadrilateral found; returning original image")
                return image

            pts = doc_quad.reshape(4, 2)
            rect = self._order_points(pts)
            (tl, tr, br, bl) = rect

            width_a = np.linalg.norm(br - bl)
            width_b = np.linalg.norm(tr - tl)
            max_width = int(max(width_a, width_b))

            height_a = np.linalg.norm(tr - br)
            height_b = np.linalg.norm(tl - bl)
            max_height = int(max(height_a, height_b))

            dst = np.array(
                [
                    [0, 0],
                    [max_width - 1, 0],
                    [max_width - 1, max_height - 1],
                    [0, max_height - 1],
                ],
                dtype="float32",
            )

            m = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img_cv, m, (max_width, max_height))
            warped_pil = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
            return warped_pil
        except Exception:
            logger.exception("Deskew failed; returning original image")
        return image

    def estimate_regions(self, image: Image.Image) -> DocumentRegions:
        """
        Heuristic region estimation on the rectified image:
        - MRZ: bottom 25% of the image
        - Portrait: right 35% of middle band
        - Text block: top 50%
        """
        width, height = image.size
        mrz_top = int(height * 0.75)
        portrait_left = int(width * 0.6)
        portrait_top = int(height * 0.25)
        portrait_bottom = int(height * 0.75)
        text_bottom = int(height * 0.5)

        mrz = image.crop((0, mrz_top, width, height)) if height > 0 else None
        portrait = (
            image.crop((portrait_left, portrait_top, width, portrait_bottom))
            if width > 0 and height > 0
            else None
        )
        text_block = image.crop((0, 0, width, text_bottom)) if height > 0 else None

        return DocumentRegions(
            mrz=mrz,
            portrait=portrait,
            text_block=text_block,
            layout_size=(width, height),
        )

    def check_watermark(self, image: Image.Image) -> bool:
        """
        Simple texture check using variance of Laplacian and FFT energy as a proxy.
        Returns True if the image has sufficient high-frequency content to suggest
        print texture (very weak heuristic).
        """
        if cv2 is None or np is None:
            logger.debug("OpenCV not available; watermark check skipped")
            return False

        try:
            img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            laplacian_var = cv2.Laplacian(img_cv, cv2.CV_64F).var()

            # FFT magnitude energy in mid-high frequencies
            f = np.fft.fft2(img_cv)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-9)
            h, w = magnitude_spectrum.shape
            # Exclude low frequencies by cropping center
            crop = magnitude_spectrum[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
            high_freq_energy = np.mean(crop)

            logger.debug(
                "Watermark texture metrics: laplacian_var=%.2f, high_freq_energy=%.2f",
                laplacian_var,
                high_freq_energy,
            )

            return laplacian_var > 50 and high_freq_energy > 5
        except Exception:
            logger.exception("Watermark check failed; returning False")
            return False

    @staticmethod
    def image_to_base64(image: Image.Image) -> str:
        """Encode PIL image to base64 string (PNG)."""
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    @staticmethod
    def _order_points(pts):
        """Order points for perspective transform (tl, tr, br, bl)."""
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect
