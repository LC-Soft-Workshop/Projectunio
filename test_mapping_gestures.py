import copy
import json
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import app
from unsaved_dialog import UnsavedDialog


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()

    def tearDown(self):
        self.root.destroy()
        for worker in (self.a.still_renderer.worker,self.a.live_audio.worker,self.a.timeline_tools.worker,self.a.media_work.worker):worker.join(5)

    def point(self,x,y):
        ox,oy,w,h=self.a.viewport(self.a.canvas); return SimpleNamespace(x=ox+x*w,y=oy+y*h)

    def test_draw_crosshair_resets_on_cancel_completion_and_mode_change(self):
        a=self.a; a.begin_zone(); self.assertEqual(a.canvas.cget('cursor'),'crosshair')
        a.cancel_zone(); self.assertEqual(a.canvas.cget('cursor'),'')
        a.begin_zone()
        for x,y in ((.1,.1),(.3,.1),(.3,.4),(.1,.4)):a.zone_click(self.point(x,y))
        self.assertEqual(a.edit_mode.get(),'mapping'); self.assertEqual(a.canvas.cget('cursor'),'')
        a.begin_zone(); a.edit_mode.set('video'); self.assertEqual(a.canvas.cget('cursor'),'')

    def test_corner_hold_clamps_to_border_and_returns_without_sticking(self):
        a=self.a; original=copy.deepcopy(a.data['zones']); x,y=original[0][0]; before=len(a.history)
        a.press(self.point(x,y)); a.drag(self.point(-.7,-.8))
        self.assertEqual(a.data['zones'][0][0],[0.,0.]); self.assertEqual(a.canvas.grab_current(),a.canvas)
        a.drag(self.point(.05,.05)); self.assertAlmostEqual(a.data['zones'][0][0][0],.05)
        a.mapping_release(); self.assertFalse(a.mapping_latched); self.assertIsNone(a.canvas.grab_current())
        self.assertEqual(len(a.history),before+1); a.undo(); self.assertEqual(a.data['zones'],original)

    def test_edge_hold_clamps_translation_and_keeps_valid_shape(self):
        a=self.a; q=copy.deepcopy(a.data['zones'][0]); x=(q[0][0]+q[1][0])/2; y=q[0][1]
        a.press(self.point(x,y)); self.assertEqual(a.edge,0)
        a.drag(self.point(x,-2.)); result=a.data['zones'][0]
        self.assertEqual(result[0][1],0.); self.assertEqual(result[1][1],0.); self.assertEqual(result[2:],q[2:]); self.assertTrue(app.valid(result))
        a.mapping_release(); self.assertIsNone(a.anchor)

    def test_click_follow_second_click_drop_and_escape(self):
        a=self.a; x,y=a.data['zones'][0][0]; a.press(self.point(x,y)); a.mapping_release()
        self.assertTrue(a.mapping_latched); a.mapping_motion(self.point(.04,.04)); self.assertAlmostEqual(a.data['zones'][0][0][0],.04)
        self.assertEqual(a.press(self.point(.06,.06)),'break'); self.assertFalse(a.mapping_latched); self.assertIsNone(a.anchor)
        a.mapping_release(); a.mapping_motion(self.point(.08,.08)); self.assertAlmostEqual(a.data['zones'][0][0][0],.06)
        a.press(self.point(.06,.06)); a.mapping_release(); a.cancel_zone(); self.assertFalse(a.mapping_latched); self.assertIsNone(a.canvas.grab_current())

    def test_native_drag_release_and_click_follow(self):
        a=self.a; p=self.point(*a.data['zones'][0][0]); target=self.point(-.2,-.3)
        a.canvas.event_generate('<ButtonPress-1>',x=int(p.x),y=int(p.y),time=1000)
        a.canvas.event_generate('<B1-Motion>',x=int(target.x),y=int(target.y),time=1100)
        a.canvas.event_generate('<ButtonRelease-1>',x=int(target.x),y=int(target.y),time=1200)
        self.root.update(); self.assertEqual(a.data['zones'][0][0],[0.,0.]); self.assertFalse(a.mapping_latched)
        p=self.point(0,0)
        a.canvas.event_generate('<ButtonPress-1>',x=int(p.x),y=int(p.y),time=2000)
        a.canvas.event_generate('<ButtonRelease-1>',x=int(p.x),y=int(p.y),time=2100)
        a.canvas.event_generate('<Motion>',x=int(p.x+10),y=int(p.y+10),time=2200)
        self.root.update(); self.assertTrue(a.mapping_latched); self.assertGreater(a.data['zones'][0][0][0],0.)

    def test_close_saves_only_dirty_tabs_and_reuses_existing_path(self):
        a=self.a
        with tempfile.TemporaryDirectory() as directory:
            first=Path(directory)/'one.json'; second=Path(directory)/'two.json'
            a.save(first); one=a.active_document
            a.new_document(); a.save(second); two=a.active_document
            with patch.object(a,'confirm_unsaved') as ask:self.assertTrue(a.save_open_documents()); ask.assert_not_called()
            a.tabs.select(one['tab']); a.change_document(); a.data['zones'][0][0][0]+=.01
            a.tabs.select(two['tab']); a.change_document()
            with patch.object(a,'confirm_unsaved',return_value=True) as ask,patch('app.filedialog.asksaveasfilename') as dialog:
                self.assertTrue(a.save_open_documents()); self.assertEqual(ask.call_args.args[0],[one]); dialog.assert_not_called()
            self.assertIs(a.active_document,two); self.assertEqual(json.loads(first.read_text(encoding='utf-8'))['zones'],one['data']['zones'])

    def test_close_cancel_discard_and_cancel_second_save_leave_all_tabs(self):
        a=self.a; a.name.set('Premier modifié'); a.new_document(); a.name.set('Second modifié'); current=a.active_document
        with patch.object(a,'confirm_unsaved',return_value=None),patch.object(a,'save') as save:
            self.assertFalse(a.save_open_documents()); save.assert_not_called()
        with patch.object(a,'confirm_unsaved',return_value=False),patch.object(a,'save') as save:
            self.assertTrue(a.save_open_documents()); save.assert_not_called()
        with patch.object(a,'confirm_unsaved',return_value=True),patch.object(a,'save',side_effect=[True,False]):
            self.assertFalse(a.save_open_documents())
        self.assertEqual(len(a.documents),2); self.assertIs(a.active_document,current)

    def test_fresh_and_new_empty_projects_close_without_save_prompt(self):
        a=self.a
        with patch.object(a,'confirm_unsaved') as ask:
            self.assertTrue(a.save_open_documents()); ask.assert_not_called()
            a.new_document(); self.root.update()
            self.assertTrue(a.save_open_documents()); ask.assert_not_called()
        with patch('studio.messagebox.askyesnocancel') as ask:
            self.assertTrue(a.close_document()); ask.assert_not_called()

    def test_loaded_unmodified_and_undone_changes_do_not_prompt(self):
        a=self.a
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'project.json'; a.save(path)
            with patch('app.filedialog.askopenfilename',return_value=str(path)):a.load()
            self.root.update()
            with patch.object(a,'confirm_unsaved') as ask:
                self.assertTrue(a.save_open_documents()); ask.assert_not_called()
                a.checkpoint(); a.data['zones'][0][0][0]+=.01; a.undo()
                self.assertTrue(a.save_open_documents()); ask.assert_not_called()
            with patch('studio.messagebox.askyesnocancel') as ask:
                self.assertTrue(a.close_document()); ask.assert_not_called()

    def test_only_modified_new_project_is_listed_and_save_clears_changes(self):
        a=self.a; empty=a.active_document; a.new_document(); changed=a.active_document; a.name.set('Modification réelle')
        with patch.object(a,'confirm_unsaved',return_value=None) as ask:
            self.assertFalse(a.save_open_documents()); self.assertEqual(ask.call_args.args[0],[changed]); self.assertNotIn(empty,ask.call_args.args[0])
        with tempfile.TemporaryDirectory() as directory:
            a.save(Path(directory)/'changed.json')
            with patch.object(a,'confirm_unsaved') as ask:self.assertTrue(a.save_open_documents()); ask.assert_not_called()

    def test_dialog_has_explicit_save_discard_cancel(self):
        observations=[]
        def inspect():
            from tkinter import ttk
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,UnsavedDialog))
            buttons=[child.cget('text') for row in dialog.winfo_children() for child in row.winfo_children() if isinstance(child,ttk.Button)]
            observations.extend(buttons); dialog.choose(False)
        self.root.after(20,inspect); result=UnsavedDialog(self.root,['Façade','Vitrine']).result
        self.assertIs(result,False); self.assertEqual(observations,['Enregistrer','Fermer sans enregistrer','Annuler'])


if __name__=='__main__':unittest.main()
