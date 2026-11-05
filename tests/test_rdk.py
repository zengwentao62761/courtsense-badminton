import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import unittest
from unittest.mock import patch
from courtsense.sources.rdk import RDKSource, RDKSourceError

# SOI, SOF0 header for 10 x 10, SOS and EOI (header validation fixture).
JPEG = bytes.fromhex('ffd8 ffc0000b08000a000a01011100 ffda0008010100003f00 00 ffd9')

def observation():
    return dict(ready=True, frame_id=5, image_space_id='upright', service_instance_id='boot',
                width=10, height=10, people=[], received_monotonic_s=1,
                processed_monotonic_s=2, wall_time_s=3)

def response(body, headers=None):
    result = io.BytesIO(body)
    result.headers = headers or {'Content-Type':'application/json'}
    return result

def pair(obs=None, **headers):
    hdr = {'Content-Type':'image/jpeg', 'X-Frame-Id':'5', 'X-Image-Space-Id':'upright',
           'X-Service-Instance-Id':'boot', 'X-Image-Width':'10', 'X-Image-Height':'10'}
    hdr.update(headers)
    return [response(json.dumps(obs or observation()).encode()), response(JPEG, hdr)]

class RDKTests(unittest.TestCase):
    @patch('courtsense.sources.rdk.urlopen')
    def test_matching_pair(self, open_url):
        open_url.side_effect = pair()
        result = RDKSource().read()
        self.assertEqual(result['jpeg'], JPEG)
        self.assertEqual(result['observation']['frame_id'], 5)
        self.assertEqual([a.args[0].full_url for a in open_url.call_args_list],
                         ['http://localhost:8080/observations', 'http://localhost:8080/frame.jpg'])

    @patch('courtsense.sources.rdk.urlopen')
    def test_mismatch_retries_and_then_returns_only_matching(self, open_url):
        open_url.side_effect = pair(**{'X-Frame-Id':'6'}) + pair()
        self.assertEqual(RDKSource().read()['observation']['frame_id'], 5)
        self.assertEqual(open_url.call_count, 4)

    @patch('courtsense.sources.rdk.urlopen')
    def test_each_identity_must_match(self, open_url):
        for key in ('X-Frame-Id', 'X-Image-Space-Id', 'X-Service-Instance-Id', 'X-Image-Width'):
            with self.subTest(key=key):
                open_url.side_effect = sum([pair(**{key:'999'}) for _ in range(3)], [])
                with self.assertRaises(RDKSourceError): RDKSource().read()

    @patch('courtsense.sources.rdk.urlopen')
    def test_not_ready_and_invalid_observations(self, open_url):
        for change in ({'ready':False}, {'frame_id':-1}, {'width':0}, {'height':100000},
                       {'received_monotonic_s':float('nan')}, {'people':[{'keypoints':[]}]}):
            obs = observation(); obs.update(change)
            open_url.side_effect = [response(json.dumps(obs).encode()) for _ in range(3)]
            with self.subTest(change=change), self.assertRaises(RDKSourceError): RDKSource().read()

    @patch('courtsense.sources.rdk.urlopen')
    def test_preview_is_smaller_than_coordinate_space(self, open_url):
        obs = observation()
        obs.update(width=20, height=20, preview_width=10, preview_height=10)
        open_url.side_effect = pair(obs, **{'X-Image-Width':'20', 'X-Image-Height':'20'})
        self.assertEqual(RDKSource().read()['observation']['width'], 20)

    @patch('courtsense.sources.rdk.urlopen')
    def test_invalid_preview_and_probability_rejected(self, open_url):
        for change in ({'preview_width':0, 'preview_height':0},
                       {'preview_width':20}, {'preview_width':20, 'preview_height':10}):
            obs = observation(); obs.update(change)
            open_url.side_effect = sum([pair(obs) for _ in range(3)], [])
            with self.subTest(change=change), self.assertRaises(RDKSourceError): RDKSource().read()
        point = dict(index=0, x=5, y=5, probability=.8, valid=True)
        for change in ({'probability':2}, {'x':10}, {'x':float('inf')}, {'probability':.1}):
            obs = observation()
            points = [dict(point, index=i) for i in range(17)]
            points[0].update(change)
            obs['people'] = [{'keypoints':points}]
            open_url.side_effect = sum([pair(obs) for _ in range(3)], [])
            with self.subTest(change=change), self.assertRaises(RDKSourceError): RDKSource().read()

    @patch('courtsense.sources.rdk.urlopen')
    def test_bad_or_empty_jpeg_rejected(self, open_url):
        for payload in (b'', b'not jpeg', JPEG[:-2]):
            responses = []
            for _ in range(3):
                batch = pair(); batch[1] = response(payload, batch[1].headers)
                responses.extend(batch)
            open_url.side_effect = responses
            with self.subTest(payload=payload), self.assertRaises(RDKSourceError): RDKSource().read()

    @patch('courtsense.sources.rdk.urlopen', side_effect=TimeoutError('timed out'))
    def test_timeout_is_bounded(self, open_url):
        with self.assertRaises(RDKSourceError): RDKSource(timeout=.1).read()
        self.assertEqual(open_url.call_count, 3)

    def test_invalid_connection_arguments(self):
        for kwargs in ({'timeout':0}, {'timeout':float('inf')}, {'base_url':'file:///tmp/a'},
                       {'base_url':'http://user:pass@localhost:8080'}, {'timeout':True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): RDKSource(**kwargs)


class RDKHTTPTests(unittest.TestCase):
    def test_real_http_gets_only_and_retries_race(self):
        routes = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                routes.append(self.path)
                self.send_response(200)
                if self.path == '/observations':
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps(observation()).encode())
                elif self.path == '/frame.jpg':
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('x-frame-id', '6' if len(routes) == 2 else '5')
                    self.send_header('X-Image-Space-Id', 'upright')
                    self.send_header('X-Service-Instance-Id', 'boot')
                    self.send_header('X-Image-Width', '10')
                    self.send_header('X-Image-Height', '10')
                    self.end_headers()
                    self.wfile.write(JPEG)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = RDKSource('http://127.0.0.1:'+str(server.server_port)).read()
            self.assertEqual(result['observation']['frame_id'], 5)
            self.assertEqual(routes, ['/observations', '/frame.jpg'] * 2)
        finally:
            server.shutdown(); server.server_close(); thread.join()
