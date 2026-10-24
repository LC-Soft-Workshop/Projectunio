import copy
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
import app


class DeferredJob:
    def __init__(self,*args,**kw):
        self.events=args[0]; self.zones=args[2]; self.clips=args[3]; self.audio_clips=args[4]; self.signature=args[5]
        self.preview=kw.get('preview',False); self.mire=kw.get('mire',False)
        self.cancelled=threading.Event(); self.thread=Mock(); self.proc=None
        self.force_stall=False
    def cancel(self):self.cancelled.set()
    def stalled(self):return self.force_stall


class Owner:
    def __init__(self):self.cleaned=False
    def cleanup(self):self.cleaned=True


class FakePreview:
    def __init__(self,parent,movie,zones,executable,project,cleanup):
        self.win=tk.Toplevel(parent); self.closed=False; self.cleanup=cleanup
        self.audio_status=tk.Label(self.win)
    def close(self):
        if self.closed:return
        self.closed=True; self.win.destroy(); self.cleanup()


def audio(path='unused.wav',end=1):
    return dict(id='a',kind='audio',path=str(path),lane=0,start=0.,**{'in':0.,'out':float(end)},duration=float(end),volume=1.)


def pump(a):
    a.root.after_cancel(a.render_timer); a.poll_render()


def wait_for(root,predicate,seconds=12):
    limit=time.monotonic()+seconds
    def tick():
        if predicate() or time.monotonic()>limit:root.quit()
        else:root.after(30,tick)
    root.after(30,tick); root.mainloop()
    if not predicate():raise AssertionError('Render state timed out')


class RenderStateTests(unittest.TestCase):
    def test_cancel_before_encoding_does_not_publish_or_open(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'video.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=160x240:d=1','-c:v','libx264',str(source)],capture_output=True,check=True,timeout=20)
            root=tk.Tk(); a=app.App(root); root.update()
            a.data['clips']=[dict(id='v',path=str(source),lane=0,start=0.,**{'in':0.,'out':1.},duration=1.,audio=False,volume=1.,fit='Remplir')]
            entered=threading.Event(); release=threading.Event(); original=app.mask
            def blocked_mask(*args):entered.set(); release.wait(5); return original(*args)
            job=None
            try:
                with patch('app.mask',blocked_mask):
                    a.export(preview=True); job=a.active_render
                    self.assertTrue(entered.wait(3))
                    a.data['clips'][0]['pan_x']=.2; a.refresh()
                    self.assertIsNone(a.active_render)
                    self.assertFalse(a.preview_button.instate(['disabled']))
                    release.set(); job.thread.join(8); self.assertFalse(job.thread.is_alive())
                    pump(a); self.assertFalse(a.previews); self.assertTrue(job.cancelled.is_set())
                    self.assertIsNone(job.proc)
            finally:
                release.set()
                if job:job.cancel(); job.thread.join(8)
                root.destroy(); a.still_renderer.worker.join(5); a.live_audio.worker.join(5)

    def test_busy_invalidation_late_result_and_failure(self):
        root=tk.Tk(); a=app.App(root); root.update(); a.data['audio_clips']=[audio()]
        try:
            with patch('app.RenderJob',side_effect=DeferredJob) as factory:
                a.toggle_preview(); first=a.active_render
                self.assertTrue(a.preview_button.instate(['disabled']))
                self.assertIn('Préparation',a.preview_button.cget('text'))
                a.preview_button.invoke(); a.export(preview=True)
                self.assertEqual(factory.call_count,1)
                a.set_playhead(.4); a.timeline.selected='a'; a.timeline.refresh()
                self.assertIs(a.active_render,first) # Selection/playhead are not render changes.
                a.data['audio_clips'][0]['start']=.2; a.timeline.refresh()
                self.assertTrue(first.cancelled.is_set()); self.assertIsNone(a.active_render)
                self.assertFalse(a.preview_button.instate(['disabled']))
                a.toggle_preview(); second=a.active_render; stale=Owner()
                a.render_events.put((first,'ready',(Path('not-opened.mp4'),stale))); pump(a)
                self.assertTrue(stale.cleaned); self.assertIs(a.active_render,second)
                self.assertTrue(a.preview_button.instate(['disabled'])); self.assertFalse(a.previews)
                # A volume change also invalidates an in-flight render snapshot.
                a.data['audio_clips'][0]['volume']=.25; a.timeline.refresh()
                self.assertTrue(second.cancelled.is_set()); self.assertIsNone(a.active_render)
                a.toggle_preview(); third=a.active_render
                with patch('app.messagebox.showerror') as error:
                    a.render_events.put((third,'error','Encoder test error')); pump(a)
                    error.assert_called_once()
                self.assertIsNone(a.active_render); self.assertFalse(a.busy)
                self.assertFalse(a.preview_button.instate(['disabled']))
                a.toggle_preview(); stuck=a.active_render; stuck.force_stall=True; pump(a)
                self.assertFalse(stuck.cancelled.is_set()); self.assertIs(a.active_render,stuck)
                self.assertTrue(a.preview_button.instate(['disabled']))
                a.cancel(); self.assertFalse(a.preview_button.instate(['disabled']))
        finally:root.destroy(); a.still_renderer.worker.join(5); a.live_audio.worker.join(5)

    def test_one_window_toggle_manual_close_and_edit(self):
        root=tk.Tk(); a=app.App(root); root.update(); a.data['audio_clips']=[audio()]
        a.live_audio.request=Mock()
        try:
            with patch('app.VideoPreview',FakePreview):
                owner=Owner(); a.show_preview(Path('unused.mp4'),a.data['zones'],owner.cleanup,[],copy.deepcopy(a.data['audio_clips']))
                self.assertEqual(a.preview_button.cget('text'),'Fermer l’aperçu')
                a.preview_button.invoke()
                self.assertTrue(owner.cleaned); self.assertFalse(a.previews)
                self.assertEqual(a.preview_button.cget('text'),'Aperçu du montage')
                a.show_preview(Path('unused.mp4'),a.data['zones'],lambda:None,[],copy.deepcopy(a.data['audio_clips']))
                player=a.previews[0][0]; player.close()
                self.assertEqual(a.preview_button.cget('text'),'Aperçu du montage')
                a.show_preview(Path('unused.mp4'),a.data['zones'],lambda:None,[],copy.deepcopy(a.data['audio_clips']))
                player=a.previews[0][0]
                a.data['audio_clips'][0]['volume']=.25; a.timeline.refresh()
                self.assertFalse(player.closed) # Applied live without invalidating the video.
                a.data['zones'][0][0]=[.1,.12]; a.refresh()
                self.assertTrue(player.closed); self.assertFalse(a.preview_button.instate(['disabled']))
        finally:root.destroy(); a.still_renderer.worker.join(5); a.live_audio.worker.join(5)

    def test_actual_render_opens_then_button_closes_and_cleans(self):
        with tempfile.TemporaryDirectory() as temp:
            sound=Path(temp)/'tone.wav'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','sine=duration=0.5',str(sound)],capture_output=True,check=True,timeout=20)
            root=tk.Tk(); a=app.App(root); root.update(); a.data['audio_clips']=[audio(sound,.5)]
            player=None
            try:
                a.toggle_preview(); wait_for(root,lambda:bool(a.previews))
                self.assertIsNone(a.active_render); self.assertFalse(a.busy)
                player=a.previews[0][0]; folder=player.movie.parent
                self.assertEqual(a.preview_button.cget('text'),'Fermer l’aperçu')
                a.preview_button.invoke()
                self.assertTrue(player.closed); self.assertFalse(a.previews)
                wait_for(root,lambda:not folder.exists())
                self.assertEqual(a.preview_button.cget('text'),'Aperçu du montage')
            finally:
                if player:player.close(); player.worker.join(5)
                root.destroy(); a.still_renderer.worker.join(5); a.live_audio.worker.join(5)

if __name__=='__main__':unittest.main()
