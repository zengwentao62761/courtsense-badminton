"""COCO-17 skeleton lines for the X5 official sample's raw keypoint logits."""

import math


COCO_EDGES = (
    (15, 13), (13, 11), (16, 14), (14, 12), (11, 12),
    (5, 11), (6, 12), (5, 6), (5, 7), (6, 8), (7, 9), (8, 10),
    (1, 2), (0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 6),
)


def skeleton_segments(keypoints, logits, width, height, kpt_conf_thresh=0.4):
    """Return in-frame segments whose two endpoint probabilities pass the threshold.

    The official ``YoloV11_Pose.post_process`` returns raw logits, shaped
    ``(17, 1)`` for each person. A probability threshold must be converted
    to logit space before comparing these values.
    """
    if not 0 < kpt_conf_thresh < 1:
        raise ValueError("Keypoint probability threshold must be between 0 and 1")
    if len(keypoints) != 17 or len(logits) != 17:
        raise ValueError("Expected COCO 17 keypoints and 17 confidence logits")
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    threshold = math.log(kpt_conf_thresh / (1 - kpt_conf_thresh))
    visible = []
    for point, score in zip(keypoints, logits):
        x, y = float(point[0]), float(point[1])
        confidence = float(score[0] if hasattr(score, "__len__") else score)
        valid = (math.isfinite(x) and math.isfinite(y) and math.isfinite(confidence)
                 and 0 <= x < width and 0 <= y < height and confidence >= threshold)
        visible.append((int(x), int(y)) if valid else None)
    return [(visible[a], visible[b]) for a, b in COCO_EDGES
            if visible[a] is not None and visible[b] is not None]


def draw_skeleton(image, keypoints, logits, kpt_conf_thresh=0.4, thickness=3):
    """Draw separate skeletons in place and return the actual line count."""
    import cv2

    if len(keypoints) != len(logits):
        raise ValueError("Keypoint and confidence person counts must match")
    height, width = image.shape[:2]
    count = 0
    for person_points, person_logits in zip(keypoints, logits):
        for start, end in skeleton_segments(
                person_points, person_logits, width, height, kpt_conf_thresh):
            cv2.line(image, start, end, (120, 245, 130), thickness, cv2.LINE_AA)
            count += 1
    return count
