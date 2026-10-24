"""Small background thumbnails and disposable video proxies; models keep originals."""
from collections import OrderedDict
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import tkinter as tk
import montage
from render_cache import RenderCache,digest

PROXY_ROOT=Path(__file__).resolve().parent/'work-media'


def stamp(path):
    try:
        s=Path(path).stat(); return s.st_size,s.st_mtime_ns
    except OSError:return None


def checked_process(command,cancel,timeout=300,progress=lambda text:None):
    with tempfile.TemporaryFile() as error:
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=error,creationflags=0x08000000 if os.name=='nt' else 0)
        try:
            while True:
                if cancel.is_set():raise RuntimeError('Opération annulée.')
                try:
                    out,_=proc.communicate(timeout=.1); break
                except subprocess.TimeoutExpired:
                    timeout-=.1
                    if timeout<=0:raise ValueError('Le calcul a dépassé le délai prévu.')
            if proc.returncode:
                error.seek(0); raise ValueError(error.read().decode(errors='replace')[-700:] or 'Décodage impossible.')
            return out
        finally:
            if proc.poll() is None:proc.terminate()
            proc.wait()
            if proc.stdout:proc.stdout.close()


def prepare_proxies(paths,executable,cancel,progress=lambda text:None,root=PROXY_ROOT):
    cache=RenderCache(root,limit=4*1024**3); records={}; errors=[]
    def check():
        if cancel.is_set():raise RuntimeError('Opération annulée.')
    for index,path in enumerate(dict.fromkeys(paths),1):
        check()
        if montage.image_path(path):continue
        progress(f'Copie de travail {index}/{len(set(paths))} : {Path(path).name}')
        try:
            before=stamp(path)
            if before is None:raise ValueError('Média introuvable.')
            source_hash=digest(path,check); binary=stamp(executable)
            key=hashlib.sha256(json.dumps([1,source_hash,binary,'640x360-H264-AAC']).encode()).hexdigest()
            with tempfile.TemporaryDirectory(prefix='projectunio-proxy-') as folder:
                target=Path(folder)/'proxy.mp4'
                if not cache.restore(key,target,check):
                    checked_process([executable,'-v','error','-nostdin','-y','-i',str(path),'-map','0:v:0','-map','0:a:0?',
                        '-vf','scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1',
                        '-c:v','libx264','-preset','ultrafast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',str(target)],cancel,timeout=3600)
                    source_duration,_=montage.probe(path,executable); proxy_duration,_=montage.probe(target,executable)
                    if abs(source_duration-proxy_duration)>1/30+.005:raise ValueError('La durée de la copie ne correspond pas à la source.')
                    check()
                    if stamp(path)!=before:raise ValueError('Source modifiée pendant la préparation.')
                    cache.store(key,target,check)
                cached=Path(root)/(key+'.mp4')
                if not cached.is_file():raise ValueError('Copie non conservée : vérifiez l’espace et l’accès au dossier work-media (limite 4 Go).')
                records[str(path)]=(before,str(cached),stamp(cached))
        except Exception as e:
            check(); errors.append(Path(path).name+' : '+str(e))
    return records,errors


class WorkMedia:
    def __init__(self,root,executable,on_change):
        self.root=root; self.executable=executable; self.on_change=on_change; self.closed=False; self.cancel=threading.Event()
        self.jobs=queue.Queue(maxsize=48); self.results=queue.SimpleQueue(); self.pending=set(); self.wanted=set(); self.images=OrderedDict(); self.visible_images=[]
        self.records={}; self.enabled=tk.BooleanVar(value=True)
        self.worker=threading.Thread(target=self.run,daemon=True); self.worker.start(); self.timer=root.after(80,self.poll)
        root.bind('<Destroy>',lambda e:self.close() if e.widget==root else None,add='+')

    def resolve(self,clips):
        result=copy.deepcopy(clips)
        if self.closed or not self.enabled.get():return result
        for clip in result:
            if clip.get('kind') in ('audio','image'):continue
            record=self.records.get(clip['path'])
            if record and stamp(clip['path'])==record[0] and stamp(record[1])==record[2]:
                clip['_audio_path']=clip['path']; clip['_original_path']=clip['path']; clip['path']=record[1]
        return result

    def begin_draw(self):self.wanted=set(); self.visible_images=[]

    def thumbnail(self,path,at):
        if self.closed:return None
        identity=stamp(path)
        if identity is None:return None
        key=(path,identity,0. if montage.image_path(path) else round(max(0.,at)*30)/30); self.wanted.add(key)
        image=self.images.get(key)
        if image is not None:
            self.images.move_to_end(key); self.visible_images.append(image); return image
        if key not in self.pending:
            try:self.jobs.put_nowait(key); self.pending.add(key)
            except queue.Full:pass
        return None

    def run(self):
        while not self.cancel.is_set():
            key=self.jobs.get()
            if key is None:return
            path,identity,at=key
            if key not in self.wanted:self.results.put((key,None)); continue
            try:
                pixels=checked_process([self.executable,'-v','error','-ss',f'{at:.9f}','-i',path,'-an','-frames:v','1',
                    '-vf','scale=64:36:force_original_aspect_ratio=decrease,pad=64:36:(ow-iw)/2:(oh-ih)/2:black',
                    '-f','image2pipe','-c:v','ppm','pipe:1'],self.cancel,timeout=12)
                self.results.put((key,pixels))
            except Exception:self.results.put((key,None))

    def poll(self):
        if self.closed:return
        changed=False
        while True:
            try:key,pixels=self.results.get_nowait()
            except queue.Empty:break
            self.pending.discard(key)
            if pixels and stamp(key[0])==key[1]:
                try:self.images[key]=tk.PhotoImage(data=pixels); changed=True
                except tk.TclError:pass
            while len(self.images)>256:self.images.popitem(last=False)
        if changed:self.on_change()
        self.timer=self.root.after(80,self.poll)

    def close(self):
        if self.closed:return
        self.closed=True; self.cancel.set()
        try:self.root.after_cancel(self.timer)
        except tk.TclError:pass
        while True:
            try:self.jobs.get_nowait()
            except queue.Empty:break
        self.jobs.put_nowait(None); self.images.clear(); self.visible_images=[]
        self.enabled=None; self.on_change=lambda:None; self.root=None
