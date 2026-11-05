"""Correct this fixed inverted MIPI mount before inference and rendering."""

ORIENTATION_DEGREES = 180
IMAGE_SPACE_ID = 'mipi-1080p-upright180-v1'


def upright_frame(image):
    import cv2
    return cv2.rotate(image, cv2.ROTATE_180)
