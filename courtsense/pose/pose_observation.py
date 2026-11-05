"""Export raw model observations; these are image measurements, not 3D assessments."""

import math


NAMES = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
         'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
         'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
         'left_knee', 'right_knee', 'left_ankle', 'right_ankle')
ANGLES = {'left_elbow': (5, 7, 9), 'right_elbow': (6, 8, 10),
          'left_knee': (11, 13, 15), 'right_knee': (12, 14, 16)}


def _finite(value):
    value = float(value)
    return value if math.isfinite(value) else None


def _angle(points, indices):
    a, b, c = (points[index] for index in indices)
    if not all(point['valid'] for point in (a, b, c)):
        return None
    u = (a['x'] - b['x'], a['y'] - b['y'])
    v = (c['x'] - b['x'], c['y'] - b['y'])
    scale = math.hypot(*u) * math.hypot(*v)
    if scale < 1e-6:
        return None
    cosine = max(-1., min(1., (u[0] * v[0] + u[1] * v[1]) / scale))
    return round(math.degrees(math.acos(cosine)), 1)


def make_observation(keypoints, logits, *, width, height, image_space_id,
                     received_monotonic_s, processed_monotonic_s, wall_time_s, zoom):
    if len(keypoints) != len(logits) or width <= 0 or height <= 0:
        raise ValueError('Expected matching people and positive image dimensions')
    people = []
    threshold = math.log(.4 / .6)
    for person_index, (person, scores) in enumerate(zip(keypoints, logits)):
        if len(person) != 17 or len(scores) != 17:
            raise ValueError('Expected COCO17 keypoints and raw logits')
        points = []
        for index, (xy, score) in enumerate(zip(person, scores)):
            x, y = _finite(xy[0]), _finite(xy[1])
            raw = _finite(score[0] if hasattr(score, '__len__') else score)
            probability = None
            if raw is not None:
                exponent = math.exp(-abs(raw))
                probability = 1 / (1 + exponent) if raw >= 0 else exponent / (1 + exponent)
            valid = (x is not None and y is not None and raw is not None
                     and 0 <= x < width and 0 <= y < height and raw >= threshold)
            reason = ('nonfinite' if None in (x, y, raw) else
                      'out_of_frame' if not (0 <= x < width and 0 <= y < height) else
                      'low_visibility' if not valid else None)
            points.append({'index': index, 'name': NAMES[index], 'x': x, 'y': y,
                           'probability': round(probability, 5) if probability is not None else None,
                           'valid': bool(valid), 'reason': reason})
        people.append({'detection_index': person_index, 'track_id': None,
                       'valid_keypoints': sum(point['valid'] for point in points),
                       'keypoints': points,
                       'angles_2d': {name: _angle(points, indices) for name, indices in ANGLES.items()}})
    return {'schema_version': 1, 'synthetic': False, 'image_space_id': image_space_id,
            'width': width, 'height': height, 'coordinate_units': 'pixels',
            'coordinate_stage': 'after_rotation_and_zoom', 'zoom': dict(zoom),
            'timestamp_source': 'host_after_get_img',
            'received_monotonic_s': received_monotonic_s,
            'processed_monotonic_s': processed_monotonic_s,
            'wall_time_s': wall_time_s, 'keypoint_probability_threshold': .4,
            'people': people}
