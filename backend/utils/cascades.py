"""Resolve Haar-cascade XML paths.

OpenCV wheels (5.0+) no longer ship the cascade XMLs under ``cv2.data``, which
silently zeroes every face detection. We vendor the XMLs under
``backend/assets/haarcascades`` and fall back to them when the packaged copy
is missing.
"""
import os

_VENDORED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "haarcascades",
)


def cascade_path(name):
    try:
        import cv2
        packaged = os.path.join(cv2.data.haarcascades, name)
        if os.path.isfile(packaged):
            return packaged
    except Exception:  # noqa: BLE001
        pass
    return os.path.join(_VENDORED_DIR, name)
