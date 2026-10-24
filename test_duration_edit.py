import copy
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import app
import montage
from clip_properties import ClipProperties


def edit_clip(t,answers):
    c=next((c for c in t.items if c['id']==t.selected),t.items[0])
    event=SimpleNamespace(x=85+(c['start']+min(1.,montage.length(c)/2))*t.pixels_per_second(),y=28+t.row(c)*50+18)
    steps=iter(answers); calls=SimpleNamespace(call_count=0); errors=SimpleNamespace(call_count=0)
    def fill():
        dialogs=[w for w in t.app.root.winfo_children() if isinstance(w,ClipProperties)]
        if not dialogs:t.app.root.after(5,fill); return
        dialog=dialogs[0]; answer=next(steps); calls.call_count+=1
        if answer is None:dialog.cancel(); return
        values=answer if isinstance(answer,dict) else {'duration':answer}
        for key,value in values.items():getattr(dialog,key).set(value)
        dialog.ok()
        if dialog.winfo_exists():errors.call_count+=1; t.app.root.after(5,fill)
    t.app.root.after(5,fill)
    assert t.edit_duration(event)=='break'
    return calls,errors


class DurationEditTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.t=self.a.timeline

    def tearDown(self):
        self.root.destroy()
        self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5)

    def clip(self,audio=False):
        c=dict(id='clip',path='example.wav' if audio else 'example.mp4',lane=0,start=3.,duration=30.,volume=1.,**{'in':2.,'out':22.})
        if audio:c['kind']='audio'
        else:c.update(audio=False,fit='Remplir')
        self.a.data['audio_clips' if audio else 'clips']=[c]
        self.t.refresh()
        return c

    def edit(self,answers):return edit_clip(self.t,answers)

    def test_audio_and_video_duration_preserve_start_and_source_in_and_undo(self):
        for audio in (False,True):
            with self.subTest(audio=audio):
                self.a.data['clips']=[]; self.a.data['audio_clips']=[]
                original=copy.deepcopy(self.clip(audio))
                self.t.dragging=(original,1,'move'); self.t.proposal=original; self.t.scrubbing=True
                self.edit(['10,0'])
                changed=self.t.items[0]
                self.assertEqual(changed['start'],3.)
                self.assertEqual(changed['in'],2.)
                self.assertEqual(montage.length(changed),10.)
                self.assertIsNone(self.t.dragging); self.assertFalse(self.t.scrubbing)
                self.assertFalse(hasattr(self.t,'proposal'))
                self.a.undo(); self.assertEqual(self.t.items[0],original)

    def test_invalid_duration_and_cancel_leave_clip_unchanged(self):
        original=copy.deepcopy(self.clip(True))
        dialog,error=self.edit(['0','nan','29','texte',None])
        self.assertEqual(error.call_count,4); self.assertEqual(dialog.call_count,5)
        self.assertEqual(self.t.items[0],original)

    def test_overlap_rejected_then_valid_extension(self):
        c=self.clip(); c['out']=7.
        following=copy.deepcopy(c); following.update(id='next',start=12.)
        self.a.data['clips'].append(following)
        _,error=self.edit(['10','8'])
        self.assertEqual(error.call_count,1)
        self.assertEqual(montage.length(self.t.items[0]),8.)
        self.assertEqual(self.t.items[0]['start'],3.)

    def test_blank_double_click_does_not_edit_selected_clip(self):
        self.clip(); self.t.selected='clip'
        with patch('timeline_ui.ClipProperties') as dialog:
            self.t.edit_duration(SimpleNamespace(x=20,y=40))
            dialog.assert_not_called()
        self.assertTrue(self.t.canvas.bind('<Double-Button-1>'))

    def test_volume_applies_only_to_selected_clip_for_its_whole_duration(self):
        original=copy.deepcopy(self.clip(True))
        second=dict(original,id='second',start=25.)
        self.a.data['audio_clips'].append(second)
        self.edit([{'volume':'25,5%'}])
        changed=self.t.audio_clips[0]
        self.assertEqual(changed['volume'],.255)
        for key in ('start','in','out'):self.assertEqual(changed[key],original[key])
        self.assertEqual(self.t.audio_clips[1],second)
        self.a.undo(); self.assertEqual(self.t.audio_clips[0],original)

    def test_invalid_volume_and_cancel_do_not_apply_duration_either(self):
        original=copy.deepcopy(self.clip(True))
        _,error=self.edit([{'duration':'10','volume':'-1'},{'volume':'nan'},{'volume':'texte'},None])
        self.assertEqual(error.call_count,3); self.assertEqual(self.t.audio_clips[0],original)

    def test_form_changes_duration_and_volume_in_one_undo_step(self):
        original=copy.deepcopy(self.clip(True)); count=len(self.a.history)
        self.edit([{'duration':'10','volume':'0'}])
        self.assertEqual(self.t.audio_clips[0]['volume'],0.)
        self.assertEqual(montage.length(self.t.audio_clips[0]),10.)
        self.assertEqual(len(self.a.history),count+1)
        self.a.undo(); self.assertEqual(self.t.audio_clips[0],original)


if __name__=='__main__':unittest.main()
