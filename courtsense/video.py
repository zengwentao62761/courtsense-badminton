"""Explicit local-video adapter. Optional inference dependencies load only at runtime."""
import copy
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from .report import ObservationSummary, write_report


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _keypoints(result):
    points = getattr(result, 'keypoints', None)
    if points is None or points.conf is None:
        return [], []
    coordinates = points.xy.cpu().tolist()
    probabilities = points.conf.cpu().tolist()
    if len(coordinates) != len(probabilities):
        raise ValueError('Pose result has mismatched people and confidences')
    keypoints, logits = [], []
    for person, scores in zip(coordinates, probabilities):
        if len(person) != 17 or len(scores) != 17:
            raise ValueError('Only COCO17 pose models are supported')
        converted = []
        for score in scores:
            if not math.isfinite(score) or not 0 <= score <= 1:
                converted.append(float('nan'))
            else:
                probability = min(1 - 1e-7, max(1e-7, score))
                converted.append(math.log(probability / (1 - probability)))
        # No candidate without any visible keypoint is presented as a detected person.
        if any(math.isfinite(score) and score >= .4 for score in scores):
            keypoints.append(person)
            logits.append(converted)
    return keypoints, logits


def analyze_video(video_path, output_dir, *, model_path, stride=5, max_frames=None,
                  on_update=None, device='cpu'):
    """Sample zero-based frames 0,stride,...; max_frames limits inference samples.

    Processing clocks are independent of source time. A nonadvancing decoder
    timestamp falls back explicitly to frame_index/fps. Never downloads weights.
    """
    if type(stride) is not int or stride <= 0:
        raise ValueError('stride must be a positive integer')
    if max_frames is not None and (type(max_frames) is not int or max_frames <= 0):
        raise ValueError('max_frames must be a positive integer or None')
    source, weights, output = Path(video_path).resolve(), Path(model_path).resolve(), Path(output_dir).resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Local video not found: {source}')
    if not weights.is_file():
        raise FileNotFoundError(f'Local pose model not found: {weights}; provide weights explicitly')
    if output.exists():
        raise FileExistsError(f'Output must be a new directory: {output}')
    try:
        import cv2
        import ultralytics
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError('Video analysis requires requirements-video.txt and an explicit local pose model') from exc
    from .pose.pose_observation import make_observation
    from .pose.pose_skeleton import draw_skeleton
    cap = cv2.VideoCapture(str(source))
    state = None
    started = time.monotonic()
    try:
        if not cap.isOpened():
            raise ValueError('Cannot open local video')
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('Video FPS must be finite and positive')
        count_value = float(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        total = int(count_value) if math.isfinite(count_value) and count_value > 0 else None
        width, height = (float(cap.get(prop)) for prop in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise ValueError('Video dimensions must be finite and positive')
        model = YOLO(str(weights), task='pose')
        if getattr(model, 'task', None) != 'pose':
            raise ValueError('Expected a pose model')
        session = uuid.uuid4().hex
        inference = {'conf': .25, 'iou': .7, 'imgsz': 640, 'max_det': 300, 'half': False, 'augment': False}
        manifest = {'schema_version': 1, 'session_id': session,
            'source': {'path': str(source), 'label': source.name, 'sha256': _sha256(source),
                       'fps': fps, 'width': int(width), 'height': int(height), 'total_frames': total},
            'model': {'path': str(weights), 'sha256': _sha256(weights), 'task': 'COCO17_pose',
                      'device': str(device), 'probability_threshold': .4, 'inference': inference,
                      'ultralytics_version': str(getattr(ultralytics, '__version__', 'unknown'))},
            'sampling': {'stride': stride, 'max_frames': max_frames, 'frame_indices': '0,stride,2*stride,...',
                         'max_frames_unit': 'processed_samples', 'source_time': 'decoder_pos_msec_else_frame_index_over_fps'},
            'platform': 'desktop_validation', 'synthetic': False,
            'opencv_version': str(getattr(cv2, '__version__', 'unknown')),
            'limitations': ['No persistent identity', 'No court calibration', 'No smash count, speed or score',
                           '2D projected joint angles; no accuracy claim', 'Decoder timestamps and FPS fallback are not capture-clock verification']}
        output.mkdir(parents=True, exist_ok=False)
        _json(output / 'manifest.json', manifest)
        state = {'session_id': session, 'status': 'running',
            'source': {'kind': 'video', 'label': source.name, 'platform': 'desktop_validation'},
            'progress': {'frame_id': None, 'video_time_s': None, 'processed_frames': 0, 'total_frames': total},
            'latest': None, 'summary': {}, 'capabilities': {'pose': True, 'court_calibrated': False,
                'shuttle': False, 'smash_count': False, 'speed': False},
            'errors': [], 'frame_url': '/api/frame.jpg', 'video_url': '/api/video', 'manifest': manifest}
        accumulator = ObservationSummary()
        frame_id, previous_source_time = 0, None
        with (output / 'observations.jsonl').open('x', encoding='utf-8') as observations:
            while max_frames is None or accumulator.frames < max_frames:
                ok, frame = cap.read()
                if not ok:
                    if frame_id == 0:
                        raise ValueError('Video contains no decodable frames')
                    if total is not None and frame_id < total:
                        raise ValueError(f'Video decoding stopped early at frame {frame_id} of {total}')
                    break
                if frame_id % stride:
                    frame_id += 1
                    continue
                received = time.monotonic()
                msec = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                source_time = msec / 1000
                timestamp_kind = 'decoder_pos_msec'
                if not math.isfinite(source_time) or source_time < 0 or (previous_source_time is not None and source_time <= previous_source_time):
                    source_time, timestamp_kind = frame_id / fps, 'frame_index_over_fps'
                previous_source_time = source_time
                results = model.predict(source=frame, device=device, verbose=False, save=False, stream=False, **inference)
                if not results:
                    raise ValueError('Pose model returned no result for a decoded frame')
                keypoints, logits = _keypoints(results[0])
                frame_height, frame_width = frame.shape[:2]
                observation = make_observation(keypoints, logits, width=frame_width, height=frame_height,
                    image_space_id=f'video:{session}:{frame_width}x{frame_height}',
                    received_monotonic_s=received, processed_monotonic_s=time.monotonic(),
                    wall_time_s=time.time(), zoom={'factor': 1.0})
                observation.update(frame_id=frame_id, video_time_s=source_time,
                    video_timestamp_source=timestamp_kind, timestamp_source='local_decode_host_monotonic')
                draw_skeleton(frame, keypoints, logits)
                encoded, jpeg = cv2.imencode('.jpg', frame)
                if not encoded:
                    raise ValueError('Failed to encode latest overlay')
                temporary = output / 'latest.tmp'
                temporary.write_bytes(jpeg.tobytes())
                temporary.replace(output / 'latest.jpg')
                observations.write(json.dumps(observation, ensure_ascii=False, allow_nan=False) + '\n')
                observations.flush()
                accumulator.add(observation)
                state.update(latest=observation, summary=accumulator.snapshot(time.monotonic() - started))
                state['progress'].update(frame_id=frame_id, video_time_s=source_time, processed_frames=accumulator.frames)
                if on_update:
                    on_update(copy.deepcopy(state))
                frame_id += 1
        state['status'] = 'complete'
        state['summary'] = accumulator.snapshot(time.monotonic() - started)
        manifest['result'] = {'processed_frames': accumulator.frames, 'decoded_frames': frame_id,
                              'stop_reason': 'max_frames' if max_frames is not None and accumulator.frames >= max_frames else 'end_of_video'}
        _json(output / 'manifest.json', manifest)
        write_report(output, state)
        if on_update:
            on_update(copy.deepcopy(state))
        return state
    except Exception as exc:
        if state is not None:
            state['status'] = 'failed'
            state['errors'].append(str(exc))
            write_report(output, state)
            if on_update:
                on_update(copy.deepcopy(state))
        raise
    finally:
        cap.release()
