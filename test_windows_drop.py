import ctypes
import struct
import tkinter as tk
import unittest
from unittest.mock import patch
from windows_drop import FileDrop


def post_drop(hwnd,paths,point=(0,0)):
    kernel=ctypes.WinDLL('kernel32'); user=ctypes.WinDLL('user32')
    kernel.GlobalAlloc.argtypes=[ctypes.c_uint,ctypes.c_size_t]; kernel.GlobalAlloc.restype=ctypes.c_void_p
    kernel.GlobalLock.argtypes=[ctypes.c_void_p]; kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[ctypes.c_void_p]
    user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    data=struct.pack('<IiiII',20,*point,0,1)+('\0'.join(paths)+'\0\0').encode('utf-16-le')
    handle=kernel.GlobalAlloc(0x42,len(data)); ptr=kernel.GlobalLock(handle)
    ctypes.memmove(ptr,data,len(data)); kernel.GlobalUnlock(handle)
    if not user.PostMessageW(hwnd,0x233,handle,0):raise ctypes.WinError()


class WindowsDropTests(unittest.TestCase):
    def test_drop_position_is_captured_before_cursor_moves_without_tcl(self):
        root=tk.Tk(); canvas=tk.Canvas(root); canvas.pack(); root.update()
        received=[]; drop=FileDrop(canvas,lambda *values:received.append(values),with_position=True)
        try:
            with patch.object(canvas,'after_idle',side_effect=AssertionError('Native handler called Tcl')):
                post_drop(canvas.winfo_id(),['C:\\Vidéos\\été.mp4'],(185,95))
                post_drop(canvas.winfo_id(),['C:\\Musique\\son.wav'],(240,145))
                root.after(220,root.quit); root.mainloop()
            self.assertEqual(received,[(['C:\\Vidéos\\été.mp4'],185,95),(['C:\\Musique\\son.wav'],240,145)])
        finally:root.destroy()

    def test_posted_drops_do_not_reenter_tk(self):
        root=tk.Tk(); card=tk.Canvas(root); card.pack(); root.update()
        received=[]; drop=FileDrop(card,received.append)
        try:
            with patch.object(card,'after_idle',side_effect=AssertionError('Native handler called Tcl')):
                post_drop(card.winfo_id(),['C:\\Vidéos\\été 1.mp4','C:\\Vidéos\\2.mp4'])
                post_drop(card.winfo_id(),['C:\\Vidéos\\3.mp4'])
                root.after(220,root.quit); root.mainloop()
            self.assertEqual(received,[['C:\\Vidéos\\été 1.mp4','C:\\Vidéos\\2.mp4'],['C:\\Vidéos\\3.mp4']])
            drop.close(); self.assertFalse(drop.active); self.assertIsNone(drop.timer)
        finally:root.destroy()

    def test_import_exception_does_not_disable_next_drop(self):
        root=tk.Tk(); card=tk.Canvas(root); card.pack(); root.update()
        errors=[]; received=[]
        root.report_callback_exception=lambda *args:errors.append(args[1])
        def receive(paths):
            if paths==['bad']:raise ValueError('Test import failure')
            received.append(paths)
        drop=FileDrop(card,receive)
        try:
            with self.assertLogs(level='ERROR'):
                post_drop(card.winfo_id(),['bad']); post_drop(card.winfo_id(),['good'])
                root.after(220,root.quit); root.mainloop()
            self.assertEqual(len(errors),1); self.assertEqual(received,[['good']]); self.assertTrue(drop.active)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
