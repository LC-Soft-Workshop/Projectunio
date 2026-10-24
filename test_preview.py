"""Integration test: actual Tk playback, optional overlay, pause and cleanup."""
from pathlib import Path
import subprocess
import tempfile
import tkinter as tk
import unittest
import app
from preview import VideoPreview


class PlaybackTest(unittest.TestCase):
    def test_play_pause_grid(self):
        with tempfile.TemporaryDirectory() as folder:
            movie=Path(folder)/'video.mp4'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=3','-f','lavfi','-i','sine=duration=3','-c:v','libx264','-c:a','aac',str(movie)],check=True,capture_output=True,timeout=20)
            root=tk.Tk(); root.withdraw(); errors=[]; completed=[]
            player=VideoPreview(root,movie,app.DEFAULT['zones'],app.ffmpeg(),app.project,lambda:completed.append(True))
            def check():
                try:
                    self.assertGreater(player.frame_number,1)
                    player.toggle(); count=player.frame_number
                    self.assertFalse(player.playing)
                    player.grid.set(True); player.overlay()
                    self.assertGreater(len(player.canvas.find_withtag('grid')),10)
                    player.grid.set(False); player.overlay()
                    self.assertEqual(len(player.canvas.find_withtag('grid')),0)
                    def resume():
                        try:
                            self.assertEqual(player.frame_number,count)
                            player.toggle(); self.assertTrue(player.playing)
                            identity=player.win.winfo_id(); geometry=player.win.geometry()
                            player.grid.set(True); player.restart()
                            def check_restart():
                                try:
                                    self.assertEqual(player.win.winfo_id(),identity)
                                    self.assertEqual(player.win.geometry(),geometry)
                                    self.assertTrue(player.grid.get())
                                    self.assertGreater(player.frame_number,0)
                                except Exception as e:errors.append(e)
                            root.after(500,check_restart)
                        except Exception as e:errors.append(e)
                    root.after(100,resume)
                except Exception as e:errors.append(e)
            root.after(1800,check)
            root.after(3000,player.close)
            root.after(3500,root.quit)
            root.mainloop(); player.close(); player.worker.join(timeout=5); root.destroy()
            if errors:raise errors[0]
            self.assertFalse(player.worker.is_alive())

if __name__=='__main__':unittest.main()
