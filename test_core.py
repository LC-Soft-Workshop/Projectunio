import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
import app

class CoreTests(unittest.TestCase):
    def test_preview_with_audio_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            app.mask(p/'mask.pgm',app.DEFAULT['zones'][0],1280,720)
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=180x320:r=24:d=0.5','-f','lavfi','-i','sine=duration=0.5','-c:v','libx264','-c:a','aac',str(p/'source.mp4')],check=True,capture_output=True,timeout=20)
            base=[app.ffmpeg(),'-v','error','-y','-i',str(p/'source.mp4'),'-loop','1','-i',str(p/'mask.pgm'),'-filter_complex',app.graph(app.DEFAULT['zones'][0],1280,720),'-map','[out]','-map','0:a:0?','-t','0.5']
            subprocess.run(base+app.output_options(True)+[str(p/'preview.ppm')],check=True,capture_output=True,timeout=20)
            self.assertTrue((p/'preview.ppm').read_bytes().startswith(b'P6'))
            subprocess.run(base+app.output_options(False)+[str(p/'final.mp4')],check=True,capture_output=True,timeout=20)
            probe=Path(app.ffmpeg()).with_name('ffprobe.exe')
            import json
            info=json.loads(subprocess.check_output([str(probe),'-v','error','-show_streams','-of','json',str(p/'final.mp4')]))
            self.assertEqual({s['codec_type'] for s in info['streams']},{'audio','video'})

    def test_geometry(self):
        q=app.DEFAULT['zones'][0]
        self.assertTrue(app.valid(q))
        self.assertFalse(app.valid([q[0],q[2],q[1],q[3]]))
        self.assertFalse(app.valid([[0,0]]*4))
        self.assertFalse(app.valid([[float('nan'),0],*q[1:]]))
        for uv,p in zip([(0,0),(1,0),(1,1),(0,1)],q):
            mapped=app.project(q,*uv)
            for a,b in zip(mapped,p): self.assertAlmostEqual(a,b)

    def test_export_silent_and_mask(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); q=copy.deepcopy(app.DEFAULT['zones'][0]); q[1]=[.48,.15]
            app.mask(p/'mask.pgm',q,1280,720)
            cmd=[app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=white:s=240x400:r=30:d=0.3','-loop','1','-i',str(p/'mask.pgm'),'-filter_complex',app.graph(q,1280,720),'-map','[out]','-an','-c:v','libx264',str(p/'test.mp4')]
            cmd[-1:-1]=['-t','0.3']
            subprocess.run(cmd,check=True,timeout=20,capture_output=True)
            self.assertGreater((p/'test.mp4').stat().st_size,500)
            raw=subprocess.run([app.ffmpeg(),'-v','error','-i',str(p/'test.mp4'),'-frames:v','1','-f','rawvideo','-pix_fmt','yuv420p','-'],check=True,capture_output=True,timeout=20).stdout
            # Studio-range YUV black is 16, white is 235.
            self.assertLessEqual(max(raw[y*1280+x] for y in range(720) for x in range(700,1280)),17)
            self.assertGreater(raw[360*1280+300],200)

if __name__=='__main__': unittest.main()
