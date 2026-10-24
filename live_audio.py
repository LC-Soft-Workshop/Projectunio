"""Prepare updated PCM audio without re-encoding the preview's video."""
import copy
import logging
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import tkinter as tk
import montage


class LiveAudio:
    def __init__(self,root,executable,callback):
        self.root=root; self.executable=executable; self.callback=callback; self.closed=False
        self.generation=0; self.jobs=queue.Queue(maxsize=1); self.results=queue.SimpleQueue(); self.proc=None
        self.worker=threading.Thread(target=self.run,daemon=True); self.worker.start()
        self.timer=root.after(50,self.poll)
        root.bind('<Destroy>',lambda e:self.close() if e.widget==root else None,add='+')

    def request(self,signature,clips,audio_clips):
        self.generation+=1; proc=self.proc
        try:self.jobs.get_nowait()
        except queue.Empty:pass
        self.jobs.put_nowait((self.generation,signature,copy.deepcopy(clips),copy.deepcopy(audio_clips)))
        if proc and proc.poll() is None:
            try:proc.terminate()
            except OSError:pass

    def run(self):
        while not self.closed:
            job=self.jobs.get()
            if job is None or self.closed:return
            generation,signature,clips,audio_clips=job
            temp=None
            try:
                temp=tempfile.TemporaryDirectory(prefix='projectunio-audio-'); path=Path(temp.name)/'mix.wav'
                args=montage.audio_mix_args(clips,audio_clips)
                if generation!=self.generation or self.closed:continue
                self.proc=subprocess.Popen([self.executable,'-v','error','-y',*args,'-vn','-ar','48000','-ac','2','-c:a','pcm_s16le',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=0x08000000)
                try:_,error=self.proc.communicate(timeout=60)
                except subprocess.TimeoutExpired:
                    self.proc.kill(); self.proc.communicate(); raise RuntimeError('Le calcul du mixage a dépassé le délai prévu.')
                if self.proc.returncode:raise RuntimeError(error.decode(errors='replace')[-600:])
                if generation==self.generation and not self.closed:
                    self.results.put((generation,signature,path,temp,None)); temp=None
            except Exception as e:
                if generation==self.generation and not self.closed:
                    logging.exception('Actualisation audio de l’aperçu')
                    self.results.put((generation,signature,None,None,str(e)))
            finally:
                self.proc=None
                if temp:temp.cleanup()

    def poll(self):
        if self.closed:return
        while True:
            try:generation,signature,path,temp,error=self.results.get_nowait()
            except queue.Empty:break
            if generation==self.generation:self.callback(signature,path,temp,error)
            elif temp:temp.cleanup()
        self.timer=self.root.after(50,self.poll)

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
        def release():
            self.worker.join()
            while True:
                try:item=self.results.get_nowait()
                except queue.Empty:break
                if item[3]:item[3].cleanup()
        threading.Thread(target=release,daemon=True).start()
