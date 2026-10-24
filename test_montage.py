import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import app
import montage


def clip(path,lane,start=0,begin=0,end=.4,audio=False):
    return dict(id=str(path)+str(start),path=str(path),lane=lane,start=start,**{'in':begin,'out':end},duration=1.,audio=audio,volume=1.,fit='Remplir')


class MontageTests(unittest.TestCase):
    def test_conflicts(self):
        a=clip('a',0); b=clip('b',1)
        montage.validate([a,b])
        b['lane']=0
        with self.assertRaises(ValueError):montage.validate([a,b])
        b['start']=.4; montage.validate([a,b])
        b['out']=float('nan')
        with self.assertRaises(ValueError):montage.validate([a,b])

    def test_simultaneous_trim_gaps_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for color in ['red','blue','green']:
                args=[app.ffmpeg(),'-v','error','-y','-f','lavfi','-i',f'color={color}:s=120x180:r=30:d=1']
                if color=='red':args+=['-f','lavfi','-i','sine=duration=1','-c:a','aac']
                subprocess.run(args+['-c:v','libx264',str(folder/(color+'.mp4'))],check=True,capture_output=True,timeout=20)
            clips=[clip(folder/'red.mp4',0,.1,.2,.6,True),clip(folder/'blue.mp4',1,0,0,.6),clip(folder/'green.mp4',0,.8)]
            args=montage.render_args(clips,app.DEFAULT['zones'],folder,app.mask,app.graph,320,180)
            subprocess.run([app.ffmpeg(),'-v','error','-y',*args,*app.output_options(False),str(folder/'montage.mp4')],check=True,capture_output=True,timeout=30)
            raw=subprocess.check_output([app.ffmpeg(),'-v','error','-i',str(folder/'montage.mp4'),'-vf','fps=10','-an','-f','rawvideo','-pix_fmt','rgb24','-'],timeout=20)
            def pixel(frame,x):
                offset=(frame*320*180+90*320+x)*3
                return tuple(raw[offset:offset+3])
            self.assertLess(max(pixel(0,80)),5)
            self.assertGreater(pixel(0,240)[2],200)
            self.assertGreater(pixel(2,80)[0],200)
            self.assertGreater(pixel(2,240)[2],200)
            self.assertLess(max(pixel(6,80)),5)
            self.assertLess(max(pixel(6,240)),5)
            self.assertGreater(pixel(10,80)[1],70)
            self.assertLess(max(pixel(10,240)),5)
            info=json.loads(subprocess.check_output([str(Path(app.ffmpeg()).with_name('ffprobe.exe')),'-v','error','-show_streams','-of','json',str(folder/'montage.mp4')]))
            self.assertEqual({s['codec_type'] for s in info['streams']},{'audio','video'})
            self.assertAlmostEqual(float(info['streams'][0]['duration']),1.2,delta=.1)

if __name__=='__main__':unittest.main()
