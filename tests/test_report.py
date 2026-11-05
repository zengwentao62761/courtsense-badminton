import json
import math
import tempfile
import unittest
from pathlib import Path
from courtsense.report import summarize, write_report


class ReportTests(unittest.TestCase):
    def test_summary_counts_detections_and_only_valid_angles_and_ankles(self):
        person = {'angles_2d': {'left_elbow': {'valid': True, 'degrees': 90},
                                'right_elbow': {'valid': False, 'degrees': 170}},
                  'keypoints': [{'name': 'left_ankle', 'valid': True, 'x': 30, 'y': 40},
                                {'name': 'right_ankle', 'valid': False, 'x': 0, 'y': 0}]}
        observations = ({'frame_id': i, 'width': 100, 'height': 100,
                         'image_space_id': 'camera', 'people': [person] if i < 2 else []}
                        for i in range(3))
        summary = summarize(observations, elapsed_s=2)
        self.assertEqual(summary['processed_frames'], 3)
        self.assertEqual(summary['frames_with_people'], 2)
        self.assertEqual(summary['person_observations'], 2)
        self.assertEqual(summary['angle_stats']['left_elbow']['mean'], 90)
        self.assertNotIn('right_elbow', summary['angle_stats'])
        self.assertEqual(len(summary['ankle_points_image']), 2)
        self.assertNotIn('track_id', summary['ankle_points_image'][0])

    def test_summary_bounded_points_and_nonfinite_measurements_excluded(self):
        observation = {'width': 100, 'height': 100, 'people': [{
            'angles_2d': {'bad': {'valid': True, 'degrees': math.nan}},
            'keypoints': [{'name': 'left_ankle', 'valid': True, 'x': 10, 'y': 20}]}]}
        summary = summarize(observation for _ in range(3000))
        self.assertLessEqual(len(summary['ankle_points_image']), 1000)
        self.assertEqual(summary['angle_stats'], {})
        json.dumps(summary, allow_nan=False)

    def test_report_escapes_source_and_rejects_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {'source': {'label': '<script>alert(1)</script>'},
                     'summary': summarize([]), 'status': 'complete'}
            write_report(directory, state)
            html = (Path(directory) / 'report.html').read_text(encoding='utf-8')
            self.assertNotIn('<script>alert', html)
            self.assertIn('&lt;script&gt;', html)
            self.assertEqual(json.loads((Path(directory) / 'report.json').read_text(encoding='utf-8')), state)
            with self.assertRaises(ValueError):
                write_report(directory, {'summary': {'bad': math.nan}})
