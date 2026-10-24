import copy
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import app
import montage
from calibration_versions import format_version
from project_transfer import check_media,gather_project
from media_relink import replacements
from render_segments import plan
from render_job import RenderJob
from source_comparison import comparison_frames
from work_media import prepare_proxies


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.folder=Path(self.temp.name)
        self.png=self.folder/'still.png'; self.jpg=self.folder/'still.jpg'
        for p in (self.png,self.jpg):
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=160x90','-frames:v','1',str(p)],check=True,capture_output=True,timeout=15)
        self.clip=dict(id='image',kind='image',path=str(self.png),lane=0,start=0.,duration=5.,audio=False,volume=1.,fit='Remplir',**{'in':0.,'out':.6})
        self.zones=[[[0.,0.],[1.,0.],[1.,1.],[0.,1.]]]

    def tearDown(self):self.temp.cleanup()

    def test_probe_validation_transfer_and_relink(self):
        for p in (self.png,self.jpg):self.assertEqual(montage.probe_image(p,app.ffmpeg()),(5.,False))
        c=dict(self.clip,**{'out':60.}); montage.validate([c]); self.assertEqual(format_version(dict(clips=[c])),9)
        data=dict(clips=[c],audio_clips=[],zones=self.zones)
        check_media(data,app.ffmpeg())
        changed=replacements(data,{str(self.png):str(self.jpg)},app.ffmpeg()); self.assertEqual(changed['clips'][0]['out'],60.)
        target=gather_project(data,self.folder/'transfer'); saved=json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(saved['version'],9); self.assertEqual(saved['clips'][0]['kind'],'image')
        self.assertTrue((target.parent/saved['clips'][0]['path']).exists())
        with self.assertRaises(ValueError):montage.validate([dict(c,audio=True)])
        self.assertNotEqual(plan([c],[])[0].key(),plan([dict(c,kind=None,duration=60.)],[])[0].key())

    def test_still_comparison_export_and_window_after_source_in(self):
        c=dict(self.clip,**{'in':10.,'out':10.6})
        for path in (self.png,self.jpg):
            c['path']=str(path)
            args=montage.render_args([c],self.zones,self.folder,app.mask,app.graph,160,90,still_at=.4)
            pixels=subprocess.check_output([app.ffmpeg(),'-v','error',*args,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],timeout=20)
            self.assertGreater(pixels[(45*160+80)*3],200)
        original,mapped,boxes=comparison_frames(app.ffmpeg(),c,[c],self.zones,.4,app.mask,app.graph,threading.Event())
        self.assertGreater(original[2][0],200); self.assertEqual(len(boxes),1)
        target=self.folder/'movie.mp4'; events=queue.Queue()
        job=RenderJob(events,app.ffmpeg(),self.zones,[c],[],'image',app.mask,app.graph,app.write_mire,app.output_options,destination=target,cache_directory=self.folder/'cache'); job.width=160; job.height=90
        job.thread.start(); job.thread.join(25); self.assertFalse(job.thread.is_alive()); self.assertTrue(target.exists())
        duration,audio=montage.probe(target,app.ffmpeg()); self.assertAlmostEqual(duration,.6,places=2); self.assertFalse(audio)
        c['panorama']=dict(lanes=[0,1],gap_mode='auto'); zones=[[[0.,0.],[.5,0.],[.5,1.],[0.,1.]],[[.5,0.],[1.,0.],[1.,1.],[.5,1.]]]
        args=montage.render_args([c],zones,self.folder,app.mask,app.graph,160,90,window=(.3,.6))
        subprocess.run([app.ffmpeg(),'-v','error',*args,'-f','null','-'],check=True,capture_output=True,timeout=20)

    def test_images_do_not_create_video_proxies(self):
        records,errors=prepare_proxies([str(self.png),str(self.jpg)],app.ffmpeg(),threading.Event(),root=self.folder/'proxy')
        self.assertEqual((records,errors),({},[]))

    def test_import_trim_properties_save_and_reload(self):
        root=tk.Tk(); a=app.App(root); root.update(); t=a.timeline
        try:
            t.import_files(0,[str(self.png),str(self.jpg)])
            self.assertEqual([c.get('kind') for c in t.clips],['image','image']); self.assertEqual([montage.length(c) for c in t.clips],[5.,5.])
            a.data['clips']=t.clips[:1]; t.selected=t.clips[0]['id']; a.timeline_tools.selection={t.selected}; t.scale.set('20'); t.refresh(); root.update(); c=t.clips[0]
            t.magnetic.set(False); t.dragging=(copy.deepcopy(c),185.,'out'); t.motion(SimpleNamespace(x=385.,y=47)); t.release(None)
            self.assertAlmostEqual(montage.length(t.clips[0]),15.)
            c=t.clips[0]; t.dragging=(copy.deepcopy(c),85.,'in'); t.motion(SimpleNamespace(x=125.,y=47)); t.release(None)
            self.assertAlmostEqual(montage.length(t.clips[0]),13.)
            # A still has no source boundary: moving it later permits extending left.
            moved=dict(t.clips[0],start=10.,**{'in':0.,'out':13.}); t.commit(moved)
            t.dragging=(copy.deepcopy(moved),285.,'in'); t.motion(SimpleNamespace(x=225.,y=47)); t.release(None)
            self.assertAlmostEqual(t.clips[0]['start'],7.); self.assertAlmostEqual(montage.length(t.clips[0]),16.)
            def change():
                from clip_properties import ClipProperties
                dialog=next(w for w in root.winfo_children() if isinstance(w,ClipProperties)); self.assertNotIn('source_in',dialog.variables); dialog.duration.set('30'); dialog.ok()
            root.after(20,change); t.open_properties(); self.assertAlmostEqual(montage.length(t.clips[0]),30.)
            path=self.folder/'project.json'
            with patch('app.filedialog.asksaveasfilename',return_value=str(path)):a.save()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['version'],9)
            with patch('app.filedialog.askopenfilename',return_value=str(path)):a.load()
            self.assertEqual(a.data['clips'][0]['kind'],'image'); self.assertEqual(montage.length(a.data['clips'][0]),30.)
        finally:
            root.destroy()
            for worker in (a.timeline_tools.worker,a.still_renderer.worker,a.live_audio.worker,a.media_work.worker):worker.join(10)


if __name__=='__main__':unittest.main()
