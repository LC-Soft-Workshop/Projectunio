import array
import copy
import json
import math
from pathlib import Path
import queue
import subprocess
import tempfile
import time
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import app
import montage
from studio import effective_items,validate_extras,consolidate_levels
from direct_preview import DirectPreview,slice_items


def clip(path='unused.mp4',lane=0,start=0.,duration=3.,audio=False):
    return dict(id=f'{lane}-{start}',path=str(path),lane=lane,start=start,duration=duration,volume=1.,audio=audio,fit='Remplir',**{'in':0.,'out':duration})


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()
        self.t=self.a.timeline; self.tools=self.a.timeline_tools

    def tearDown(self):
        self.root.destroy(); self.a.still_renderer.worker.join(5); self.a.live_audio.worker.join(5); self.tools.worker.join(5)

    def test_tabs_keep_project_history_selection_and_cursor(self):
        first=self.a.active_document; self.a.data['clips']=[clip()]; self.a.name.set('Premier'); self.a.checkpoint(); self.a.set_playhead(1.); self.t.selected=self.a.data['clips'][0]['id']
        self.a.new_document(); second=self.a.active_document; self.a.name.set('Deuxième'); self.a.add_zone([[.1,.1],[.3,.1],[.3,.3],[.1,.3]])
        self.a.tabs.select(first['tab']); self.a.change_document()
        self.assertEqual(self.a.name.get(),'Premier'); self.assertEqual(self.a.playhead,1.); self.assertEqual(len(self.a.data['zones']),2); self.assertEqual(len(self.a.history),1)
        self.a.tabs.select(second['tab']); self.a.change_document()
        self.assertEqual(self.a.name.get(),'Deuxième'); self.assertEqual(len(self.a.data['zones']),3); self.assertEqual(self.a.data['clips'],[])

    def test_draw_zone_then_render_lane_and_remove_reindexes(self):
        self.a.begin_zone(); ox,oy,w,h=self.a.viewport(self.a.canvas)
        for x,y in ((.1,.1),(.3,.1),(.3,.3),(.1,.3)):self.a.zone_click(SimpleNamespace(x=ox+x*w,y=oy+y*h))
        self.assertEqual(len(self.a.data['zones']),3); self.assertEqual(len(self.t.hooks),1); self.assertIsNone(self.a.drawing_zone)
        self.a.data['clips']=[clip(lane=2)]; self.t.refresh(); self.assertEqual(self.t.row(self.a.data['clips'][0]),2)
        audio=dict(clip(),kind='audio'); self.assertEqual(self.t.row(audio),3)
        self.a.zone=0; self.a.delete_zone(); self.assertEqual(self.a.data['clips'][0]['lane'],1); self.assertEqual(len(self.a.data['zones']),2)
        self.a.undo(); self.assertEqual(len(self.a.data['zones']),3); self.assertEqual(self.a.data['clips'][0]['lane'],2)

    def test_edge_translation_moves_only_two_corners_and_undo(self):
        old=copy.deepcopy(self.a.data['zones'][0]); ox,oy,w,h=self.a.viewport(self.a.canvas)
        self.a.press(SimpleNamespace(x=ox+.25*w,y=oy+.1*h)); self.assertEqual(self.a.edge,0)
        self.a.drag(SimpleNamespace(x=ox+.25*w,y=oy+.15*h))
        q=self.a.data['zones'][0]
        for i in (0,1):self.assertAlmostEqual(q[i][1],old[i][1]+.05)
        self.assertEqual(q[2:],old[2:]); self.a.undo(); self.assertEqual(self.a.data['zones'][0],old)

    def test_split_duplicate_group_move_and_conflict_is_atomic(self):
        self.a.data['clips']=[clip()]; self.t.selected=self.a.data['clips'][0]['id']; self.a.playhead=1.; self.tools.split()
        self.assertEqual([montage.length(c) for c in self.t.clips],[1.,2.]); self.assertEqual(self.t.clips[1]['in'],1.)
        self.tools.selection={c['id'] for c in self.t.items}; self.tools.duplicate()
        self.assertEqual(len(self.t.clips),4); self.assertEqual([c['start'] for c in self.t.clips],[0.,1.,3.,4.])
        before=copy.deepcopy(self.a.data); self.tools.paste(0.)
        self.assertEqual(before,self.a.data)
        self.tools.selection={c['id'] for c in self.t.clips[2:]}; self.t.selected=self.t.clips[2]['id']
        self.tools.press(SimpleNamespace(x=85+3.5*40,y=40,state=0)); self.tools.motion(SimpleNamespace(x=85+4.5*40,y=40)); self.tools.release(None)
        self.assertEqual([c['start'] for c in self.t.clips],[0.,1.,4.,5.])

    def test_mixer_is_non_destructive_and_solo_applies_to_video_audio(self):
        c=clip(audio=True); sound=dict(clip('x.wav',start=1.),kind='audio',id='sound')
        data=dict(clips=[c],audio_clips=[sound],master_volume=.5,mixer={'a0':dict(volume=.5,solo=True)})
        video,audio=effective_items(data)
        self.assertEqual(video[0]['volume'],0.); self.assertEqual(audio[0]['volume'],.25); self.assertEqual(sound['volume'],1.)
        validate_extras(dict(data,zones=app.DEFAULT['zones']))
        with self.assertRaises(ValueError):validate_extras(dict(zones=app.DEFAULT['zones'],master_volume=float('nan')))

    def test_old_mixer_levels_are_preserved_by_single_clip_volume(self):
        sound=dict(clip('x.wav'),kind='audio')
        data=dict(clips=[],audio_clips=[sound],master_volume=.5,mixer={'a0':dict(volume=.5,mute=False,solo=True)})
        before=effective_items(data)[1][0]['volume']; consolidate_levels(data)
        self.assertEqual(sound['volume'],.25); self.assertEqual(data['master_volume'],1.)
        self.assertEqual(data['mixer']['a0']['volume'],1.)
        self.assertTrue(data['mixer']['a0']['solo']); self.assertEqual(effective_items(data)[1][0]['volume'],before)
        consolidate_levels(data); self.assertEqual(sound['volume'],.25)

    def test_recovery_contains_all_projects_and_restores_without_replacing(self):
        with tempfile.TemporaryDirectory() as folder:
            self.a.recovery_path=Path(folder)/'session.json'; self.a.name.set('Recover 1'); self.a.new_document(); self.a.name.set('Recover 2'); self.a.write_recovery()
            data=json.loads(self.a.recovery_path.read_text(encoding='utf-8')); self.assertEqual(len(data['projects']),2)
            with patch('studio.filedialog.askopenfilename',return_value=str(self.a.recovery_path)):self.a.recover_session()
            self.assertEqual(len(self.a.documents),4); self.assertEqual(self.a.name.get(),'Recover 2')

    def test_markers_and_framing_selection(self):
        self.a.data['clips']=[clip(lane=0),clip(lane=1)]; self.t.selected=self.t.clips[0]['id']; self.t.clips[0].update(zoom=1.7,pan_x=.3)
        self.a.copy_framing(); self.tools.selection={c['id'] for c in self.t.clips}; self.a.paste_framing(); self.assertEqual(self.t.clips[1]['zoom'],1.7)
        self.a.playhead=1.2
        with patch('timeline_tools.simpledialog.askstring',return_value='Temps fort'):self.tools.marker()
        self.assertEqual(self.a.data['markers'],[dict(time=1.2,name='Temps fort')]); self.assertTrue(self.t.canvas.find_withtag('marker'))

    def test_schema_four_save_load_presets_and_small_screen_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); project=folder/'show.json'; preset=folder/'mapping.json'
            self.a.add_zone([[.1,.1],[.3,.1],[.3,.3],[.1,.3]])
            self.a.data.update(master_volume=.25,markers=[dict(time=2.,name='Top')],mixer={'a0':dict(mute=True,solo=False,volume=.5)})
            with patch('app.filedialog.asksaveasfilename',return_value=str(project)):self.a.save()
            self.assertEqual(json.loads(project.read_text(encoding='utf-8'))['version'],4)
            with patch('studio.filedialog.asksaveasfilename',return_value=str(preset)):self.a.save_mapping()
            with patch('app.filedialog.askopenfilename',return_value=str(project)):self.a.load()
            self.assertEqual(self.a.data['master_volume'],1.); self.assertEqual(len(self.a.documents),2); self.assertEqual(len(self.a.data['zones']),3)
            self.a.data['zones']=copy.deepcopy(app.DEFAULT['zones']); self.a.data.pop('zone_names')
            with patch('studio.filedialog.askopenfilename',return_value=str(preset)):self.a.load_mapping()
            self.assertEqual(len(self.a.data['zones']),3)
            self.root.geometry('1080x780'); self.root.update()
            self.assertTrue(self.a.export_button.winfo_ismapped()); self.assertLess(self.a.export_button.winfo_rooty(),self.root.winfo_rooty()+780)


class StudioRenderTests(unittest.TestCase):
    def encode(self,args):
        result=subprocess.run([app.ffmpeg(),'-v','error','-y',*args],capture_output=True,timeout=60)
        if result.returncode:raise AssertionError(result.stderr.decode(errors='replace'))
        return result.stdout

    def test_fades_video_and_audio_and_window_offsets(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); video=folder/'red.mp4'
            self.encode(['-f','lavfi','-i','color=red:s=80x80:r=30:d=2','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(video)])
            c=clip(video,duration=2.,audio=True); c.update(fade_in=.8,fade_out=.8)
            zones=[[[0.,0.],[1.,0.],[1.,1.],[0.,1.]]]
            args=montage.render_args([dict(c,audio=False)],zones,folder,app.mask,app.graph,80,80)
            raw=self.encode([*args,'-an','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
            def red(at):return raw[round(at*30)*80*80*3+(40*80+40)*3]
            self.assertLess(red(0.),10); self.assertGreater(red(1.),200); self.assertLess(red(1.9),80)
            def rms(begin,end):
                raw=self.encode([*montage.audio_mix_args([c],[],window=(begin,end)),'-ac','1','-ar','48000','-f','f32le','pipe:1']); samples=array.array('f',raw); return math.sqrt(sum(v*v for v in samples)/len(samples))
            normal=rms(.9,1.); self.assertLess(rms(0.,.1),normal*.2)
            self.assertGreater(rms(.4,.5),normal*.45); self.assertLess(rms(.4,.5),normal*.7)
            sliced=slice_items([c],.4,.6)[0]; self.assertAlmostEqual(sliced['_effect_offset'],.4)

    def test_three_zones_render_and_direct_play_from_cursor_without_movie(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); path=folder/'source.mp4'; self.encode(['-f','lavfi','-i','color=red:s=80x80:d=1','-c:v','libx264',str(path)])
            c=clip(path,lane=2,duration=1.); zones=copy.deepcopy(app.DEFAULT['zones'])+[ [[.3,.3],[.7,.3],[.7,.7],[.3,.7]] ]
            root=tk.Tk(); player=DirectPreview(root,app.ffmpeg(),zones,[c],[],.4,app.mask,app.graph,app.project)
            try:
                limit=time.monotonic()+15
                def poll():
                    if player.frame or time.monotonic()>limit:root.quit()
                    else:root.after(20,poll)
                poll(); root.mainloop()
                self.assertIsNotNone(player.frame); self.assertTrue(player.win.winfo_exists()); self.assertGreaterEqual(player.seek.get(),.4)
                self.assertFalse(list(folder.glob('result.mp4')))
            finally:
                player.close(); root.destroy()
                for worker in player.workers+player.retired:worker.join(5)

    def test_waveform_decoding_and_direct_audio_are_bounded_and_cancellable(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); sound=folder/'music.wav'
            self.encode(['-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.6',str(sound)])
            c=dict(clip(sound,duration=.6),kind='audio'); c['id']='music'; c['volume']=.25
            root=tk.Tk(); a=app.App(root); a.data['audio_clips']=[c]; a.timeline.refresh()
            played=[]
            class Output:
                def write(self,data,stop,playing):played.append(data)
                def close(self):pass
            try:
                deadline=time.monotonic()+10
                def poll_wave():
                    if a.timeline_tools.waves or time.monotonic()>deadline:root.quit()
                    else:root.after(20,poll_wave)
                poll_wave(); root.mainloop(); peaks=next(iter(a.timeline_tools.waves.values())); self.assertEqual(len(peaks),6); self.assertGreater(max(peaks),.1)
                with patch('direct_preview.WaveOutput',Output):
                    a.direct_play(); p=a.direct_player; p.ready.set(); p.workers[1].join(10)
                    self.assertFalse(p.workers[1].is_alive()); self.assertTrue(played); self.assertGreater(p.peak,.01); self.assertLess(p.peak,.04)
                    self.assertAlmostEqual(sum(len(block) for block in played)/192000,.6,delta=.001)
                    p.close()
                    for worker in p.workers:worker.join(5)
            finally:
                root.destroy(); a.timeline_tools.worker.join(5); a.still_renderer.worker.join(5); a.live_audio.worker.join(5)

    def test_preflight_relinks_all_occurrences_and_can_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            sound=Path(folder)/'found.wav'; self.encode(['-f','lavfi','-i','sine=frequency=440:duration=1',str(sound)])
            root=tk.Tk(); a=app.App(root)
            missing=str(Path(folder)/'missing.wav'); first=dict(clip(missing,duration=.5),kind='audio'); second=dict(first,id='second',start=2.)
            a.data['audio_clips']=[first,second]
            try:
                a.preflight(); window=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
                text=next(w for w in window.winfo_children() if isinstance(w,tk.Text)); self.assertIn('Fichiers introuvables',text.get('1.0','end'))
                button=next(w for w in window.winfo_children() if isinstance(w,app.ttk.Button))
                with patch('studio.filedialog.askopenfilename',return_value=str(sound)):button.invoke()
                self.assertEqual([c['path'] for c in a.data['audio_clips']],[str(sound.resolve())]*2)
                self.assertEqual([c['start'] for c in a.data['audio_clips']],[0.,2.]); self.assertEqual([c['out'] for c in a.data['audio_clips']],[.5,.5])
                self.assertIn('Tous les fichiers',text.get('1.0','end')); a.undo(); self.assertEqual(a.data['audio_clips'][0]['path'],missing)
            finally:
                root.destroy(); a.timeline_tools.worker.join(5); a.still_renderer.worker.join(5); a.live_audio.worker.join(5)


if __name__=='__main__':unittest.main()
