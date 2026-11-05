"""Read the existing RDK HTTP service without changing camera state."""
import json
import math
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class RDKSourceError(RuntimeError):
    """No validated, matching observation/JPEG pair was available."""


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def _validate_observation(obs):
    if not isinstance(obs, dict) or obs.get('ready') is not True:
        raise ValueError('RDK observation is not ready')
    if not _integer(obs.get('frame_id'), 0, 2**63-1):
        raise ValueError('Invalid frame_id')
    for key in ('image_space_id', 'service_instance_id'):
        if not isinstance(obs.get(key), str) or not 0 < len(obs[key]) <= 256:
            raise ValueError('Missing or invalid ' + key)
    for key in ('width', 'height'):
        if not _integer(obs.get(key), 1, 16384):
            raise ValueError('Invalid image dimensions')
    if 'preview_width' in obs or 'preview_height' in obs:
        for key in ('preview_width', 'preview_height'):
            if not _integer(obs.get(key), 1, 16384):
                raise ValueError('Invalid preview dimensions')
    for key in ('received_monotonic_s', 'processed_monotonic_s', 'wall_time_s'):
        if not _number(obs.get(key)) or obs[key] < 0:
            raise ValueError('Invalid timestamp ' + key)
    if obs['processed_monotonic_s'] < obs['received_monotonic_s']:
        raise ValueError('Processing precedes reception')
    people = obs.get('people')
    if not isinstance(people, list) or len(people) > 256:
        raise ValueError('Invalid people list')
    for person in people:
        if not isinstance(person, dict):
            raise ValueError('Invalid person')
        points = person.get('keypoints')
        if not isinstance(points, list) or len(points) != 17:
            raise ValueError('Expected COCO17 points')
        for index, point in enumerate(points):
            if not isinstance(point, dict) or point.get('index') != index or type(point.get('valid')) is not bool:
                raise ValueError('Invalid keypoint')
            probability = point.get('probability')
            # Service JSON already contains probabilities, never sigmoid these again.
            if probability is not None and (not _number(probability) or not 0 <= probability <= 1):
                raise ValueError('Expected probability, not raw logit')
            x, y = point.get('x'), point.get('y')
            if any(v is not None and not _number(v) for v in (x, y)):
                raise ValueError('Nonfinite keypoint coordinates')
            if point['valid'] and (probability is None or probability < .4 or
                    not _number(x) or not _number(y) or not (0 <= x < obs['width'] and 0 <= y < obs['height'])):
                raise ValueError('Valid keypoint outside image or below probability threshold')


def _jpeg_dimensions(data):
    """Check JPEG framing and read SOF dimensions without image dependencies.

    This checks the envelope/header, not entropy decoding of every pixel.
    """
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError('Empty, truncated or non-JPEG frame')
    offset = 2
    dimensions = None
    while offset < len(data)-2:
        if data[offset] != 255:
            raise ValueError('Invalid JPEG marker')
        while offset < len(data) and data[offset] == 255:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]; offset += 1
        if marker in (0xd8, 0xd9) or 0xd0 <= marker <= 0xd7:
            continue
        if offset+2 > len(data):
            raise ValueError('Truncated JPEG segment')
        length = int.from_bytes(data[offset:offset+2], 'big')
        if length < 2 or offset+length > len(data)-2:
            raise ValueError('Invalid JPEG segment length')
        if marker in (0xc0, 0xc1, 0xc2):
            if length < 8:
                raise ValueError('Invalid JPEG SOF')
            dimensions = (int.from_bytes(data[offset+5:offset+7], 'big'),
                          int.from_bytes(data[offset+3:offset+5], 'big'))
        if marker == 0xda:
            if dimensions is None:
                raise ValueError('JPEG scan precedes dimensions')
            return dimensions
        offset += length
    raise ValueError('Missing JPEG scan')


class RDKSource:
    """Fetch at most three pairs; each read checks a shared network deadline.

    Consecutive GETs may race with inference. No matched historical-frame API
    exists, so a busy service can legitimately exhaust retries.
    """
    def __init__(self, base_url='http://localhost:8080', timeout=3):
        if not isinstance(base_url, str):
            raise ValueError('Expected HTTP service URL')
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username or parsed.password or parsed.query or parsed.fragment or
                parsed.path not in ('', '/')):
            raise ValueError('Expected HTTP(S) origin without credentials')
        if not _number(timeout) or not 0 < timeout <= 60:
            raise ValueError('Timeout must be finite and within (0, 60] seconds')
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def _get(self, path, limit, deadline, content_type):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('RDK read deadline exceeded')
        request = Request(self.base_url+path, headers={'Cache-Control':'no-cache'})
        with urlopen(request, timeout=remaining) as response:
            if response.headers.get('Content-Type', '').split(';')[0].strip().lower() != content_type:
                raise ValueError('Unexpected content type for '+path)
            chunks = []
            size = 0
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError('RDK read deadline exceeded')
                # read1 avoids waiting to fill a large read on a slow response.
                reader = getattr(response, 'read1', response.read)
                chunk = reader(min(65536, limit+1-size))
                if not chunk:
                    break
                chunks.append(chunk); size += len(chunk)
                if size > limit:
                    raise ValueError('RDK response exceeds size limit')
            return b''.join(chunks), response.headers

    def read(self):
        deadline = time.monotonic()+self.timeout
        last_error = None
        for _ in range(3):
            try:
                payload, _ = self._get('/observations', 2*1024*1024, deadline, 'application/json')
                obs = json.loads(payload)
                _validate_observation(obs)
                jpeg, headers = self._get('/frame.jpg', 16*1024*1024, deadline, 'image/jpeg')
                for key, header in (('frame_id','X-Frame-Id'), ('image_space_id','X-Image-Space-Id'),
                                    ('service_instance_id','X-Service-Instance-Id'),
                                    ('width','X-Image-Width'), ('height','X-Image-Height')):
                    if headers.get(header) != str(obs[key]):
                        raise ValueError('Observation/JPEG mismatch: '+key)
                if _jpeg_dimensions(jpeg) != (obs.get('preview_width', obs['width']),
                                               obs.get('preview_height', obs['height'])):
                    raise ValueError('JPEG dimensions differ from observation')
                return {'observation':obs, 'jpeg':jpeg}
            except (OSError, URLError, ValueError, TypeError, KeyError, RecursionError) as error:
                last_error = error
        raise RDKSourceError('No matched RDK frame: '+str(last_error)) from last_error
