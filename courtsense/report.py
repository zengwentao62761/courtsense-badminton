"""Bounded summaries of image observations; no identity or action inference."""
from collections import deque
import html
import json
import math
from pathlib import Path


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class ObservationSummary:
    """Online accumulator; retains only the latest 1000 visible ankle samples."""
    def __init__(self):
        self.frames = self.with_people = self.people = 0
        self.angles = {}
        self.ankles = deque(maxlen=1000)
        self.ankle_count = 0

    def add(self, observation):
        people = observation.get('people', [])
        self.frames += 1
        self.with_people += bool(people)
        self.people += len(people)
        for person in people:
            for name, value in person.get('angles_2d', {}).items():
                if name not in ('left_elbow', 'right_elbow', 'left_knee', 'right_knee'):
                    continue
                if isinstance(value, dict):
                    value = value.get('degrees') if value.get('valid') else None
                if not _finite(value) or not 0 <= value <= 180:
                    continue
                entry = self.angles.setdefault(name, {'count': 0, 'mean': 0., 'min': value, 'max': value})
                entry['count'] += 1
                entry['mean'] += (value - entry['mean']) / entry['count']
                entry['min'], entry['max'] = min(entry['min'], value), max(entry['max'], value)
            width, height = observation.get('width'), observation.get('height')
            for point in person.get('keypoints', []):
                x, y = point.get('x'), point.get('y')
                if (point.get('name') not in ('left_ankle', 'right_ankle') or not point.get('valid')
                        or not all(_finite(v) for v in (x, y, width, height))
                        or not (0 <= x < width and 0 <= y < height)):
                    continue
                self.ankle_count += 1
                self.ankles.append({'frame_id': observation.get('frame_id'), 'name': point['name'],
                    'x': x, 'y': y, 'width': width, 'height': height,
                    'image_space_id': observation.get('image_space_id'),
                    'video_time_s': observation.get('video_time_s')})

    def snapshot(self, elapsed_s=0):
        if not _finite(elapsed_s) or elapsed_s < 0:
            raise ValueError('elapsed_s must be finite and nonnegative')
        return {'processed_frames': self.frames, 'frames_with_people': self.with_people,
                'person_observations': self.people, 'elapsed_s': elapsed_s,
                'angle_stats': {name: dict(entry) for name, entry in self.angles.items()},
                'ankle_points_image': list(self.ankles), 'ankle_points_seen': self.ankle_count,
                'ankle_sampling': 'latest_1000_valid_points_from_processed_frames',
                'interpretation': '2D visible-joint angles and image ankle pixels; detections are not unique athletes. No court calibration, identity, smash count, speed or score.'}


def summarize(observations, elapsed_s=0):
    accumulator = ObservationSummary()
    for observation in observations:
        accumulator.add(observation)
    return accumulator.snapshot(elapsed_s)


def write_report(output_dir, state):
    """Write a strict JSON snapshot and standalone escaped HTML to an existing directory."""
    serialized = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)
    summary = state.get('summary', {})
    title = html.escape(str(state.get('source', {}).get('label', 'CourtSense')))
    circles = []
    for point in summary.get('ankle_points_image', []):
        values = [point.get(key) for key in ('x', 'y', 'width', 'height')]
        if all(_finite(v) for v in values) and values[2] > 0 and values[3] > 0:
            x, y, width, height = values
            circles.append(f'<circle cx="{x / width * 640:.2f}" cy="{y / height * 360:.2f}" r="2" fill="#40cfad" opacity=".5"/>')
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>CourtSense report</title>
<style>body{{font:16px system-ui;background:#11212b;color:#e4edf0;max-width:1000px;margin:32px auto;padding:20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}svg{{width:100%;background:#07161e}}a{{color:#5fdbbe}}</style>
<h1>CourtSense · {title}</h1><p>真实检测摘要：人数观察不等于独立运动员数量。角度仅为可见关节二维投影描述统计。</p>
<p>足踝图为处理帧中最近最多1000个有效图像点，按各帧宽高归一化；不是球场跑位、距离或时间加权热图。未校准球场，不提供身份、扣杀、速度或评分。</p>
<h2>图像足踝点</h2><svg viewBox="0 0 640 360" role="img" aria-label="归一化图像足踝分布">{''.join(circles)}</svg>
<h2>观察与来源记录</h2><pre>{html.escape(serialized)}</pre></html>'''
    directory = Path(output_dir)
    for name, contents in (('report.json', serialized + '\n'), ('report.html', document)):
        temporary = directory / (name + '.tmp')
        temporary.write_text(contents, encoding='utf-8')
        temporary.replace(directory / name)
