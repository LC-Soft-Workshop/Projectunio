import copy
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import app


class CanvasPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()
        self.a.data['clips']=[dict(id=str(i),lane=0,path='unused.mp4',start=i*2.,duration=2.,audio=False,volume=1.,fit='Remplir',**{'in':0.,'out':2.}) for i in range(2)]
        self.a.refresh()

    def tearDown(self):
        self.root.destroy(); self.a.timeline_tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def point(self,lane=0):
        ox,oy,w,h=self.a.viewport(self.a.canvas); p=app.project(self.a.data['zones'][lane],.5,.5)
        return SimpleNamespace(x=round(ox+p[0]*w),y=round(oy+p[1]*h))

    def test_current_video_at_cut_and_single_selection_properties(self):
        before=copy.deepcopy(self.a.data)
        for at,identity in [(0.,'0'),(1.99,'0'),(2.,'1'),(3.,'1')]:
            self.a.playhead=at; self.a.timeline_tools.selection={'0','1'}
            with patch('timeline_ui.ClipProperties') as dialog:
                dialog.return_value.result=None
                self.a.open_canvas_video_properties(self.point())
                self.assertEqual(dialog.call_args.args[1]['id'],identity)
            self.assertEqual(self.a.timeline_tools.selected_ids(),{identity})
            self.assertEqual(self.a.playhead,at)
        self.assertEqual(self.a.data,before)

    def test_empty_zone_gap_end_and_background_do_not_open(self):
        with patch.object(self.a.timeline,'open_properties') as properties:
            self.a.playhead=4.; self.a.open_canvas_video_properties(self.point())
            self.a.playhead=1.; self.a.open_canvas_video_properties(self.point(1))
            self.a.open_canvas_video_properties(SimpleNamespace(x=0,y=0))
            properties.assert_not_called()

    def test_native_double_click_in_mapping_and_video_modes(self):
        p=self.point(); self.a.playhead=2.5
        for index,mode in enumerate(('mapping','video')):
            self.a.edit_mode.set(mode)
            with patch.object(self.a.timeline,'open_properties',return_value='break') as properties:
                for name,time in [('<ButtonPress-1>',1000),('<ButtonRelease-1>',1010),('<ButtonPress-1>',1100),('<ButtonRelease-1>',1110)]:
                    self.a.canvas.event_generate(name,x=p.x,y=p.y,time=time+index*5000)
                self.root.update(); properties.assert_called_once()
                self.assertEqual(self.a.timeline.selected,'1'); self.assertIsNone(self.a.anchor)
