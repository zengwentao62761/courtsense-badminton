import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from courtsense.monitor import MonitorStore, make_server, parse_args


class MonitorTests(unittest.TestCase):
    def test_rdk_same_frame_recovers_connection_and_becomes_stale(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from courtsense.monitor import _run_rdk
        with tempfile.TemporaryDirectory() as d:
            packet = {'observation': {'frame_id': 7, 'image_space_id': 'space',
                       'service_instance_id': 'boot', 'people': []}, 'jpeg': b'jpeg'}
            clock = [0]
            statuses = []
            class Stop:
                def is_set(self): return clock[0] >= 6
                def wait(self, seconds):
                    statuses.append(store.snapshot()[0]['status'])
                    clock[0] += 1
            store = MonitorStore(Path(d)/'run')
            args = SimpleNamespace(upstream='http://localhost:8080', output=Path(d)/'run', max_frames=None)
            with patch('courtsense.sources.rdk.RDKSource') as source, patch('courtsense.monitor.time.monotonic', side_effect=lambda: clock[0]):
                source.return_value.read.side_effect = [packet, OSError('offline'), packet, packet, packet, packet]
                _run_rdk(args, store, Stop())
            self.assertEqual(statuses[:3], ['running', 'offline', 'running'])
            self.assertEqual(statuses[-1], 'stale')
            self.assertEqual(store.snapshot()[0]['summary']['processed_frames'], 1)

    def test_default_is_rdk_and_no_video_model_required(self):
        args = parse_args([])
        self.assertEqual(args.source, 'rdk')
        self.assertEqual(args.upstream, 'http://127.0.0.1:8080')
        self.assertEqual(args.host, '127.0.0.1')

    def test_http_snapshot_pairing_and_paths(self):
        with tempfile.TemporaryDirectory() as d:
            store = MonitorStore(Path(d))
            store.update({'status': 'running', 'latest': {'frame_id': 7,
                'image_space_id': 'space', 'service_instance_id': 'boot'}}, b'jpeg-7')
            server = make_server(store, '127.0.0.1', 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base+'/api/frame.jpg?frame_id=7&image_space_id=space&service_instance_id=boot') as response:
                    self.assertEqual(response.read(), b'jpeg-7')
                    self.assertEqual(response.headers['X-Frame-Id'], '7')
                with self.assertRaises(HTTPError) as error:
                    urlopen(base+'/api/frame.jpg?frame_id=8&image_space_id=space&service_instance_id=boot')
                self.assertEqual(error.exception.code, 409)
                with self.assertRaises(HTTPError):
                    urlopen(base+'/assets/../../AGENTS.md')
                with urlopen(base+'/api/state') as response:
                    self.assertEqual(json.load(response)['latest']['frame_id'], 7)
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_video_range_is_only_selected_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'clip.mp4'
            path.write_bytes(b'0123456789')
            store = MonitorStore(Path(d), video_path=path)
            server = make_server(store, '127.0.0.1', 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                from urllib.request import Request
                request = Request(f'http://127.0.0.1:{server.server_port}/api/video', headers={'Range':'bytes=2-5'})
                with urlopen(request) as r:
                    self.assertEqual(r.status, 206)
                    self.assertEqual(r.read(), b'2345')
            finally:
                server.shutdown(); server.server_close(); thread.join()
