"""Manual release verification: extracted archive, bundled tools, clean search path."""
from pathlib import Path
import os
import subprocess
import zipfile
import sys
import uuid

root=Path(__file__).resolve().parent
destination=root/'test-output'/('Essai ZIP déplacement '+uuid.uuid4().hex[:8])
destination.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(Path(sys.argv[1]) if len(sys.argv)>1 else root/'dist'/'Projectunio-Portable-Windows-x64.zip') as archive:
    assert archive.testzip() is None
    names=archive.namelist()
    assert not any('/'+part+'/' in name for name in names for part in ('logs','recovery','render-cache','work-media','test-output','.git'))
    assert 'Projectunio-Portable/Projectunio.exe' in names
    assert 'Projectunio-Portable/VERSION' in names
    assert 'Projectunio-Portable/THIRD_PARTY_NOTICES.md' in names
    archive.extractall(destination)
portable=destination/'Projectunio-Portable'
smoke=portable/'_verification.py'
smoke.write_text('''from pathlib import Path
import subprocess
import tkinter as tk
import sys
import app
import montage
root=Path(__file__).resolve().parent
assert Path(app.ffmpeg())==root/'runtime'/'ffmpeg.exe'
movie=root/'verification.mp4'
subprocess.run([app.ffmpeg(),'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=blue:s=128x72:r=30:d=0.2','-f','lavfi','-i','sine=frequency=440:duration=0.2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(movie)],check=True,timeout=30)
duration,audio=montage.probe(str(movie),app.ffmpeg())
assert duration>0 and audio
subprocess.run([app.ffmpeg(),'-hide_banner','-loglevel','error','-i',str(movie),'-frames:v','1',str(root/'verification.ppm')],check=True,timeout=30)
window=tk.Tk(); instance=app.App(window); window.update()
assert instance.timeline.zone_count==2
assert instance.icon_toolbar.buttons['draw'].cget('image')
instance.begin_zone(); instance.cancel_mapping_pointer(); assert instance.drawing_zone is None
instance.mapping_grid.set(True); instance.draw()
assert instance.canvas.find_withtag('mapping_grid')
window.destroy()
instance.timeline_tools.worker.join(5); instance.still_renderer.worker.join(5); instance.live_audio.worker.join(5); instance.media_work.worker.join(5)
assert str(root/'runtime'/'python') in sys.executable
print('OK: interface Tk, mapping, encodage H264/AAC, lecture image et FFprobe avec runtime inclus.')
''',encoding='utf-8')
environment=os.environ.copy()
for key in ('PYTHONHOME','PYTHONPATH','TCL_LIBRARY','TK_LIBRARY'):environment.pop(key,None)
environment['PATH']=str(Path(environment.get('SystemRoot','C:/Windows'))/'System32')
environment['PYTHONNOUSERSITE']='1'
subprocess.run([str(portable/'runtime'/'python'/'python.exe'),'-E','-S',str(smoke)],cwd=portable,env=environment,check=True,timeout=60)
print('ZIP extrait et vérifié dans un chemin différent, avec espaces et accent, sans Python ni FFmpeg système.')
