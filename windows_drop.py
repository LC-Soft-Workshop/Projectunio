"""Receive WM_DROPFILES without calling Tcl from a native Windows callback.

Windows sends shell messages outside Tk's normal event dispatch. Queue the paths
and invoke application code only from a Tk-owned polling callback.
"""
import ctypes
from ctypes import wintypes
import logging
import os
import queue
import sys


class FileDrop:
    def __init__(self,widget,callback,with_position=False):
        self.widget=widget; self.callback=callback; self.hwnd=widget.winfo_id(); self.active=False
        self.with_position=with_position
        self.pending=queue.SimpleQueue(); self.timer=None
        if os.name!='nt':return
        self.shell=ctypes.WinDLL('shell32',use_last_error=True)
        self.controls=ctypes.WinDLL('comctl32',use_last_error=True)
        self.shell.DragAcceptFiles.argtypes=[wintypes.HWND,wintypes.BOOL]
        self.shell.DragQueryFileW.argtypes=[wintypes.HANDLE,wintypes.UINT,wintypes.LPWSTR,wintypes.UINT]
        self.shell.DragQueryFileW.restype=wintypes.UINT
        self.shell.DragFinish.argtypes=[wintypes.HANDLE]
        self.shell.DragQueryPoint.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.POINT)]
        self.shell.DragQueryPoint.restype=wintypes.BOOL
        proc=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,ctypes.c_size_t,ctypes.c_size_t)
        self.controls.SetWindowSubclass.argtypes=[wintypes.HWND,proc,ctypes.c_size_t,ctypes.c_size_t]
        self.controls.SetWindowSubclass.restype=wintypes.BOOL
        self.controls.RemoveWindowSubclass.argtypes=[wintypes.HWND,proc,ctypes.c_size_t]
        self.controls.RemoveWindowSubclass.restype=wintypes.BOOL
        self.controls.DefSubclassProc.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.controls.DefSubclassProc.restype=ctypes.c_ssize_t
        def receive(hwnd,msg,wp,lp,identity,refdata):
            if msg==0x0233:
                paths=[]
                try:
                    for i in range(self.shell.DragQueryFileW(wp,0xffffffff,None,0)):
                        count=self.shell.DragQueryFileW(wp,i,None,0); buf=ctypes.create_unicode_buffer(count+1)
                        self.shell.DragQueryFileW(wp,i,buf,count+1); paths.append(buf.value)
                    if self.with_position:
                        point=wintypes.POINT()
                        position=(point.x,point.y) if self.shell.DragQueryPoint(wp,ctypes.byref(point)) else (None,None)
                        self.pending.put((paths,*position))
                    else:self.pending.put(paths)
                    logging.info('Dépôt Windows reçu : %r',paths)
                except Exception:
                    logging.exception('Erreur de réception du dépôt Windows')
                finally:self.shell.DragFinish(wp)
                return 0
            if msg==0x0082:  # WM_NCDESTROY: remove while the HWND still exists.
                self.controls.RemoveWindowSubclass(hwnd,self.proc,1)
                self.active=False
            return self.controls.DefSubclassProc(hwnd,msg,wp,lp)
        self.proc=proc(receive)
        # SetWindowSubclass maintains the original handler and safely chains it.
        # https://learn.microsoft.com/en-us/windows/win32/api/commctrl/nf-commctrl-setwindowsubclass
        if not self.controls.SetWindowSubclass(self.hwnd,self.proc,1,0):raise OSError('Impossible d’activer le dépôt de fichiers Windows.')
        self.active=True; self.shell.DragAcceptFiles(self.hwnd,True)
        widget.bind('<Destroy>',self.close,add='+')
        self.timer=widget.after(50,self.poll)

    def poll(self):
        self.timer=None
        if not self.active:return
        try:
            paths=self.pending.get_nowait()
        except queue.Empty:paths=None
        try:
            if paths:
                if self.with_position:self.callback(*paths)
                else:self.callback(paths)
        except Exception:
            logging.exception('Erreur lors de l’import des vidéos déposées')
            self.widget._root().report_callback_exception(*sys.exc_info())
        finally:
            if self.active:self.timer=self.widget.after(50,self.poll)

    def close(self,event=None):
        if event is not None and event.widget!=self.widget:return
        if self.timer is not None:
            self.widget.after_cancel(self.timer); self.timer=None
        if self.active:
            self.shell.DragAcceptFiles(self.hwnd,False)
            self.controls.RemoveWindowSubclass(self.hwnd,self.proc,1); self.active=False
