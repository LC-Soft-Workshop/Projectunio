import copy
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
import app
from studio import validate_extras


class EditorControlsTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()
        self.a.data['clips']=[dict(id='one',lane=0,path='unused.mp4',start=0.,duration=5.,volume=1.,audio=False,fit='Remplir',**{'in':0.,'out':5.})]
        self.a.timeline.selected='one'; self.a.timeline_tools.selection={'one'}; self.a.refresh()

    def tearDown(self):
        self.root.destroy(); self.a.timeline_tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def lock(self,key,value=True):
        self.a.lock_vars[key].set(value); self.a.toggle_editor_lock(key)

    def test_grid_toggle_without_video_and_with_video(self):
        for frame in (None,(2,2,b'\xff\x00\x00'*4)):
            self.a.still_frame=frame; self.a.still_images.clear()
            for value in (False,True,False):
                self.a.mapping_grid.set(value); self.a.draw()
                self.assertEqual(bool(self.a.canvas.find_withtag('mapping_grid')),value)

    def test_corner_dialog_targets_any_zone_and_saves_both_percentages(self):
        before=copy.deepcopy(self.a.data); lane=1; corner=2
        ox,oy,w,h=self.a.viewport(self.a.canvas); x,y=self.a.data['zones'][lane][corner]
        def accept():
            dialog=next(c for c in self.root.winfo_children() if isinstance(c,tk.Toplevel))
            entries=[c for c in dialog.winfo_children() if isinstance(c,ttk.Entry)]
            for entry,value in zip(entries,('93','87')):entry.delete(0,'end'); entry.insert(0,value)
            next(c for c in dialog.winfo_children() if isinstance(c,ttk.Button) and c.cget('text')=='Valider').invoke()
        self.root.after(50,accept)
        with patch.object(self.a.timeline,'open_properties') as video:
            self.a.open_canvas_video_properties(SimpleNamespace(x=ox+x*w,y=oy+y*h)); video.assert_not_called()
        self.assertEqual(self.a.data['zones'][1][2],[.93,.87]); self.assertEqual(self.a.data['zones'][0],before['zones'][0])
        self.a.undo(); self.assertEqual(self.a.data,before)

    def test_mapping_lock_and_timeline_lock_are_independent(self):
        self.lock('mapping'); before=copy.deepcopy(self.a.data)
        self.a.x.set('10'); self.a.y.set('15'); self.a.numeric()
        self.a.add_zone(copy.deepcopy(self.a.data['zones'][0])); self.a.timeline.edit_zone_name(0)
        self.assertEqual(self.a.data,before); self.assertIsNone(self.a.timeline.name_editor)
        self.a.timeline_tools.remove(); self.assertEqual(self.a.data['clips'],[])
        self.a.undo(); self.assertEqual(self.a.data['clips'],[]) # undo cannot bypass a lock
        self.lock('mapping',False); self.lock('timeline')
        before=copy.deepcopy(self.a.data)
        self.a.timeline.add_audio_track(); self.a.timeline_tools.remove(); self.a.timeline_tools.paste()
        self.assertEqual(self.a.data,before)
        self.a.x.set('10'); self.a.y.set('15'); self.a.numeric()
        self.assertEqual(self.a.data['zones'][0][0],[.1,.15])
        self.a.set_playhead(0.)

    def test_global_lock_is_saved_per_project_and_new_project_is_unlocked(self):
        self.lock('project'); first=self.a.active_document
        self.a.timeline_tools.remove(); self.a.delete_timeline_track(0)
        self.assertEqual(len(self.a.data['zones']),2); self.assertEqual(len(self.a.data['clips']),1)
        validate_extras(self.a.data)
        self.assertEqual(str(self.a.name_entry.cget('state')),'disabled')
        self.a.new_document(); self.root.update()
        self.assertFalse(self.a.edit_locked('mapping')); self.assertFalse(self.a.lock_vars['project'].get())
        self.a.tabs.select(first['tab']); self.root.update()
        self.assertTrue(self.a.lock_vars['project'].get()); self.assertTrue(self.a.edit_locked('timeline'))
        self.lock('project',False); self.assertFalse(self.a.edit_locked('timeline'))
