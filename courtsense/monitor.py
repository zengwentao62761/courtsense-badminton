"""Local workbench; default source is the existing RDK HTTP pose service."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from .report import ObservationSummary, write_report


class MonitorStore:
    def __init__(self, output_dir, video_path=None):
        self.output_dir = Path(output_dir)
        self.video_path = Path(video_path).resolve() if video_path else None
        self.lock = threading.Lock()
        self.jpeg = None
        self.state = {'session_id': uuid.uuid4().hex, 'status': 'waiting',
            'source': {'kind': 'rdk', 'label': 'Waiting for RDK service', 'platform': 'unverified_host'},
            'progress': {}, 'latest': None, 'summary': {}, 'errors': [],
            'capabilities': {'pose': True, 'court_calibrated': False, 'shuttle': False,
                             'smash_count': False, 'speed': False},
            'frame_url': '/api/frame.jpg', 'video_url': None}

    def update(self, state, jpeg=None):
        with self.lock:
            self.state = copy.deepcopy(state)
            if jpeg is not None:
                self.jpeg = jpeg

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state), self.jpeg


def make_server(store, host, port):
    web = Path(__file__).parent / 'web'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body, content_type, status=200, headers=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in (headers or {}).items():
                self.send_header(key, str(value))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/api/state':
                state, _ = store.snapshot()
                return self.send(json.dumps(state, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8')
            if url.path == '/api/frame.jpg':
                state, jpeg = store.snapshot()
                obs = state.get('latest') or {}
                if jpeg is None:
                    return self.send(b'No paired frame yet', 'text/plain', 503)
                query = parse_qs(url.query, keep_blank_values=True)
                for key in ('frame_id', 'image_space_id', 'service_instance_id'):
                    if key in query and query[key] != [str(obs.get(key, ''))]:
                        return self.send(b'Frame snapshot advanced; retry state', 'text/plain', 409)
                return self.send(jpeg, 'image/jpeg', headers={
                    'X-Frame-Id': obs.get('frame_id', ''),
                    'X-Image-Space-Id': obs.get('image_space_id', ''),
                    'X-Service-Instance-Id': obs.get('service_instance_id', '')})
            if url.path in ('/api/report.json', '/api/report.html'):
                path = store.output_dir / ('report.json' if url.path.endswith('.json') else 'report.html')
                if not path.is_file():
                    return self.send(b'Report not ready', 'text/plain', 404)
                return self.send(path.read_bytes(), 'application/json; charset=utf-8' if path.suffix == '.json' else 'text/html; charset=utf-8')
            if url.path == '/api/video' and store.video_path is not None:
                return self.video()
            assets = {'/': 'index.html', '/index.html': 'index.html',
                      '/assets/style.css': 'style.css', '/assets/app.js': 'app.js'}
            if url.path in assets:
                path = web / assets[url.path]
                return self.send(path.read_bytes(), (mimetypes.guess_type(str(path))[0] or 'application/octet-stream') + '; charset=utf-8')
            return self.send(b'Not found', 'text/plain', 404)

        def video(self):
            path = store.video_path
            if not path.is_file():
                return self.send(b'Selected video unavailable', 'text/plain', 404)
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            value = self.headers.get('Range')
            if value:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
                if not match or not any(match.groups()):
                    return self.send(b'Invalid byte range', 'text/plain', 416)
                left, right = match.groups()
                if left:
                    start, end = int(left), min(int(right), size-1) if right else size-1
                else:
                    start = max(0, size-int(right))
                if start > end or start >= size:
                    return self.send(b'Unsatisfiable byte range', 'text/plain', 416, {'Content-Range': f'bytes */{size}'})
                status = 206
            self.send_response(status)
            self.send_header('Content-Type', mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(end-start+1))
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    block = stream.read(min(65536, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=('rdk', 'video'), default='rdk')
    parser.add_argument('--upstream', default='http://127.0.0.1:8080')
    parser.add_argument('--video', type=Path)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--stride', type=int, default=5)
    parser.add_argument('--max-frames', type=int)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8793)
    parser.add_argument('--output', type=Path, default=Path('artifacts') / ('monitor-'+uuid.uuid4().hex[:12]))
    args = parser.parse_args(argv)
    if args.stride <= 0 or (args.max_frames is not None and args.max_frames <= 0):
        parser.error('stride and max-frames must be positive')
    if args.source == 'video' and (not args.video or not args.model):
        parser.error('video source requires --video and --model local files')
    if args.output.exists():
        parser.error('output must be a NEW directory')
    return args


def _run_rdk(args, store, stop):
    from .sources.rdk import RDKSource
    source = RDKSource(args.upstream)
    accumulator = ObservationSummary()
    args.output.mkdir(parents=True, exist_ok=False)
    state, _ = store.snapshot()
    state['source'] = {'kind': 'rdk', 'label': 'Configured RDK pose service', 'platform': 'rdk_service_adapter'}
    started, last_key = time.monotonic(), None
    advanced_at, report_at = started, -10.
    with (args.output/'observations.jsonl').open('x', encoding='utf-8') as output:
        while not stop.is_set():
            try:
                packet = source.read()
                obs, jpeg = packet['observation'], packet['jpeg']
                key = (obs['service_instance_id'], obs['image_space_id'], obs['frame_id'])
                if key != last_key:
                    advanced_at = time.monotonic()
                    accumulator.add(obs)
                    output.write(json.dumps(obs, ensure_ascii=False, allow_nan=False)+'\n')
                    output.flush()
                    state.update(latest=obs, status='running', errors=[], frame_age_s=0,
                        summary=accumulator.snapshot(time.monotonic()-started),
                        progress={'frame_id': obs['frame_id'], 'processed_frames': accumulator.frames,
                                  'video_time_s': None, 'total_frames': None})
                    store.update(state, jpeg)
                    if time.monotonic() - report_at >= 5:
                        write_report(args.output, state)
                        report_at = time.monotonic()
                    last_key = key
                    if args.max_frames and accumulator.frames >= args.max_frames:
                        break
                else:
                    age = time.monotonic() - advanced_at
                    state.update(status='stale' if age >= 5 else 'running',
                        errors=['Upstream frame has not advanced for at least 5 seconds'] if age >= 5 else [])
                    state['frame_age_s'] = age
                    store.update(state)
            except Exception as exc:
                state.update(status='offline', errors=[str(exc)])
                store.update(state)
            stop.wait(.25)
    state['status'] = 'complete' if last_key else 'failed'
    store.update(state)
    write_report(args.output, state)


def main(argv=None):
    args = parse_args(argv)
    store = MonitorStore(args.output, args.video if args.source == 'video' else None)
    if args.source == 'video':
        initial, _ = store.snapshot()
        initial['source'] = {'kind': 'video', 'label': args.video.name, 'platform': 'desktop_validation'}
        store.update(initial)
    stop = threading.Event()

    def worker():
        try:
            if args.source == 'rdk':
                _run_rdk(args, store, stop)
            else:
                from .video import analyze_video
                def update(state):
                    path = args.output/'latest.jpg'
                    store.update(state, path.read_bytes() if path.exists() else None)
                analyze_video(args.video, args.output, model_path=args.model, stride=args.stride,
                              max_frames=args.max_frames, device=args.device, on_update=update)
        except Exception as exc:
            state, _ = store.snapshot()
            state.update(status='failed', errors=[str(exc)])
            store.update(state)

    server = make_server(store, args.host, args.port)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    print(f'CourtSense: http://{args.host}:{server.server_port}/ ; source={args.source}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        thread.join(timeout=5)
    return 0
