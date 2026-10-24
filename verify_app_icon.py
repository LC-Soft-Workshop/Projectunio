import ctypes
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import time
import tkinter as tk
from package_portable import FILES,SOURCE,ROOT

for name in FILES:
    (SOURCE/name).parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/name,SOURCE/name)
shutil.copy2(ROOT/'PORTABLE-LIRE-MOI.txt',SOURCE/'LIRE-MOI.txt')
icon=ROOT/'assets'/'projectunio.ico'
raw=icon.read_bytes(); assert raw[:4]==b'\x00\x00\x01\x00' and int.from_bytes(raw[4:6],'little')==10
shell=ctypes.windll.shell32
shell.ExtractIconExW.argtypes=[ctypes.c_wchar_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
assert shell.ExtractIconExW(str(SOURCE/'Projectunio.exe'),-1,None,None,0)>=1

# Exercise the actual launcher from a folder containing spaces and accents.
with tempfile.TemporaryDirectory(prefix='Lanceur icône ',dir=ROOT/'test-output') as folder:
    folder=Path(folder); shutil.copy2(SOURCE/'Projectunio.exe',folder/'Projectunio.exe')
    (folder/'app.py').write_text("from pathlib import Path\nPath(__file__).with_name('started.txt').write_text(str(Path.cwd()),encoding='utf-8')\n",encoding='utf-8')
    env=dict(os.environ); env['PATH']=str(SOURCE/'runtime'/'python')+os.pathsep+env['PATH']
    result=subprocess.run([str(folder/'Projectunio.exe')],env=env,timeout=15); assert result.returncode==0
    marker=folder/'started.txt'; until=time.monotonic()+15
    while not marker.exists() and time.monotonic()<until:time.sleep(.1)
    assert marker.exists() and Path(marker.read_text(encoding='utf-8'))==folder

script=SOURCE/'_icon_smoke.py'
script.write_text('''from pathlib import Path
import sys,tkinter as tk,ctypes
sys.path.insert(0,str(Path(__file__).resolve().parent))
import app
root=tk.Tk(); a=app.App(root); root.update()
user=ctypes.windll.user32
user.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]; user.GetAncestor.restype=ctypes.c_void_p
user.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]; user.SendMessageW.restype=ctypes.c_ssize_t
hwnd=user.GetAncestor(root.winfo_id(),2)
assert user.SendMessageW(hwnd,0x7f,1,0) and user.SendMessageW(hwnd,0x7f,0,0)
child=tk.Toplevel(root); root.update(); child.destroy(); root.destroy()
for worker in (a.timeline_tools.worker,a.still_renderer.worker,a.live_audio.worker,a.media_work.worker):worker.join(10)
print('Icône de fenêtre et lanceur portable vérifiés.')
''',encoding='utf-8')
try:
    env=dict(os.environ,PROJECTUNIO_RECOVERY_DIR=str(ROOT/'test-output'/'icon-smoke-recovery'))
    subprocess.run([str(SOURCE/'runtime/python/python.exe'),str(script)],check=True,timeout=40,env=env)
finally:script.unlink(missing_ok=True)
