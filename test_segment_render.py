import array
import copy
import json
import math
from pathlib import Path
import queue
import subprocess
import tempfile
import unittest
import app
from render_job import RenderJob
from render_segments import plan


def ff(args):return subprocess.run([app.ffmpeg(),'-v','error','-y',*args],check=True,capture_output=True,timeout=30)


def clip(path,identity,lane,start,begin,end,duration,audio=False):
    return dict(id=identity,path=str(path),lane=lane,start=start,**{'in':begin,'out':end},duration=duration,audio=audio,volume=.1,fit='Remplir')


def music(path,duration):return dict(id='music',kind='audio',path=str(path),lane=0,start=0.,**{'in':0.,'out':duration},duration=duration,volume=.25)


class SegmentedRenderTests(unittest.TestCase):
    def render(self,folder,clips,audio,width=320,height=180):
        events=queue.SimpleQueue(); destination=folder/f'final-{width}.mp4'
        job=RenderJob(events,app.ffmpeg(),copy.deepcopy(app.DEFAULT['zones']),clips,audio,'test',app.mask,app.graph,app.write_mire,app.output_options,destination=destination,log_directory=folder/'logs')
        job.width=width; job.height=height; job.thread.start(); job.thread.join(35)
        if job.thread.is_alive():job.cancel(); job.thread.join(5); self.fail('Segmented render stalled')
        results=[]
        while not events.empty():results.append(events.get())
        errors=[payload for _,kind,payload in results if kind=='error']
        self.assertEqual(errors,[],job.log_path.read_text(encoding='utf-8')[-1800:] if errors and job.log_path else '')
        self.assertTrue(any(kind=='complete' for _,kind,_ in results))
        return destination,job

    def project(self,folder,count=18):
        colors=['red','green','blue','yellow']; sources=[]
        for i,color in enumerate(colors):
            source=folder/f'source-{i}.mp4'; sources.append(source)
            ff(['-f','lavfi','-i',f'color={color}:s=160x240:r=30:d=0.3','-f','lavfi','-i',f'sine=frequency={330+i*110}:sample_rate=48000:duration=0.3','-c:v','libx264','-c:a','aac',str(source)])
        clips=[clip(sources[i%4],f'v{i}',i%2,i*.3,0.,.3,.3,True) for i in range(count)]
        duration=count*.3
        sound=folder/'song.wav'; ff(['-f','lavfi','-i',f'sine=frequency=1000:sample_rate=48000:duration={duration}',str(sound)])
        return clips,[music(sound,duration)]

    def test_nine_alternating_pairs_four_sources_full_length_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); clips,audio=self.project(folder)
            segments=plan(clips,audio)
            self.assertEqual(len(segments),18)
            self.assertTrue(all(len(s.clips)==1 for s in segments))
            destination,job=self.render(folder,clips,audio)
            self.assertEqual(job.encoded_segments,4); self.assertEqual(job.reused_segments,14)
            raw=ff(['-i',str(destination),'-an','-vf','fps=10','-f','rawvideo','-pix_fmt','rgb24','pipe:1']).stdout
            expected=[(255,0,0),(0,128,0),(0,0,255),(255,255,0)]
            for i in range(18):
                frame=i*3+1
                def pixel(x):
                    offset=(frame*320*180+90*320+x)*3
                    return tuple(raw[offset:offset+3])
                active=pixel(80 if i%2==0 else 240); black=pixel(240 if i%2==0 else 80)
                self.assertLess(max(black),6,f'Inactive lane at occurrence {i}')
                for value,wanted in zip(active,expected[i%4]):self.assertAlmostEqual(value,wanted,delta=15,msg=f'Occurrence {i}')
            samples=array.array('f',ff(['-i',str(destination),'-vn','-ac','1','-ar','48000','-f','f32le','pipe:1']).stdout)
            for i in range(18):
                start=int((i*.3+.1)*48000); part=samples[start:start+2400]
                self.assertGreater(math.sqrt(sum(x*x for x in part)/len(part)),.005)
            self.assertAlmostEqual(len(samples)/48000,5.4,delta=.03)
            self.assertTrue(job.log_path.is_file())

    def test_nine_pairs_at_actual_720p(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); clips,audio=self.project(folder,36)
            destination,job=self.render(folder,clips,audio,1280,720)
            probe=Path(app.ffmpeg()).with_name('ffprobe.exe')
            info=json.loads(subprocess.check_output([str(probe),'-v','error','-show_streams','-of','json',str(destination)]))
            video=next(s for s in info['streams'] if s['codec_type']=='video')
            self.assertEqual((video['width'],video['height']),(1280,720))
            self.assertEqual(int(video['nb_frames']),324)
            self.assertAlmostEqual(float(video['duration']),10.8,delta=.002)
            self.assertTrue(any(s['codec_type']=='audio' for s in info['streams']))
            self.assertEqual(job.encoded_segments,4)

    def test_continuing_clip_trim_simultaneous_lanes_and_black_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); changing=folder/'changing.mp4'; blue=folder/'blue.mp4'; sound=folder/'song.wav'
            ff(['-f','lavfi','-i',"color=blue:s=160x240:r=30:d=1.5,drawbox=color=red:t=fill:enable='gte(t,0.5)',drawbox=color=green:t=fill:enable='gte(t,1)'",'-c:v','libx264',str(changing)])
            ff(['-f','lavfi','-i','color=blue:s=160x240:r=30:d=1','-c:v','libx264',str(blue)])
            ff(['-f','lavfi','-i','sine=duration=1.4',str(sound)])
            clips=[clip(changing,'g',0,.1,.2,1.3,1.5),clip(blue,'d',1,.4,0.,.8,1.)]
            destination,job=self.render(folder,clips,[music(sound,1.4)])
            raw=ff(['-i',str(destination),'-an','-vf','fps=10','-f','rawvideo','-pix_fmt','rgb24','pipe:1']).stdout
            def pixel(frame,x):
                offset=(frame*320*180+90*320+x)*3; return tuple(raw[offset:offset+3])
            self.assertGreater(pixel(2,80)[2],200); self.assertLess(max(pixel(2,240)),6)
            self.assertGreater(pixel(6,80)[0],200); self.assertGreater(pixel(6,240)[2],200)
            self.assertGreater(pixel(10,80)[1],70)
            self.assertLess(max(pixel(13,80)),6); self.assertLess(max(pixel(13,240)),6)

if __name__=='__main__':unittest.main()
