import array
import copy
import json
import math
from pathlib import Path
import subprocess
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import app
from test_duration_edit import edit_clip
import montage
from mapping_still import read_ppm


def run(args):return subprocess.run([app.ffmpeg(),'-v','error','-y',*args],check=True,capture_output=True,timeout=30)


def video_clip(path):
    return dict(id='video',path=str(path),lane=0,start=0.,**{'in':0.,'out':1.},duration=1.,audio=False,volume=1.,fit='Remplir')


def music(path,identity,lane,start,begin,end,volume):
    return dict(id=identity,kind='audio',path=str(path),lane=lane,start=start,**{'in':begin,'out':end},duration=1.,volume=volume)


def make_video(path):
    run(['-f','lavfi','-i','color=green:s=900x300:r=30:d=1,drawbox=x=0:y=0:w=300:h=300:color=red:t=fill,drawbox=x=600:y=0:w=300:h=300:color=blue:t=fill','-c:v','libx264',str(path)])


class FramingAudioTests(unittest.TestCase):
    def test_pan_and_zoom_render_without_changing_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); path=folder/'bands.mp4'; make_video(path)
            clip=video_clip(path); zones=copy.deepcopy(app.DEFAULT['zones'])
            def pixel(pan,zoom=1):
                clip.update(pan_x=pan,zoom=zoom)
                args=montage.render_args([clip],zones,folder,app.mask,app.graph,320,180,still_at=.5)
                data=run([*args,'-an','-frames:v','1','-f','image2pipe','-c:v','ppm','pipe:1']).stdout
                w,h,rgb=read_ppm(data); return rgb[(90*w+80)*3:(90*w+80)*3+3]
            self.assertGreater(pixel(0)[1],70)
            self.assertGreater(pixel(1)[0],200)
            self.assertGreater(pixel(-1)[2],200)
            self.assertGreater(pixel(0,2)[1],70)
            pixel(1,.25)
            self.assertEqual(zones,app.DEFAULT['zones'])
            q=[[.1,.2],[.4,.1],[.45,.9],[.05,.8]]
            for u,v in [(.2,.7),(.5,.5),(0,0),(1,1)]:
                result=app.unproject(q,*app.project(q,u,v))
                self.assertAlmostEqual(result[0],u); self.assertAlmostEqual(result[1],v)

    def test_multiple_audio_tracks_mix_trim_volume_and_extend_video(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); source=folder/'video.mp4'; make_video(source)
            for frequency in (440,880):run(['-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=48000:duration=1',str(folder/f'{frequency}.wav')])
            audios=[music(folder/'440.wav','a',0,.3,.2,.8,.5),music(folder/'880.wav','b',1,.6,0.,1.,.25)]
            args=montage.render_args([video_clip(source)],app.DEFAULT['zones'],folder,app.mask,app.graph,320,180,audio_clips=audios)
            run([*args,*app.output_options(False),str(folder/'final.mp4')])
            samples=array.array('f',run(['-i',str(folder/'final.mp4'),'-vn','-ar','48000','-ac','1','-f','f32le','pipe:1']).stdout)
            def rms(at):
                part=samples[int(at*48000):int((at+.08)*48000)]
                return math.sqrt(sum(x*x for x in part)/len(part))
            self.assertLess(rms(.1),.002)
            self.assertGreater(rms(.4),.035)
            self.assertGreater(rms(.7),rms(.4)*1.04)
            self.assertGreater(rms(1.2),.015)
            self.assertLess(rms(1.2),rms(.4)*.7)
            self.assertAlmostEqual(len(samples)/48000,1.6,delta=.06)
            black=run(['-ss','1.2','-i',str(folder/'final.mp4'),'-an','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1']).stdout
            self.assertLess(max(black),5)

    def test_direct_drag_audio_import_and_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); source=folder/'bands.mp4'; sound=folder/'musique.wav'; make_video(source)
            run(['-f','lavfi','-i','sine=duration=1',str(sound)])
            root=tk.Tk(); a=app.App(root); root.update()
            try:
                a.timeline.import_files(0,[str(source)]); a.set_playhead(.5)
                a.edit_mode.set('video'); q=copy.deepcopy(a.data['zones'][0]); ox,oy,w,h=a.viewport(a.canvas)
                p=app.project(q,.5,.5); r=app.project(q,.75,.5)
                a.press(SimpleNamespace(x=ox+p[0]*w,y=oy+p[1]*h))
                a.drag(SimpleNamespace(x=ox+r[0]*w,y=oy+r[1]*h))
                a.finish_video_drag()
                self.assertAlmostEqual(a.data['clips'][0]['pan_x'],.25)
                self.assertEqual(a.data['zones'][0],q)
                self.assertEqual(a.data['clips'][0]['start'],0)
                a.timeline.fields['zoom'].set('150'); a.timeline.apply()
                self.assertAlmostEqual(a.data['clips'][0]['zoom'],1.5)
                a.timeline.import_audio([str(sound)]); a.timeline.add_audio_track(); a.timeline.import_audio([str(sound)])
                self.assertEqual(a.data['audio_track_count'],2)
                self.assertEqual([c['lane'] for c in a.data['audio_clips']],[0,1])
                a.timeline.fields['start'].set('2'); a.timeline.apply(); edit_clip(a.timeline,[{'volume':'30'}])
                self.assertEqual(a.data['audio_clips'][1]['start'],2)
                self.assertAlmostEqual(a.data['audio_clips'][1]['volume'],.3)
                project=folder/'spectacle.json'
                with patch('app.filedialog.asksaveasfilename',return_value=str(project)):a.save()
                with patch('app.filedialog.askopenfilename',return_value=str(project)):a.load()
                self.assertEqual(len(a.data['audio_clips']),2)
                self.assertAlmostEqual(a.data['clips'][0]['pan_x'],.25)
                self.assertAlmostEqual(a.data['clips'][0]['zoom'],1.5)
                self.assertEqual(a.data['audio_clips'][1]['path'],str(sound.resolve()))
            finally:root.destroy(); a.still_renderer.worker.join(10)

if __name__=='__main__':unittest.main()
