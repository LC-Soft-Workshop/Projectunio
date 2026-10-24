import copy
import gc
import itertools
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import subprocess
import app
import montage
from zone_drawing import ordered_quad
from mapping_loupe import magnified_pixels
from projection_output import ProjectionOutput
from source_comparison import comparison_frames,regions
from work_media import prepare_proxies,stamp
from test_clip_context import video


def make_video(path,duration=.6,audio=False):
    inputs=['-f','lavfi','-i',f'color=red:s=960x540:r=30:d={duration},drawbox=x=480:y=0:w=480:h=270:color=yellow:t=fill,drawbox=x=480:y=270:w=480:h=270:color=blue:t=fill']
    if audio:inputs+=['-f','lavfi','-i',f'sine=frequency=440:duration={duration}']
    subprocess.run([app.ffmpeg(),'-v','error','-y',*inputs,'-c:v','libx264',*(['-c:a','aac','-shortest'] if audio else []),str(path)],check=True,capture_output=True,timeout=20)


class EditingModelTests(unittest.TestCase):
    def test_four_corners_accept_any_order_but_reject_interior_or_duplicate(self):
        rectangle=[[.1,.1],[.3,.1],[.3,.3],[.1,.3]]
        for points in itertools.permutations(rectangle):self.assertEqual(ordered_quad(points),rectangle)
        self.assertIsNone(ordered_quad([[.1,.1],[.3,.1],[.3,.3],[.25,.15]]))
        self.assertIsNone(ordered_quad([rectangle[0]]*4))

    def test_loupe_samples_selected_point_and_pads_outside_image(self):
        frame=(2,2,b'\xff\0\0'*4)
        pixels=magnified_pixels(frame,(0.,0.),(4,4),(2,2),1).split(b'\n',3)[3]
        self.assertEqual(pixels[:3],b'\0\0\0'); self.assertEqual(pixels[(2*4+2)*3:(2*4+2)*3+3],b'\xff\0\0')

    def test_proxy_preparation_preserves_duration_reuses_cache_and_can_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.mp4'; make_video(source,audio=True)
            records,errors=prepare_proxies([str(source)],app.ffmpeg(),threading.Event(),root=root/'work')
            self.assertFalse(errors); record=records[str(source)]; self.assertNotEqual(record[1],str(source))
            original_duration,_=montage.probe(source,app.ffmpeg()); proxy_duration,has_audio=montage.probe(record[1],app.ffmpeg())
            self.assertAlmostEqual(original_duration,proxy_duration,delta=1/30); self.assertTrue(has_audio)
            with patch('work_media.checked_process',side_effect=AssertionError('Should reuse existing copy')):
                again,errors=prepare_proxies([str(source)],app.ffmpeg(),threading.Event(),root=root/'work')
            self.assertFalse(errors); self.assertEqual(again[str(source)][1],record[1])
            cancel=threading.Event(); cancel.set()
            with self.assertRaises(RuntimeError):prepare_proxies([str(source)],app.ffmpeg(),cancel,root=root/'work')

    def test_source_and_mapping_use_same_spatial_regions(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4'; make_video(source)
            clip=video('pan'); clip.update(path=str(source),duration=.6,fit='Contenir',panorama=dict(lanes=[0,1,2],gap_mode='auto')); clip['out']=.6
            zones=[[[0.,0.],[.45,0.],[.45,1.],[0.,1.]],[[.55,.5],[1.,.5],[1.,1.],[.55,1.]],[[.57,.04],[.91,.01],[.99,.4],[.56,.39]]]
            source_frame,mapped,rectangles=comparison_frames(app.ffmpeg(),clip,[clip],zones,.2,app.mask,app.graph,threading.Event())
            boxes=dict(rectangles); self.assertLess(boxes[2][1]+boxes[2][3],boxes[1][1]); self.assertAlmostEqual(boxes[1][0],.55)
            def pixel(frame,x,y):
                w,h,data=frame; at=(int(y*h)*w+int(x*w))*3; return data[at:at+3]
            for frame in (source_frame,mapped):
                upper=pixel(frame,.75,.2); lower=pixel(frame,.75,.75)
                self.assertGreater(upper[0],180); self.assertGreater(upper[1],180); self.assertLess(upper[2],50)
                self.assertGreater(lower[2],180); self.assertLess(lower[0],50)


class EditingUITests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update(); self.t=self.a.timeline; self.tools=self.a.timeline_tools

    def tearDown(self):
        a=self.a; self.root.destroy()
        for worker in [a.still_renderer.worker,a.live_audio.worker,self.tools.worker,a.media_work.worker]:worker.join(5)
        tool=getattr(a,'source_comparison',None)
        if tool:tool.worker.join(5)
        self.a=None; self.root=None; self.t=None; self.tools=None; gc.collect()

    def wait_for(self,predicate,seconds=12):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:self.root.update(); time.sleep(.01)
        self.assertTrue(predicate())

    def click_zone(self,x,y):
        ox,oy,w,h=self.a.viewport(self.a.canvas)
        self.a.canvas.event_generate('<Button-1>',x=round(ox+x*w),y=round(oy+y*h)); self.a.canvas.event_generate('<ButtonRelease-1>',x=round(ox+x*w),y=round(oy+y*h)); self.root.update()

    def test_drawing_fourth_corner_creates_zone_in_visual_editor(self):
        self.a.begin_zone()
        for x,y in ((.1,.1),(.3,.1),(.1,.3),(.3,.3)):self.click_zone(x,y)
        self.assertEqual(len(self.a.data['zones']),3); self.assertIsNone(self.a.drawing_zone); self.assertTrue(app.valid(self.a.data['zones'][2]))
        self.assertEqual(len(self.a.canvas.find_withtag('mapping_corner')),12)
        self.a.undo(); self.assertEqual(len(self.a.data['zones']),2)

    def test_invalid_fourth_corner_preserves_first_three_for_retry(self):
        self.a.begin_zone()
        for x,y in ((.1,.1),(.3,.1),(.3,.3),(.25,.15)):self.click_zone(x,y)
        self.assertEqual(len(self.a.data['zones']),2); self.assertEqual(len(self.a.drawing_zone),3)
        self.a.undo_drawing_point(); self.assertEqual(len(self.a.drawing_zone),2); self.click_zone(.3,.3)
        self.click_zone(.1,.3); self.assertEqual(len(self.a.data['zones']),3)

    def audio(self):
        clip=dict(id='audio',kind='audio',path='unused.wav',lane=0,start=2.,duration=6.,volume=1.,**{'in':0.,'out':4.})
        self.a.data['audio_clips']=[clip]; self.t.scale.set('40'); self.t.magnetic.set(False); self.t.selected='audio'; self.t.refresh()
        key=self.tools.wave_key(clip['path']); self.tools.waves[key]=[0.]*10+[.6]*50
        return clip

    def event(self,at,row=2):return SimpleNamespace(x=85+at*self.t.pixels_per_second()-self.t.canvas.canvasx(0),y=28+row*50+19-self.t.canvas.canvasy(0),state=0)

    def test_audio_hover_both_edges_and_left_trim_keep_waveform_visible(self):
        clip=self.audio(); event=self.event(2.25)
        self.t.hover_cursor(event); self.assertEqual(self.t.hover[1],'in'); self.assertEqual(self.t.canvas.cget('cursor'),'sb_h_double_arrow')
        self.assertTrue(self.t.canvas.find_withtag('trim_in')); self.assertTrue(self.t.canvas.find_withtag('trim_out'))
        self.tools.press(event); self.assertEqual(self.t.dragging[2],'in'); self.tools.motion(self.event(3.25))
        self.assertAlmostEqual(self.t.proposal['in'],1.); self.assertAlmostEqual(self.t.proposal['start'],3.); self.assertAlmostEqual(self.t.proposal['out'],4.)
        self.tools.draw()  # A background thumbnail/waveform result must preserve the trim preview.
        first_wave=min(self.t.canvas.coords(item)[0] for item in self.t.canvas.find_withtag('waveform'))
        self.assertGreater(first_wave,85+3.*40)
        self.assertTrue(self.t.canvas.find_withtag('waveform')); self.tools.release(None)
        self.assertAlmostEqual(self.t.audio_clips[0]['in'],1.); self.a.undo(); self.assertEqual(self.t.audio_clips[0]['in'],0.)
        self.t.hover_cursor(self.event(5.75)); self.assertEqual(self.t.hover[1],'out')

    def test_resize_edge_wins_over_multi_selection_and_neighbor_limits_extension(self):
        clip=self.audio(); other=dict(clip,id='other',start=7.)
        self.a.data['audio_clips'].append(other); self.tools.selection={'audio','other'}; self.t.selected='audio'; self.t.refresh()
        self.tools.press(self.event(5.75)); self.assertIsNone(self.tools.group); self.assertEqual(self.t.dragging[2],'out')
        self.tools.motion(self.event(20.)); self.assertAlmostEqual(self.t.proposal['out'],5.); self.tools.release(None)
        self.assertAlmostEqual(self.t.audio_clips[1]['start'],7.)

    def test_loupe_nudge_moves_one_output_pixel_and_respects_lock(self):
        self.a.toggle_loupe(); loupe=self.a.mapping_loupe; before=copy.deepcopy(self.a.data['zones'][0][0])
        loupe.nudge(SimpleNamespace(keysym='Right',state=0)); after=self.a.data['zones'][0][0]
        self.assertAlmostEqual(after[0]-before[0],1/1280); self.assertTrue(loupe.win.winfo_exists())
        self.a.data['locks']=dict(mapping=True); loupe.nudge(SimpleNamespace(keysym='Right',state=0)); self.assertEqual(self.a.data['zones'][0][0],after)

    def test_black_and_freeze_affect_output_without_losing_latest_frame(self):
        with patch('projection_output.place_projector_window'):
            output=ProjectionOutput(self.root,(0,0,320,180)); self.root.update()
        red=(2,2,b'\xff\0\0'*4); blue=(2,2,b'\0\0\xff'*4)
        output.show(red); output.set_frozen(True); output.show(blue); self.assertEqual(output.frame,red)
        output.set_black(True); self.assertFalse(output.canvas.find_all()); self.assertEqual(output.latest,blue)
        output.set_frozen(False); output.set_black(False); self.assertEqual(output.frame,blue); self.assertTrue(output.canvas.find_all()); output.close()

    def test_real_thumbnails_and_source_comparison_are_generated_in_background(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4'; make_video(source)
            clip=video('clip'); clip.update(path=str(source),duration=.6); clip['out']=.6
            self.a.data['clips']=[clip]; self.t.selected='clip'; self.t.scale.set('80'); self.t.refresh()
            self.wait_for(lambda:bool(self.t.canvas.find_withtag('thumbnail')))
            name=self.t.canvas.itemcget(self.t.canvas.find_withtag('thumbnail')[0],'image'); self.assertIn(name,self.root.tk.call('image','names'))
            self.a.playhead=.2; self.a.open_source_view(); comparison=self.a.source_comparison
            self.wait_for(lambda:comparison.frames is not None); self.assertTrue(comparison.canvases[0].find_withtag('source_region')); comparison.close()
            comparison.worker.join(5); self.a.media_work.close(); self.a.media_work.worker.join(5)
            self.a.still_renderer.close(); self.a.still_renderer.worker.join(5)

    def test_work_copy_resolution_never_changes_original_project_or_export_paths(self):
        from test_render_state import DeferredJob
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.mp4'; make_video(source,audio=True)
            records,errors=prepare_proxies([str(source)],app.ffmpeg(),threading.Event(),root=root/'work'); self.assertFalse(errors)
            clip=video('clip'); clip.update(path=str(source),duration=.6,audio=True); clip['out']=.6; self.a.data['clips']=[clip]
            self.a.media_work.records.update(records); resolved=self.a.media_work.resolve([clip])[0]
            self.assertNotEqual(resolved['path'],clip['path']); self.assertEqual(resolved['_audio_path'],clip['path'])
            mix=montage.audio_mix_args([resolved],[]); self.assertIn(str(source),mix); self.assertNotIn(resolved['path'],mix)
            with patch('app.RenderJob',DeferredJob),patch('app.filedialog.asksaveasfilename',return_value=str(root/'final.mp4')):
                self.a.export(); self.assertEqual(self.a.active_render.clips[0]['path'],str(source)); self.a.cancel()
            source.write_bytes(b'changed'); self.assertEqual(self.a.media_work.resolve([clip])[0]['path'],str(source))


if __name__=='__main__':unittest.main()
