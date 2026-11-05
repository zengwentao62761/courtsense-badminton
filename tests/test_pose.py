import math
import unittest
from courtsense.pose.pose_observation import make_observation
from courtsense.pose.pose_skeleton import skeleton_segments

class PoseTests(unittest.TestCase):
    def observe(self, points, scores):
        return make_observation([points], [scores], width=100, height=100,
            image_space_id='test', received_monotonic_s=1, processed_monotonic_s=2,
            wall_time_s=3, zoom={})['people'][0]

    def test_raw_logits_and_boundaries(self):
        points = [[10, 10] for _ in range(17)]
        points[0] = [100, 10]
        points[1] = [float('nan'), 10]
        scores = [0.0] * 17
        scores[2] = -10
        person = self.observe(points, scores)
        self.assertEqual(person['keypoints'][3]['probability'], .5)
        self.assertEqual([p['reason'] for p in person['keypoints'][:3]],
                         ['out_of_frame', 'nonfinite', 'low_visibility'])
        self.assertIsNone(person['track_id'])

    def test_angle_and_skeleton(self):
        points = [[10, 10] for _ in range(17)]
        points[5], points[7], points[9] = [10, 20], [10, 10], [20, 10]
        self.assertEqual(self.observe(points, [0]*17)['angles_2d']['left_elbow'], 90)
        self.assertTrue(skeleton_segments(points, [0]*17, 100, 100))
        self.assertEqual(skeleton_segments(points, [-10]*17, 100, 100), [])
