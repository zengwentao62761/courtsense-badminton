import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from courtsense.court import nominal_court, render_svg


class CourtPreviewTests(unittest.TestCase):
    def test_lines_stay_in_bounds_and_reflect_about_net(self):
        court = nominal_court()
        segments = court['segments']
        self.assertEqual((court['width_m'], court['length_m']), (6.1, 13.4))
        self.assertEqual(len({s['id'] for s in segments}), len(segments))
        for segment in segments:
            for x, y in (segment['start'], segment['end']):
                self.assertTrue(0 <= x <= 6.1 and 0 <= y <= 13.4)
        rows = [s for s in segments if s['kind'] == 'short_service']
        self.assertAlmostEqual(sum(s['start'][1] for s in rows), 13.4)
        centers = [s for s in segments if s['kind'] == 'center_service']
        self.assertEqual(len(centers), 2)
        for s in centers:
            self.assertTrue(max(s['start'][1], s['end'][1]) <= 4.72 or
                            min(s['start'][1], s['end'][1]) >= 8.68)

    def test_svg_is_parseable_and_explicitly_non_measured(self):
        court = nominal_court()
        root = ET.fromstring(render_svg(court))
        self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')
        content = ''.join(root.itertext())
        self.assertIn('NOT A CALIBRATION', content)
        self.assertFalse(court['usable_for_metric_calibration'])
        self.assertEqual(court['evidence_type'], 'nominal_geometry')

    def test_cli_exports_and_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'preview'
            args = [sys.executable, '-m', 'courtsense', '--output', str(output)]
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = (output / 'court.svg').read_bytes()
            data = json.loads((output / 'court.json').read_text(encoding='utf-8'))
            self.assertFalse(data['usable_for_metric_calibration'])
            again = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((output / 'court.svg').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
