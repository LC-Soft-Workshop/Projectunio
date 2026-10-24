from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import app
import montage


class TimelineZoomTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update(); self.t=self.a.timeline

    def tearDown(self):
        self.root.destroy(); self.a.timeline_tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def assert_end_visible(self):
        end=85+montage.duration(self.t.items)*self.t.pixels_per_second()
        self.assertLessEqual(end,self.t.canvas.winfo_width()-23)
        self.assertAlmostEqual(self.t.canvas.canvasx(0),0.,delta=1.)

    def test_audio_five_minutes_import_fits_and_end_can_be_trimmed(self):
        with patch('montage.probe',return_value=(10.,False)):self.t.import_files(0,['short.mp4'])
        with patch('montage.probe_audio',return_value=300.):self.t.import_audio(['long.wav'])
        self.root.update(); self.assertEqual(self.t.scale.get(),'Auto'); self.assert_end_visible()
        audio=self.t.audio_clips[0]; px=self.t.pixels_per_second(); right=85+300*px; y=28+self.t.row(audio)*50+18
        self.t.press(SimpleNamespace(x=right-1,y=y)); self.assertEqual(self.t.dragging[2],'out')
        self.t.motion(SimpleNamespace(x=right-1-30*px,y=y)); self.t.release(None)
        self.assertAlmostEqual(montage.length(self.t.audio_clips[0]),270.,delta=1/px)
        self.assertEqual(self.t.audio_clips[0]['start'],0.); self.assert_end_visible()

    def test_longest_video_or_late_clip_controls_fit_and_resize(self):
        with patch('montage.probe_audio',return_value=30.):self.t.import_audio(['short.wav'])
        with patch('montage.probe',return_value=(900.,False)):self.t.import_files(1,['long.mp4'])
        self.root.update(); self.assert_end_visible(); self.assertLess(self.t.pixels_per_second(),2.)
        clip=dict(self.t.clips[0],start=150.); self.t.commit(clip); self.assert_end_visible()
        self.root.geometry('1080x780'); self.root.update(); self.assert_end_visible()

    def test_manual_zoom_and_independent_tab_preferences(self):
        with patch('montage.probe_audio',return_value=300.):self.t.import_audio(['long.wav'])
        self.root.update(); first=self.a.active_document; self.t.scale.set('20'); self.t.draw()
        self.assertEqual(self.t.pixels_per_second(),20.); self.assertGreater(float(self.t.canvas.cget('scrollregion').split()[2]),self.t.canvas.winfo_width())
        self.a.new_document(); self.root.update(); self.assertEqual(self.t.scale.get(),'Auto')
        self.a.tabs.select(first['tab']); self.a.change_document(); self.assertEqual(self.t.scale.get(),'20')
        self.t.canvas.xview_moveto(.5); self.t.scale.set('Auto'); self.root.update(); self.assert_end_visible()


if __name__=='__main__':unittest.main()
