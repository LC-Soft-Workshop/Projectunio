import array
import math
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk
import unittest
import wave
import app
import montage
from test_duration_edit import edit_clip


def rms(values):return math.sqrt(sum(float(v)*float(v) for v in values)/len(values))


def music(path):return dict(id='music',kind='audio',path=str(path),lane=0,start=0.,**{'in':0.,'out':2.},duration=2.,volume=1.)


def encode(args):return subprocess.run([app.ffmpeg(),'-v','error','-y',*args],capture_output=True,check=True,timeout=30)


def wait_for(root,predicate,seconds=12):
    deadline=time.monotonic()+seconds
    def tick():
        if predicate() or time.monotonic()>deadline:root.quit()
        else:root.after(30,tick)
    root.after(30,tick); root.mainloop()
    if not predicate():raise AssertionError('Timed out waiting for preview/volume update')


class VolumeSelectionTests(unittest.TestCase):
    def test_volume_25_and_mute_are_measurable_in_mix_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); sound=folder/'tone.wav'
            encode(['-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2',str(sound)])
            c=music(sound)
            def sample():
                raw=encode([*montage.audio_mix_args([],[c]),'-vn','-ac','1','-ar','48000','-f','f32le','pipe:1']).stdout
                return rms(array.array('f',raw)[4800:24000])
            normal=sample(); c['volume']=.25; quiet=sample()
            self.assertAlmostEqual(quiet/normal,.25,delta=.005)
            args=montage.render_args([],app.DEFAULT['zones'],folder,app.mask,app.graph,320,180,audio_clips=[c])
            encode([*args,*app.output_options(False),str(folder/'quarter.mp4')])
            raw=encode(['-i',str(folder/'quarter.mp4'),'-vn','-ac','1','-ar','48000','-f','f32le','pipe:1']).stdout
            self.assertAlmostEqual(rms(array.array('f',raw)[4800:24000])/normal,.25,delta=.02)
            c['volume']=0; self.assertLess(sample(),.00001)

    def test_double_click_volume_and_halo(self):
        root=tk.Tk(); a=app.App(root); root.update()
        try:
            a.data['audio_clips']=[music('not-needed.wav')]; t=a.timeline; t.selected='music'; t.refresh()
            self.assertGreaterEqual(len(t.canvas.find_withtag('selection_halo')),3)
            edit_clip(t,[{'volume':'25%'}])
            self.assertAlmostEqual(a.data['audio_clips'][0]['volume'],.25)
            self.assertIn('25 %',t.description.cget('text'))
            self.assertNotIn('volume',t.fields)
            self.assertFalse(hasattr(t,'volume_slider'))
            a.undo(); self.assertEqual(a.data['audio_clips'][0]['volume'],1)
            t.selected=None; t.refresh(); self.assertFalse(t.canvas.find_withtag('selection_halo'))
        finally:root.destroy(); a.live_audio.worker.join(5); a.still_renderer.worker.join(5)

    def test_open_paused_preview_receives_new_audio_without_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); sound=folder/'tone.wav'; movie=folder/'preview.mp4'
            encode(['-f','lavfi','-i','sine=duration=2',str(sound)])
            c=music(sound)
            args=montage.render_args([],app.DEFAULT['zones'],folder,app.mask,app.graph,320,180,audio_clips=[c])
            encode([*args,*app.output_options(False),'-ac','2',str(movie)])
            root=tk.Tk(); a=app.App(root); root.update(); a.data['audio_clips']=[c]
            a.show_preview(movie,a.data['zones'],lambda:None,[],[dict(c)])
            player=a.previews[-1][0]
            try:
                wait_for(root,lambda:player.frame_number>4 and getattr(player,'audio_path',None) is not None)
                self.assertTrue(player.audio,'Windows did not open the preview audio')
                with wave.open(str(player.audio_path),'rb') as f:normal=rms(array.array('h',f.readframes(f.getnframes())))
                player.toggle(); count=player.frame_number; identity=player.win.winfo_id(); old_path=getattr(player,'override_audio_path',None)
                a.timeline.selected='music'; a.timeline.refresh(); edit_clip(a.timeline,[{'volume':'25'}])
                wait_for(root,lambda:getattr(player,'override_audio_path',None)!=old_path)
                with wave.open(str(player.override_audio_path),'rb') as f:quiet=rms(array.array('h',f.readframes(f.getnframes())))
                self.assertAlmostEqual(quiet/normal,.25,delta=.01)
                self.assertFalse(player.playing); self.assertEqual(player.frame_number,count)
                self.assertEqual(player.win.winfo_id(),identity)
                self.assertTrue(player.audio,'Windows did not open the updated mix')
                player.toggle(); self.assertTrue(player.playing)
            finally:
                player.close(); player.worker.join(5); root.destroy(); a.live_audio.worker.join(5); a.still_renderer.worker.join(5)

if __name__=='__main__':unittest.main()
