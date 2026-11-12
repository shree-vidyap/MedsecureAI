import cv2
import numpy as np


def load(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def variants(img):
    """Yields several versions of the photo. Small QR/barcodes inside a big pack photo are easier to find
    in a zoomed crop, so we also scan overlapping tiles."""
    h, w = img.shape[:2]
    scale = 1600 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    yield img
    yield gray
    yield cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    if max(h, w) < 1400:
        yield cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    th, tw = h // 2, w // 2                                   # 3x3 overlapping tiles
    for y in range(0, h - th + 1, max(1, th // 2)):
        for x in range(0, w - tw + 1, max(1, tw // 2)):
            tile = gray[y:y + th, x:x + tw]
            yield cv2.resize(tile, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
