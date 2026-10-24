"""Low-resolution on-demand mapped playback; no pre-rendered movie required."""
import array
import copy
import ctypes
import math
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import montage
from mapping_still import resize_ppm


def slice_items(items,begin,end):
    result=[]
    for c in items:
        first=max(begin,c['start']); last=min(end,c['start']+montage.length(c))
        if last-first<1/48000:continue
        offset=first-c['start']; item=dict(c,start=first,**{'in':c['in']+offset,'out':c['in']+offset+last-first})
        item['_effect_length']=c.get('_effect_length',montage.length(c)); item['_effect_offset']=c.get('_effect_offset',0.)+offset
        result.append(item)
    return result


class WaveOutput:
    """Windows PCM output with bounded buffering and a real signal peak."""
    class Format(ctypes.Structure):
        _fields_=[('format',ctypes.c_ushort),('channels',ctypes.c_ushort),('rate',ctypes.c_uint32),('bytes',ctypes.c_uint32),('align',ctypes.c_ushort),('bits',ctypes.c_ushort),('extra',ctypes.c_ushort)]
    class Header(ctypes.Structure):
        _fields_=[('data',ctypes.c_void_p),('length',ctypes.c_uint32),('recorded',ctypes.c_uint32),('user',ctypes.c_size_t),('flags',ctypes.c_uint32),('loops',ctypes.c_uint32),('next',ctypes.c_void_p),('reserved',ctypes.c_size_t)]

    def __init__(self):
        self.handle=ctypes.c_void_p(); self.winmm=ctypes.WinDLL('winmm')
        self.winmm.waveOutOpen.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint,ctypes.POINTER(self.Format),ctypes.c_size_t,ctypes.c_size_t,ctypes.c_uint]
        for name in ('waveOutPrepareHeader','waveOutWrite','waveOutUnprepareHeader'):
            getattr(self.winmm,name).argtypes=[ctypes.c_void_p,ctypes.POINTER(self.Header),ctypes.c_uint]
        for name in ('waveOutReset','waveOutClose','waveOutPause','waveOutRestart'):getattr(self.winmm,name).argtypes=[ctypes.c_void_p]
        fmt=self.Format(1,2,48000,192000,4,16,0)
        if self.winmm.waveOutOpen(ctypes.byref(self.handle),0xffffffff,ctypes.byref(fmt),0,0,0):raise OSError('Sortie audio Windows indisponible.')

    def write(self,data,stop,playing):
        buffer=ctypes.create_string_buffer(data); header=self.Header(ctypes.cast(buffer,ctypes.c_void_p),len(data),0,0,0,0,None,0); size=ctypes.sizeof(header)
        if self.winmm.waveOutPrepareHeader(self.handle,ctypes.byref(header),size):raise OSError('Préparation audio impossible.')
        try:
            if self.winmm.waveOutWrite(self.handle,ctypes.byref(header),size):raise OSError('Lecture audio impossible.')
            paused=False
            while not header.flags&1:
                if stop.wait(.005):self.winmm.waveOutReset(self.handle); break
                if not playing.is_set() and not paused:self.winmm.waveOutPause(self.handle); paused=True
                elif playing.is_set() and paused:self.winmm.waveOutRestart(self.handle); paused=False
        finally:self.winmm.waveOutUnprepareHeader(self.handle,ctypes.byref(header),size)

    def close(self):self.winmm.waveOutReset(self.handle); self.winmm.waveOutClose(self.handle)


class DirectPreview:
    def __init__(self,parent,executable,zones,clips,audio,position,mask,graph,project):
        self.executable=executable; self.zones=copy.deepcopy(zones); self.clips=copy.deepcopy(clips); self.audio=copy.deepcopy(audio)
        self.position=position; self.total=montage.duration(clips+audio); self.mask=mask; self.graph=graph; self.project=project; self.closed=False; self.image=None; self.frame=None; self.bounds=None
        self.procs=set(); self.lock=threading.Lock(); self.retired=[]; self.peak=0.; self.sound_error=''; self.audio_seconds=0.
        self.win=tk.Toplevel(parent); self.win.title('Lecture directe — Projectunio'); self.win.geometry('960x650')
        bar=ttk.Frame(self.win,padding=8); bar.pack(fill='x')
        self.button=ttk.Button(bar,text='Pause',command=self.toggle); self.button.pack(side='left')
        ttk.Button(bar,text='Recommencer au début',command=self.restart).pack(side='left',padx=6)
        self.grid=tk.BooleanVar(value=False); ttk.Checkbutton(bar,text='Grille',variable=self.grid,command=self.redraw).pack(side='left')
        self.quality=tk.StringVar(value='480 × 270'); quality=ttk.Combobox(bar,textvariable=self.quality,values=['480 × 270','640 × 360','1280 × 720'],state='readonly',width=12); quality.pack(side='left',padx=6); quality.bind('<<ComboboxSelected>>',lambda e:self.launch(self.current_time()))
        self.label=ttk.Label(bar,text='Démarrage…'); self.label.pack(side='right')
        self.projection=None
        ttk.Button(bar,text='Projeter HDMI',command=lambda:getattr(self,'projection_request',lambda:None)()).pack(side='left',padx=4)
        from projection_output import ProjectionControls
        self.projection_controls=ProjectionControls(self)
        loopbar=ttk.Frame(self.win,padding=8); loopbar.pack(fill='x')
        self.loop=tk.BooleanVar(value=False); self.loop_start=0.; self.loop_end=self.total; self.loop_count=0
        self.loop_in=tk.StringVar(value='0'); self.loop_out=tk.StringVar(value=f'{self.total:.3f}')
        ttk.Checkbutton(loopbar,text='Boucle',variable=self.loop,command=self.apply_loop).pack(side='left')
        for label,variable in [('Entrée (s)',self.loop_in),('Sortie (s)',self.loop_out)]:
            ttk.Label(loopbar,text=label).pack(side='left',padx=5)
            ttk.Entry(loopbar,textvariable=variable,width=9).pack(side='left')
        ttk.Button(loopbar,text='Entrée au curseur',command=lambda:self.loop_in.set(f'{self.seek.get():.3f}')).pack(side='left',padx=5)
        ttk.Button(loopbar,text='Sortie au curseur',command=lambda:self.loop_out.set(f'{self.seek.get():.3f}')).pack(side='left')
        ttk.Button(loopbar,text='Appliquer',command=self.apply_loop).pack(side='left',padx=5)
        self.canvas=tk.Canvas(self.win,bg='black',highlightthickness=0); self.canvas.pack(fill='both',expand=True); self.canvas.bind('<Configure>',lambda e:self.redraw())
        self.meter=ttk.Label(self.win,text='Niveau audio : —'); self.meter.pack(anchor='w',padx=10)
        self.seek=tk.DoubleVar(value=position); scale=ttk.Scale(self.win,from_=0,to=self.total,variable=self.seek); scale.pack(fill='x',padx=10,pady=6); scale.bind('<ButtonRelease-1>',lambda e:self.launch(self.seek.get()))
        self.win.protocol('WM_DELETE_WINDOW',self.close); self.win.bind('<Destroy>',lambda e:self.close() if e.widget==self.win else None); self.win.bind('<space>',lambda e:self.toggle())
        self.launch(position); self.timer=self.win.after(10,self.tick)

    def current_time(self):return min(self.total,self.position+(self.elapsed if self.started is None else time.monotonic()-self.started))

    def launch(self,position):
        if hasattr(self,'stop'):
            self.stop.set()
            with self.lock:
                for proc in self.procs:
                    if proc.poll() is None:proc.terminate()
            self.retired.extend(self.workers)
        if self.loop.get() and not self.loop_start<=position<self.loop_end:position=self.loop_start
        end=self.loop_end if self.loop.get() else self.total
        self.position=min(max(0.,round(position*30)/30),max(0.,end-1/30)); self.frames=queue.Queue(maxsize=3); self.stop=threading.Event(); self.playing=threading.Event(); self.playing.set(); self.ready=threading.Event(); self.started=None; self.elapsed=0.; self.next_frame=None; self.ended=False
        self.audio_seconds=0.; self.peak=0.; self.sound_error=''; self.button.configure(text='Pause')
        w,h=map(int,self.quality.get().split('×'))
        self.retired=[worker for worker in self.retired if worker.is_alive()]
        args=(self.stop,self.playing,self.ready,self.frames,self.position,w,h,end)
        self.workers=[threading.Thread(target=self.video_worker,args=args,daemon=True),threading.Thread(target=self.audio_worker,args=(self.stop,self.playing,self.ready,self.position,end),daemon=True)]
        for worker in self.workers:worker.start()

    def spawn(self,args,stop):
        if stop.is_set():raise InterruptedError()
        proc=subprocess.Popen([self.executable,'-v','error',*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)
        with self.lock:
            self.procs.add(proc)
            if stop.is_set():proc.terminate()
        return proc

    def release(self,proc):
        if proc.poll() is None:proc.terminate()
        proc.wait()
        if proc.stdout:proc.stdout.close()
        with self.lock:self.procs.discard(proc)

    @staticmethod
    def put(frames,value,stop):
        while not stop.is_set():
            try:frames.put(value,timeout=.1); return
            except queue.Full:pass

    def video_worker(self,stop,playing,ready,frames,position,w,h,end_time=None):
        total=self.total if end_time is None else end_time
        try:
            with tempfile.TemporaryDirectory(prefix='projectunio-direct-') as folder:
                # One bounded graph per scene avoids opening the entire montage.
                boundaries=sorted({position,total}|{max(position,min(total,t)) for c in self.clips for t in (c['start'],c['start']+montage.length(c))})
                cached={}
                def mask(path,q,width,height):
                    key=repr(q)
                    if key not in cached:
                        self.mask(path,q,width,height); cached[key]=Path(path).read_bytes()
                    else:Path(path).write_bytes(cached[key])
                for begin,end in zip(boundaries,boundaries[1:]):
                    if stop.is_set():return
                    if end-begin<1/30:continue
                    items=slice_items(self.clips,begin,end)
                    for c in items:c['audio']=False
                    args=montage.render_args(items,self.zones,folder,mask,self.graph,w,h,window=(begin,end),playback=True)
                    proc=self.spawn([*args,'-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stop)
                    try:
                        index=0
                        while not stop.is_set():
                            data=bytearray()
                            while len(data)<w*h*3:
                                block=proc.stdout.read(w*h*3-len(data))
                                if not block:break
                                data.extend(block)
                            if len(data)!=w*h*3:break
                            self.put(frames,(begin+index/30,(w,h,bytes(data))),stop); index+=1
                        code=proc.wait()
                        if code and not stop.is_set():raise RuntimeError('Décodage vidéo impossible. Vérifiez les fichiers du projet.')
                    finally:self.release(proc)
                self.put(frames,None,stop)
        except InterruptedError:pass
        except Exception as e:self.put(frames,e,stop)

    def audio_worker(self,stop,playing,ready,position,end_time=None):
        total=self.total if end_time is None else end_time
        output=None
        try:
            if not any(c.get('audio') and c['volume']>0 for c in self.clips) and not any(c['volume']>0 for c in self.audio):return
            if os.name!='nt':return
            output=WaveOutput(); begin=position
            while begin<total and not stop.is_set():
                end=min(total,begin+3.)
                args=montage.audio_mix_args(self.clips,self.audio,window=(begin,end))
                proc=self.spawn([*args,'-vn','-ac','2','-ar','48000','-f','s16le','pipe:1'],stop)
                try:
                    while not stop.is_set():
                        data=proc.stdout.read(19200)
                        if not data:break
                        while (not ready.is_set() or not playing.is_set()) and not stop.wait(.01):pass
                        if stop.is_set():break
                        samples=array.array('h',data); self.peak=max((abs(v)/32768 for v in samples),default=0.)
                        output.write(data,stop,playing); self.audio_seconds+=len(data)/192000
                    code=proc.wait()
                    if code and not stop.is_set():raise RuntimeError('Décodage audio impossible.')
                finally:self.release(proc)
                begin=end
        except InterruptedError:pass
        except Exception as e:
            if not stop.is_set():self.sound_error=str(e)
        finally:
            if output:output.close()

    def tick(self):
        if self.closed:return
        if self.loop.get() and self.playing.is_set() and not self.ended and self.started is not None and self.current_time()>=self.loop_end:
            self.loop_count+=1; self.launch(self.loop_start); self.seek.set(self.loop_start)
        if self.playing.is_set() and not self.ended:
            if self.next_frame is None:
                try:self.next_frame=self.frames.get_nowait()
                except queue.Empty:self.next_frame=False
            frame=self.next_frame
            if frame is None or isinstance(frame,Exception):
                if frame is None and self.loop.get():
                    if self.current_time()>=self.loop_end-1/60:
                        self.loop_count+=1; self.launch(self.loop_start); self.seek.set(self.loop_start)
                    # Keep the end sentinel until the last frame's duration has elapsed.
                else:
                    self.ended=True; self.label.configure(text=str(frame) if isinstance(frame,Exception) else 'Fin'); self.button.configure(text='Relire')
            elif frame is not False:
                at,pixels=frame
                if self.started is None:self.started=time.monotonic()-self.elapsed; self.ready.set()
                now=self.current_time()
                if at<=now+.02:
                    self.frame=pixels; self.redraw(); self.label.configure(text=f'{at:.2f} / {self.total:.2f} s'); self.seek.set(at); self.next_frame=None
            else:self.next_frame=None
        db=20*math.log10(max(self.peak,1e-6)); self.meter.configure(text=self.sound_error or f'Niveau audio : {db:.1f} dBFS'+(' • SATURATION' if self.peak>=.99 else ''))
        self.timer=self.win.after(10,self.tick)

    def toggle(self):
        if self.ended:self.restart(); return
        if self.playing.is_set():
            self.elapsed=self.current_time()-self.position; self.started=None; self.playing.clear(); self.button.configure(text='Lecture')
        else:self.started=None; self.playing.set(); self.button.configure(text='Pause')

    def apply_loop(self):
        if self.loop.get():
            try:
                begin=float(self.loop_in.get().replace(',','.')); end=float(self.loop_out.get().replace(',','.'))
                if not math.isfinite(begin) or not math.isfinite(end) or not 0<=begin<end<=self.total+.0005:raise ValueError()
                begin=round(begin*30)/30; end=min(self.total,round(end*30)/30)
                if end-begin<1/30-1e-6:raise ValueError()
            except ValueError:
                self.loop.set(False)
                messagebox.showerror('Boucle','Indiquez une entrée et une sortie comprises dans le montage, séparées d’au moins une image.',parent=self.win)
                self.launch(self.current_time()); return
            self.loop_start=begin; self.loop_end=end
            self.loop_in.set(f'{begin:.3f}'); self.loop_out.set(f'{end:.3f}')
            self.launch(begin); self.seek.set(begin)
        else:self.launch(self.current_time())

    def restart(self):
        self.launch(0.)
        self.frame=None; self.redraw()
        self.seek.set(0.)
        self.label.configure(text='Retour au début…')

    def redraw(self):
        if self.closed:return
        if self.projection and not self.projection.closed:self.projection.show(self.frame)
        c=self.canvas; c.delete('all'); w,h=max(1,c.winfo_width()),max(1,c.winfo_height()); scale=min(w/16,h/9); iw,ih=max(1,round(16*scale)),max(1,round(9*scale)); ox,oy=(w-iw)/2,(h-ih)/2
        if self.frame:self.image=tk.PhotoImage(data=resize_ppm(self.frame,iw,ih)); c.create_image(w/2,h/2,image=self.image)
        if self.grid.get():
            for i,q in enumerate(self.zones):
                color=['#41d8ff','#ffc45c','#c298ff','#70edaf'][i%4]
                c.create_polygon(*[v for x,y in q for v in (ox+x*iw,oy+y*ih)],fill='',outline=color,width=2)
                for k in range(1,8):
                    for a,b in [((k/8,0),(k/8,1)),((0,k/8),(1,k/8))]:
                        p=self.project(q,*a); r=self.project(q,*b); c.create_line(ox+p[0]*iw,oy+p[1]*ih,ox+r[0]*iw,oy+r[1]*ih,fill=color)

    def close(self):
        if self.closed:return
        if self.projection:self.projection.close()
        self.closed=True; self.stop.set()
        with self.lock:
            for proc in self.procs:
                if proc.poll() is None:proc.terminate()
        try:self.win.after_cancel(self.timer); self.win.destroy()
        except (tk.TclError,AttributeError):pass
