import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from courtsense.analysis import analyze, calibrate, project, current_binding
from courtsense.monitor import MonitorStore, make_server


def example():
    return json.loads((Path(__file__).parents[1]/'docs/examples/analysis-input.json').read_text(encoding='utf-8'))


class AnalysisTests(unittest.TestCase):
    def test_perspective_controls_and_ground_contact_gate(self):
        p = example(); result = analyze(p,None)
        h = result['calibration']['homography']
        for pair in p['calibration']['points']:
            self.assertLess(sum((a-b)**2 for a,b in zip(project(h,pair['pixel']),pair['court_m'])),1e-10)
        self.assertIsNone(result['player_tracks'][0]['points'][1]['court_m'])
        self.assertIsNotNone(result['player_tracks'][0]['points'][0]['court_m'])
        self.assertEqual(result['shuttle_tracks'][0]['points'][2]['pixel'],None)

    def test_collinear_and_duplicate_controls_rejected(self):
        for points in ([{'pixel':[i*10,i*10],'court_m':[i,i]} for i in range(4)],
                       [example()['calibration']['points'][0]]*4):
            with self.assertRaises(ValueError):
                calibrate({'input_space':'undistorted_pixels','points':points},example()['image_space'])

    def test_overdetermined_calibration_and_reprojection(self):
        p = example()
        h = analyze(p,None)['calibration']['homography']
        p['calibration']['points'].append({'pixel':[600,350],'court_m':project(h,[600,350])})
        self.assertLess(analyze(p,None)['calibration']['reprojection_rmse_m'],1e-7)
        p['calibration']['points'][-1]['court_m'] = [50,50]
        with self.assertRaises(ValueError): analyze(p,None)

    def test_smash_deduplication_and_conflicts(self):
        p = example(); p['events'].append(copy.deepcopy(p['events'][0]))
        result = analyze(p,None)['smash']
        self.assertEqual((result['confirmed_count'],result['candidate_count']),(1,1))
        p['events'][-1]['status'] = 'candidate'
        with self.assertRaises(ValueError): analyze(p,None)

    def test_speed_uses_actual_time_and_never_homography(self):
        p = example(); result = analyze(p,None)['speed']
        self.assertEqual(len(result['pixel_segments']),1)
        self.assertAlmostEqual(result['pixel_segments'][0]['pixel_per_s'],(20**2+100**2)**.5/.1)
        self.assertAlmostEqual(result['world3d_segments'][0]['estimated_km_per_h'],2**.5/.1*3.6)
        for point in p['shuttle_points']:
            point.pop('world3d_m',None); point.pop('world3d_source',None)
        self.assertEqual(analyze(p,None)['speed']['world3d_segments'],[])
        p['shuttle_points'][1]['t_s'] = 0
        with self.assertRaises(ValueError): analyze(p,None)

    def test_validation_boundaries_and_3d_provenance(self):
        bad = []
        p=example(); p['shuttle_points'][0].pop('world3d_source'); bad.append(p)
        p=example(); p['player_points'][0]['pixel'][0]=1280; bad.append(p)
        p=example(); p['player_points'][0]['t_s']=float('nan'); bad.append(p)
        p=example(); p['player_points'][0]['contact_confirmed']=1; bad.append(p)
        p=example(); p['player_points']*=4000; bad.append(p)
        p=example(); p['shuttle_points'][1]['t_s']=1e-15; bad.append(p)
        p=example(); p['calibration']['input_space']='raw_pixels'; bad.append(p)
        p=example(); p['player_points'][0]['t_s']=10**1000; bad.append(p)
        p=example(); p['events'].reverse(); bad.append(p)
        for payload in bad:
            with self.subTest(payload=str(payload)[:120]), self.assertRaises(ValueError): analyze(payload,None)

    def test_speed_does_not_bridge_missing_or_changed_3d_provenance(self):
        p=example(); p['shuttle_points'][1]['world3d_source']='another reconstruction'
        self.assertEqual(analyze(p,None)['speed']['world3d_segments'],[])
        p['shuttle_points'][1].pop('world3d_m'); p['shuttle_points'][1].pop('world3d_source')
        self.assertEqual(analyze(p,None)['speed']['world3d_segments'],[])
        p['calibration']=None
        self.assertIsNone(analyze(p,None)['player_tracks'][0]['points'][0]['court_m'])

    def test_session_and_source_changes_invalidate_live_results(self):
        with tempfile.TemporaryDirectory() as d:
            store=MonitorStore(d)
            state,_=store.snapshot()
            state['latest']={'image_space_id':'s','width':1280,'height':720,'service_instance_id':'boot'}
            store.update(state)
            for mutation in ('session','source','service'):
                p=example(); p['mode']='live'; p['binding']=current_binding(state); p['image_space']=p['binding']['image_space']
                store.replace_analysis(p)
                if mutation=='session': state['session_id']='new-session'
                if mutation=='source': state['source']['label']='another source'
                if mutation=='service': state['latest']['service_instance_id']='another-boot'
                store.update(state)
                self.assertEqual(store.analysis_snapshot()['status'],'invalidated')
                with self.assertRaises(ValueError): store.replace_analysis(example())

    def test_persistence_failure_keeps_previous_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            store=MonitorStore(d); store.replace_analysis(example()); before=store.analysis_snapshot()
            with patch.object(Path,'replace',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): store.replace_analysis({},reset=True)
            self.assertEqual(store.analysis_snapshot(),before)
            self.assertEqual(len(list(Path(d).glob('analysis-*.json'))),1)
            self.assertEqual(list(Path(d).glob('*.tmp')),[])

    def test_binding_invalidation_and_reset_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            store=MonitorStore(d); store.replace_analysis(example())
            state,_=store.snapshot(); state['latest']={'image_space_id':'s','width':1280,'height':720,'service_instance_id':'boot'}
            store.update(state)
            self.assertEqual(store.analysis_snapshot()['status'],'invalidated')
            p=example(); p['mode']='live'; p['binding']=current_binding(state); p['image_space']=p['binding']['image_space']
            store.replace_analysis(p)
            state['latest']['width']=1200; store.update(state)
            self.assertEqual(store.analysis_snapshot()['status'],'invalidated')
            self.assertIsNone(store.analysis_snapshot()['result'])
            with self.assertRaises(ValueError): store.replace_analysis(p)
            self.assertEqual(store.replace_analysis({},reset=True)['status'],'empty')
            self.assertEqual(len(list(Path(d).glob('analysis-*.json'))),3)

    def test_http_atomic_import_security_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            store=MonitorStore(d); server=make_server(store,'127.0.0.1',0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def post(body,path='/api/analysis',headers=None):
                return urlopen(Request(base+path,data=body,headers={'Content-Type':'application/json',**(headers or {})}))
            try:
                with post(json.dumps(example()).encode()) as response:
                    self.assertEqual(json.load(response)['status'],'ready')
                for body,headers,code in [(b'{',{},400),(b'{"a":1,"a":2}',{},400),
                    (b'NaN',{},400),(b'[]',{},400), (b'{}',{'Origin':'http://evil.example'},403),
                    (b'{}',{'Host':f'evil.example:{server.server_port}'},403),
                    (b'{}',{'Sec-Fetch-Site':'cross-site'},403),
                    (b'{}',{'Content-Type':'text/plain'},415),
                    (b'x'*1048577,{},413)]:
                    with self.assertRaises(HTTPError) as err: post(body,headers=headers)
                    self.assertEqual(err.exception.code,code)
                with urlopen(base+'/api/analysis') as response:
                    self.assertEqual(json.load(response)['data'],example())
                with post(b'{}','/api/analysis/reset') as response:
                    self.assertEqual(json.load(response)['status'],'empty')
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
