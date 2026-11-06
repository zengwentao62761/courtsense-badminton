"""Manual/offline analysis foundation. No automatic detection or measured accuracy."""
import copy
import math


LIMITATIONS = ['Manual/imported observations; no automatic shuttle or smash detector.',
    'Ground homography applies only to confirmed ground contacts in undistorted pixels.',
    '3D speeds are imported reconstruction estimates, not independently measured speeds.']


def fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError('Invalid object fields; expected: ' + ', '.join(allowed))


def number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError('Expected finite number in [%s, %s]' % (low, high))
    return value


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError('Expected nonempty text up to 256 characters')
    return value


def vector(value, size, low, high):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError('Invalid coordinate dimension')
    return [number(v, low, high) for v in value]


def image_space(value):
    fields(value, ('id', 'width', 'height', 'service_instance_id'), ('id', 'width', 'height', 'service_instance_id'))
    label(value['id']); label(value['service_instance_id'])
    for key in ('width', 'height'):
        if type(value[key]) is not int:
            raise ValueError('Image dimensions must be integers')
        number(value[key], 1, 32768)
    return value


def pixel(value, space):
    point = vector(value, 2, 0, 32768)
    if point[0] >= space['width'] or point[1] >= space['height']:
        raise ValueError('Pixel outside image_space')
    return point


def _solve(matrix, rhs):
    """Pivoted elimination; reject singular/poorly conditioned normalized systems."""
    rows = [list(row) + [v] for row, v in zip(matrix, rhs)]
    for column in range(len(rhs)):
        pivot = max(range(column, len(rows)), key=lambda i: abs(rows[i][column]))
        if abs(rows[pivot][column]) < 1e-10:
            raise ValueError('Degenerate calibration control points')
        rows[column], rows[pivot] = rows[pivot], rows[column]
        scale = rows[column][column]
        rows[column] = [x / scale for x in rows[column]]
        for i in range(len(rows)):
            if i != column:
                scale = rows[i][column]
                rows[i] = [a - scale*b for a, b in zip(rows[i], rows[column])]
    return [row[-1] for row in rows]


def project(h, point):
    x, y = point
    divisor = h[6]*x + h[7]*y + h[8]
    if abs(divisor) < 1e-10:
        raise ValueError('Point projects to infinity')
    result = [(h[0]*x+h[1]*y+h[2])/divisor, (h[3]*x+h[4]*y+h[5])/divisor]
    vector(result, 2, -1000, 1000)
    return result


def calibrate(value, space):
    if value is None:
        return None
    fields(value, ('input_space', 'points'), ('input_space', 'points'))
    if value['input_space'] != 'undistorted_pixels':
        raise ValueError('Calibration requires undistorted_pixels; undistortion is upstream responsibility')
    points = value['points']
    if not isinstance(points, list) or not 4 <= len(points) <= 64:
        raise ValueError('Calibration requires 4..64 point pairs')
    pairs = []
    for item in points:
        fields(item, ('pixel', 'court_m'), ('pixel', 'court_m'))
        pairs.append((pixel(item['pixel'], space), vector(item['court_m'], 2, -100, 100)))
    if len({tuple(p[0]) for p in pairs}) != len(pairs) or len({tuple(p[1]) for p in pairs}) != len(pairs):
        raise ValueError('Duplicate calibration control point')
    # Normalize both coordinate domains to improve the normal equation conditioning.
    def normalization(values):
        center = [sum(p[i] for p in values)/len(values) for i in range(2)]
        scale = math.sqrt(sum(sum((p[i]-center[i])**2 for i in range(2)) for p in values)/len(values))
        if scale < 1e-9:
            raise ValueError('Degenerate calibration')
        return center, scale
    pc, ps = normalization([p for p, _ in pairs]); qc, qs = normalization([q for _, q in pairs])
    rows, rhs = [], []
    for p, q in pairs:
        x, y = [(p[i]-pc[i])/ps for i in range(2)]
        u, v = [(q[i]-qc[i])/qs for i in range(2)]
        rows += [[x,y,1,0,0,0,-u*x,-u*y], [0,0,0,x,y,1,-v*x,-v*y]]
        rhs += [u,v]
    a = [[sum(row[i]*row[j] for row in rows) for j in range(8)] for i in range(8)]
    b = [sum(row[i]*v for row,v in zip(rows,rhs)) for i in range(8)]
    hn = _solve(a,b)+[1.]
    def multiply(a,b):
        return [sum(a[i*3+k]*b[k*3+j] for k in range(3)) for i in range(3) for j in range(3)]
    h = multiply([qs,0,qc[0],0,qs,qc[1],0,0,1], multiply(hn,[1/ps,0,-pc[0]/ps,0,1/ps,-pc[1]/ps,0,0,1]))
    determinant = h[0]*(h[4]*h[8]-h[5]*h[7])-h[1]*(h[3]*h[8]-h[5]*h[6])+h[2]*(h[3]*h[7]-h[4]*h[6])
    if abs(determinant) < 1e-12:
        raise ValueError('Singular homography')
    error = math.sqrt(sum(sum((a-b)**2 for a,b in zip(project(h,p),q)) for p,q in pairs)/len(pairs))
    if error > .25:
        raise ValueError('Control point reprojection RMSE exceeds 0.25m; check correspondences')
    return {'homography':h, 'reprojection_rmse_m':error, 'point_count':len(pairs),
            'validation':'development_unverified', 'input_space':'undistorted_pixels'}


def current_binding(state):
    obs = state.get('latest') or {}
    if not all(key in obs for key in ('image_space_id','width','height','service_instance_id')) or not state.get('session_id'):
        return None
    return {'session_id':state['session_id'], 'source_identity':copy.deepcopy(state.get('source', {})),
        'image_space':{'id':obs['image_space_id'], 'width':obs['width'], 'height':obs['height'],
                       'service_instance_id':obs['service_instance_id']}}


def analyze(payload, binding):
    allowed = ('schema_version','mode','source_name','synthetic','binding','image_space','calibration','player_points','shuttle_points','events')
    fields(payload, allowed, ('schema_version','mode','source_name','synthetic','image_space'))
    if type(payload['schema_version']) is not int or payload['schema_version'] != 1 or type(payload['synthetic']) is not bool:
        raise ValueError('Expected schema_version=1 and boolean synthetic')
    label(payload['source_name'])
    space = image_space(payload['image_space'])
    if payload['mode'] == 'live':
        if binding is None or payload.get('binding') != binding or space != binding['image_space']:
            raise ValueError('Live binding mismatch; refresh current session and image_space')
    elif payload['mode'] == 'offline_development':
        if binding is not None or 'binding' in payload:
            raise ValueError('Offline development requires no current live frame and no live binding')
    else:
        raise ValueError('mode must be live or offline_development')
    calibration = calibrate(payload.get('calibration'), space)
    tracks, shuttle, times = {}, {}, {}
    pixel_speed, world_speed = [], []
    for key in ('player_points', 'shuttle_points', 'events'):
        if not isinstance(payload.get(key, []), list) or len(payload.get(key, [])) > 10000:
            raise ValueError('Each record list is limited to 10000 entries')
    for p in payload.get('player_points', []):
        fields(p, ('t_s','player_id','pixel','contact_confirmed'), ('t_s','player_id','pixel','contact_confirmed'))
        name = label(p['player_id']); t = number(p['t_s'],0,1e9)
        if type(p['contact_confirmed']) is not bool:
            raise ValueError('contact_confirmed must be boolean')
        if t <= times.get(('p',name), -1):
            raise ValueError('Player timestamps must strictly increase per identity')
        times['p',name] = t
        point = pixel(p['pixel'],space)
        mapped = project(calibration['homography'],point) if calibration and p['contact_confirmed'] else None
        tracks.setdefault(name,[]).append(dict(p,court_m=mapped))
    for p in payload.get('shuttle_points', []):
        fields(p, ('t_s','track_id','pixel','world3d_m','world3d_source'), ('t_s','track_id','pixel'))
        name = label(p['track_id']); t = number(p['t_s'],0,1e9)
        if t <= times.get(('s',name),-1):
            raise ValueError('Shuttle timestamps must strictly increase per track')
        times['s',name] = t
        if p['pixel'] is not None:
            pixel(p['pixel'],space)
        if 'world3d_m' in p:
            vector(p['world3d_m'],3,-1000,1000); label(p.get('world3d_source'))
        elif 'world3d_source' in p:
            raise ValueError('world3d_source requires world3d_m')
        previous = shuttle.get(name, [])[-1:]
        if previous:
            prev = previous[0]; delta = t-prev['t_s']
            segment = {'track_id':name,'t_start_s':prev['t_s'],'t_end_s':t}
            if prev['pixel'] is not None and p['pixel'] is not None:
                pixel_speed.append(dict(segment,pixel_per_s=number(math.dist(prev['pixel'],p['pixel'])/delta,0,1e12)))
            if all('world3d_m' in q for q in (prev,p)) and prev['world3d_source'] == p['world3d_source']:
                speed = number(math.dist(prev['world3d_m'],p['world3d_m'])/delta,0,1e6)
                world_speed.append(dict(segment,estimated_m_per_s=speed,estimated_km_per_h=speed*3.6,source=p['world3d_source']))
        shuttle.setdefault(name,[]).append(copy.deepcopy(p))
    events = {}
    for e in payload.get('events', []):
        fields(e, ('event_id','t_s','type','status','source'), ('event_id','t_s','type','status','source'))
        identity = label(e['event_id']); label(e['source']); number(e['t_s'],0,1e9)
        if e['type'] != 'smash' or e['status'] not in ('candidate','confirmed'):
            raise ValueError('Only candidate or confirmed smash events are supported')
        if identity in events and events[identity] != e:
            raise ValueError('Conflicting duplicate event_id')
        if identity not in events and events and e['t_s'] < next(reversed(events.values()))['t_s']:
            raise ValueError('Unique event timestamps must be nondecreasing')
        events[identity] = copy.deepcopy(e)
    ordered = sorted(events.values(),key=lambda e:(e['t_s'],e['event_id']))
    return {'mode':payload['mode'], 'synthetic':payload['synthetic'], 'source_name':payload['source_name'],
        'validation':'development_unverified', 'calibration':calibration,
        'player_tracks':[{'player_id':k,'points':v} for k,v in tracks.items()],
        'shuttle_tracks':[{'track_id':k,'points':v} for k,v in shuttle.items()],
        'smash':{'confirmed_count':sum(e['status']=='confirmed' for e in ordered),
                 'candidate_count':sum(e['status']=='candidate' for e in ordered),'events':ordered},
        'speed':{'pixel_segments':pixel_speed,'world3d_segments':world_speed}}
