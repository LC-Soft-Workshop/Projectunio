import copy
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import app
import montage


class TimelineDropTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update(); self.t=self.a.timeline; self.t.magnetic.set(False)

    def tearDown(self):
        self.root.destroy(); self.a.timeline_tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def point(self,row,at):
        return 85+at*self.t.pixels_per_second()-self.t.canvas.canvasx(0),28+row*50+18-self.t.canvas.canvasy(0)

    def test_video_left_right_and_audio_land_on_their_tracks_at_drop_time(self):
        for lane in (0,1):
            with patch('montage.probe',return_value=(3.,False)):self.t.drop_files([f'{lane}.mp4'],*self.point(lane,4.))
        with patch('montage.probe_audio',return_value=5.):self.t.drop_files(['sound.wav'],*self.point(2,7.))
        self.assertEqual([(c['lane'],c['start']) for c in self.t.clips],[(0,4.),(1,4.)])
        self.assertEqual(self.t.audio_clips[0]['lane'],0); self.assertEqual(self.t.audio_clips[0]['start'],7.)
        self.assertFalse(hasattr(self.t,'cards')); self.assertEqual(len(self.t.hooks),1)
        self.a.undo(); self.assertEqual(self.t.audio_clips,[])

    def test_batch_uses_next_free_gap_without_overwriting(self):
        with patch('montage.probe',return_value=(5.,False)):self.t.import_files(0,['existing.mp4'])
        original=copy.deepcopy(self.t.clips[0]); before=len(self.a.history)
        with patch('montage.probe',return_value=(3.,False)):self.t.drop_files(['a.mp4','b.mp4'],*self.point(0,2.))
        self.assertEqual(self.t.clips[0],original); self.assertEqual([c['start'] for c in self.t.clips],[0.,5.,8.])
        self.assertEqual(len(self.a.history),before+1); montage.validate(self.t.clips)
        self.a.undo(); self.assertEqual(self.t.clips,[original])

    def test_scrolled_timeline_routes_to_new_zone_and_third_audio_track(self):
        self.a.data['zones']+=copy.deepcopy(self.a.data['zones'])*2; self.a.data['audio_track_count']=4
        self.t.scale.set('40'); self.t.refresh()
        with patch('montage.probe',return_value=(300.,False)):self.t.import_files(0,['long.mp4'])
        self.root.update(); self.t.canvas.xview_moveto(.4); self.t.canvas.yview_moveto(.55); self.root.update()
        at=(self.t.canvas.canvasx(100)-85)/40; row=self.t.zone_count+2
        with patch('montage.probe_audio',return_value=2.):self.t.drop_files(['third.wav'],*self.point(row,at))
        self.assertEqual(self.t.audio_clips[0]['lane'],2); self.assertAlmostEqual(self.t.audio_clips[0]['start'],at,delta=1/40)
        self.t.canvas.yview_moveto(.2); self.root.update()
        with patch('montage.probe',return_value=(2.,False)):self.t.drop_files(['zone.mp4'],*self.point(4,at))
        self.assertEqual(self.t.clips[-1]['lane'],4)

    def test_ruler_or_invalid_media_does_not_change_project(self):
        old=copy.deepcopy(self.a.data)
        self.t.drop_files(['bad.wav'],200,10); self.assertEqual(self.a.data,old)
        with patch('montage.probe',side_effect=ValueError('Ce fichier ne contient pas de vidéo.')),patch('timeline_ui.messagebox.showerror') as error:
            self.t.drop_files(['audio.wav'],*self.point(0,0.)); error.assert_called_once()
        self.assertEqual(self.a.data,old)

    def test_right_click_import_targets_track_and_marker_menu_still_works(self):
        self.t.magnetic.set(True); self.a.data['markers']=[dict(time=3.,name='Top')]
        x,y=self.point(1,3.1)
        self.assertAlmostEqual(self.t.drop_target(x,y)[1],3.)
        with patch('timeline_ui.tk.Menu') as menu:
            self.t.track_menu(SimpleNamespace(x=x,y=y,x_root=100,y_root=100))
            action=menu.return_value.add_command.call_args.kwargs['command']
            with patch('timeline_ui.filedialog.askopenfilenames',return_value=['choice.mp4']),patch('montage.probe',return_value=(1.,False)):action()
        self.assertEqual(self.t.clips[0]['lane'],1); self.assertEqual(self.t.clips[0]['start'],3.)


if __name__=='__main__':unittest.main()
