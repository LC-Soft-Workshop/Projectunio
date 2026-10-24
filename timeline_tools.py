"""Multi-selection, clip editing, markers and asynchronous audio waveforms."""
import array
import copy
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import uuid
import montage
import panorama


class TimelineTools:
    def __init__(self,app):
        self.app=app; self.t=app.timeline; self.selection=set(); self.clipboard=[]; self.group=None; self.closed=False
        self.waves={}; self.pending=set(); self.jobs=queue.Queue(); self.results=queue.SimpleQueue(); self.proc=None
        self.waveforms=tk.BooleanVar(value=True); self.draw_timer=None
        self.thumbnails=tk.BooleanVar(value=True)
        from work_media import WorkMedia
        app.media_work=WorkMedia(app.root,app.executable,self.draw)
        app.still_renderer.resolve_clips=app.media_work.resolve
        self.original_draw=self.t.draw; self.t.draw=self.draw
        self.original_press=self.t.press; self.original_motion=self.t.motion; self.original_release=self.t.release
        self.t.canvas.bind('<Button-1>',self.press); self.t.canvas.bind('<B1-Motion>',self.motion); self.t.canvas.bind('<ButtonRelease-1>',self.release)
        self.t.canvas.bind('<Button-3>',self.context_menu)
        def shortcut(fn):
            def invoke(event):fn(); return 'break'
            return invoke
        for key,fn in [('<Control-c>',self.copy),('<Control-v>',self.paste),('<Control-d>',self.duplicate),('<Delete>',self.remove),('<KP_Delete>',self.remove)]:self.t.canvas.bind(key,shortcut(fn))
        self.t.canvas.bind('<Control-a>',self.select_all)
        original_duration=self.t.edit_duration
        def duration(event):
            self.group=None
            if hasattr(self,'group_proposal'):del self.group_proposal
            lane=self.t.header_row(event)
            if lane is not None:self.t.edit_zone_name(lane); return 'break'
            clip=self.hit(event)
            if clip and clip['id'] not in self.selected_ids():self.selection={clip['id']}
            elif clip is None:self.selection=set()
            return original_duration(event)
        self.t.canvas.bind('<Double-Button-1>',duration)
        self.t.canvas.configure(xscrollcommand=lambda first,last:self.scroll_changed(first,last))
        self.scrollbar=next(child for child in self.t.frame.winfo_children() if isinstance(child,ttk.Scrollbar) and str(child.cget('orient'))=='horizontal')
        toolbar=ttk.Frame(self.t.frame); toolbar.pack(fill='x',before=self.t.canvas.master)
        ttk.Button(toolbar,text='+ Repère',command=self.marker).pack(side='left',padx=2)
        ttk.Checkbutton(toolbar,text='Onde audio',variable=self.waveforms,command=self.draw).pack(side='left',padx=5)
        ttk.Checkbutton(toolbar,text='Miniatures',variable=self.thumbnails,command=self.draw).pack(side='left',padx=5)
        self.worker=threading.Thread(target=self.wave_worker,daemon=True); self.worker.start(); self.timer=app.root.after(100,self.poll)
        menu=tk.Menu(app.root,tearoff=False)
        for label,fn in [('Tout sélectionner (Ctrl+A)',self.select_all),('Ajouter un repère',self.marker)]:menu.add_command(label=label,command=fn)
        app.root.nametowidget(app.root.cget('menu')).add_cascade(label='Montage',menu=menu)

    def selected_ids(self):
        ids={c['id'] for c in self.t.items}; self.selection.intersection_update(ids)
        if self.t.selected and self.t.selected not in self.selection:return {self.t.selected}
        return set(self.selection)

    def select_all(self,event=None):
        self.selection={c['id'] for c in self.t.items}; self.t.selected=next(iter(self.selection),None); self.draw(); return 'break'

    def hit(self,event):
        hit=self.t.hit_test(event); return hit[0] if hit else None

    def press(self,event):
        if self.app.edit_locked('timeline'):
            self.t.dragging=None; self.group=None; self.t.canvas.focus_set()
            self.t.scrubbing=self.t.canvas.canvasy(event.y)<28
            if self.t.header_row(event) is None:self.app.set_playhead((self.t.canvas.canvasx(event.x)-85)/self.t.pixels_per_second())
            return 'break'
        if self.t.header_row(event) is not None:return self.original_press(event)
        clip=self.hit(event); self.group=None
        if hasattr(self,'group_proposal'):del self.group_proposal
        if event.state&4 and clip:
            if clip['id'] in self.selection:self.selection.remove(clip['id'])
            else:self.selection.add(clip['id'])
            self.t.selected=clip['id'] if clip['id'] in self.selection else next(iter(self.selection),None)
            self.t.dragging=None; self.t.scrubbing=False; self.t.refresh(); return 'break'
        hit=self.t.hit_test(event)
        if clip and clip['id'] in self.selection and len(self.selection)>1 and hit[1]=='move':
            self.t.selected=clip['id']; self.t.canvas.focus_set()
            self.group=(copy.deepcopy([c for c in self.t.items if c['id'] in self.selection]),self.t.canvas.canvasx(event.x),clip['id']); return 'break'
        self.selection={clip['id']} if clip else set()
        if hasattr(self.t,'proposal'):del self.t.proposal
        self.original_press(event)

    def motion(self,event):
        if self.app.edit_locked('timeline'):
            if self.t.scrubbing:self.app.set_playhead((self.t.canvas.canvasx(event.x)-85)/self.t.pixels_per_second())
            return
        if self.group:
            originals,anchor,primary=self.group; delta=(self.t.canvas.canvasx(event.x)-anchor)/self.t.pixels_per_second()
            delta=max(delta,-min(c['start'] for c in originals))
            moved=[dict(c,start=c['start']+delta) for c in originals]
            if self.t.magnetic.get():
                leader=next(c for c in moved if c['id']==primary); others=[c for c in self.t.items if c['id'] not in self.selection]+[leader]
                snapped,guide=montage.snap_clip(leader,others,'move',10/self.t.pixels_per_second(),[m['time'] for m in self.app.data.get('markers',[])])
                shift=snapped['start']-leader['start']; moved=[dict(c,start=c['start']+shift) for c in moved]; self.t.snap_time=guide
            replacements={c['id']:c for c in moved}; proposed=[replacements.get(c['id'],c) for c in self.t.items]
            try:montage.validate_items(proposed)
            except ValueError:return
            self.group_proposal=proposed; self.draw(proposed); return
        self.original_motion(event)

    def release(self,event):
        if self.group:
            self.group=None; self.t.snap_time=None
            if hasattr(self,'group_proposal'):proposed=self.group_proposal; del self.group_proposal; self.commit(proposed)
            else:self.draw()
            return
        self.original_release(event)

    def commit(self,items):
        try:montage.validate_items(items)
        except ValueError as e:self.app.status.set(str(e)); return False
        self.app.checkpoint(); self.app.data['clips']=[c for c in items if c.get('kind')!='audio']; self.app.data['audio_clips']=[c for c in items if c.get('kind')=='audio']; self.t.refresh(); return True

    def split(self):
        ids=self.selected_ids(); at=self.app.playhead; output=[]; changed=False
        for c in self.t.items:
            d=montage.length(c); offset=at-c['start']
            if c['id'] in ids and offset>=1/30 and d-offset>=1/30:
                left=copy.deepcopy(c); right=copy.deepcopy(c); cut=c['in']+offset
                left['out']=cut; right.update(id=uuid.uuid4().hex,start=at); right['in']=cut
                left['fade_out']=0.; left['fade_in']=min(c.get('fade_in',0.),offset)
                right['fade_in']=0.; right['fade_out']=min(c.get('fade_out',0.),d-offset)
                output.extend((left,right)); changed=True
            else:output.append(c)
        if changed:self.commit(output)
        else:self.app.status.set('Placez le curseur à l’intérieur d’un clip sélectionné (au moins une image de chaque côté).')

    def copy(self):
        ids=self.selected_ids(); self.clipboard=copy.deepcopy([c for c in self.t.items if c['id'] in ids]); self.app.status.set(f'{len(self.clipboard)} clip(s) copié(s).')

    def paste(self,position=None):
        if not self.clipboard:return
        anchor=min(c['start'] for c in self.clipboard); at=self.app.playhead if position is None else position
        added=[dict(copy.deepcopy(c),id=uuid.uuid4().hex,start=at+c['start']-anchor) for c in self.clipboard]
        if any(c.get('kind')!='audio' and max(panorama.lanes(c))>=self.t.zone_count for c in added):self.app.status.set('Le projet de destination ne contient pas les zones nécessaires.'); return
        if self.commit(self.t.items+added):
            self.app.data['audio_track_count']=max(self.t.track_count,max((c['lane']+1 for c in added if c.get('kind')=='audio'),default=0))
            if 'audio_track_names' in self.app.data:self.app.data['audio_track_names']=self.app.audio_names()
            self.selection={c['id'] for c in added}; self.t.selected=added[-1]['id']; self.t.refresh()

    def duplicate(self):
        self.copy()
        if self.clipboard:self.paste(max(c['start']+montage.length(c) for c in self.clipboard))

    def remove(self):
        ids=self.selected_ids()
        if ids and self.commit([c for c in self.t.items if c['id'] not in ids]):self.selection.clear(); self.t.selected=None; self.t.refresh()

    def fades(self):return self.t.open_properties()

    def context_menu(self,event):
        self.t.finish_name_edit(); self.t.canvas.focus_set()
        row=self.t.header_row(event)
        if row is not None:
            menu=tk.Menu(self.app.root,tearoff=False)
            menu.add_command(label='Renommer',command=lambda:self.t.edit_zone_name(row))
            menu.add_command(label='Supprimer la piste audio' if row>=self.t.zone_count else 'Supprimer la zone',command=lambda:self.app.delete_timeline_track(row))
            menu.tk_popup(event.x_root,event.y_root); return 'break'
        clip=self.hit(event)
        if clip is None:return self.marker_menu(event)
        self.group=None; self.t.dragging=None; self.t.scrubbing=False; self.t.snap_time=None
        if hasattr(self,'group_proposal'):del self.group_proposal
        if hasattr(self.t,'proposal'):del self.t.proposal
        if clip['id'] not in self.selected_ids():self.selection={clip['id']}
        self.t.selected=clip['id']; self.t.refresh()
        menu=tk.Menu(self.app.root,tearoff=False)
        menu.add_command(label='Propriétés…',accelerator='Double-clic',command=self.t.open_properties)
        menu.add_separator()
        can_split=any(c['id'] in self.selected_ids() and c['start']+1/30<=self.app.playhead<=c['start']+montage.length(c)-1/30 for c in self.t.items)
        for label,key,fn in [('Dupliquer','Ctrl+D',self.duplicate),('Copier','Ctrl+C',self.copy),('Couper au curseur','',self.split),('Supprimer','Suppr',self.remove)]:menu.add_command(label=label,accelerator=key,command=fn,state='disabled' if label=='Couper au curseur' and not can_split else 'normal')
        menu.add_command(label='Coller au curseur',accelerator='Ctrl+V',command=self.paste,state='normal' if self.clipboard else 'disabled')
        videos=[c for c in self.t.clips if c['id'] in self.selected_ids()]
        if videos:
            menu.add_command(label='Vidéo panoramique…',command=self.app.edit_panorama,state='normal' if len(videos)==1 else 'disabled')
            menu.add_separator(); menu.add_command(label='Copier le cadrage',command=self.app.copy_framing,state='disabled' if clip.get('kind')=='audio' else 'normal')
            menu.add_command(label='Coller le cadrage',command=self.app.paste_framing,state='normal' if hasattr(self.app,'framing') else 'disabled')
            def reset():
                ids=self.selected_ids(); self.commit([dict(c,zoom=1.,pan_x=0.,pan_y=0.) if c['id'] in ids and c.get('kind')!='audio' else c for c in self.t.items])
            menu.add_command(label='Réinitialiser le cadrage',command=reset)
        menu.tk_popup(event.x_root,event.y_root)
        return 'break'

    def marker(self):
        name=simpledialog.askstring('Repère','Nom du repère',initialvalue=f'Repère {len(self.app.data.get("markers",[]))+1}',parent=self.app.root)
        if name:
            self.app.checkpoint(); self.app.data.setdefault('markers',[]).append(dict(time=self.app.playhead,name=name)); self.draw()

    def marker_menu(self,event):
        x=self.t.canvas.canvasx(event.x); px=self.t.pixels_per_second(); candidates=[m for m in self.app.data.get('markers',[]) if abs(85+m['time']*px-x)<12]
        if not candidates:
            target=self.t.drop_target(event.x,event.y)
            if target is None:return
            menu=tk.Menu(self.app.root,tearoff=False)
            self.t.track_menu(event,menu=menu)
            menu.add_command(label='Coller ici',accelerator='Ctrl+V',command=lambda:self.paste(target[1]),state='normal' if self.clipboard else 'disabled')
            if self.t.header_row(event) is not None:menu.add_command(label='Renommer la zone',command=lambda:self.t.edit_zone_name(target[0]))
            menu.tk_popup(event.x_root,event.y_root); return

        if self.app.edit_locked('timeline'):return
        marker=min(candidates,key=lambda m:abs(85+m['time']*px-x)); menu=tk.Menu(self.app.root,tearoff=False)
        menu.add_command(label='Aller à '+marker['name'],command=lambda:self.app.set_playhead(marker['time']))
        def remove():self.app.checkpoint(); self.app.data['markers'].remove(marker); self.draw()
        menu.add_command(label='Supprimer ce repère',command=remove); menu.tk_popup(event.x_root,event.y_root)

    def draw(self,clips=None):
        if self.closed:return
        if clips is None and self.group and hasattr(self,'group_proposal'):clips=self.group_proposal
        elif clips is None and self.t.dragging and hasattr(self.t,'proposal'):
            clips=[self.t.proposal if c['id']==self.t.proposal['id'] else c for c in self.t.items]
        self.original_draw(clips); c=self.t.canvas; px=self.t.pixels_per_second(); ids=self.selected_ids()
        media=self.app.media_work; media.begin_draw()
        for item in self.t.display_items(self.t.items if clips is None else clips):
            x=85+item['start']*px; y=28+self.t.row(item)*50; end=x+montage.length(item)*px
            if self.thumbnails.get() and item.get('kind')!='audio' and end-x>=32 and c.canvasy(0)<=y+38 and y<=c.canvasy(c.winfo_height()):
                left=max(x,c.canvasx(0)); right=min(end,c.canvasx(c.winfo_width())); spacing=max(68,(right-left)/12)
                position=left+4
                while position+28<right:
                    at=min(item['out']-1/30,item['in']+(position-x)/px)
                    image=media.thumbnail(item['path'],max(item['in'],at))
                    if image is not None:
                        # Keep the miniature inside the clip and above its name.
                        small=image.subsample(2); media.visible_images.append(small)
                        c.create_image(position,y+2,image=small,anchor='nw',tags='thumbnail')
                    position+=spacing
            if item['id'] in ids and item['id']!=self.t.selected:c.create_rectangle(x-3,y-2,end+3,y+40,outline='#ffe275',width=3,tags='multi_selection')
            if self.waveforms.get() and (item.get('audio') or item.get('kind')=='audio'):
                path=item['path']; key=self.wave_key(path); peaks=self.waves.get(key)
                if peaks is None and key not in self.pending and Path(path).is_file():self.pending.add(key); self.jobs.put((key,path))
                if peaks:
                    # Draw only the visible viewport; long recordings remain inexpensive.
                    left=max(x,c.canvasx(0)); right=min(end,c.canvasx(c.winfo_width()))
                    for xx in range(round(left)+1,round(right),3):
                        source=item['in']+(xx-x)/px; index=int(source*10)
                        peak=peaks[index] if 0<=index<len(peaks) else 0.; audio=item.get('kind')=='audio'; amplitude=peak*(10 if audio else 3); center=y+(27 if audio else 22)
                        c.create_line(xx,center-amplitude,xx,center+amplitude,fill='#9ee6d3',tags='waveform')
            for key,direction in [('fade_in',1),('fade_out',-1)]:
                amount=item.get(key,0.)
                if amount:
                    first=x if direction==1 else end-amount*px; last=x+amount*px if direction==1 else end
                    c.create_line(first,y+(36 if direction==1 else 2),last,y+(2 if direction==1 else 36),fill='#ffdb9a',width=2,tags='fade')
        height=30+(self.t.zone_count+self.t.track_count)*50
        for marker in self.app.data.get('markers',[]):
            x=85+marker['time']*px; c.create_line(x,0,x,height,fill='#a3ef8b',dash=(3,4),tags='marker'); c.create_text(x+4,3,text=marker['name'],anchor='nw',fill='#a3ef8b',tags='marker')
        self.t.draw_trim_handles(self.t.items if clips is None else clips)

    def scroll_changed(self,first,last):
        if hasattr(self,'scrollbar'):self.scrollbar.set(first,last)
        # Canvas moves existing waveform strokes; redraw after a scroll to fill newly exposed ranges.
        if getattr(self,'last_scroll',None)!=(first,last):
            self.last_scroll=(first,last)
            if not self.closed and self.draw_timer is None:self.draw_timer=self.app.root.after_idle(self.scroll_redraw)

    def scroll_redraw(self):
        self.draw_timer=None
        if not self.closed:self.draw()

    @staticmethod
    def wave_key(path):
        try:stat=Path(path).stat(); return path,stat.st_size,stat.st_mtime_ns
        except OSError:return path,0,0

    def wave_worker(self):
        while True:
            job=self.jobs.get()
            if job is None or self.closed:return
            key,path=job; peaks=[]
            try:
                self.proc=subprocess.Popen([self.app.executable,'-v','error','-i',path,'-vn','-ac','1','-ar','1000','-f','s16le','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)
                if self.closed and self.proc.poll() is None:self.proc.terminate()
                while not self.closed:
                    block=self.proc.stdout.read(200)
                    if not block:break
                    samples=array.array('h',block[:len(block)//2*2]); peaks.append(max((abs(v)/32768 for v in samples),default=0.))
                if self.closed and self.proc.poll() is None:self.proc.terminate()
                self.proc.wait()
            except OSError:pass
            finally:
                if self.proc:
                    if self.proc.poll() is None:self.proc.terminate(); self.proc.wait()
                    if self.proc.stdout:self.proc.stdout.close()
                self.proc=None
            self.results.put((key,peaks))

    def poll(self):
        if self.closed:return
        changed=False
        while True:
            try:key,peaks=self.results.get_nowait()
            except queue.Empty:break
            self.waves[key]=peaks; self.pending.discard(key); changed=True
        if changed:self.draw()
        self.timer=self.app.root.after(100,self.poll)

    def close(self):
        self.closed=True
        self.app.media_work.close()
        try:self.app.root.after_cancel(self.timer)
        except tk.TclError:pass
        if self.draw_timer is not None:
            try:self.app.root.after_cancel(self.draw_timer)
            except tk.TclError:pass
            self.draw_timer=None
        if self.proc and self.proc.poll() is None:self.proc.terminate()
        self.jobs.put(None)


from editor_controls import guard_methods
guard_methods(TimelineTools,"commit paste duplicate remove split marker", "timeline")
