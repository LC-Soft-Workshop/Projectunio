import array
import copy
import gc
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch,Mock
import app
import montage
from audio_analysis import analyse,AnalysisCancelled
from calibration_versions import snapshot,restore,validate,format_version
from media_relink import find_candidates,replacements
from render_cache import RenderCache,digest
from render_job import RenderJob
from test_clip_context import video


def tone(path):
    subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.4',str(path)],check=True,capture_output=True,timeout=15)


def sound(path,identity='a',volume=1.):
    return dict(id=identity,kind='audio',path=str(path),lane=0 if identity=='a' else 1,start=0.,duration=.4,volume=volume,**{'in':0.,'out':.4})


class AdvancedModelTests(unittest.TestCase):
    def test_folder_search_keeps_ambiguous_names_and_relink_is_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('a','b'):(root/name).mkdir(); (root/name/'clip.mp4').write_bytes(b'video')
            missing=['old/clip.mp4','old/absent.wav']; candidates,errors=find_candidates(missing,root)
            self.assertEqual(len(candidates[missing[0]]),2); self.assertEqual(candidates[missing[1]],[]); self.assertFalse(errors)
            c=video('first'); c['path']=missing[0]; other=dict(c,id='second',start=3.)
            data=dict(clips=[c,other],audio_clips=[]); before=copy.deepcopy(data)
            with patch('media_relink.montage.probe',return_value=(4.,False)):
                proposed=replacements(data,{missing[0]:candidates[missing[0]][0]},'ffmpeg')
            self.assertEqual(data,before); self.assertEqual(proposed['clips'][0]['path'],proposed['clips'][1]['path'])
            with patch('media_relink.montage.probe',return_value=(1.,False)),self.assertRaises(ValueError):replacements(data,{missing[0]:candidates[missing[0]][0]},'ffmpeg')
            self.assertEqual(data,before)

    def test_calibration_restore_preserves_montage_and_rejects_wrong_count(self):
        data=copy.deepcopy(app.DEFAULT); data['clips']=[video('clip')]
        version=snapshot(data,'HDMI validé'); data['zones'][0][0][0]+=.01
        result=restore(data,version); self.assertEqual(result['clips'],data['clips']); self.assertEqual(result['zones'],app.DEFAULT['zones'])
        data['zones'].pop()
        with self.assertRaises(ValueError):restore(data,version)
        bad=copy.deepcopy(version); bad['zones'][0]=[[0.,0.]]*4
        with self.assertRaises(ValueError):validate([bad])
        self.assertEqual(format_version(dict(calibration_versions=[version])),6)

    def test_cache_checks_corruption_quota_and_clear_preserves_other_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cache=RenderCache(root/'cache',limit=8); source=root/'source'; source.write_bytes(b'12345')
            cache.store('a'*64,source); output=root/'output'; self.assertTrue(cache.restore('a'*64,output)); self.assertEqual(output.read_bytes(),b'12345')
            (cache.root/('a'*64+'.mp4')).write_bytes(b'wrong')
            self.assertFalse(cache.restore('a'*64,output))
            cache.store('b'*64,source); self.assertLessEqual(cache.usage()[1],8)
            unrelated=cache.root/'original.mp4'; unrelated.write_bytes(b'keep'); cache.clear(); self.assertEqual(unrelated.read_bytes(),b'keep'); self.assertEqual(cache.usage(),(0,0))

    def test_float_mix_analysis_finds_overload_and_reduction_preserves_balance(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'tone.wav'; tone(source)
            clips=[sound(source,'a',8.),sound(source,'b',8.)]; report=analyse([],clips,app.ffmpeg())
            self.assertGreater(report['peak'],1.3); self.assertTrue(report['ranges']); self.assertLess(report['gain'],.7)
            corrected=analyse([],[dict(c,volume=c['volume']*report['gain']) for c in clips],app.ffmpeg())
            self.assertAlmostEqual(corrected['db'],-1.,delta=.02); self.assertFalse(corrected['ranges'])
            cancel=threading.Event(); cancel.set()
            with self.assertRaises(AnalysisCancelled):analyse([],clips,app.ffmpeg(),cancel)
            self.assertEqual(analyse([],[],app.ffmpeg())['peak'],0.)

    def test_cache_reuses_exports_and_invalidates_source_content_and_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.mp4'
            def make(color):subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i',f'color={color}:s=64x64:r=30:d=0.2','-c:v','libx264',str(source)],check=True,capture_output=True,timeout=15)
            make('red'); clip=video('clip'); clip.update(path=str(source),duration=.2); clip['out']=.2
            zones=copy.deepcopy(app.DEFAULT['zones'])
            def render(index):
                events=queue.Queue(); target=root/f'final{index}.mp4'
                job=RenderJob(events,app.ffmpeg(),zones,[copy.deepcopy(clip)],[],'test',app.mask,app.graph,app.write_mire,app.output_options,destination=target,cache_directory=root/'cache'); job.width=320; job.height=180
                job.thread.start(); job.thread.join(15)
                self.assertFalse(job.thread.is_alive()); results=[]
                while not events.empty():results.append(events.get())
                self.assertFalse([value for _,kind,value in results if kind=='error']); self.assertTrue(target.exists()); return job
            first=render(1); second=render(2); self.assertEqual(first.encoded_segments,1); self.assertEqual(second.disk_reused,1); self.assertEqual(second.encoded_segments,0)
            before=digest(source); make('blue'); self.assertNotEqual(before,digest(source)); self.assertEqual(render(3).encoded_segments,1)
            zones[0][0][0]+=.01; self.assertEqual(render(4).encoded_segments,1)

    def test_export_waits_for_sound_decision_and_can_apply_reduction(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'tone.wav'; tone(source); original=[sound(source,'a',8.),sound(source,'b',8.)]
            events=queue.Queue(); job=RenderJob(events,app.ffmpeg(),app.DEFAULT['zones'],[],copy.deepcopy(original),'test',app.mask,app.graph,app.write_mire,app.output_options,destination=root/'export.mp4',cache_directory=root/'cache'); job.width=320; job.height=180; job.review_audio=True
            job.thread.start(); report=None; deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                _,kind,value=events.get(timeout=10)
                if kind=='audio_warning':report=value; break
                if kind=='error':self.fail(value)
            self.assertIsNotNone(report); self.assertFalse((root/'export.mp4').exists())
            job.audio_gain=report['gain']; job.audio_decision.set(); job.thread.join(15); self.assertFalse(job.thread.is_alive()); self.assertTrue((root/'export.mp4').exists())
            values=array.array('f',subprocess.check_output([app.ffmpeg(),'-v','error','-i',str(root/'export.mp4'),'-vn','-f','f32le','pipe:1'],timeout=10))
            self.assertLess(max(abs(x) for x in values),1.); self.assertEqual(original[0]['volume'],8.)

    def test_many_audio_clips_are_analysed_in_bounded_windows(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'tone.wav'; tone(source)
            clips=[dict(sound(source),id=str(i),start=i*.4) for i in range(17)]
            report=analyse([],clips,app.ffmpeg())
            self.assertAlmostEqual(report['duration'],6.8); self.assertLess(report['peak'],.1); self.assertGreater(report['peak'],.08)


class AdvancedUITests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()

    def tearDown(self):
        self.root.destroy()
        for worker in [self.a.timeline_tools.worker,self.a.still_renderer.worker,self.a.live_audio.worker]:worker.join(5)
        self.a=None; self.root=None; gc.collect()

    def children(self,parent):
        result=[]
        for widget in parent.winfo_children():result.append(widget); result.extend(self.children(widget))
        return result

    def button(self,parent,text):return next(w for w in self.children(parent) if isinstance(w,ttk.Button) and w.cget('text')==text)

    def test_calibration_ui_compare_restore_undo_and_version_six_roundtrip(self):
        self.a.data['clips']=[video('clip')]; self.a.calibration_versions(); win=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Versions de calibration')
        with patch('advanced_features.simpledialog.askstring',return_value='HDMI validé'):self.button(win,'Enregistrer l’actuelle…').invoke()
        tree=next(w for w in self.children(win) if isinstance(w,ttk.Treeview)); identifier=self.a.data['calibration_versions'][0]['id']; tree.selection_set(identifier)
        self.a.data['zones'][0][0][0]+=.01; self.button(win,'Restaurer la sélection').invoke()
        self.assertEqual(self.a.data['zones'],app.DEFAULT['zones']); self.assertEqual(len(self.a.data['clips']),1)
        self.a.undo(); self.assertNotEqual(self.a.data['zones'],app.DEFAULT['zones'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'calibration.json'
            with patch('app.filedialog.asksaveasfilename',return_value=str(path)):self.a.save()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['version'],6)
            with patch('app.filedialog.askopenfilename',return_value=str(path)):self.a.load()
            self.assertEqual(self.a.data['calibration_versions'][0]['name'],'HDMI validé')

    def test_folder_dialog_applies_unique_matches_as_one_undo_step(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'video.mp4'; source.write_bytes(b'x'); clip=video('clip'); clip['path']=str(root/'missing'/'video.mp4'); self.a.data['clips']=[clip]
            def inline(title,work,done):done(work(threading.Event(),lambda value:None))
            with patch.object(self.a,'run_background',side_effect=inline),patch('advanced_features.filedialog.askdirectory',return_value=folder),patch('media_relink.montage.probe',return_value=(4.,False)):
                self.a.find_media_folder(); win=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Correspondances des médias'); self.button(win,'Appliquer les correspondances').invoke()
            self.assertEqual(self.a.data['clips'][0]['path'],str(source.resolve())); self.a.undo(); self.assertIn('missing',self.a.data['clips'][0]['path'])

    def test_audio_correction_is_explicit_and_undoable(self):
        self.a.data['audio_clips']=[sound('unused.wav','a',2.)]
        report=dict(peak=2.,db=6.,gain=.4,ranges=[[0.,.4]])
        with patch('audio_analysis.analyse',return_value=report),patch.object(self.a,'run_background',side_effect=lambda title,work,done:done(work(threading.Event(),lambda value:None))):self.a.analyse_audio()
        self.assertEqual(self.a.data['audio_clips'][0]['volume'],2.)
        win=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Analyse sonore du montage'); self.button(win,'Appliquer la réduction au projet').invoke()
        self.assertAlmostEqual(self.a.data['audio_clips'][0]['volume'],.8); self.a.undo(); self.assertEqual(self.a.data['audio_clips'][0]['volume'],2.)

    def test_projection_disconnection_closes_only_output(self):
        from projection_output import ProjectionOutput
        rectangle=(0,0,320,180); closed=Mock()
        with patch('projection_output.place_projector_window'),patch('projection_output.monitor_rectangles',return_value=[rectangle]):
            output=ProjectionOutput(self.root,rectangle,closed); self.root.update(); output.show((2,2,b'\xff\0\0'*4)); self.assertIsNotNone(output.image)
            with patch('projection_output.monitor_rectangles',return_value=[]):output.check_monitor()
            self.assertTrue(output.closed); self.assertTrue(self.root.winfo_exists()); closed.assert_called_once()

    def test_read_only_locks_and_stale_background_results(self):
        original=self.a.data; state=json.dumps(original,sort_keys=True); self.a.data=copy.deepcopy(original)
        with patch('advanced_features.messagebox.showinfo'):self.assertFalse(self.a.current_snapshot(original,state))
        self.a.data['locks']=dict(timeline=True)
        with patch('advanced_features.filedialog.askdirectory') as dialog:self.a.find_media_folder(); dialog.assert_not_called()


if __name__=='__main__':unittest.main()
