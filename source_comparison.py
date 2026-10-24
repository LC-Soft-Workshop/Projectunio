"""Cancellable paired source/mapped stills using the same framing as export."""
import copy
import json
import math
from pathlib import Path
import queue
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import montage
import panorama
from mapping_still import read_ppm,resize_ppm
from work_media import checked_process


def regions(clip,zones):
    views=panorama.views(clip,zones)
    if views[0][1] is None:
        q=zones[clip['lane']]
        ratio=(math.dist(q[0],q[1])+math.dist(q[3],q[2]))*16/9/(math.dist(q[0],q[3])+math.dist(q[1],q[2]))
        return ratio,[(clip['lane'],(0.,0.,1.,1.))]
    ratio=views[0][1][2]; result=[]
    for lane,view in views:
        if len(view)==3:result.append((lane,(view[0]/view[2],0.,view[1]/view[2],1.)))
        else:result.append((lane,(view[0]/view[2],view[3]/view[5],view[1]/view[2],view[4]/view[5])))
    return ratio,result


def comparison_frames(executable,clip,clips,zones,position,mask,graph,cancel):
    from app import framing_filter
    ratio,rectangles=regions(clip,zones); height=max(2,round(min(270,960/ratio)/2)*2); width=max(2,round(height*ratio/2)*2)
    sizing=framing_filter(width,height,clip.get('fit','Remplir'),clip.get('zoom',1.),clip.get('pan_x',0.),clip.get('pan_y',0.))
    seek=clip['in']+position-clip['start']
    source=checked_process([executable,'-v','error',*montage.visual_input(clip,seek,.1),'-an','-vf',sizing+',setsar=1','-frames:v','1','-f','image2pipe','-c:v','ppm','pipe:1'],cancel,timeout=25)
    with tempfile.TemporaryDirectory(prefix='projectunio-compare-') as folder:
        args=montage.render_args(clips,zones,folder,mask,graph,640,360,still_at=position)
        mapped=checked_process([executable,'-v','error',*args,'-an','-frames:v','1','-f','image2pipe','-c:v','ppm','pipe:1'],cancel,timeout=30)
    return read_ppm(source),read_ppm(mapped),rectangles


class SourceComparison:
    def __init__(self,app):
        self.app=app; self.closed=False; self.generation=0; self.key=None; self.stop=threading.Event(); self.active_cancel=None
        self.jobs=queue.Queue(maxsize=1); self.results=queue.SimpleQueue(); self.frames=None; self.photos=[]; self.last_request=0.
        self.win=tk.Toplevel(app.root); self.win.title('Source / Répartition'); self.win.geometry('1000x490'); self.win.minsize(760,360)
        ttk.Label(self.win,text='La source cadrée montre les portions utilisées ; le résultat applique la perspective et les masques.',padding=8).pack()
        panes=ttk.Panedwindow(self.win,orient='horizontal'); panes.pack(fill='both',expand=True,padx=8)
        self.canvases=[]
        for title in ('Source cadrée • avant fondus','Résultat du mapping'):
            frame=ttk.Frame(panes); panes.add(frame,weight=1); ttk.Label(frame,text=title,padding=5).pack()
            canvas=tk.Canvas(frame,bg='black',highlightthickness=0); canvas.pack(fill='both',expand=True); canvas.bind('<Configure>',lambda e:self.draw()); self.canvases.append(canvas)
        self.label=ttk.Label(self.win,padding=10,wraplength=950); self.label.pack(fill='x')
        self.win.protocol('WM_DELETE_WINDOW',self.close); self.win.bind('<Escape>',lambda e:self.close()); self.win.bind('<Destroy>',lambda e:self.close() if e.widget==self.win and not self.closed else None)
        self.worker=threading.Thread(target=self.run,args=(self.jobs,self.results,self.stop),daemon=True); self.worker.start(); self.poll()

    @staticmethod
    def run(jobs,results,stop):
        while not stop.is_set():
            job=jobs.get()
            if job is None:return
            generation,payload,cancel=job
            if cancel.is_set():continue
            try:results.put((generation,comparison_frames(*payload,cancel),None))
            except Exception as e:
                if not cancel.is_set():results.put((generation,None,str(e)))

    def request(self):
        a=self.app; position=a.playhead
        clips=a.media_work.resolve(a.data.get('clips',[]))
        active=[c for c in clips if c['start']<=position<c['start']+montage.length(c)]
        clip=next((c for c in active if c['id']==a.timeline.selected),None) or next((c for c in active if a.zone in panorama.lanes(c)),None)
        if clip is None:
            if self.key is not None:
                self.generation+=1
                if self.active_cancel:self.active_cancel.set()
            self.key=None; self.frames=None; self.draw(); self.label.configure(text='Choisissez un instant où une vidéo est active, puis sélectionnez son clip ou sa zone.'); return
        zones=copy.deepcopy(a.data['zones']); names=a.zone_names(); key=json.dumps([clip['id'],clips,zones,names,position],sort_keys=True)
        if key==self.key:return
        self.key=key; self.generation+=1
        if self.active_cancel:self.active_cancel.set()
        self.active_cancel=threading.Event(); self.names=names; self.zones=zones
        try:self.jobs.get_nowait()
        except queue.Empty:pass
        from app import mask,graph
        payload=(a.executable,clip,clips,zones,position,mask,graph)
        self.jobs.put_nowait((self.generation,payload,self.active_cancel))
        self.label.configure(text=f'{Path(clip.get("_original_path",clip["path"])).name} • {position:.3f} s • Actualisation…')

    def poll(self):
        if self.closed:return
        if time.monotonic()-self.last_request>.2:self.last_request=time.monotonic(); self.request()
        while True:
            try:generation,frames,error=self.results.get_nowait()
            except queue.Empty:break
            if generation!=self.generation:continue
            if error:self.label.configure(text='Image indisponible : '+error)
            else:
                self.frames=frames; self.draw(); self.label.configure(text=f'Image à {self.app.playhead:.3f} s • Les couleurs identifient les mêmes zones dans la source et sur le mapping.')
        self.timer=self.win.after(70,self.poll)

    def draw(self):
        self.photos=[]
        for panel,c in enumerate(self.canvases):
            c.delete('all')
            if self.frames is None:continue
            frame=self.frames[panel]; sw,sh,_=frame; width=max(1,c.winfo_width()); height=max(1,c.winfo_height()); scale=min(width/sw,height/sh); iw=max(1,round(sw*scale)); ih=max(1,round(sh*scale)); ox=(width-iw)/2; oy=(height-ih)/2
            photo=tk.PhotoImage(data=resize_ppm(frame,iw,ih)); self.photos.append(photo); c.create_image(width/2,height/2,image=photo)
            if panel==0:
                for lane,(x,y,w,h) in self.frames[2]:
                    color=['#41d8ff','#ffc45c','#c298ff','#70edaf'][lane%4]
                    c.create_rectangle(ox+x*iw,oy+y*ih,ox+(x+w)*iw,oy+(y+h)*ih,outline=color,width=2,tags='source_region')
                    c.create_text(ox+(x+w/2)*iw,oy+(y+h/2)*ih,text=self.names[lane],fill=color,font=('Segoe UI',10,'bold'),width=max(20,w*iw))
            else:
                for lane,rect in self.frames[2]:
                    color=['#41d8ff','#ffc45c','#c298ff','#70edaf'][lane%4]; q=self.zones[lane]
                    c.create_polygon(*[v for x,y in q for v in (ox+x*iw,oy+y*ih)],outline=color,fill='',width=2,tags='mapped_region')

    def close(self):
        if self.closed:return
        self.closed=True; self.stop.set(); self.photos=[]
        if self.active_cancel:self.active_cancel.set()
        try:
            if hasattr(self,'timer'):self.win.after_cancel(self.timer)
            self.win.destroy()
        except tk.TclError:pass
        try:self.jobs.get_nowait()
        except queue.Empty:pass
        self.jobs.put_nowait(None)
