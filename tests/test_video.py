import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from courtsense.video import analyze_video


def tensor(values):
    value = MagicMock()
    value.cpu.return_value.tolist.return_value = values
    return value


class VideoTests(unittest.TestCase):
    def fixture(self, directory, *, fps=25, opened=True, count=6):
        source, model = Path(directory) / 'video.mp4', Path(directory) / 'pose.pt'
        source.write_bytes(b'local-video')
        model.write_bytes(b'local-model')
        cv = MagicMock()
        cv.CAP_PROP_FPS, cv.CAP_PROP_FRAME_COUNT, cv.CAP_PROP_POS_MSEC = 1, 2, 3
        cv.CAP_PROP_FRAME_WIDTH, cv.CAP_PROP_FRAME_HEIGHT = 4, 5
        cap = cv.VideoCapture.return_value
        cap.isOpened.return_value = opened
        cap.get.side_effect = lambda key: {1: fps, 2: count, 3: 0, 4: 100, 5: 80}[key]
        frame = MagicMock()
        frame.shape = (80, 100, 3)
        cap.read.side_effect = [(True, frame) for _ in range(count)] + [(False, None)]
        cv.imencode.return_value = (True, SimpleNamespace(tobytes=lambda: b'JPEG'))
        result = SimpleNamespace(keypoints=SimpleNamespace(
            xy=tensor([[[20, 30] for _ in range(17)]]),
            conf=tensor([[.8 for _ in range(17)]])))
        yolo = MagicMock()
        yolo.return_value.task = 'pose'
        yolo.return_value.predict.return_value = [result]
        return source, model, cv, yolo

    def test_local_pipeline_preserves_probability_stride_time_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source, model, cv, yolo = self.fixture(directory)
            updates = []
            with patch.dict('sys.modules', {'cv2': cv, 'ultralytics': SimpleNamespace(YOLO=yolo)}):
                out = Path(directory) / 'out'
                state = analyze_video(source, out, model_path=model, stride=2, max_frames=2, on_update=updates.append)
            self.assertEqual(state['status'], 'complete')
            self.assertEqual(state['summary']['processed_frames'], 2)
            observations = [json.loads(line) for line in (out / 'observations.jsonl').read_text().splitlines()]
            self.assertEqual([item['frame_id'] for item in observations], [0, 2])
            self.assertAlmostEqual(observations[1]['video_time_s'], .08)
            self.assertEqual(observations[1]['video_timestamp_source'], 'frame_index_over_fps')
            self.assertAlmostEqual(observations[0]['people'][0]['keypoints'][0]['probability'], .8)
            self.assertIsNone(observations[0]['people'][0]['track_id'])
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['source']['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest['sampling']['max_frames'], 2)
            self.assertEqual((out / 'latest.jpg').read_bytes(), b'JPEG')
            self.assertTrue((out / 'report.html').is_file())
            self.assertEqual(updates[0]['summary']['processed_frames'], 1)
            self.assertTrue(cv.VideoCapture.return_value.release.called)

    def test_preflight_refuses_missing_model_existing_output_and_invalid_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            source, model, _, _ = self.fixture(directory)
            for kwargs in ({'stride': 0}, {'stride': True}, {'max_frames': 0}):
                with self.assertRaises(ValueError):
                    analyze_video(source, Path(directory) / 'out', model_path=model, **kwargs)
            with self.assertRaises(FileExistsError):
                analyze_video(source, directory, model_path=model)
            with self.assertRaises(FileNotFoundError):
                analyze_video(source, Path(directory) / 'out', model_path=Path(directory) / 'missing.pt')

    def test_bad_video_or_nonfinite_fps_refused_and_capture_released(self):
        for fps, opened in ((math.nan, True), (0, True), (25, False)):
            with self.subTest(fps=fps, opened=opened), tempfile.TemporaryDirectory() as directory:
                source, model, cv, yolo = self.fixture(directory, fps=fps, opened=opened)
                with patch.dict('sys.modules', {'cv2': cv, 'ultralytics': SimpleNamespace(YOLO=yolo)}):
                    with self.assertRaises(ValueError):
                        analyze_video(source, Path(directory) / 'out', model_path=model)
                self.assertTrue(cv.VideoCapture.return_value.release.called)

    def test_empty_and_truncated_video_leave_failed_audit_report(self):
        for count in (0, 3):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                source, model, cv, yolo = self.fixture(directory, count=count)
                if count:
                    cv.VideoCapture.return_value.read.side_effect = [(True, cv.VideoCapture.return_value.read.side_effect.__next__()[1]), (False, None)]
                output = Path(directory) / 'out'
                with patch.dict('sys.modules', {'cv2': cv, 'ultralytics': SimpleNamespace(YOLO=yolo)}):
                    with self.assertRaises(ValueError):
                        analyze_video(source, output, model_path=model, stride=1)
                report = json.loads((output / 'report.json').read_text())
                self.assertEqual(report['status'], 'failed')
                self.assertTrue(report['errors'])

    def test_absent_pose_and_low_visibility_are_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            source, model, cv, yolo = self.fixture(directory, count=3)
            model_result = yolo.return_value.predict.return_value[0]
            visible = SimpleNamespace(keypoints=SimpleNamespace(
                xy=tensor([[[20, 30] for _ in range(17)]]),
                conf=tensor([[.8] + [.2] * 16])))
            yolo.return_value.predict.side_effect = [[SimpleNamespace(keypoints=None)], [visible], [model_result]]
            with patch.dict('sys.modules', {'cv2': cv, 'ultralytics': SimpleNamespace(YOLO=yolo)}):
                state = analyze_video(source, Path(directory) / 'out', model_path=model, stride=1)
            observations = [json.loads(line) for line in (Path(directory) / 'out/observations.jsonl').read_text().splitlines()]
            self.assertEqual(observations[0]['people'], [])
            self.assertFalse(observations[1]['people'][0]['keypoints'][1]['valid'])
            self.assertEqual(observations[1]['people'][0]['keypoints'][1]['probability'], .2)
            self.assertEqual(state['summary']['frames_with_people'], 2)

    def test_manifest_records_fixed_inference_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            source, model, cv, yolo = self.fixture(directory, count=1)
            with patch.dict('sys.modules', {'cv2': cv, 'ultralytics': SimpleNamespace(YOLO=yolo)}):
                state = analyze_video(source, Path(directory) / 'out', model_path=model, stride=1)
            settings = state['manifest']['model']['inference']
            self.assertEqual(settings['conf'], .25)
            self.assertEqual(settings['imgsz'], 640)
            self.assertEqual(yolo.return_value.predict.call_args.kwargs['conf'], settings['conf'])
