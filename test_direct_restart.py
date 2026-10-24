from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
import app
from direct_preview import DirectPreview


class DirectRestartTests(unittest.TestCase):
    def wait_for(self,root,predicate):
        deadline=time.monotonic()+15
        def poll():
            if predicate() or time.monotonic()>deadline:root.quit()
            else:root.after(10,poll)
        poll(); root.mainloop(); self.assertTrue(predicate())

    def test_replay_after_late_seek_and_restart_button_return_to_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'red-then-blue.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=80x80:r=30:d=0.8',
                '-vf',"drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='gte(t,0.4)'",'-c:v','libx264',str(source)],capture_output=True,check=True,timeout=30)
            clip=dict(id='clip',path=str(source),lane=0,start=0.,duration=.8,volume=1.,audio=False,fit='Remplir',**{'in':0.,'out':.8})
            zones=[[[0.,0.],[1.,0.],[1.,1.],[0.,1.]]]
            root=tk.Tk(); player=DirectPreview(root,app.ffmpeg(),zones,[clip],[],.6,app.mask,app.graph,app.project)
            try:
                self.wait_for(root,lambda:player.ended)
                self.assertEqual(player.button.cget('text'),'Relire')
                geometry=player.win.geometry(); player.grid.set(True)
                player.button.invoke()
                self.assertEqual(player.position,0.); self.assertEqual(player.seek.get(),0.)
                self.wait_for(root,lambda:player.frame is not None)
                w,h,pixels=player.frame; offset=((h//2)*w+w//2)*3
                self.assertGreater(pixels[offset],200); self.assertLess(pixels[offset+2],30)
                self.assertEqual(player.win.geometry(),geometry); self.assertTrue(player.grid.get())
                player.launch(.6)
                bar=player.win.winfo_children()[0]
                restart=next(w for w in bar.winfo_children() if isinstance(w,ttk.Button) and w.cget('text')=='Recommencer au début')
                restart.invoke(); self.assertEqual(player.position,0.); self.assertEqual(player.seek.get(),0.)
                self.wait_for(root,lambda:player.frame is not None)
                self.assertGreater(player.frame[2][offset],200)
                player.loop_in.set('0,2'); player.loop_out.set('0,5'); player.loop.set(True); player.apply_loop()
                self.wait_for(root,lambda:player.loop_count>=2)
                self.assertFalse(player.ended); self.assertAlmostEqual(player.position,.2)
                player.toggle(); count=player.loop_count
                deadline=time.monotonic()+.4
                self.wait_for(root,lambda:time.monotonic()>=deadline)
                self.assertEqual(player.loop_count,count); self.assertFalse(player.playing.is_set())
                player.toggle(); self.wait_for(root,lambda:player.loop_count>count)
                player.loop.set(False); player.apply_loop()
                self.wait_for(root,lambda:player.ended)
                player.loop_in.set('0.6'); player.loop_out.set('0.2'); player.loop.set(True)
                with patch('direct_preview.messagebox.showerror') as error:
                    player.apply_loop(); error.assert_called_once()
                self.assertFalse(player.loop.get())
            finally:
                player.close(); root.destroy()
                for worker in player.workers+player.retired:worker.join(5)


if __name__=='__main__':unittest.main()
