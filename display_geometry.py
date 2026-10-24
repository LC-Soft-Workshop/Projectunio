"""Physical monitor rectangles and borderless placement on mixed-DPI Windows."""
import ctypes
import os
from contextlib import contextmanager


def enable_per_monitor_dpi():
    if os.name!='nt':return
    user=ctypes.windll.user32
    try:
        user.SetProcessDpiAwarenessContext.argtypes=[ctypes.c_void_p]
        user.SetProcessDpiAwarenessContext.restype=ctypes.c_int
        if user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):return
    except AttributeError:pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2)==0:return
    except AttributeError:pass
    user.SetProcessDPIAware()


@contextmanager
def physical_coordinates():
    previous=None
    if os.name=='nt':
        try:
            setter=ctypes.windll.user32.SetThreadDpiAwarenessContext
            setter.argtypes=[ctypes.c_void_p]; setter.restype=ctypes.c_void_p
            previous=setter(ctypes.c_void_p(-4))
        except AttributeError:pass
    try:yield
    finally:
        if previous:setter(ctypes.c_void_p(previous))


def monitor_rectangles():
    if os.name!='nt':return [(0,0,1280,720)]
    from ctypes.wintypes import RECT
    rects=[]
    callback=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(RECT),ctypes.c_void_p)
    def collect(m,dc,r,data):
        a=r.contents; rects.append((a.left,a.top,a.right-a.left,a.bottom-a.top)); return 1
    with physical_coordinates():
        if not ctypes.windll.user32.EnumDisplayMonitors(None,None,callback(collect),0) or not rects:raise OSError('Impossible de détecter les écrans Windows.')
    return rects


def place_projector_window(window,rectangle):
    x,y,w,h=rectangle
    if os.name!='nt':window.geometry(f'{w}x{h}{x:+d}{y:+d}'); return
    window.update_idletasks()
    user=ctypes.windll.user32
    user.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]; user.GetAncestor.restype=ctypes.c_void_p
    user.SetWindowPos.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
    user.SetWindowPos.restype=ctypes.c_int
    hwnd=user.GetAncestor(window.winfo_id(),2)
    with physical_coordinates():
        if not user.SetWindowPos(hwnd,ctypes.c_void_p(-1),x,y,w,h,0x0040):raise OSError('Impossible de positionner la mire sur le projecteur.')
    window.update_idletasks()
