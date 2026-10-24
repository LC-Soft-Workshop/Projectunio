import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import app


class ZoneNameTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update(); self.t=self.a.timeline

    def tearDown(self):
        self.t.finish_name_edit(False); self.root.destroy()
        self.a.timeline_tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def test_new_zones_have_numbered_defaults_without_name_dialog(self):
        self.assertEqual(self.a.zone_names(),['Zone 1','Zone 2'])
        with patch('studio.simpledialog.askstring',side_effect=AssertionError('Unexpected name prompt')):
            self.a.add_zone([[.1,.1],[.3,.1],[.3,.3],[.1,.3]])
            self.assertEqual(self.t.zone_names(),['Zone 1','Zone 2','Zone 3'])
            self.a.rename_zone(); self.assertIsNotNone(self.t.name_editor)
        self.t.finish_name_edit(False)

    def test_double_click_header_edits_inline_without_seeking(self):
        self.a.data['audio_clips']=[dict(id='sound',kind='audio',path='unused.wav',lane=0,start=0.,duration=10.,volume=1.,**{'in':0.,'out':10.})]
        self.a.playhead=5.; self.t.refresh(); before=len(self.a.history)
        with patch('timeline_ui.ClipProperties',side_effect=AssertionError('Clip dialog on header')):
            self.t.canvas.event_generate('<ButtonPress-1>',x=20,y=46,time=1000)
            self.t.canvas.event_generate('<ButtonRelease-1>',x=20,y=46,time=1010)
            self.t.canvas.event_generate('<ButtonPress-1>',x=20,y=46,time=1100)
            self.t.canvas.event_generate('<ButtonRelease-1>',x=20,y=46,time=1110)
            self.root.update()
            self.assertIsNotNone(self.t.name_editor)
            self.t.name_edit_value.set('Fenêtre cuisine'); self.t.draw()
            self.assertTrue(self.t.name_editor.winfo_ismapped())
            self.t.name_editor.focus_force(); self.root.update()
            self.t.name_editor.event_generate('<Return>')
        self.assertEqual(self.a.zone_names()[0],'Fenêtre cuisine')
        self.assertEqual(len(self.a.history),before+1)
        self.assertEqual(self.a.playhead,5.)
        self.assertIn('Fenêtre cuisine',self.a.zone_selector.cget('values'))
        self.a.undo(); self.assertEqual(self.a.zone_names()[0],'Zone 1')

    def test_cancel_empty_name_and_focus_out(self):
        self.t.edit_zone_name(1); self.root.update(); self.t.name_editor.focus_force(); self.root.update(); self.t.name_edit_value.set('Annuler ceci')
        self.t.name_editor.event_generate('<Escape>'); self.assertIsNone(self.t.name_editor); self.assertEqual(self.a.zone_names()[1],'Zone 2')
        self.t.edit_zone_name(1); self.t.name_edit_value.set('   '); self.t.finish_name_edit()
        self.assertEqual(self.a.zone_names()[1],'Zone 2')
        self.t.edit_zone_name(1); self.root.update(); self.t.name_editor.focus_force(); self.root.update(); self.t.name_edit_value.set('Porte')
        self.t.canvas.focus_set(); self.root.update(); self.assertEqual(self.a.zone_names()[1],'Porte')

    def test_inline_name_is_saved_and_preserved_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'project.json'; self.t.edit_zone_name(0); self.t.name_edit_value.set('Mur principal')
            with patch('app.filedialog.asksaveasfilename',return_value=str(path)):self.a.save()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['zone_names'][0],'Mur principal')
            with patch('app.filedialog.askopenfilename',return_value=str(path)):self.a.load()
            self.assertEqual(self.a.zone_names(),['Mur principal','Zone 2'])

    def test_scrolled_header_and_project_switch_edit_correct_project(self):
        first=self.a.active_document
        for i in range(4):self.a.add_zone([[.1,.1],[.3,.1],[.3,.3],[.1,.3]])
        self.a.zone=4; self.a.rename_zone(); self.root.update()
        self.assertEqual(self.t.name_edit_lane,4)
        self.t.name_edit_value.set('Étage'); self.a.new_document()
        self.assertEqual(self.a.zone_names(),['Zone 1','Zone 2'])
        self.a.tabs.select(first['tab']); self.a.change_document()
        self.assertEqual(self.a.zone_names()[4],'Étage')


if __name__=='__main__':unittest.main()
