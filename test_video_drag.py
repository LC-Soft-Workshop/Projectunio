import copy
from pathlib import Path
import queue
import subprocess
import tempfile
import time
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
import app
from mapping_still import MappingStill


class SmoothVideoDragTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()
        self.clip=dict(id='video',path='unused.mp4',lane=0,start=0.,duration=2.,volume=1.,audio=False,fit='Remplir',pan_x=0.,pan_y=0.,zoom=1.,**{'in':0.,'out':2.})
        self.a.data['clips']=[self.clip]; self.a.playhead=.5; self.a.refresh()
        self.a.edit_mode.set('video'); self.frame=(2,2,b'\xff\x00\x00'*4)
        self.a.still_frame=self.frame; self.a.draw()

    def tearDown(self):
        self.root.destroy(); self.a.timeline_tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def point(self,u,v):
        ox,oy,w,h=self.a.viewport(self.a.canvas); p=app.project(self.a.data['zones'][0],u,v)
        return SimpleNamespace(x=ox+p[0]*w,y=oy+p[1]*h)

    def test_drag_uses_proxy_and_only_renders_once_after_release(self):
        original=copy.deepcopy(self.a.data); history=len(self.a.history)
        with patch.object(self.a.still_renderer,'request') as request,patch.object(self.a.timeline,'refresh',wraps=self.a.timeline.refresh) as refresh:
            with patch('app.resize_ppm',side_effect=AssertionError('Video resized during drag')):
                self.a.press(self.point(.5,.5)); self.assertIsNone(self.a._still_timer)
                self.assertTrue(self.a.canvas.find_withtag('video_proxy')); self.assertFalse(self.a.canvas.find_withtag('mapping_image'))
                first=self.a.canvas.coords(self.a.canvas.find_withtag('video_proxy_cross')[0])
                for i in range(1,101):self.a.drag(self.point(.5+i/400,.5))
                self.assertEqual(refresh.call_count,1)
                self.assertNotEqual(first,self.a.canvas.coords(self.a.canvas.find_withtag('video_proxy_cross')[0]))
                self.root.after(250,self.root.quit); self.root.mainloop()
                request.assert_not_called()
            self.assertAlmostEqual(self.a.data['clips'][0]['pan_x'],.25)
            self.assertEqual(self.a.data['zones'],original['zones']); self.assertEqual(len(self.a.history),history+1)
            self.a.finish_video_drag()
            self.assertIsNone(self.a.video_drag); self.assertTrue(self.a.canvas.find_withtag('video_proxy'))
            self.root.after(260,self.root.quit); self.root.mainloop()
            request.assert_called_once()
            self.assertAlmostEqual(request.call_args.args[0][0]['pan_x'],.25)
            self.a.receive_still(self.frame,None)
            self.assertIsNone(self.a.video_proxy); self.assertTrue(self.a.canvas.find_withtag('mapping_image'))
            self.a.undo(); self.assertEqual(self.a.data,original)

    def test_late_frame_ignored_and_switching_projects_clears_proxy(self):
        self.a.press(self.point(.5,.5)); self.a.drag(self.point(.7,.5))
        self.a.receive_still((2,2,b'\x00\xff\x00'*4),None)
        self.assertEqual(self.a.still_frame,self.frame)
        self.assertTrue(self.a.canvas.find_withtag('video_proxy'))
        self.a.new_document()
        self.assertIsNone(self.a.video_drag); self.assertIsNone(self.a.video_proxy)
        self.assertFalse(self.a.canvas.find_withtag('video_proxy'))

    def test_cancel_pending_invalidates_results_and_terminates_decoder(self):
        renderer=MappingStill.__new__(MappingStill); renderer.closed=False; renderer.generation=2; renderer.jobs=queue.Queue(); renderer.jobs.put('pending'); renderer.proc=Mock(); renderer.proc.poll.return_value=None
        renderer.cancel_pending(); self.assertEqual(renderer.generation,3); self.assertTrue(renderer.jobs.empty()); renderer.proc.terminate.assert_called_once()

    def test_real_video_is_recomputed_on_mouse_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'wide.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=640x180:d=1','-vf','drawbox=x=iw/2:y=0:w=iw/2:h=ih:color=blue:t=fill','-c:v','libx264',str(source)],capture_output=True,check=True,timeout=20)
            self.a.data['clips'][0]['path']=str(source); self.a.data['clips'][0]['duration']=1.; self.a.data['clips'][0]['out']=1.; self.a.refresh()
            def ready():
                deadline=time.monotonic()+15
                def poll():
                    if self.a.still_status.get().startswith('Image arrêtée') or time.monotonic()>deadline:self.root.quit()
                    else:self.root.after(20,poll)
                poll(); self.root.mainloop(); self.assertTrue(self.a.still_status.get().startswith('Image arrêtée'),self.a.still_status.get())
            ready(); before=self.a.still_frame
            with patch.object(self.a.still_renderer,'request',wraps=self.a.still_renderer.request) as request:
                self.a.press(self.point(.5,.5)); self.a.drag(self.point(.75,.5))
                request.assert_not_called()
                self.a.canvas.event_generate('<ButtonRelease-1>')
                self.assertIsNone(self.a.video_drag); ready(); request.assert_called_once()
            self.assertNotEqual(self.a.still_frame[2],before[2]); self.assertIsNone(self.a.video_proxy)
            self.assertTrue(self.a.canvas.find_withtag('mapping_image'))


if __name__=='__main__':unittest.main()
