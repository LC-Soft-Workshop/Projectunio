"""Projectunio phase A. Python standard library + FFmpeg, Windows x64."""
import ctypes
from display_geometry import enable_per_monitor_dpi, monitor_rectangles, place_projector_window
enable_per_monitor_dpi()
from functools import partial
import json
import math
import os
import queue
from pathlib import Path
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from preview import VideoPreview
import montage
import panorama
from timeline_ui import Timeline
from mapping_still import MappingStill, resize_ppm
from live_audio import LiveAudio
from render_job import RenderJob
from export_settings import RESOLUTIONS, valid_resolution
from mapping_interaction import MappingInteraction
from studio import StudioFeatures, effective_items, validate_extras
from editor_controls import EditorControls, guard_methods

ROOT = Path(__file__).resolve().parent
DEFAULT = {'version': 4, 'name': 'Installation', 'resolution': [1280, 720], 'clips': [], 'audio_clips': [], 'audio_track_count': 1,
           'zones': [[[.05,.1],[.45,.1],[.45,.9],[.05,.9]],
                     [[.55,.1],[.95,.1],[.95,.9],[.55,.9]]]}

def valid(q):
    if len(q) != 4 or any(len(p) != 2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in p) for p in q):
        return False
    crosses = []
    for i in range(4):
        a,b,c = q[i],q[(i+1)%4],q[(i+2)%4]
        crosses.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
    return min(crosses) > .0001

def inside(x,y,q):
    return all((q[(i+1)%4][0]-q[i][0])*(y-q[i][1])-(q[(i+1)%4][1]-q[i][1])*(x-q[i][0]) >= 0 for i in range(4))

def mask(path,q,w,h):
    with open(path,'wb') as f:
        f.write(f'P5\n{w} {h}\n255\n'.encode())
        for y in range(h):
            f.write(bytes(255 if inside((x+.5)/w,(y+.5)/h,q) else 0 for x in range(w)))

def ffmpeg():
    p = ROOT/'runtime'/'ffmpeg.exe'
    return str(p) if p.exists() else shutil.which('ffmpeg') or 'ffmpeg'

def output_options(preview):
    if preview:
        return ['-an','-frames:v','1','-c:v','ppm']
    return ['-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-r','30','-c:a','aac','-b:a','160k','-movflags','+faststart']

def framing_filter(lw,lh,fit='Remplir',zoom=1.,pan_x=0.,pan_y=0.):
    zw,zh=max(2,round(lw*zoom/2)*2),max(2,round(lh*zoom/2)*2)
    policy='increase' if fit=='Remplir' else 'decrease'
    sizing=f"scale={zw}:{zh}:force_original_aspect_ratio={policy},pad=w='max(iw,{lw*3})':h='max(ih,{lh*3})':x=(ow-iw)/2:y=(oh-ih)/2:color=black,crop={lw}:{lh}:x=(iw-ow)/2-({pan_x:.8f})*{lw}:y=(ih-oh)/2-({pan_y:.8f})*{lh}"
    return sizing

def graph(q,w,h,fit='Remplir',zoom=1.,pan_x=0.,pan_y=0.,view=None):
    # Frame the source in a logical rectangle, then warp and strictly mask.
    ratio = (math.dist(q[0],q[1])+math.dist(q[3],q[2]))*w / ((math.dist(q[0],q[3])+math.dist(q[1],q[2]))*h)
    lw,lh = max(2,round(h*ratio/2)*2),h
    if view is not None:lw=max(2,round(h*view[2]/2)*2)
    sizing=framing_filter(lw,lh,fit,zoom,pan_x,pan_y)
    if view is not None:
        left=max(0,round(lw*view[0]/view[2]/2)*2)
        right=min(lw,round(lw*(view[0]+view[1])/view[2]/2)*2)
        top=0 if len(view)==3 else max(0,round(lh*view[3]/view[5]/2)*2)
        bottom=lh if len(view)==3 else min(lh,round(lh*(view[3]+view[4])/view[5]/2)*2)
        sizing+=f',crop={max(2,right-left)}:{max(2,bottom-top)}:{min(left,lw-2)}:{min(top,lh-2)}'
    order=[q[0],q[1],q[3],q[2]]
    coords=':'.join(f'x{i}={p[0]*(w-1):.6f}:y{i}={p[1]*(h-1):.6f}' for i,p in enumerate(order))
    return f"[0:v]{sizing},setsar=1,scale={w}:{h},perspective={coords}:sense=destination,format=yuv444p,split[warp][base];[base]lut=y=16:u=128:v=128[black];[1:v]format=yuv444p,geq=lum='if(gt(lum(X,Y),128),255,0)':cb='if(gt(lum(X,Y),128),255,0)':cr='if(gt(lum(X,Y),128),255,0)'[mask];[black][warp][mask]maskedmerge,format=yuv420p,setrange=limited[out]"

def screens():
    return monitor_rectangles()

class App(MappingInteraction,EditorControls,StudioFeatures):
    def __init__(self,root):
        self.root=root; root.title('Projectunio — Mapping et montage'); root.geometry('1150x950'); root.minsize(1080,780)
        if os.name=='nt':
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LCSoftWorkshop.Projectunio')
        icon=ROOT/'assets'/'projectunio.ico'
        if icon.is_file():root.iconbitmap(default=str(icon)); root.iconbitmap(str(icon))
        self.executable=ffmpeg()
        self.playhead=0.; self.still_frame=None; self.still_images={}; self._still_wanted_key=None; self._still_request_key=None; self._still_timer=None
        self.mapping_grid=tk.BooleanVar(value=False); self.mire_grid=tk.BooleanVar(value=True); self.still_status=tk.StringVar(value='Cliquez dans la timeline pour choisir une image.')
        self.edit_mode=tk.StringVar(value='mapping'); self.video_drag=None; self.video_proxy=None; self.video_drag_changed=False
        self.previews=[]; self.audio_assets={}
        self.active_render=None; self.render_jobs=set(); self.render_events=queue.SimpleQueue(); self.closing=False
        self.data=json.loads(json.dumps(DEFAULT)); self.zone=0; self.corner=0; self.history=[]; self.redo=[]; self.project=None; self.output=None; self.proc=None; self.cancelled=False; self.busy=False
        self.status=tk.StringVar(value='Calibration : choisissez une zone puis déplacez ses coins.'); self.name=tk.StringVar(value='Installation')
        bar=ttk.Frame(root,padding=10); bar.pack(fill='x')
        ttk.Label(bar,text='Installation').pack(side='left'); self.name_entry=ttk.Entry(bar,textvariable=self.name,width=24); self.name_entry.pack(side='left',padx=8)
        self.monitors=screens(); self.screen=ttk.Combobox(bar,state='readonly',width=22,values=[f'Écran {i+1} — {s[2]}×{s[3]}' for i,s in enumerate(self.monitors)]); self.screen.current(min(1,len(self.monitors)-1)); self.screen.pack(side='left',padx=5)
        self.canvas=tk.Canvas(root,bg='black',height=80,highlightthickness=0,takefocus=True); self.canvas.pack(fill='both',expand=True,padx=12)
        self.canvas.bind('<Configure>',lambda e:self.draw()); self.canvas.bind('<Button-1>',self.press); self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<KeyPress>',self.key)
        self.canvas.bind('<ButtonRelease-1>',self.finish_video_drag)
        self.canvas.bind('<Double-Button-1>',self.open_canvas_video_properties)
        self.canvas.bind('<MouseWheel>',lambda e:self.timeline.change_zoom(1.1 if e.delta>0 else 1/1.1) if self.edit_mode.get()=='video' else None)
        self.x=tk.StringVar(); self.y=tk.StringVar()
        self.zone_selector=ttk.Combobox(root,state='readonly')
        self.csel=ttk.Combobox(root,state='readonly',values=['Haut gauche','Haut droit','Bas droit','Bas gauche']); self.csel.current(0)
        self.install_editor_toolbar()
        ttk.Label(root,text='Flèches : 1 pixel • Maj + flèches : 10 pixels • Dessin : clic droit ou Échap pour annuler').pack()
        self.timeline=Timeline(self,root)
        row=ttk.Frame(root,padding=(10,3)); row.pack(fill='x')
        self.preview_button=ttk.Button(row,text='Aperçu du montage',command=self.toggle_preview); self.preview_button.pack(side='left',padx=4)
        self.export_button=ttk.Button(row,text='Exporter le montage MP4',command=self.export); self.export_button.pack(side='left',padx=4)
        ttk.Label(row,text='Résolution :').pack(side='left',padx=(8,2))
        self.export_resolution=tk.StringVar(value=next(iter(RESOLUTIONS)))
        self.resolution_selector=ttk.Combobox(row,state='readonly',width=25,textvariable=self.export_resolution,values=list(RESOLUTIONS)); self.resolution_selector.pack(side='left',padx=3)
        self.resolution_selector.bind('<<ComboboxSelected>>',lambda e:self.choose_resolution())
        self.mire_button=ttk.Button(row,text='Mire USB',command=lambda:self.export(mire=True)); self.mire_button.pack(side='left',padx=4)
        self.cancel_button=ttk.Button(row,text='Arrêter le rendu',command=self.cancel); self.cancel_button.pack(side='left',padx=4)
        ttk.Label(root,textvariable=self.status,padding=10,wraplength=1050).pack(fill='x')
        self.still_renderer=MappingStill(root,self.executable,mask,graph,self.receive_still)
        self.live_audio=LiveAudio(root,self.executable,self.receive_preview_audio)
        self.render_timer=root.after(40,self.poll_render)
        def stop_still(event):
            if event.widget==root:
                self.closing=True; root.after_cancel(self.render_timer)
                jobs=list(self.render_jobs)
                for job in jobs:job.cancel()
                def release_renders():
                    for job in jobs:job.thread.join()
                    while True:
                        try:job,kind,payload=self.render_events.get_nowait()
                        except queue.Empty:break
                        if kind=='ready':payload[1].cleanup()
                threading.Thread(target=release_renders,daemon=True).start()
                if self._still_timer is not None:root.after_cancel(self._still_timer); self._still_timer=None
                for asset in self.audio_assets.values():asset.cleanup()
                self.audio_assets.clear()
        root.bind('<Destroy>',stop_still,add='+')
        self.root.protocol('WM_DELETE_WINDOW',self.close); self.refresh(); self.sync_render_buttons(); self.install_studio()

    def set_playhead(self,value):
        if not math.isfinite(value):return
        self.playhead=min(max(0,value),montage.duration(self.data.get('clips',[])+self.data.get('audio_clips',[])))
        self.timeline.time.set(f'{self.playhead:.3f}'); self.timeline.draw(); self.schedule_still()

    def schedule_still(self):
        if self.video_drag is not None:return
        self.check_render_invalidation()
        if not hasattr(self,'still_renderer'):return
        key=json.dumps([self.playhead,self.data['zones'],self.data.get('clips',[])],sort_keys=True)
        if key==self._still_wanted_key:return
        self._still_wanted_key=key
        if self._still_timer is not None:self.root.after_cancel(self._still_timer)
        self._still_timer=None
        if not self.data.get('clips'):
            self.still_frame=None; self.still_images.clear(); self.draw()
            self.still_status.set('Déposez une vidéo puis cliquez dans la timeline.'); return
        self.still_status.set(f'Image à {self.playhead:.3f} s — actualisation…')
        def request():
            self._still_timer=None; self._still_request_key=self._still_wanted_key
            self.still_renderer.request(self.data['clips'],self.data['zones'],self.playhead)
        self._still_timer=self.root.after(180,request)

    def receive_still(self,frame,error):
        if self.video_drag is not None:return
        if self._still_request_key!=self._still_wanted_key:return
        self.video_proxy=None
        if error:
            self.still_frame=None; self.still_images.clear(); self.draw(); self.still_status.set('Image indisponible : '+error[-180:]); return
        self.still_frame=frame; self.still_images.clear(); self.draw()
        self.still_status.set(f'Image arrêtée à {self.playhead:.3f} s — les coins restent modifiables.')

    def checkpoint(self):
        self.history.append(json.loads(json.dumps(self.data))); self.history=self.history[-100:]; self.redo.clear()
    def undo(self):
        if self.history: self.redo.append(self.data); self.data=self.history.pop(); self.refresh(); self.refresh_preview_audio()
    def restore(self):
        if self.redo: self.history.append(self.data); self.data=self.redo.pop(); self.refresh(); self.refresh_preview_audio()
    def select(self,z): self.edge=None; self.zone=z; self.refresh(); self.canvas.focus_set()
    def choose_corner(self): self.edge=None; self.corner=self.csel.current(); self.refresh(); self.canvas.focus_set()
    def refresh(self):
        self.sync_editor_locks()
        if hasattr(self,'export_resolution'):
            self.export_resolution.set(next(label for label,size in RESOLUTIONS.items() if list(size)==self.data['resolution']))
        self.zone=min(self.zone,len(self.data['zones'])-1)
        if hasattr(self,'zone_selector'):self.zone_selector.configure(values=self.zone_names()); self.zone_selector.current(self.zone)
        p=self.data['zones'][self.zone][self.corner]; self.x.set(f'{p[0]*100:.3f}'); self.y.set(f'{p[1]*100:.3f}'); self.csel.current(self.corner); self.draw()
        if hasattr(self,'timeline'):self.timeline.refresh()

    def choose_resolution(self):
        size=RESOLUTIONS.get(self.export_resolution.get())
        if size is None or list(size)==self.data['resolution']:return
        self.checkpoint(); self.data['resolution']=list(size); self.refresh()
        self.status.set(f'Export : {self.export_resolution.get()}. Le mapping conserve ses proportions.')
    def viewport(self,c):
        w,h=max(c.winfo_width(),10),max(c.winfo_height(),10); scale=min(w/1280,h/720); return (w-1280*scale)/2,(h-720*scale)/2,1280*scale,720*scale
    def draw(self):
        canvases=[self.canvas]+([self.output.canvas] if self.output and self.output.winfo_exists() else [])
        for c in canvases:
            if self.video_proxy is not None and self.edit_mode.get()=='video':
                if c==self.canvas or getattr(self.output,'show_frame',False):self.draw_video_proxy(c)
                continue
            c.delete('all'); ox,oy,w,h=self.viewport(c)
            show_frame=self.still_frame is not None and (c==self.canvas or getattr(self.output,'show_frame',False))
            if show_frame:
                size=(max(1,round(w)),max(1,round(h)))
                if size not in self.still_images:
                    self.still_images[size]=tk.PhotoImage(data=resize_ppm(self.still_frame,*size))
                    if len(self.still_images)>4:self.still_images.pop(next(iter(self.still_images)))
                c.create_image(ox+w/2,oy+h/2,image=self.still_images[size],tags='mapping_image')
            c.create_rectangle(ox,oy,ox+w,oy+h,outline='#444')
            for z,q in enumerate(self.data['zones']):
                color=['#41d8ff','#ffc45c','#c298ff','#70edaf'][z%4]; pts=[(ox+x*w,oy+y*h) for x,y in q]
                c.create_polygon(*[v for p in pts for v in p],fill='',outline=color,width=3)
                if z==self.zone and getattr(self,'edge',None) is not None:
                    a,b=pts[self.edge],pts[(self.edge+1)%4]; c.create_line(*a,*b,fill='white',width=5,tags='selected_edge')
                # Projective grid: same homography as export, not a bilinear approximation.
                for k in (range(1,8) if (self.mapping_grid.get() if c==self.canvas else self.mire_grid.get()) else []):
                    t=k/8
                    for a,b in [((t,0),(t,1)),((0,t),(1,t))]:
                        p=project(q,*a); r=project(q,*b); c.create_line(ox+p[0]*w,oy+p[1]*h,ox+r[0]*w,oy+r[1]*h,fill=color,tags='mapping_grid')
                for i,(x,y) in (enumerate(pts) if self.edit_mode.get()=='mapping' or not show_frame else []):
                    r=10 if z==self.zone and i==self.corner else 7
                    c.create_oval(x-r,y-r,x+r,y+r,fill=color,outline='white',tags=('mapping_corner',f'corner_{z}_{i}')); c.create_text(x+16,y-16,text=str(i+1),fill='white')
                if not show_frame:c.create_text(sum(p[0] for p in pts)/4,sum(p[1] for p in pts)/4,text=self.zone_names()[z],fill='white',font=('Segoe UI',20,'bold'))

    def draw_video_proxy(self,c):
        c.delete('all'); ox,oy,w,h=self.viewport(c); clip=self.video_proxy
        c.create_rectangle(ox,oy,ox+w,oy+h,outline='#444')
        for lane,q in enumerate(self.data['zones']):
            color=['#41d8ff','#ffc45c','#c298ff','#70edaf'][lane%4]
            c.create_polygon(*[v for x,y in q for v in (ox+x*w,oy+y*h)],fill='#173d4a' if lane in panorama.lanes(clip) else '#101820',outline=color,width=3,tags='video_proxy')
            if lane not in panorama.lanes(clip):continue
            view=dict(panorama.views(clip,self.data['zones']))[lane]
            for axis,key in ((0,'pan_x'),(1,'pan_y')):
                for k in (range(-4,9) if self.mapping_grid.get() else []):
                    t=k/4+clip.get(key,0.)
                    if axis==0 and view is not None:t=(t*view[2]-view[0])/view[1]
                    if axis==1 and view is not None and len(view)>3:t=(t*view[5]-view[3])/view[4]
                    if not 0<t<1:continue
                    a,b=((t,0),(t,1)) if axis==0 else ((0,t),(1,t))
                    p=project(q,*a); r=project(q,*b)
                    c.create_line(ox+p[0]*w,oy+p[1]*h,ox+r[0]*w,oy+r[1]*h,fill=color,width=2,tags='video_proxy_motion')
            p=project(q,.5,.5)
            c.create_text(ox+p[0]*w,oy+p[1]*h,text=f'{self.zone_names()[lane]}\nX : {clip.get("pan_x",0.)*100:+.1f} %  •  Y : {clip.get("pan_y",0.)*100:+.1f} %',fill='white',font=('Segoe UI',12,'bold'),tags='video_proxy_motion')
            u,v=.5+clip.get('pan_x',0.),.5+clip.get('pan_y',0.)
            if view is not None:u=(u*view[2]-view[0])/view[1]
            if view is not None and len(view)>3:v=(v*view[5]-view[3])/view[4]
            if 0<=u<=1 and 0<=v<=1:
                center=project(q,u,v); x,y=ox+center[0]*w,oy+center[1]*h
                c.create_oval(x-7,y-7,x+7,y+7,outline='white',width=2,tags='video_proxy_cross')

    def discard_video_proxy(self):
        self.video_drag=None; self.video_proxy=None; self.video_drag_changed=False

    def finish_video_drag(self,event=None):
        if self.video_drag is None:return
        changed=self.video_drag_changed
        self.video_drag=None; self.video_drag_changed=False
        if not changed:self.video_proxy=None
        self.timeline.refresh(); self.draw()
    def open_canvas_video_properties(self,event):
        if self.edit_mode.get()=='draw':return self.zone_click(event)
        if self.open_corner_properties(event):return 'break'
        if self.edit_locked('timeline'):return 'break'
        self.anchor=None; self.video_drag=None; self.video_drag_changed=False; self.video_proxy=None
        ox,oy,w,h=self.viewport(self.canvas)
        if w<=0 or h<=0:return 'break'
        point=((event.x-ox)/w,(event.y-oy)/h)
        for lane in reversed(range(len(self.data['zones']))):
            if not inside(*point,self.data['zones'][lane]):continue
            clip=next((c for c in self.data['clips'] if lane in panorama.lanes(c) and c['start']<=self.playhead<c['start']+montage.length(c)),None)
            if clip is None:
                self.draw(); self.status.set('Aucune vidéo dans cette zone à cet instant de la timeline.'); return 'break'
            self.zone=lane; self.timeline.selected=clip['id']; self.timeline_tools.selection={clip['id']}
            self.timeline.dragging=None; self.timeline.scrubbing=False
            self.refresh()
            return self.timeline.open_properties()
        self.draw(); return 'break'

    def press(self,e):
        if self.edit_mode.get()=='mapping' and getattr(self,'mapping_latched',False):
            self.drag(e); self.end_mapping_gesture(); return 'break'
        if self.edit_mode.get()=='draw':return
        if self.edit_locked('timeline' if self.edit_mode.get()=='video' else 'mapping'):return
        self.canvas.focus_set(); ox,oy,w,h=self.viewport(self.canvas); p=((e.x-ox)/w,(e.y-oy)/h)
        if self.edit_mode.get()=='video':
            self.video_drag=None
            for lane,q in enumerate(self.data['zones']):
                if not inside(*p,q):continue
                clip=next((c for c in self.data['clips'] if lane in panorama.lanes(c) and c['start']<=self.playhead<c['start']+montage.length(c)),None)
                anchor=unproject(q,*p)
                if clip is None or anchor is None:continue
                self.checkpoint(); self.video_drag=(json.loads(json.dumps(clip)),anchor)
                self.video_drag_lane=lane
                self.video_proxy=json.loads(json.dumps(clip)); self.video_drag_changed=False
                if self._still_timer is not None:self.root.after_cancel(self._still_timer); self._still_timer=None
                self._still_wanted_key=None; self._still_request_key=None; self.still_renderer.cancel_pending()
                self.timeline.selected=clip['id']; self.timeline.refresh(); self.draw()
                self.still_status.set('Déplacement simplifié — image actualisée au relâchement.')
                self.status.set('Déplacez la vidéo dans sa zone. La calibration reste inchangée.'); return
            self.status.set('Choisissez dans la timeline un instant où une vidéo est active dans cette zone.'); return
        self.begin_mapping_gesture(e)
        self.anchor=p; self.checkpoint(); self.start=json.loads(json.dumps(self.data['zones'])); self.whole=False; self.edge=None
        candidates=[(math.hypot((p[0]-v[0])*w,(p[1]-v[1])*h),z,i) for z,q in enumerate(self.start) for i,v in enumerate(q)]
        d,z,i=min(candidates)
        if d<24: self.zone=z; self.corner=i
        else:
            edges=[(self.edge_distance(p,q[i],q[(i+1)%4],w,h),z,i) for z,q in enumerate(self.start) for i in range(4)]
            distance,z,i=min(edges)
            if distance<12:
                self.zone=z; self.edge=i; self.corner=i; self.refresh(); return
            for z,q in enumerate(self.start):
                if inside(*p,q): self.zone=z; self.whole=True; break
            else: self.end_mapping_gesture()
        self.refresh()
    def drag(self,e):
        if self.edit_mode.get()=='draw':return
        if self.edit_locked('timeline' if self.edit_mode.get()=='video' else 'mapping'):return
        if self.edit_mode.get()=='video':
            if self.video_drag is None:return
            old,anchor=self.video_drag; ox,oy,w,h=self.viewport(self.canvas)
            lane=getattr(self,'video_drag_lane',old['lane'])
            point=unproject(self.data['zones'][lane],(e.x-ox)/w,(e.y-oy)/h)
            if point is None:return
            view=dict(panorama.views(old,self.data['zones']))[lane]
            factor=1. if view is None else view[1]/view[2]
            vertical=1. if view is None or len(view)==3 else view[4]/view[5]
            clip=json.loads(json.dumps(old)); clip['pan_x']=min(1.,max(-1.,old.get('pan_x',0.)+(point[0]-anchor[0])*factor)); clip['pan_y']=min(1.,max(-1.,old.get('pan_y',0.)+(point[1]-anchor[1])*vertical))
            previous=next((c for c in self.data['clips'] if c['id']==old['id']),None)
            if clip==previous:return
            self.data['clips']=[clip if c['id']==old['id'] else c for c in self.data['clips']]
            if not self.video_drag_changed:self.video_drag_changed=True; self.check_render_invalidation()
            self.video_proxy=clip
            self.timeline.fields['pan_x'].set(f'{clip["pan_x"]*100:.3f}'); self.timeline.fields['pan_y'].set(f'{clip["pan_y"]*100:.3f}')
            self.draw(); return
        if not getattr(self,'anchor',None): return
        q=self.bounded_mapping_quad(e)
        if q!=self.data['zones'][self.zone]:self.data['zones'][self.zone]=q; self.refresh()
    def numeric(self):
        try: p=[float(self.x.get())/100,float(self.y.get())/100]
        except ValueError: return
        q=json.loads(json.dumps(self.data['zones'][self.zone])); q[self.corner]=p
        if valid(q): self.checkpoint(); self.data['zones'][self.zone]=q; self.refresh()
        else: messagebox.showerror('Géométrie','Les coins doivent former un quadrilatère convexe dans l’image.'); self.refresh()
    def key(self,e):
        if self.edit_mode.get()=='video':return
        if e.keysym not in ['Left','Right','Up','Down']: return
        step=10 if e.state & 1 else 1; q=json.loads(json.dumps(self.data['zones'][self.zone])); p=q[self.corner]
        p[0]+=({'Left':-step,'Right':step}.get(e.keysym,0))/self.data['resolution'][0]; p[1]+=({'Up':-step,'Down':step}.get(e.keysym,0))/self.data['resolution'][1]
        if getattr(self,'edge',None) is not None:
            q=json.loads(json.dumps(self.data['zones'][self.zone]))
            for i in (self.edge,(self.edge+1)%4):
                q[i][0]+=({'Left':-step,'Right':step}.get(e.keysym,0))/self.data['resolution'][0]; q[i][1]+=({'Up':-step,'Down':step}.get(e.keysym,0))/self.data['resolution'][1]
        if valid(q): self.checkpoint(); self.data['zones'][self.zone]=q; self.refresh()
    def refresh_screens(self):
        previous=self.monitors[max(0,self.screen.current())][:2] if self.monitors else None
        self.monitors=screens()
        selected=next((i for i,m in enumerate(self.monitors) if m[:2]==previous),min(1,len(self.monitors)-1))
        self.screen.configure(values=[f'Écran {i+1} — {s[2]}×{s[3]} (Windows)' for i,s in enumerate(self.monitors)])
        self.screen.current(selected)

    def sync_hdmi_buttons(self,event=None):
        output=self.output
        opened=bool(output and output.winfo_exists() and (event is None or event.widget is not output))
        for key,var in getattr(self,'hdmi_vars',{}).items():var.set(opened and bool(output.show_frame)==(key=='image'))

    def projector(self,show_frame=False):
        if self.output and self.output.winfo_exists() and self.output.show_frame==show_frame:
            self.output.destroy(); self.output=None
            self.sync_hdmi_buttons()
            self.status.set('Image HDMI fermée.' if show_frame else 'Mire HDMI fermée.')
            return
        self.refresh_screens()
        if len(self.monitors)<2: messagebox.showinfo('Bureau étendu','Un seul écran détecté. Sur le portable, branchez HDMI puis choisissez Windows + P → Étendre. La mire reste disponible sur cet écran pour essai.')
        if self.output and self.output.winfo_exists(): self.output.destroy()
        x,y,w,h=self.monitors[self.screen.current()]; self.output=tk.Toplevel(self.root); self.output.overrideredirect(True); self.output.geometry(f'{w}x{h}{x:+d}{y:+d}'); self.output.attributes('-topmost',True)
        self.output.show_frame=show_frame
        self.output.bind('<Destroy>',self.sync_hdmi_buttons,add='+')
        self.sync_hdmi_buttons()
        self.output.canvas=tk.Canvas(self.output,bg='black',highlightthickness=0); self.output.canvas.pack(fill='both',expand=True); self.output.canvas.bind('<Configure>',lambda e:self.draw()); self.output.bind('<Escape>',lambda e:self.output.destroy()); self.root.bind('<Escape>',lambda e:self.output.destroy() if self.output and self.output.winfo_exists() else None,add='+'); place_projector_window(self.output,(x,y,w,h)); self.draw()
        self.status.set(f'{"Image" if show_frame else "Mire"} HDMI : écran {self.screen.current()+1}, mode Windows {w} × {h}.')
    def save(self,destination=None):
        self.timeline.finish_name_edit()
        p=destination or filedialog.asksaveasfilename(defaultextension='.projectunio.json',filetypes=[('Installation Projectunio','*.json')])
        if not p:return False
        self.data['name']=self.name.get(); dest=Path(p)
        try:
            if dest.exists(): shutil.copy2(dest,str(dest)+'.bak')
            from calibration_versions import format_version
            saved=json.loads(json.dumps(self.data)); saved['version']=format_version(saved)
            for clip in saved.get('clips',[])+saved.get('audio_clips',[]):
                try:clip['path']=os.path.relpath(clip['path'],dest.parent)
                except ValueError:pass
            temp=Path(str(dest)+'.tmp'); temp.write_text(json.dumps(saved,indent=2,ensure_ascii=False),encoding='utf-8'); temp.replace(dest); self.project=dest; self.status.set('Installation et montage enregistrés : '+str(dest)); self.snapshot_document(); self.active_document['saved_data']=json.loads(json.dumps(self.data)); return True
        except OSError as e: messagebox.showerror('Enregistrement',str(e)); return False
    def load(self):
        p=filedialog.askopenfilename(filetypes=[('Installation Projectunio','*.json')])
        if not p:return
        try:
            d=json.loads(Path(p).read_text(encoding='utf-8'))
            if d['version'] not in (1,2,3,4,5,6,7,8,9) or not valid_resolution(d['resolution']) or not 1<=len(d['zones'])<=64 or not all(valid(q) for q in d['zones']): raise ValueError('Format ou géométrie invalide')
            d.setdefault('clips',[]); d.setdefault('audio_clips',[]); d.setdefault('audio_track_count',1); d['version']=4; montage.validate_items(d['clips']+d['audio_clips'])
            if type(d['audio_track_count'])!=int or not 0<=d['audio_track_count']<=64 or any(c['lane']>=d['audio_track_count'] for c in d['audio_clips']):raise ValueError('Nombre de pistes audio invalide (0 à 64).')
            if any(c['lane']>=len(d['zones']) for c in d['clips']):raise ValueError('Zone vidéo inexistante.')
            for clip in d['clips']+d['audio_clips']:
                clip['path']=str((Path(p).parent/clip['path']).resolve())
            validate_extras(d); self.open_document(d,Path(p))
            missing=[c['path'] for c in d['clips']+d['audio_clips'] if not Path(c['path']).is_file()]
            self.status.set('Médias introuvables : '+', '.join(missing) if missing else 'Installation et montage chargés.')
        except (OSError,ValueError,KeyError,TypeError) as e: messagebox.showerror('Ouverture',str(e))
    def export(self,mire=False,preview=False):
        if preview and any(not p.closed for p,s in self.previews):self.close_previews(); return
        if self.active_render is not None:return
        if not mire and not (self.data.get('clips') or self.data.get('audio_clips')): messagebox.showinfo('Médias','Déposez des vidéos ou des sons pour composer le montage.'); return
        dest=None if preview else filedialog.asksaveasfilename(defaultextension='.mp4',filetypes=[('Vidéo MP4','*.mp4')])
        if not preview and not dest:return
        # Dialog confirms replacement; the worker only replaces after successful encoding.
        zones=json.loads(json.dumps(self.data['zones'])); clips,audio_clips=effective_items(self.data)
        job=RenderJob(self.render_events,self.executable,zones,clips,audio_clips,self.render_signature(mire,preview),mask,graph,partial(write_mire,grid=self.mire_grid.get()),output_options,preview=preview,mire=mire,destination=dest,log_directory=ROOT/'logs',resolution=(1280,720) if preview else tuple(self.data['resolution']))
        job.review_audio=not preview and not mire
        self.active_render=job; self.render_jobs.add(job); self.busy=True; self.cancelled=False
        self.status.set('Préparation de l’aperçu…' if preview else 'Préparation du rendu…')
        self.sync_render_buttons(); job.thread.start()

    def render_signature(self,mire=False,preview=False):
        if mire:return json.dumps([self.data['zones'],self.data['resolution'],self.mire_grid.get()],sort_keys=True)
        clips,audio=effective_items(self.data)
        return json.dumps([self.data['zones'],clips,audio,[1280,720] if preview else self.data['resolution']],sort_keys=True)

    def toggle_preview(self):
        if any(not p.closed for p,s in self.previews):self.close_previews()
        elif self.active_render is None:self.export(preview=True)

    def close_previews(self):
        for player,signature in list(self.previews):
            if not player.closed:player.close()
        self.previews=[]; self.sync_render_buttons()

    def sync_render_buttons(self):
        if self.closing or not hasattr(self,'preview_button'):return
        try:
            self.previews=[(p,s) for p,s in self.previews if not p.closed]
            opened=bool(self.previews); job=self.active_render
            label='Fermer l’aperçu' if opened else 'Préparation de l’aperçu…' if job and job.preview else 'Aperçu du montage'
            self.preview_button.configure(text=label,state='normal' if opened or job is None else 'disabled')
            for button in (self.export_button,self.mire_button):button.configure(state='disabled' if job else 'normal')
            self.cancel_button.configure(state='normal' if job else 'disabled')
        except tk.TclError:pass

    def check_render_invalidation(self):
        if self.closing:return
        direct=getattr(self,'direct_player',None)
        if direct and not direct.closed and getattr(self,'direct_signature',None)!=self.render_signature(preview=True):
            self.stop_direct(); self.status.set('Lecture directe arrêtée après modification. Relancez-la au curseur.')
        job=self.active_render
        if job and job.signature!=self.render_signature(job.mire,job.preview):
            self.cancel(); self.status.set('Rendu annulé après modification. Vous pouvez relancer le rendu.')
        if self.previews:
            clips,audio=effective_items(self.data)
            signature=self.preview_signature(self.data['zones'],clips,audio)
            for player,old in list(self.previews):
                if not player.closed and old!=signature:
                    player.close(); self.status.set('Aperçu fermé après modification. Vous pouvez le recalculer.')
            self.sync_render_buttons()

    def poll_render(self):
        if self.closing:return
        if self.active_render and self.active_render.stalled() and not getattr(self.active_render,'progress_warning',False):
            self.active_render.progress_warning=True
            self.status.set('Le calcul prend du temps. Le rendu continue ; « Arrêter le rendu » reste disponible.')
        while True:
            try:job,kind,payload=self.render_events.get_nowait()
            except queue.Empty:break
            if kind not in ('progress','audio_warning'):self.render_jobs.discard(job)
            valid=job is self.active_render and not job.cancelled.is_set() and job.signature==self.render_signature(job.mire,job.preview)
            if not valid:
                if kind=='ready':payload[1].cleanup()
                if job is self.active_render:
                    job.cancel(); self.active_render=None; self.busy=False; self.sync_render_buttons()
                continue
            if kind=='progress':
                self.status.set('Rendu : '+payload)
                continue
            if kind=='audio_warning':
                from audio_analysis import describe
                choice=messagebox.askyesnocancel('Niveau sonore avant export',describe(payload)+'\n\nOui : réduire pour cet export uniquement.\nNon : exporter les niveaux actuels.\nAnnuler : arrêter et corriger le projet dans Audio → Analyser le niveau sonore.',parent=self.root)
                if choice is None:job.cancel()
                else:job.audio_gain=payload['gain'] if choice else 1.
                job.audio_decision.set(); continue
            self.active_render=None; self.busy=False; self.sync_render_buttons()
            if kind=='ready':
                movie,owner=payload
                self.show_preview(movie,job.zones,owner.cleanup,job.clips,job.audio_clips)
            elif kind=='complete':self.status.set('Export terminé : '+payload)
            elif kind=='cancelled':self.status.set('Rendu annulé.')
            elif kind=='error':
                self.status.set('Le rendu a échoué. Vous pouvez réessayer.')
                messagebox.showerror('Rendu impossible',payload,parent=self.root)
        self.render_timer=self.root.after(40,self.poll_render)
    @staticmethod
    def preview_signature(zones,clips,audio_clips):
        return json.dumps([zones,[[{k:v for k,v in c.items() if k!='volume'} for c in items] for items in (clips,audio_clips)]],sort_keys=True)

    def show_preview(self,movie,zones,cleanup,clips=None,audio_clips=None):
        self.close_previews()
        player=VideoPreview(self.root,movie,zones,ffmpeg(),project,cleanup)
        player.projection_request=lambda:self.project_player(player)
        signature=self.preview_signature(zones,clips or [],audio_clips or [])
        self.previews.append((player,signature))
        snapshot=json.dumps([zones,clips or [],audio_clips or [],[1280,720]],sort_keys=True)
        if snapshot!=self.render_signature(preview=True):self.refresh_preview_audio()
        player.win.bind('<Destroy>',lambda e:self.sync_render_buttons() if e.widget==player.win else None,add='+')
        self.sync_render_buttons()
        self.status.set('Aperçu ouvert : lecture/pause, grille facultative et bouton « Fermer l’aperçu ».')

    def refresh_preview_audio(self):
        if not hasattr(self,'live_audio'):return
        self.previews=[(p,s) for p,s in self.previews if not p.closed]
        clips,audio=effective_items(self.data)
        signature=self.preview_signature(self.data['zones'],clips,audio)
        if any(s==signature for p,s in self.previews):
            self.live_audio.request(signature,clips,audio)
            for p,s in self.previews:
                if s==signature:p.audio_status.configure(text='Actualisation du volume…')

    def receive_preview_audio(self,signature,path,asset,error):
        if error:
            self.status.set('Actualisation audio impossible : '+error)
            for p,s in self.previews:
                if not p.closed and s==signature:p.audio_status.configure(text='Échec de l’actualisation audio')
            return
        players=[p for p,s in self.previews if not p.closed and s==signature]
        if not players:asset.cleanup(); return
        self.audio_assets[path]=asset
        for player in players:
            if not player.replace_audio(path):self.status.set('Le nouveau mixage a été calculé mais Windows n’a pas pu le lire.')
        used={getattr(p,'override_audio_path',None) for p,s in self.previews if not p.closed}
        for old in list(self.audio_assets):
            if old not in used:self.audio_assets.pop(old).cleanup()
    def cancel(self):
        self.cancelled=True
        job=self.active_render
        if job:job.cancel(); self.status.set('Rendu annulé.')
        self.active_render=None; self.busy=False; self.sync_render_buttons()
    def close(self):
        if not self.save_open_documents():return
        try:self.write_recovery(state='closed')
        except OSError as e:self.status.set('Récupération non enregistrée : '+str(e)); return
        self.cancel(); self.close_previews(); self.root.destroy()

def project(q,u,v):
    a,b,c,d=q; dx1=b[0]-c[0]; dx2=d[0]-c[0]; dx3=a[0]-b[0]+c[0]-d[0]; dy1=b[1]-c[1]; dy2=d[1]-c[1]; dy3=a[1]-b[1]+c[1]-d[1]
    det=dx1*dy2-dx2*dy1; g=(dx3*dy2-dx2*dy3)/det; h=(dx1*dy3-dx3*dy1)/det
    den=g*u+h*v+1
    return (( (b[0]-a[0]+g*b[0])*u+(d[0]-a[0]+h*d[0])*v+a[0])/den,((b[1]-a[1]+g*b[1])*u+(d[1]-a[1]+h*d[1])*v+a[1])/den)


def unproject(q,x,y):
    a,b,c,d=q; dx1=b[0]-c[0]; dx2=d[0]-c[0]; dx3=a[0]-b[0]+c[0]-d[0]; dy1=b[1]-c[1]; dy2=d[1]-c[1]; dy3=a[1]-b[1]+c[1]-d[1]
    det=dx1*dy2-dx2*dy1; g=(dx3*dy2-dx2*dy3)/det; h=(dx1*dy3-dx3*dy1)/det
    aa=b[0]-a[0]+g*b[0]-x*g; bb=d[0]-a[0]+h*d[0]-x*h
    cc=b[1]-a[1]+g*b[1]-y*g; dd=d[1]-a[1]+h*d[1]-y*h
    det=aa*dd-bb*cc
    if abs(det)<1e-12:return None
    return (((x-a[0])*dd-bb*(y-a[1]))/det,(aa*(y-a[1])-(x-a[0])*cc)/det)

def write_mire(path,zones,w,h,grid=True):
    buf=bytearray(w*h*3)
    def line(a,b,color):
        x,y=a[0]*(w-1),a[1]*(h-1); dx,dy=b[0]*(w-1)-x,b[1]*(h-1)-y; steps=max(1,math.ceil(max(abs(dx),abs(dy))))
        for i in range(steps+1):
            xx,yy=round(x+dx*i/steps),round(y+dy*i/steps)
            if 0<=xx<w and 0<=yy<h: idx=(yy*w+xx)*3; buf[idx:idx+3]=bytes(color)
    for i,q in enumerate(zones):
        color=[(65,216,255),(255,196,92),(194,152,255),(112,237,175)][i%4]
        for k in (range(9) if grid else (0,8)):
            t=k/8
            line(project(q,t,0),project(q,t,1),color); line(project(q,0,t),project(q,1,t),color)
    Path(path).write_bytes(f'P6\n{w} {h}\n255\n'.encode()+buf)

guard_methods(App,'numeric key','mapping')
guard_methods(App,'undo restore','any')
guard_methods(App,'choose_resolution','project')

if __name__=='__main__':
    root=tk.Tk()
    from diagnostics import install
    install(root,ROOT)
    App(root); root.mainloop()
