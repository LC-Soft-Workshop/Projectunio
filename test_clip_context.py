import copy
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
import app
from clip_properties import ClipProperties


def video(identity,lane=0,start=0.):
    return dict(id=identity,path='unused.mp4',lane=lane,start=start,duration=4.,volume=1.,audio=False,fit='Remplir',**{'in':0.,'out':2.})


class ClipContextTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update(); self.t=self.a.timeline; self.tools=self.a.timeline_tools
        self.a.data['clips']=[video('first'),video('second',1,4.)]; self.t.selected='first'; self.tools.selection={'first'}; self.t.refresh()

    def tearDown(self):
        self.root.destroy(); self.tools.worker.join(5); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def point(self,c):
        return SimpleNamespace(x=85+(c['start']+.5)*self.t.pixels_per_second()-self.t.canvas.canvasx(0),y=28+self.t.row(c)*50+18-self.t.canvas.canvasy(0),x_root=100,y_root=100)

    def menu(self,c):
        with patch('timeline_tools.tk.Menu') as factory:
            self.tools.context_menu(self.point(c))
            return {call.kwargs['label']:call.kwargs for call in factory.return_value.add_command.call_args_list}

    def form(self,values,check=None):
        errors=[]
        def edit():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,ClipProperties))
            if check:check(dialog)
            for key,value in values.items():getattr(dialog,key).set(value)
            dialog.ok()
            if dialog.winfo_exists():errors.append(dialog.error.get()); dialog.cancel()
        self.root.after(10,edit); self.t.open_properties(); return errors

    def test_right_click_selects_only_target_and_keeps_cursor(self):
        self.a.playhead=1.; menu=self.menu(self.t.clips[1])
        self.assertEqual(self.tools.selected_ids(),{'second'}); self.assertEqual(self.a.playhead,1.)
        self.assertEqual(menu['Dupliquer']['accelerator'],'Ctrl+D'); self.assertEqual(menu['Supprimer']['accelerator'],'Suppr')
        with patch('timeline_ui.ClipProperties') as dialog:
            dialog.return_value.result=None; menu['Propriétés…']['command'](); context=dialog.call_args.args[1]
            self.t.edit_duration(self.point(self.t.clips[1])); double=dialog.call_args.args[1]
        self.assertEqual(context,double)

    def test_context_duplicate_and_keyboard_delete_use_the_same_group(self):
        self.a.data['clips'][1]['start']=0.; self.tools.selection={'first','second'}
        menu=self.menu(self.t.clips[1]); self.assertEqual(self.tools.selected_ids(),{'first','second'})
        menu['Dupliquer']['command'](); self.assertEqual(len(self.t.clips),4)
        self.assertEqual(sorted(c['start'] for c in self.t.clips),[0.,0.,2.,2.])
        self.t.canvas.focus_force(); self.root.update(); self.t.canvas.event_generate('<Control-d>')
        self.assertEqual(len(self.t.clips),6)
        self.t.canvas.event_generate('<Delete>'); self.assertEqual(len(self.t.clips),4)
        self.menu(self.t.clips[0])['Supprimer']['command'](); self.assertEqual(len(self.t.clips),3)

    def test_all_single_clip_parameters_live_in_properties(self):
        second=copy.deepcopy(self.t.clips[1])
        errors=self.form(dict(start='1',source_in='0,25',duration='1',volume='25',fade_in='0.2',fade_out='0.3',fit='Contenir',zoom='150',pan_x='10',pan_y='-15',track='2 — Zone 2'))
        self.assertFalse(errors,errors); c=self.t.clips[0]
        for key,value in dict(start=1.,volume=.25,fade_in=.2,fade_out=.3,fit='Contenir',zoom=1.5,pan_x=.1,pan_y=-.15,lane=1).items():self.assertEqual(c[key],value)
        self.assertEqual(c['in'],.25); self.assertEqual(c['out'],1.25); self.assertEqual(self.t.clips[1],second)
        self.a.undo(); self.assertEqual(self.t.clips[0],video('first'))

    def test_multi_mixed_properties_preserve_other_values_and_apply_image_only_to_video(self):
        sound=dict(id='sound',kind='audio',path='unused.wav',lane=0,start=3.,duration=4.,volume=.5,**{'in':1.,'out':2.})
        self.a.data['audio_clips']=[sound]; self.tools.selection={'first','sound'}
        def check(dialog):self.assertEqual(dialog.duration.get(),''); self.assertEqual(dialog.volume.get(),'')
        before=len(self.a.history)
        errors=self.form(dict(volume='25',fade_in='0.1',start='2',zoom='140'),check)
        self.assertFalse(errors,errors); self.assertEqual([self.t.clips[0]['start'],self.t.audio_clips[0]['start']],[2.,5.])
        self.assertEqual([self.t.clips[0]['out'],self.t.audio_clips[0]['out']],[2.,2.])
        self.assertEqual(self.t.audio_clips[0]['volume'],.25); self.assertEqual(self.t.clips[0]['volume'],.25)
        self.assertEqual(self.t.clips[0]['zoom'],1.4); self.assertNotIn('zoom',self.t.audio_clips[0]); self.assertEqual(len(self.a.history),before+1)

    def test_invalid_batch_properties_are_atomic(self):
        self.tools.selection={'first','second'}; original=copy.deepcopy(self.a.data); count=len(self.a.history)
        errors=self.form(dict(duration='10',volume='0'))
        self.assertTrue(errors); self.assertEqual(self.a.data,original); self.assertEqual(len(self.a.history),count)

    def test_clip_buttons_are_removed_from_permanent_timeline_panels(self):
        def buttons(widget):
            return [str(c.cget('text')) for c in widget.winfo_children() if isinstance(c,ttk.Button)]+[name for c in widget.winfo_children() for name in buttons(c)]
        visible=buttons(self.t.frame)
        for label in ('Dupliquer','Supprimer','Copier','Coller','Couper','Fondus…','Appliquer au clip','+ Zoom','− Zoom'):self.assertNotIn(label,visible)


if __name__=='__main__':unittest.main()
