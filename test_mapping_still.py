import copy
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import app
import montage
from mapping_still import read_ppm


def make_source(path):
    subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i',"color=black:s=160x240:r=30:d=2,drawbox=color=red:t=fill:enable='between(t,0.5,1.5)'",'-c:v','libx264',str(path)],capture_output=True,check=True,timeout=20)


def make_clip(path):
    return dict(id='test',path=str(path),lane=0,start=.2,**{'in':.3,'out':1.8},duration=2.,audio=False,volume=1.,fit='Remplir')


class FrozenMappingTests(unittest.TestCase):
    def test_seek_respects_source_trim_and_black_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); source=folder/'black-red-black.mp4'; make_source(source); clip=make_clip(source)
            def pixel(position):
                args=montage.render_args([clip],app.DEFAULT['zones'],folder,app.mask,app.graph,320,180,still_at=position)
                data=subprocess.check_output([app.ffmpeg(),'-v','error',*args,'-an','-frames:v','1','-f','image2pipe','-c:v','ppm','pipe:1'],timeout=20)
                w,h,rgb=read_ppm(data); offset=(90*w+80)*3
                return rgb[offset:offset+3]
            self.assertLess(max(pixel(.05)),5)  # gap before the clip
            self.assertLess(max(pixel(.2)),5)   # black source at .3
            self.assertGreater(pixel(.8)[0],200) # seek to source .9, not its black first image
            self.assertLess(max(pixel(1.6)),5)  # black source at 1.7
            self.assertLess(max(pixel(1.7)),5)  # exact clip end is an empty interval

    def test_edit_mapping_on_selected_still(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'clip.mp4'; make_source(source)
            root=tk.Tk(); a=app.App(root); root.update()
            a.data['clips']=[make_clip(source)]; a.refresh()
            def wait_ready():
                deadline=time.monotonic()+12
                def check():
                    if a.still_frame is not None and a.still_status.get().startswith('Image arrêtée'):root.quit()
                    elif time.monotonic()>deadline:root.quit()
                    else:root.after(30,check)
                root.after(30,check); root.mainloop()
                self.assertIsNotNone(a.still_frame)
                self.assertTrue(a.still_status.get().startswith('Image arrêtée'),a.still_status.get())
            try:
                from types import SimpleNamespace
                a.timeline.press(SimpleNamespace(x=85+.8*40,y=10)); a.timeline.release(SimpleNamespace())
                wait_ready()
                self.assertAlmostEqual(a.playhead,.8)
                self.assertTrue(a.canvas.find_withtag('mapping_image'))
                w,h,pixels=a.still_frame; self.assertGreater(pixels[(270*w+230)*3],200)
                clips=copy.deepcopy(a.data['clips'])
                a.x.set('10'); a.y.set('15'); a.numeric(); wait_ready()
                self.assertEqual(a.data['clips'],clips)
                self.assertAlmostEqual(a.playhead,.8)
                self.assertEqual(a.data['zones'][0][0],[.1,.15])
                a.monitors=[(0,0,640,360)]; a.screen.current(0)
                with patch('app.messagebox.showinfo'):a.projector(True)
                root.update()
                self.assertTrue(a.output.canvas.find_withtag('mapping_image'))
                a.output.destroy()
            finally:
                root.destroy(); a.still_renderer.worker.join(timeout=10)
                self.assertFalse(a.still_renderer.worker.is_alive())

if __name__=='__main__':unittest.main()
