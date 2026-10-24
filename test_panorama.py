import copy
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import app
import montage
import panorama
from panorama_dialog import PanoramaDialog
from render_segments import plan
from studio import validate_extras
from test_clip_context import video


class PanoramaModelTests(unittest.TestCase):
    @staticmethod
    def rectangle(left,right,top=.1,bottom=.9):return [[left,top],[right,top],[right,bottom],[left,bottom]]

    def test_auto_gap_is_geometric_per_pair_and_follows_mapping(self):
        zones=[self.rectangle(0,.2),self.rectangle(.3,.5),self.rectangle(.8,1.)]
        clip=video('pan'); clip['panorama']=dict(lanes=[0,1,2],gap_mode='auto',gap=0.)
        widths,gaps=panorama.layout(clip,zones)
        self.assertAlmostEqual(gaps[0]/widths[0],.5); self.assertAlmostEqual(gaps[1]/widths[1],1.5)
        before=panorama.views(clip,zones); zones[1]=self.rectangle(.4,.6)
        self.assertNotEqual(before,panorama.views(clip,zones))
        reverse=dict(clip,lane=2,panorama=dict(lanes=[2,1,0],gap_mode='auto'))
        self.assertEqual([round(g,9) for g in panorama.layout(reverse,zones)[1]],[round(g,9) for g in reversed(panorama.layout(clip,zones)[1])])

    def test_auto_gap_ignores_vertical_offset_and_handles_touch_overlap_and_rotation(self):
        left=self.rectangle(0,.3,.1,.5); right=self.rectangle(.4,.7,.3,.7)
        gap=panorama.estimated_gaps([left,right],[0,1])[0]
        right_aligned=self.rectangle(.4,.7,.1,.5)
        self.assertAlmostEqual(gap,panorama.estimated_gaps([left,right_aligned],[0,1])[0])
        for start in (.3,.2):self.assertAlmostEqual(panorama.estimated_gaps([left,self.rectangle(start,start+.3,.1,.5)],[0,1])[0],0.)
        rotated=right_aligned[2:]+right_aligned[:2]
        self.assertAlmostEqual(gap,panorama.estimated_gaps([left,rotated],[0,1])[0])
        invalid=video('bad'); invalid['panorama']=dict(lanes=[0,1],gap_mode='unknown')
        with self.assertRaises(ValueError):panorama.validate(invalid)

    def test_conflicts_cover_every_zone_and_structure_is_validated(self):
        clip=video('pan'); clip['panorama']=dict(lanes=[0,2],gap=.1)
        montage.validate([clip,video('other',1)])
        with self.assertRaises(ValueError):montage.validate([clip,video('other',2)])
        for value in [dict(lanes=[0,0]),dict(lanes=[0]),dict(lanes=[0,64]),dict(lanes=[1,0]),dict(lanes=[0,2],gap=float('nan'))]:
            with self.subTest(value=value),self.assertRaises(ValueError):montage.validate([dict(clip,panorama=value)])
        with self.assertRaises(ValueError):validate_extras(dict(zones=app.DEFAULT['zones'],clips=[clip]))

    def test_slices_order_gap_unequal_widths_and_cache_keys(self):
        zones=copy.deepcopy(app.DEFAULT['zones']); zones[1]=[[.55,.1],[.75,.1],[.75,.9],[.55,.9]]
        clip=video('pan'); clip['panorama']=dict(lanes=[0,1],gap=0.)
        views=panorama.views(clip,zones)
        self.assertAlmostEqual(views[0][1][1],2*views[1][1][1]); self.assertAlmostEqual(views[1][1][0],views[0][1][1])
        first=plan([clip],[])[0].key(); clip['panorama']['gap']=.5
        self.assertNotEqual(first,plan([clip],[])[0].key())
        self.assertGreater(panorama.views(clip,zones)[1][1][0],views[1][1][0])
        clip['panorama']=dict(lanes=[0,2],gap=.2)
        adjusted=panorama.reindex(clip,1)
        self.assertEqual(adjusted['panorama']['lanes'],[0,1]); self.assertEqual(clip['panorama']['lanes'],[0,2])


class PanoramaUITests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()
        self.clip=video('pan'); self.clip['panorama']=dict(lanes=[0,1],gap=0.)
        self.a.data['clips']=[self.clip]; self.t=self.a.timeline; self.t.selected='pan'; self.a.timeline_tools.selection={'pan'}; self.t.refresh()

    def tearDown(self):
        self.root.destroy()
        for worker in [self.a.timeline_tools.worker,self.a.still_renderer.worker,self.a.live_audio.worker]:worker.join(5)

    def point(self,lane,at=.6):return SimpleNamespace(x=85+at*self.t.pixels_per_second(),y=28+lane*50+19,state=0)

    def test_secondary_part_selects_trims_moves_and_splits_one_clip(self):
        event=self.point(1)
        self.assertEqual(self.a.timeline_tools.hit(event)['id'],'pan')
        self.t.press(event); self.t.motion(self.point(1,1.)); self.t.release(None)
        self.assertEqual(len(self.t.clips),1); self.assertEqual(self.t.clips[0]['lane'],0)
        self.assertAlmostEqual(self.t.clips[0]['start'],.4); self.assertEqual(self.t.clips[0]['panorama']['lanes'],[0,1])
        self.a.playhead=1.; self.a.timeline_tools.split()
        self.assertEqual(len(self.t.clips),2)
        self.assertTrue(all(c['panorama']['lanes']==[0,1] for c in self.t.clips))
        self.a.undo(); self.assertEqual(len(self.t.clips),1)

    def test_drag_in_secondary_zone_updates_common_framing(self):
        self.a.playhead=.5; self.a.edit_mode.set('video'); self.a.draw()
        ox,oy,w,h=self.a.viewport(self.a.canvas); q=self.a.data['zones'][1]
        p=app.project(q,.4,.5); r=app.project(q,.6,.5)
        self.a.press(SimpleNamespace(x=ox+p[0]*w,y=oy+p[1]*h))
        self.a.drag(SimpleNamespace(x=ox+r[0]*w,y=oy+r[1]*h)); self.a.finish_video_drag()
        self.assertAlmostEqual(self.t.clips[0]['pan_x'],.1,places=5)
        self.assertEqual(self.a.data['zones'],app.DEFAULT['zones'])
        self.a.undo(); self.assertEqual(self.t.clips[0].get('pan_x',0.),0.)

    def test_dialog_order_gap_and_disable_are_atomic(self):
        errors=[]
        def edit():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,PanoramaDialog))
            dialog.list.selection_clear(0,'end'); dialog.list.selection_set(1); dialog.move(-1)
            dialog.list.selection_set(0,'end'); dialog.gap.set('12,5'); dialog.ok()
            if dialog.winfo_exists():errors.append(dialog.error.get()); dialog.cancel()
        self.root.after(20,edit); self.a.edit_panorama()
        self.assertFalse(errors); self.assertEqual(self.t.clips[0]['panorama'],dict(lanes=[1,0],gap=.125)); self.assertEqual(self.t.clips[0]['lane'],1)
        self.a.undo(); self.assertEqual(self.t.clips[0]['panorama']['lanes'],[0,1])
        self.root.after(20,lambda:next(w for w in self.root.winfo_children() if isinstance(w,PanoramaDialog)).disable())
        self.a.edit_panorama(); self.assertNotIn('panorama',self.t.clips[0]); self.a.undo(); self.assertIn('panorama',self.t.clips[0])

    def test_new_panorama_defaults_to_auto_and_manual_override_is_optional(self):
        self.clip.pop('panorama'); states=[]
        def edit():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,PanoramaDialog))
            states.append(dialog.auto_gap.get()); self.assertEqual(str(dialog.gap_entry.cget('state')),'disabled')
            self.assertIn('Disposition 2D',dialog.gap_summary.get()); dialog.ok()
        self.root.after(20,edit); self.a.edit_panorama()
        self.assertEqual(states,[True]); self.assertEqual(self.t.clips[0]['panorama']['gap_mode'],'auto')
        def manual():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,PanoramaDialog))
            dialog.auto_gap.set(False); dialog.auto_changed(); self.assertAlmostEqual(float(dialog.gap.get()),25.)
            dialog.gap.set('10'); dialog.ok()
        self.root.after(20,manual); self.a.edit_panorama()
        self.assertEqual(self.t.clips[0]['panorama'],dict(lanes=[0,1],gap=.1)); self.a.undo()
        self.assertEqual(self.t.clips[0]['panorama']['gap_mode'],'auto')

    def test_auto_mode_saves_loads_and_transfers_as_version_eight(self):
        from project_transfer import gather_project
        self.clip['panorama']['gap_mode']='auto'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.mp4'; source.write_bytes(b'original'); self.clip['path']=str(source); target=root/'auto.json'
            with patch('app.filedialog.asksaveasfilename',return_value=str(target)):self.a.save()
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['version'],8)
            with patch('app.filedialog.askopenfilename',return_value=str(target)):self.a.load()
            self.assertEqual(self.a.data['clips'][0]['panorama']['gap_mode'],'auto')
            copied=gather_project(self.a.data,root/'transfer')
            self.assertEqual(json.loads(copied.read_text(encoding='utf-8'))['version'],8)

    def test_spatial_preview_keeps_third_zone_above_second(self):
        self.a.data['zones']=[[[0.,0.],[.45,0.],[.45,1.],[0.,1.]],[[.55,.5],[1.,.5],[1.,1.],[.55,1.]],[[.57,.04],[.91,.01],[.99,.4],[.56,.39]]]
        self.clip['panorama']=dict(lanes=[0,1,2],gap=0.,gap_mode='auto'); observations=[]
        def inspect():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,PanoramaDialog))
            lower=dialog.strip.coords('panorama_zone_1'); upper=dialog.strip.coords('panorama_zone_2')
            observations.append(max(upper[1::2])<min(lower[1::2]))
            observations.append(min(upper[0::2])<max(lower[0::2]) and max(upper[0::2])>min(lower[0::2]))
            observations.append(all(str(button.cget('state'))=='disabled' for button in dialog.order_buttons)); dialog.cancel()
        self.root.after(20,inspect); self.a.edit_panorama(); self.assertEqual(observations,[True,True,True])

    def test_drag_upper_zone_uses_common_horizontal_and_vertical_coordinates(self):
        self.a.data['zones']=[[[0.,0.],[.45,0.],[.45,1.],[0.,1.]],[[.55,.5],[1.,.5],[1.,1.],[.55,1.]],[[.57,.04],[.91,.01],[.99,.4],[.56,.39]]]
        self.clip['panorama']=dict(lanes=[0,1,2],gap=0.,gap_mode='auto')
        self.a.playhead=.5; self.a.edit_mode.set('video'); self.a.draw(); original=copy.deepcopy(self.a.data['zones'])
        ox,oy,w,h=self.a.viewport(self.a.canvas); q=original[2]; p=app.project(q,.4,.4); r=app.project(q,.6,.6)
        self.a.press(SimpleNamespace(x=ox+p[0]*w,y=oy+p[1]*h)); self.a.drag(SimpleNamespace(x=ox+r[0]*w,y=oy+r[1]*h)); self.a.finish_video_drag()
        self.assertAlmostEqual(self.t.clips[0]['pan_x'],.2*(.99-.56),places=5)
        self.assertAlmostEqual(self.t.clips[0]['pan_y'],.2*(.4-.01),places=5)
        self.assertEqual(self.a.data['zones'],original)

    def test_save_reopen_transfer_and_locks(self):
        from project_transfer import gather_project
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.mp4'; source.write_bytes(b'original'); self.clip['path']=str(source)
            target=root/'test.json'
            with patch('app.filedialog.asksaveasfilename',return_value=str(target)):self.a.save()
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['version'],5)
            with patch('app.filedialog.askopenfilename',return_value=str(target)):self.a.load()
            self.assertEqual(self.a.data['clips'][0]['panorama'],self.clip['panorama'])
            transferred=gather_project(self.a.data,root/'transfer')
            self.assertEqual(json.loads(transferred.read_text(encoding='utf-8'))['version'],5)
            self.a.data['locks']=dict(timeline=True)
            with patch('panorama_dialog.PanoramaDialog') as dialog:self.a.edit_panorama(); dialog.assert_not_called()

    def test_deleting_used_zone_warns_about_whole_panorama_and_undo_restores(self):
        with patch('studio.messagebox.askyesno',return_value=False) as question:
            self.a.delete_timeline_track(1)
            self.assertIn('toutes leurs zones',question.call_args.args[1]); self.assertEqual(len(self.t.clips),1)
        with patch('studio.messagebox.askyesno',return_value=True):self.a.delete_timeline_track(1)
        self.assertEqual(self.t.clips,[]); self.a.undo()
        self.assertEqual(self.t.clips[0]['panorama']['lanes'],[0,1]); self.assertEqual(self.t.zone_count,2)


class PanoramaRenderTests(unittest.TestCase):
    def test_third_zone_samples_top_right_instead_of_a_third_horizontal_segment(self):
        from render_job import RenderJob
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'quadrants.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=320x180:r=30:d=0.3,drawbox=x=176:y=0:w=144:h=90:color=yellow:t=fill,drawbox=x=176:y=90:w=144:h=90:color=blue:t=fill','-c:v','libx264',str(source)],check=True,capture_output=True,timeout=20)
            zones=[[[0.,0.],[.45,0.],[.45,1.],[0.,1.]],[[.55,.5],[1.,.5],[1.,1.],[.55,1.]],[[.57,.04],[.91,.01],[.99,.4],[.56,.39]]]
            clip=video('pan'); clip.update(path=str(source),duration=.3,fit='Contenir',panorama=dict(lanes=[0,1,2],gap=0.,gap_mode='auto')); clip['out']=.3
            def check(pixels):
                def pixel(x,y):return pixels[(y*320+x)*3:(y*320+x)*3+3]
                left=pixel(70,90); lower=pixel(240,135); upper=pixel(240,40)
                self.assertGreater(left[0],180); self.assertLess(left[2],50)
                self.assertGreater(lower[2],180); self.assertLess(lower[0],50)
                self.assertGreater(upper[0],180); self.assertGreater(upper[1],180); self.assertLess(upper[2],50)
            args=montage.render_args([clip],zones,root,app.mask,app.graph,320,180,still_at=.1)
            check(subprocess.check_output([app.ffmpeg(),'-v','error',*args,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],timeout=20))
            events=queue.Queue(); target=root/'final.mp4'
            job=RenderJob(events,app.ffmpeg(),zones,[clip],[],'test',app.mask,app.graph,app.write_mire,app.output_options,destination=target,cache_directory=root/'cache'); job.width=320; job.height=180
            job.thread.start(); job.thread.join(20); self.assertFalse(job.thread.is_alive()); self.assertTrue(target.exists())
            check(subprocess.check_output([app.ffmpeg(),'-v','error','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],timeout=20))

    def test_gap_hides_middle_of_source_and_order_reverses_surfaces(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'bands.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=300x126:r=30:d=0.3,drawbox=x=100:y=0:w=100:h=126:color=lime:t=fill,drawbox=x=200:y=0:w=100:h=126:color=blue:t=fill','-c:v','libx264',str(source)],check=True,capture_output=True,timeout=20)
            zones=[[[0.,0.],[.45,0.],[.45,1.],[0.,1.]],[[.55,0.],[1.,0.],[1.,1.],[.55,1.]]]
            clip=video('pan'); clip.update(path=str(source),duration=.3,fit='Contenir',panorama=dict(lanes=[0,1],gap=0.)); clip['out']=.3
            def sample(x):
                args=montage.render_args([clip],zones,root,app.mask,app.graph,320,180,still_at=.1)
                pixels=subprocess.check_output([app.ffmpeg(),'-v','error',*args,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],timeout=20)
                offset=(90*320+x)*3; return pixels[offset:offset+3]
            self.assertGreater(sample(130)[1],180)  # The middle green band is visible without a gap.
            clip['panorama']['gap']=1.
            self.assertGreater(sample(130)[0],180)  # With a gap it is hidden between the two surfaces.
            self.assertGreater(sample(190)[2],180)
            clip['lane']=1; clip['panorama']['lanes']=[1,0]
            self.assertGreater(sample(130)[2],180); self.assertGreater(sample(190)[0],180)

    def test_still_direct_and_export_show_distinct_halves_and_one_audio(self):
        from direct_preview import DirectPreview
        from render_job import RenderJob
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'pan.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=320x180:r=30:d=0.6,drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill','-f','lavfi','-i','sine=frequency=440:duration=0.6','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,capture_output=True,timeout=20)
            clip=video('pan'); clip.update(path=str(source),duration=.6,audio=True,fit='Contenir',panorama=dict(lanes=[0,1],gap=0.,gap_mode='auto')); clip['out']=.6
            zones=[[[0.,0.],[.45,0.],[.45,1.],[0.,1.]],[[.55,0.],[1.,0.],[1.,1.],[.55,1.]]]
            def pixel_check(pixels,w,h):
                left=pixels[((h//2)*w+w//4)*3:((h//2)*w+w//4)*3+3]
                right=pixels[((h//2)*w+3*w//4)*3:((h//2)*w+3*w//4)*3+3]
                self.assertGreater(left[0],180); self.assertLess(left[2],50); self.assertGreater(right[2],180); self.assertLess(right[0],50)
            args=montage.render_args([clip],zones,root,app.mask,app.graph,320,180,still_at=.2)
            pixels=subprocess.check_output([app.ffmpeg(),'-v','error',*args,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],timeout=20)
            pixel_check(pixels,320,180)
            moving=montage.render_args([clip],zones,root,app.mask,app.graph,320,180)
            self.assertEqual(moving.count(str(source)),1)  # Decode once, split the decoded frames across surfaces.
            filters=moving[moving.index('-filter_complex')+1]
            self.assertEqual(filters.count('volume='),1)
            events=queue.Queue(); target=root/'final.mp4'
            job=RenderJob(events,app.ffmpeg(),zones,[clip],[],'test',app.mask,app.graph,app.write_mire,app.output_options,destination=target); job.width=320; job.height=180
            job.thread.start(); job.thread.join(20); self.assertFalse(job.thread.is_alive())
            results=[]
            while not events.empty():results.append(events.get())
            self.assertFalse([value for _,kind,value in results if kind=='error']); self.assertTrue(target.exists())
            pixels=subprocess.check_output([app.ffmpeg(),'-v','error','-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],timeout=20); pixel_check(pixels,320,180)
            window=tk.Tk(); player=DirectPreview(window,app.ffmpeg(),zones,[clip],[],0.,app.mask,app.graph,app.project)
            try:
                deadline=time.monotonic()+12
                while player.frame is None and not player.ended and time.monotonic()<deadline:window.update(); time.sleep(.01)
                self.assertIsNotNone(player.frame); w,h,pixels=player.frame; pixel_check(pixels,w,h)
            finally:
                player.close(); window.destroy()
                for worker in player.workers+player.retired:worker.join(5)


if __name__=='__main__':unittest.main()

