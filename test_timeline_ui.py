import ctypes
from pathlib import Path
import tempfile
import subprocess
import tkinter as tk
import unittest
from unittest.mock import patch
import app


class TimelineUITests(unittest.TestCase):
    def test_drop_edit_save_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); video=folder/'clip été test.mp4'; project=folder/'spectacle.json'
            subprocess.run([app.ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=red:s=180x320:d=1','-c:v','libx264',str(video)],capture_output=True,check=True,timeout=20)
            root=tk.Tk(); a=app.App(root); root.update()
            try:
                # Exercise the actual WM_DROPFILES handler, including UTF-16 paths.
                kernel=ctypes.WinDLL('kernel32'); user=ctypes.WinDLL('user32')
                kernel.GlobalAlloc.argtypes=[ctypes.c_uint,ctypes.c_size_t]; kernel.GlobalAlloc.restype=ctypes.c_void_p
                kernel.GlobalLock.argtypes=[ctypes.c_void_p]; kernel.GlobalLock.restype=ctypes.c_void_p
                kernel.GlobalUnlock.argtypes=[ctypes.c_void_p]
                user.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
                payload=(str(video)+'\0\0').encode('utf-16-le')
                import struct
                data=struct.pack('<IiiII',20,85,45,0,1)+payload
                handle=kernel.GlobalAlloc(0x42,len(data)); ptr=kernel.GlobalLock(handle)
                ctypes.memmove(ptr,data,len(data)); kernel.GlobalUnlock(handle)
                user.SendMessageW(a.timeline.canvas.winfo_id(),0x233,handle,0)
                # Native callbacks must not invoke Tcl or perform an import inline.
                self.assertEqual(a.data['clips'],[])
                root.after(120,root.quit); root.mainloop()
                self.assertEqual(len(a.data['clips']),1)
                self.assertEqual(a.data['clips'][0]['path'],str(video))
                a.timeline.import_files(1,[str(video)]); root.update()
                self.assertEqual([c['start'] for c in a.data['clips']],[0,0])
                a.timeline.fields['start'].set('0.5'); a.timeline.fields['in'].set('0.2'); a.timeline.fields['out'].set('0.7'); a.timeline.apply()
                self.assertAlmostEqual(a.data['clips'][1]['start'],.5)
                a.undo(); self.assertEqual(a.data['clips'][1]['start'],0)
                with patch('app.filedialog.asksaveasfilename',return_value=str(project)):a.save()
                a.data['clips']=[]
                with patch('app.filedialog.askopenfilename',return_value=str(project)):a.load()
                self.assertEqual(len(a.data['clips']),2)
                self.assertEqual(a.data['clips'][0]['path'],str(video.resolve()))
            finally:root.destroy()

if __name__=='__main__':unittest.main()
