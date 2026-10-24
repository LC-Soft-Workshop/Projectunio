"""Playback of the mapped export with a reversible, UI-only calibration overlay."""
import ctypes
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk
import uuid


class VideoPreview:
    def __init__(self, parent, movie, zones, executable, project, cleanup):
        self.movie=Path(movie); self.zones=zones; self.executable=executable
        self.project=project; self.cleanup=cleanup; self.closed=False
        self.frames=queue.Queue(maxsize=3); self.stop=threading.Event()
        self.playing=True; self.started=None; self.position=0; self.frame_number=0; self.ended=False; self.restarting=False
        self.alias='projectunio'+uuid.uuid4().hex; self.audio=False; self.proc=None
        self.win=tk.Toplevel(parent); self.win.title('Aperçu vidéo — Projectunio')
        self.win.geometry('1000x650'); self.win.minsize(700,460)
        bar=ttk.Frame(self.win,padding=10); bar.pack(fill='x')
        self.button=ttk.Button(bar,text='Pause',command=self.toggle); self.button.pack(side='left')
        ttk.Button(bar,text='Recommencer',command=self.restart).pack(side='left',padx=6)
        self.grid=tk.BooleanVar(value=False)
        ttk.Checkbutton(bar,text='Afficher la grille de mapping',variable=self.grid,command=self.overlay).pack(side='left',padx=12)
        self.label=ttk.Label(bar,text='Préparation de la lecture…'); self.label.pack(side='right')
        self.audio_status=ttk.Label(bar,text=''); self.audio_status.pack(side='right',padx=8)
        self.projection=None
        ttk.Button(bar,text='Projeter HDMI',command=lambda:getattr(self,'projection_request',lambda:None)()).pack(side='left')
        from projection_output import ProjectionControls
        self.projection_controls=ProjectionControls(self)
        self.canvas=tk.Canvas(self.win,bg='black',highlightthickness=0); self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.redraw())
        self.image=None; self.pixels=None; self.win.protocol('WM_DELETE_WINDOW',self.close)
        self.win.bind('<Destroy>',lambda e:self.close() if e.widget==self.win and not self.closed else None)
        self.win.bind('<space>',lambda e:self.toggle()); self.win.bind('<Escape>',lambda e:self.close())
        self.worker=threading.Thread(target=self.decode,daemon=True); self.worker.start()
        self.timer=self.win.after(10,self.tick)

    def mci(self,command):
        if os.name=='nt': return ctypes.windll.winmm.mciSendStringW(command,None,0,None)
        return 1

    def decode(self):
        flags=0x08000000 if os.name=='nt' else 0
        try:
            wav=getattr(self,'audio_path',None)
            if wav is None:
                wav=self.movie.with_name(self.alias+'.wav')
                with open(self.movie.with_suffix('.audio.log'),'w') as log:
                    audio_proc=subprocess.Popen([self.executable,'-v','error','-y','-i',str(self.movie),'-vn','-c:a','pcm_s16le',str(wav)],stdout=subprocess.DEVNULL,stderr=log,creationflags=flags)
                    self.proc=audio_proc
                    code=audio_proc.wait()
            else:code=0
            if self.stop.is_set(): return
            self.audio_path=getattr(self,'override_audio_path',None) or (wav if code==0 else None)
            self.proc=subprocess.Popen([self.executable,'-v','error','-i',str(self.movie),'-an','-vf','scale=960:540,fps=30','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=flags)
            size=960*540*3
            while not self.stop.is_set():
                chunks=bytearray()
                while len(chunks)<size:
                    part=self.proc.stdout.read(size-len(chunks))
                    if not part:break
                    chunks.extend(part)
                if len(chunks)!=size:break
                if not self.enqueue(bytes(chunks)): return
            code=self.proc.wait()
            self.enqueue(RuntimeError('Impossible de décoder la vidéo.') if code and not self.stop.is_set() else None)
        except Exception as e:
            self.enqueue(e)
        finally:
            if self.proc:
                if self.proc.poll() is None:self.proc.terminate()
                self.proc.wait()
                if self.proc.stdout:self.proc.stdout.close()

    def enqueue(self,value):
        while not self.stop.is_set():
            try:self.frames.put(value,timeout=.1); return True
            except queue.Full:pass
        return False

    def tick(self):
        if self.closed:return
        if self.playing and (self.started is None or time.monotonic()-self.started >= self.frame_number/30):
            try:frame=self.frames.get_nowait()
            except queue.Empty:frame=False
            if frame is None or isinstance(frame,Exception):
                self.playing=False; self.ended=True; self.button.configure(text='Relire'); self.mci(f'stop {self.alias}')
                self.label.configure(text=str(frame) if isinstance(frame,Exception) else 'Fin — Recommencer pour relire')
            elif frame is not False:
                if self.frame_number and self.started is not None and time.monotonic()-self.started-self.frame_number/30>.15:
                    # Keep playback speed stable when this machine decodes slower than realtime.
                    self.started=time.monotonic()-self.frame_number/30
                if self.started is None:
                    wav=getattr(self,'audio_path',None)
                    self.audio=bool(wav) and self.mci(f'open "{wav}" type waveaudio alias {self.alias}')==0
                    self.started=time.monotonic(); self.mci(f'play {self.alias}')
                self.pixels=b'P6\n960 540\n255\n'+frame; self.frame_number+=1
                self.label.configure(text=f'{self.frame_number/30:.1f} s'); self.redraw()
        self.timer=self.win.after(5,self.tick)

    def redraw(self):
        if self.closed:return
        if self.projection and not self.projection.closed:
            from mapping_still import read_ppm
            self.projection.show(read_ppm(self.pixels) if self.pixels else None)
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        # Integer subsampling keeps dependencies limited to Tk. Window remains resizable.
        if self.pixels:
            self.image=tk.PhotoImage(data=self.pixels)
            factor=max(1,(960+max(w,1)-1)//max(w,1),(540+max(h,1)-1)//max(h,1))
            if factor>1:self.image=self.image.subsample(factor)
            iw,ih=self.image.width(),self.image.height()
            self.bounds=((w-iw)/2,(h-ih)/2,iw,ih)
            self.canvas.delete('video'); self.canvas.create_image(w/2,h/2,image=self.image,tags='video'); self.canvas.tag_lower('video')
        self.overlay()

    def overlay(self):
        self.canvas.delete('grid')
        if not self.grid.get() or not hasattr(self,'bounds'):return
        ox,oy,w,h=self.bounds
        for i,q in enumerate(self.zones):
            color=['#41d8ff','#ffc45c','#c298ff','#70edaf'][i%4]
            self.canvas.create_polygon(*[v for x,y in q for v in (ox+x*w,oy+y*h)],fill='',outline=color,width=2,tags='grid')
            for i in range(1,8):
                for a,b in [((i/8,0),(i/8,1)),((0,i/8),(1,i/8))]:
                    p=self.project(q,*a); r=self.project(q,*b)
                    self.canvas.create_line(ox+p[0]*w,oy+p[1]*h,ox+r[0]*w,oy+r[1]*h,fill=color,tags='grid')

    def toggle(self):
        if self.restarting:return
        if self.ended:self.restart(); return
        if self.started is None:return
        if self.playing:
            self.playing=False; self.position=time.monotonic()-self.started
            self.mci(f'pause {self.alias}'); self.button.configure(text='Lecture')
        else:
            self.playing=True; self.started=time.monotonic()-self.position
            self.mci(f'play {self.alias} from {round(self.frame_number/30*1000)}'); self.button.configure(text='Pause')

    def replace_audio(self,path):
        if self.closed:return False
        self.override_audio_path=Path(path); self.audio_path=Path(path)
        self.audio_status.configure(text='Volumes actualisés')
        if self.started is None:return True
        self.mci(f'close {self.alias}')
        self.audio=self.mci(f'open "{path}" type waveaudio alias {self.alias}')==0
        if not self.audio:return False
        self.mci(f'set {self.alias} time format milliseconds')
        position=round(self.frame_number/30*1000)
        self.mci(f'seek {self.alias} to {position}')
        if self.playing and not self.ended:self.mci(f'play {self.alias} from {position}')
        return True

    def restart(self):
        if self.closed or self.restarting:return
        self.restarting=True; self.playing=False; self.stop.set()
        self.mci(f'close {self.alias}')
        if self.proc and self.proc.poll() is None:self.proc.terminate()
        self.label.configure(text='Retour au début…')
        def resume():
            if self.closed:return
            if self.worker.is_alive():self.win.after(10,resume); return
            self.stop=threading.Event(); self.frames=queue.Queue(maxsize=3)
            self.proc=None; self.started=None; self.position=0; self.frame_number=0
            self.ended=False; self.restarting=False; self.playing=True
            self.button.configure(text='Pause')
            self.worker=threading.Thread(target=self.decode,daemon=True); self.worker.start()
        resume()

    def close(self):
        if self.closed:return
        if self.projection:self.projection.close()
        self.closed=True; self.stop.set(); self.win.after_cancel(self.timer)
        self.mci(f'close {self.alias}')
        if self.proc and self.proc.poll() is None:self.proc.terminate()
        try:self.win.destroy()
        except tk.TclError:pass
        # The decoder must release its files before the temporary directory is removed.
        def release():
            self.worker.join()
            self.cleanup()
        threading.Thread(target=release,daemon=True).start()
