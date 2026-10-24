import copy
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import app
import montage
from export_settings import RESOLUTIONS,valid_resolution
from render_job import RenderJob
from test_render_state import DeferredJob,audio


class ExportResolutionUITests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()

    def tearDown(self):
        self.root.destroy(); self.a.timeline_tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def choose(self,index):
        self.a.export_resolution.set(list(RESOLUTIONS)[index]); self.a.choose_resolution()

    def test_selector_updates_export_mire_and_preview_keeps_bounded_resolution(self):
        self.a.data['audio_clips']=[audio()]; self.choose(2)
        self.root.geometry('1080x780'); self.root.update(); self.assertTrue(self.a.resolution_selector.winfo_ismapped())
        with patch('app.RenderJob',DeferredJob),patch('app.filedialog.asksaveasfilename',return_value='unused.mp4'):
            self.a.export(); export=self.a.active_render
            self.choose(1); self.assertTrue(export.cancelled.is_set()); self.assertIsNone(self.a.active_render)
        with patch('app.RenderJob') as factory,patch('app.filedialog.asksaveasfilename',return_value='unused.mp4'):
            factory.return_value.preview=False; self.a.export(mire=True)
            self.assertEqual(factory.call_args.kwargs['resolution'],(1920,1080)); self.a.cancel()
        with patch('app.RenderJob',DeferredJob):
            self.a.export(preview=True); preview=self.a.active_render
            self.choose(2); self.assertIs(self.a.active_render,preview); self.assertFalse(preview.cancelled.is_set()); self.a.cancel()
        with patch('app.RenderJob') as factory:
            factory.return_value.preview=True; self.a.export(preview=True)
            self.assertEqual(factory.call_args.kwargs['resolution'],(1280,720)); self.a.cancel()

    def test_resolution_persists_per_project_undo_and_recovery(self):
        mapping=copy.deepcopy(self.a.data['zones']); self.choose(2)
        self.assertEqual(self.a.data['resolution'],[3840,2160]); self.assertEqual(self.a.data['zones'],mapping)
        self.a.undo(); self.assertEqual(self.a.data['resolution'],[1280,720]); self.a.restore()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'4k.json'
            with patch('app.filedialog.asksaveasfilename',return_value=str(path)):self.a.save()
            self.a.new_document(); self.assertEqual(self.a.data['resolution'],[1280,720])
            with patch('app.filedialog.askopenfilename',return_value=str(path)):self.a.load()
            self.assertEqual(self.a.data['resolution'],[3840,2160]); self.assertIn('4K',self.a.export_resolution.get())
            self.a.recovery_path=Path(tmp)/'session.json'; self.a.write_recovery()
            with patch('studio.filedialog.askopenfilename',return_value=str(self.a.recovery_path)):self.a.recover_session()
            self.assertEqual(self.a.data['resolution'],[3840,2160])
        self.assertFalse(valid_resolution([4096,2160])); self.assertFalse(valid_resolution([1280.,720.]))


class ExportResolutionRenderTests(unittest.TestCase):
    def test_real_mapped_exports_have_requested_dimensions_and_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); source=folder/'red.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=64x64:r=30:d=0.1','-c:v','libx264',str(source)],check=True,capture_output=True,timeout=20)
            clip=dict(id='clip',path=str(source),lane=0,start=0.,duration=.1,volume=1.,audio=False,fit='Remplir',**{'in':0.,'out':2/30})
            zones=[[[0.,0.],[1.,0.],[1.,1.],[0.,1.]]]
            # The mask of this exact full-frame quadrilateral is uniformly white.
            def full_mask(path,q,w,h):Path(path).write_bytes(f'P5\n{w} {h}\n255\n'.encode()+b'\xff'*(w*h))
            def options(preview):return app.output_options(preview)+['-threads','2']
            for width,height in RESOLUTIONS.values():
                with self.subTest(resolution=(width,height)):
                    events=queue.SimpleQueue(); destination=folder/f'{height}p.mp4'
                    job=RenderJob(events,app.ffmpeg(),zones,[clip],[],'test',full_mask,app.graph,app.write_mire,options,destination=destination,resolution=(width,height),log_directory=folder)
                    job.thread.start(); job.thread.join(50)
                    if job.thread.is_alive():job.cancel(); job.thread.join(5); self.fail('Export timed out')
                    messages=[]
                    while not events.empty():messages.append(events.get())
                    self.assertTrue(any(kind=='complete' for _,kind,_ in messages),messages)
                    streams=montage.media_info(destination,app.ffmpeg())['streams']; video=next(s for s in streams if s['codec_type']=='video')
                    self.assertEqual((video['width'],video['height']),(width,height)); self.assertEqual(int(video['nb_frames']),2)
                    pixel=subprocess.run([app.ffmpeg(),'-v','error','-i',str(destination),'-vf','crop=2:2','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,capture_output=True,timeout=20).stdout
                    self.assertGreater(pixel[0],200); self.assertLess(pixel[2],30)


if __name__=='__main__':unittest.main()
