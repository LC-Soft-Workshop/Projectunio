"""Asynchronous frozen timeline frame, using the export composition engine."""
import copy
import logging
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import tkinter as tk
import montage


def read_ppm(data):
    magic,size,maximum,pixels=data.split(b'\n',3)
    w,h=map(int,size.split())
    if magic!=b'P6' or maximum!=b'255' or len(pixels)!=w*h*3:raise ValueError('Image d’aperçu invalide.')
    return w,h,pixels


def resize_ppm(frame,w,h):
    """Resize the video to exactly the same rectangle as the mapping handles."""
    sw,sh,pixels=frame
    xs=[min(sw-1,int(x*sw/w))*3 for x in range(w)]
    rows={}; output=[]
    for y in range(h):
        sy=min(sh-1,int(y*sh/h))
        if sy not in rows:
            row=memoryview(pixels)[sy*sw*3:(sy+1)*sw*3]
            rows[sy]=b''.join(row[x:x+3] for x in xs)
        output.append(rows[sy])
    return f'P6\n{w} {h}\n255\n'.encode()+b''.join(output)


class MappingStill:
    def __init__(self,root,executable,mask,graph,callback):
        self.root=root; self.executable=executable; self.mask=mask; self.graph=graph; self.callback=callback
        self.closed=False; self.generation=0; self.jobs=queue.Queue(maxsize=1); self.results=queue.SimpleQueue(); self.proc=None
        self.worker=threading.Thread(target=self.run,daemon=True); self.worker.start()
        self.timer=root.after(40,self.poll)
        root.bind('<Destroy>',lambda e:self.close() if e.widget==root else None,add='+')

    def request(self,clips,zones,position):
        if self.closed:return
        if hasattr(self,'resolve_clips'):clips=self.resolve_clips(clips)
        self.generation+=1
        proc=self.proc
        try:self.jobs.get_nowait()
        except queue.Empty:pass
        self.jobs.put_nowait((self.generation,copy.deepcopy(clips),copy.deepcopy(zones),position))
        if proc and proc.poll() is None:
            try:proc.terminate()
            except OSError:pass

    def cancel_pending(self):
        if self.closed:return
        self.generation+=1
        try:self.jobs.get_nowait()
        except queue.Empty:pass
        proc=self.proc
        if proc and proc.poll() is None:
            try:proc.terminate()
            except OSError:pass

    def run(self):
        while not self.closed:
            job=self.jobs.get()
            if job is None or self.closed:return
            generation,clips,zones,position=job
            try:
                with tempfile.TemporaryDirectory(prefix='projectunio-still-') as folder:
                    args=montage.render_args(clips,zones,folder,self.mask,self.graph,960,540,still_at=position)
                    if self.closed or generation!=self.generation:continue
                    self.proc=subprocess.Popen([self.executable,'-v','error',*args,'-an','-frames:v','1','-f','image2pipe','-c:v','ppm','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000 if os.name=='nt' else 0)
                    if self.closed or generation!=self.generation:self.proc.terminate()
                    try:data,error=self.proc.communicate(timeout=25)
                    except subprocess.TimeoutExpired:
                        self.proc.kill(); self.proc.communicate(); raise RuntimeError('Le calcul de l’image a dépassé le délai prévu.')
                    if self.proc.returncode:raise RuntimeError(error.decode(errors='replace')[-800:])
                    self.results.put((generation,read_ppm(data),None))
            except Exception as e:
                if generation==self.generation and not self.closed:
                    logging.exception('Image de mapping à %.3f s',position)
                    self.results.put((generation,None,str(e)))
            finally:self.proc=None

    def poll(self):
        if self.closed:return
        while True:
            try:generation,frame,error=self.results.get_nowait()
            except queue.Empty:break
            if generation==self.generation:self.callback(frame,error)
        self.timer=self.root.after(40,self.poll)

    def close(self):
        if self.closed:return
        self.closed=True
        try:self.root.after_cancel(self.timer)
        except tk.TclError:pass
        try:self.jobs.get_nowait()
        except queue.Empty:pass
        self.jobs.put_nowait(None)
        proc=self.proc
        if proc and proc.poll() is None:
            try:proc.terminate()
            except OSError:pass
