import copy
import tkinter as tk
from types import SimpleNamespace
import unittest
import app
import montage


def clip(identity,lane,start,end=2):
    return {'id':identity,'path':identity+'.mp4','lane':lane,'start':start,'in':0.,'out':end,'duration':20.,'audio':False,'volume':1.,'fit':'Remplir'}


class MagneticTests(unittest.TestCase):
    def test_alternation_and_reverse_alignment(self):
        left=clip('left',0,0,3.37); right=clip('right',1,3.5)
        snapped,target=montage.snap_clip(right,[left,right],'move',.25)
        self.assertEqual(snapped['lane'],1)
        self.assertAlmostEqual(snapped['start'],3.37)
        self.assertAlmostEqual(target,3.37)
        self.assertEqual(montage.length(snapped),2)
        # The right edge can align to the beginning of a later clip too.
        later=clip('later',1,8.13); moving=clip('moving',0,6.25)
        snapped,target=montage.snap_clip(moving,[later,moving],'move',.25)
        self.assertAlmostEqual(snapped['start']+montage.length(snapped),8.13)

    def test_legal_trims_and_no_illegal_overlap(self):
        reference=clip('ref',1,4,1); moving=clip('move',0,2,1.9)
        snapped,target=montage.snap_clip(moving,[reference,moving],'out',.2)
        self.assertAlmostEqual(snapped['out'],2)
        moving=clip('move',0,5.1); moving['in']=.5; moving['out']=2.5
        snapped,target=montage.snap_clip(moving,[reference,moving],'in',.2)
        self.assertAlmostEqual(snapped['start'],5)
        self.assertAlmostEqual(snapped['in'],.4)
        # A nearby boundary cannot pull this clip into a clip on its own lane.
        block=clip('block',0,2,2); moving=clip('move',0,4.1)
        reference=clip('ref',1,3.95,5)
        snapped,target=montage.snap_clip(moving,[block,reference,moving],'move',.2)
        self.assertAlmostEqual(snapped['start'],4)
        montage.validate([block,reference,snapped])

    def test_outside_magnet_range(self):
        left=clip('left',0,0,3); right=clip('right',1,4)
        snapped,target=montage.snap_clip(right,[left,right],'move',.1)
        self.assertEqual(snapped,right); self.assertIsNone(target)

    def test_drag_guide_toggle_and_undo(self):
        root=tk.Tk(); a=app.App(root); root.update()
        try:
            left=clip('left',0,0,3.37); right=clip('right',1,6)
            a.data['clips']=[left,right]; t=a.timeline; t.refresh()
            t.press(SimpleNamespace(x=85+6*40+30,y=97))
            t.motion(SimpleNamespace(x=85+3.5*40+30,y=97))
            self.assertAlmostEqual(t.proposal['start'],3.37)
            self.assertEqual(t.proposal['lane'],1)
            self.assertTrue(t.canvas.find_withtag('snapguide'))
            t.release(SimpleNamespace())
            self.assertFalse(t.canvas.find_withtag('snapguide'))
            self.assertAlmostEqual(a.data['clips'][1]['start'],3.37)
            a.undo(); self.assertEqual(a.data['clips'][1]['start'],6)
            t.magnetic.set(False)
            t.press(SimpleNamespace(x=85+6*40+30,y=97))
            t.motion(SimpleNamespace(x=85+3.5*40+30,y=97))
            self.assertAlmostEqual(t.proposal['start'],3.5)
            self.assertFalse(t.canvas.find_withtag('snapguide'))
        finally:root.destroy()

if __name__=='__main__':unittest.main()
