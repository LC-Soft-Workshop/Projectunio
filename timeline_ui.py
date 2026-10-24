"""Editable multizone timeline with direct native file drops onto its tracks."""
import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid
import montage
import panorama
from clip_properties import ClipProperties
from windows_drop import FileDrop


class Timeline:
    def __init__(self,app,parent):
        self.app=app; self.selected=None; self.dragging=None; self.hooks=[]; self.snap_time=None; self.scrubbing=False
        self.audio_lane=tk.StringVar(value='1'); self.name_editor=None; self.hover=None
        self.frame=ttk.Frame(parent,padding=(10,4)); self.frame.pack(fill='x')
        audio_bar=ttk.Frame(self.frame); audio_bar.pack(fill='x')
        ttk.Button(audio_bar,text='+ Piste audio',command=self.add_audio_track).pack(side='left')
        ttk.Label(audio_bar,text='Glissez vos fichiers sur les pistes • Clic droit : importer un fichier').pack(side='left',padx=10)
        top=ttk.Frame(self.frame); top.pack(fill='x',pady=(6,2))
        ttk.Label(top,text='Montage • Double-clic : propriétés • Glisser : déplacer / raccourcir').pack(side='left')
        self.magnetic=tk.BooleanVar(value=True)
        ttk.Checkbutton(top,text='Magnétisme',variable=self.magnetic).pack(side='left',padx=12)
        self.total=ttk.Label(top); self.total.pack(side='right')
        self.scale=tk.StringVar(value='Auto')
        ttk.Combobox(top,textvariable=self.scale,values=['Auto','1','2','5','10','20','40','80'],state='readonly',width=5).pack(side='right',padx=5)
        ttk.Label(top,text='Zoom').pack(side='right'); self.scale.trace_add('write',lambda *a:self.draw())
        seek=ttk.Frame(self.frame); seek.pack(fill='x',pady=2)
        ttk.Label(seek,text='Image arrêtée (s)').pack(side='left')
        self.time=tk.StringVar(value='0.000')
        time_entry=ttk.Entry(seek,textvariable=self.time,width=9); time_entry.pack(side='left',padx=4); time_entry.bind('<Return>',lambda e:self.seek_field())
        ttk.Button(seek,text='Afficher',command=self.seek_field).pack(side='left')
        ttk.Button(seek,text='◀ Image',command=lambda:self.app.set_playhead(self.app.playhead-1/30)).pack(side='left',padx=3)
        ttk.Button(seek,text='Image ▶',command=lambda:self.app.set_playhead(self.app.playhead+1/30)).pack(side='left')
        ttk.Label(seek,textvariable=app.still_status).pack(side='left',padx=10)
        canvas_area=ttk.Frame(self.frame); canvas_area.pack(fill='x')
        self.canvas=tk.Canvas(canvas_area,height=180,bg='#17212a',highlightthickness=0,takefocus=True)
        self.canvas.pack(side='left',fill='both',expand=True); self.canvas.bind('<Configure>',lambda e:self.draw())
        vertical=ttk.Scrollbar(canvas_area,orient='vertical',command=self.canvas.yview); vertical.pack(side='right',fill='y'); self.canvas.configure(yscrollcommand=lambda a,b:(vertical.set(a,b),self.position_name_editor()))
        scroll=ttk.Scrollbar(self.frame,orient='horizontal',command=self.canvas.xview); scroll.pack(fill='x'); self.canvas.configure(xscrollcommand=scroll.set)
        self.canvas.bind('<Button-1>',self.press); self.canvas.bind('<B1-Motion>',self.motion); self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Delete>',lambda e:self.remove())
        self.canvas.bind('<Double-Button-1>',self.edit_duration)
        self.canvas.bind('<Motion>',self.hover_cursor); self.canvas.bind('<Leave>',self.leave_cursor)
        self.canvas.update_idletasks()
        try:self.hooks.append(FileDrop(self.canvas,self.drop_files,with_position=True))
        except OSError as e:self.app.status.set('Dépôt Windows indisponible ; utilisez le clic droit sur une piste. '+str(e))
        self.fields={k:tk.StringVar(value=v) for k,v in [('start','0'),('in','0'),('out','0'),('zoom','100'),('pan_x','0'),('pan_y','0')]}
        self.fit=tk.StringVar(value='Remplir')
        self.description=ttk.Label(self.frame,text='Glissez une vidéo, une image ou un son directement sur sa piste dans la timeline.',wraplength=1000)
        self.description.pack(anchor='w')
        self.refresh()

    @property
    def clips(self):return self.app.data.setdefault('clips',[])

    @property
    def audio_clips(self):return self.app.data.setdefault('audio_clips',[])

    @property
    def items(self):return self.clips+self.audio_clips

    @property
    def track_count(self):return self.app.data.setdefault('audio_track_count',1)

    @property
    def zone_count(self):return len(self.app.data['zones'])

    def zone_names(self):return self.app.zone_names()

    def header_row(self,event):
        x=self.canvas.canvasx(event.x); row=int((self.canvas.canvasy(event.y)-28)//50)
        return row if 0<=x<85 and 0<=row<self.zone_count+self.track_count else None

    def edit_zone_name(self,lane):
        if self.app.edit_locked('mapping' if lane<self.zone_count else 'timeline'):return
        self.finish_name_edit()
        if not 0<=lane<self.zone_count+self.track_count:return
        self.dragging=None; self.scrubbing=False
        if hasattr(self,'proposal'):del self.proposal
        self.name_edit_lane=lane; self.name_edit_data=self.app.data
        self.name_edit_value=tk.StringVar(value=(self.zone_names()+self.app.audio_names())[lane])
        self.name_editor=ttk.Entry(self.canvas,textvariable=self.name_edit_value)
        self.name_editor.bind('<Return>',lambda e:self.finish_name_edit())
        self.name_editor.bind('<Escape>',lambda e:self.finish_name_edit(False))
        self.name_editor.bind('<FocusOut>',lambda e:self.finish_name_edit())
        self.position_name_editor(); self.name_editor.focus_set(); self.name_editor.selection_range(0,'end')
        self.app.status.set('Renommer la piste : Entrée ou clic ailleurs pour valider • Échap pour annuler.')

    def position_name_editor(self):
        if self.name_editor is None:return
        y=28+self.name_edit_lane*50-self.canvas.canvasy(0)
        self.name_editor.place(x=2,y=round(y+2),width=220,height=34)

    def finish_name_edit(self,save=True):
        if self.name_editor is None:return 'break'
        entry=self.name_editor; self.name_editor=None
        name=self.name_edit_value.get().strip(); lane=self.name_edit_lane; data=self.name_edit_data
        entry.destroy()
        if save and not self.app.closing and self.app.data is data and lane<self.zone_count+self.track_count and name and name!=(self.zone_names()+self.app.audio_names())[lane]:
            audio=lane>=self.zone_count; names=self.app.audio_names() if audio else self.zone_names(); names[lane-self.zone_count if audio else lane]=name
            self.app.checkpoint(); self.app.data['audio_track_names' if audio else 'zone_names']=names; self.app.refresh()
            self.app.status.set('Zone renommée : '+name)
        return 'break'

    def row(self,clip):return clip['lane']+(self.zone_count if clip.get('kind')=='audio' else 0)

    def hits_row(self,clip,y):
        rows=[self.row(clip)] if clip.get('kind')=='audio' else panorama.lanes(clip)
        return any(28+row*50<=y<=66+row*50 for row in rows)

    def display_items(self,items):
        return [dict(c,lane=lane) for c in items for lane in ([c['lane']] if c.get('kind')=='audio' else panorama.lanes(c))]

    def hit_test(self,event):
        x=self.canvas.canvasx(event.x); y=self.canvas.canvasy(event.y); px=self.pixels_per_second()
        if x<85 or y<28:return None
        edges=[]; bodies=[]; row=int((y-28)//50)
        for clip in reversed(self.items):
            if not self.hits_row(clip,y):continue
            left=85+clip['start']*px; right=left+montage.length(clip)*px; reach=min(12,max(3,(right-left)*.25))
            if left-4<=x<=right+4:
                for mode,at in [('in',left),('out',right)]:
                    distance=abs(x-at)
                    if distance<=reach:edges.append((distance,clip['id']!=self.selected,clip,mode,row))
            if left<=x<=right:bodies.append((clip,'move',row))
        if edges:
            hit=min(edges,key=lambda item:item[:2]); return hit[2:]
        return bodies[0] if bodies else None

    def hover_cursor(self,event):
        if self.dragging:return
        hit=self.hit_test(event)
        locked=any(self.app.data.get('locks',{}).get(k,False) for k in ('timeline','project'))
        hover=None if hit is None or locked else (hit[0]['id'],hit[1],hit[2])
        self.canvas.configure(cursor='sb_h_double_arrow' if hover and hover[1] in ('in','out') else '')
        if hover!=self.hover:self.hover=hover; self.draw_trim_handles()

    def leave_cursor(self,event=None):
        if self.dragging:return
        self.hover=None; self.canvas.configure(cursor=''); self.canvas.delete('trim_handle')

    def draw_trim_handles(self,items=None):
        self.canvas.delete('trim_handle')
        if self.hover is None:return
        identifier,mode,row=self.hover
        clip=next((c for c in (self.items if items is None else items) if c['id']==identifier),None)
        if clip is None:return
        px=self.pixels_per_second(); left=85+clip['start']*px; right=left+montage.length(clip)*px; y=28+row*50
        for side,x in [('in',left),('out',right)]:
            color='#fff1a8' if side==mode else '#d0e5ed'
            center=x+4 if side=='in' else x-4
            self.canvas.create_rectangle(center-4,y+2,center+4,y+36,fill=color,outline='#17212a',tags=('trim_handle',f'trim_{side}'))
            self.canvas.create_text(center,y+19,text='↔',fill='#17212a',font=('Segoe UI',9,'bold'),tags=('trim_handle',f'trim_{side}'))

    def drop_target(self,x,y):
        if x is None or y is None:return None
        row=int((self.canvas.canvasy(y)-28)//50)
        if not 0<=row<self.zone_count+self.track_count:return None
        at=max(0.,(self.canvas.canvasx(x)-85)/self.pixels_per_second())
        if self.magnetic.get():
            targets={0.}|{v for c in self.items for v in (c['start'],c['start']+montage.length(c))}|{m['time'] for m in self.app.data.get('markers',[])}
            nearest=min(targets,key=lambda t:abs(t-at))
            if abs(nearest-at)<=10/self.pixels_per_second():at=nearest
        return row,at

    def drop_files(self,paths,x,y):
        target=self.drop_target(x,y)
        if target is None:self.app.status.set('Déposez les fichiers sur une piste vidéo ou audio.'); return
        row,at=target
        if row<self.zone_count:self.import_files(row,paths,start=at)
        else:self.import_audio(paths,lane=row-self.zone_count,start=at)

    def track_menu(self,event,menu=None):
        target=self.drop_target(event.x,event.y)
        if target is None:return
        row,at=target; popup=menu is None
        if menu is None:menu=tk.Menu(self.app.root,tearoff=False)
        if row<self.zone_count:
            menu.add_command(label=f'Importer une vidéo ou image ici — {self.zone_names()[row]}',command=lambda:self.import_files(row,start=at))
        else:
            menu.add_command(label=f'Importer un son ici — {self.app.audio_names()[row-self.zone_count]}',command=lambda:self.import_audio(lane=row-self.zone_count,start=at))
        if popup:menu.tk_popup(event.x_root,event.y_root)

    @staticmethod
    def free_start(items,lane,start,duration):
        for c in sorted((c for c in items if lane in panorama.lanes(c)),key=lambda c:c['start']):
            if start+duration<=c['start']+1e-8:break
            if start<c['start']+montage.length(c)-1e-8:start=c['start']+montage.length(c)
        return start

    def add_audio_track(self):
        if self.track_count>=64:self.app.status.set('La limite de 64 pistes audio est atteinte.'); return
        names=self.app.audio_names()+[f'Audio {self.track_count+1}']
        self.app.checkpoint(); self.app.data['audio_track_count']=self.track_count+1; self.app.data['audio_track_names']=names
        self.audio_lane.set(str(self.track_count)); self.refresh()

    def import_audio(self,paths=None,lane=None,start=None):
        if paths is None:paths=filedialog.askopenfilenames(title='Ajouter des sons',filetypes=[('Audio','*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.mp4'),('Tous','*.*')])
        if not paths:return
        if not self.track_count:self.add_audio_track()
        lane=min(self.track_count-1,int(self.audio_lane.get())-1) if lane is None else lane
        start=max((c['start']+montage.length(c) for c in self.audio_clips if c['lane']==lane),default=0) if start is None else start
        added=[]; errors=[]
        for path in paths:
            try:
                self.app.status.set('Import audio : '+Path(path).name); self.app.root.update_idletasks()
                d=montage.probe_audio(path,self.app.executable)
                start=self.free_start(self.audio_clips+added,lane,start,d)
                added.append(dict(id=uuid.uuid4().hex,kind='audio',path=str(Path(path).resolve()),lane=lane,start=start,**{'in':0.,'out':d},duration=d,volume=1.)); start+=d
            except Exception as e:errors.append(Path(path).name+' : '+str(e)[-400:])
        if added:
            self.app.checkpoint(); self.audio_clips.extend(added); self.selected=added[-1]['id']; self.refresh()
            self.app.status.set('Audio ajouté. Déplacez le bloc pour le caler sur les vidéos.')
        if errors:messagebox.showerror('Import audio impossible','\n\n'.join(errors),parent=self.app.root)

    def import_files(self,lane,paths=None,start=None):
        if paths is None:
            paths=filedialog.askopenfilenames(title='Vidéos et images pour '+self.zone_names()[lane],filetypes=[('Vidéos et images','*.mp4 *.mov *.mkv *.avi *.webm *.jpg *.jpeg *.png'),('Images','*.jpg *.jpeg *.png'),('Tous','*.*')])
        if not paths:return
        added=[]; errors=[]
        start=max((c['start']+montage.length(c) for c in self.clips if lane in panorama.lanes(c)),default=0) if start is None else start
        for path in paths:
            try:
                self.app.status.set('Import : '+Path(path).name); self.app.root.update_idletasks()
                image=montage.image_path(path)
                duration,audio=(montage.probe_image if image else montage.probe)(path,self.app.executable)
                start=self.free_start(self.clips+added,lane,start,duration)
                clip={'id':uuid.uuid4().hex,'path':str(Path(path).resolve()),'lane':lane,'start':start,'in':0.,'out':duration,'duration':duration,'audio':audio,'volume':1.,'fit':'Remplir','zoom':1.,'pan_x':0.,'pan_y':0.}
                if image:clip['kind']='image'
                added.append(clip); start+=duration
            except Exception as e:errors.append(Path(path).name+' : '+str(e)[-400:])
        if added:
            self.app.checkpoint(); self.clips.extend(added); self.selected=added[-1]['id']; self.refresh()
            self.app.status.set(f'{len(added)} média(s) ajouté(s) à '+self.zone_names()[lane]+'. L’aperçu lit toutes les pistes ensemble.')
        if errors:messagebox.showerror('Import impossible','\n\n'.join(errors),parent=self.app.root)

    def refresh(self):
        self.snap_time=None
        if int(self.audio_lane.get())>self.track_count:self.audio_lane.set('1')
        self.app.playhead=min(self.app.playhead,montage.duration(self.items)); self.time.set(f'{self.app.playhead:.3f}')
        self.draw()
        clip=next((c for c in self.items if c['id']==self.selected),None)
        if clip:
            for key,var in self.fields.items():var.set(f'{clip.get(key,1. if key=="zoom" else 0.)*(100 if key in ("volume","zoom","pan_x","pan_y") else 1):.3f}'.rstrip('0').rstrip('.'))
            audio=clip.get('kind')=='audio'; self.fit.set(clip.get('fit','Remplir'))
            self.description.configure(text=Path(clip['path']).name+' • '+(self.app.audio_names()[clip['lane']] if audio else self.zone_names()[clip['lane']]))
            self.description.configure(text=self.description.cget('text')+f' • Volume {clip["volume"]*100:g} %')
            if 'panorama' in clip:self.description.configure(text=Path(clip['path']).name+' • Panoramique : '+' → '.join(self.zone_names()[lane] for lane in panorama.lanes(clip))+f' • Volume {clip["volume"]*100:g} %')
        else:self.selected=None; self.description.configure(text='Glissez une vidéo, une image ou un son directement sur sa piste dans la timeline.')
        self.app.schedule_still()

    def seek_field(self):
        try:self.app.set_playhead(float(self.time.get().replace(',','.')))
        except ValueError:self.time.set(f'{self.app.playhead:.3f}')

    def pixels_per_second(self):
        if self.scale.get()!='Auto':return float(self.scale.get())
        total=montage.duration(self.items); width=self.canvas.winfo_width()
        if total<=0 or width<=110:return 40.
        return min(40.,max(1e-9,(width-85-24)/total))

    def draw(self,clips=None):
        if not hasattr(self,'canvas'):return
        clips=self.items if clips is None else clips; c=self.canvas; c.delete('all'); px=self.pixels_per_second()
        total=montage.duration(clips); width=c.winfo_width() if self.scale.get()=='Auto' else max(c.winfo_width(),120+(max(total,montage.duration(self.items))+2)*px)
        height=30+(self.zone_count+self.track_count)*50
        c.configure(height=min(180,height),scrollregion=(0,0,width,height)); self.total.configure(text=f'Durée : {total:.2f} s')
        if self.scale.get()=='Auto':c.xview_moveto(0)
        tick=max(1,round(80/px))
        for second in range(0,int((width-85)/px)+1,tick):
            x=85+second*px; c.create_line(x,20,x,height,fill='#2a3945'); c.create_text(x,10,text=f'{second}s',fill='#b6c3ce')
        for lane,label in enumerate(self.zone_names()+self.app.audio_names()):
            shown=label if len(label)<=11 else label[:10]+'…'
            y=28+lane*50; c.create_text(6,y+19,text=shown,fill='white',anchor='w',tags=('track_name',f'track_name_{lane}')); c.create_line(0,y+45,width,y+45,fill='#48545e')
        for clip in sorted(self.display_items(clips),key=lambda c:c['id']==self.selected):
            x=85+clip['start']*px; y=28+self.row(clip)*50; end=x+montage.length(clip)*px; color='#37785b' if clip.get('kind')=='audio' else ['#21768b','#987338','#7657a3','#397b78'][clip['lane']%4]
            selected=clip['id']==self.selected
            if selected:
                c.create_rectangle(x-6,y-5,end+6,y+43,fill='#45412a',outline='#766837',width=2,tags=('selection_halo',clip['id']))
                c.create_rectangle(x-3,y-2,end+3,y+40,outline='#ffe275',width=3,tags=('selection_halo',clip['id']))
                color='#4b9c72' if clip.get('kind')=='audio' else ['#339eb8','#bf913c','#9677c3','#599b98'][clip['lane']%4]
            c.create_rectangle(x,y,end,y+38,fill=color,outline='#ffe275' if selected else color,width=2,tags=('clip',clip['id']))
            if selected:c.create_rectangle(x,y,x+5,y+38,fill='#ffe275',outline='',tags='selection_halo')
            c.create_line(x+3,y+9,x+3,y+29,fill='#d8e2e9'); c.create_line(end-3,y+9,end-3,y+29,fill='#d8e2e9')
            limit=max(1,int((end-x-10)/7)); text=('↔ ' if 'panorama' in clip else '')+Path(clip['path']).name
            c.create_text(x+8,y+(12 if clip.get('kind')=='audio' else 29),anchor='w',text=text if len(text)<=limit else text[:max(1,limit-1)]+'…',fill='white',font=('Segoe UI',9,'bold' if selected else 'normal'),tags=('clip',clip['id']))
        if self.snap_time is not None:
            x=85+self.snap_time*px
            c.create_line(x,20,x,height,fill='#ffdf70',width=2,dash=(4,2),tags='snapguide')
            c.create_text(x+5,10,text=f'{self.snap_time:.3f} s',fill='#ffdf70',anchor='w',tags='snapguide')
        x=85+self.app.playhead*px
        c.create_line(x,20,x,height,fill='#f17a87',width=2,tags='playhead')
        c.create_polygon(x-6,20,x+6,20,x,27,fill='#f17a87',tags='playhead')
        self.position_name_editor()
        self.draw_trim_handles(clips)

    def press(self,event):
        lane=self.header_row(event)
        if lane is not None:
            self.dragging=None; self.scrubbing=False
            
            if lane<self.zone_count:self.app.zone=lane
            self.app.refresh(); return
        self.canvas.focus_set(); x=self.canvas.canvasx(event.x); y=self.canvas.canvasy(event.y); px=self.pixels_per_second()
        self.app.set_playhead((x-85)/px)
        self.scrubbing=y<28
        if self.scrubbing:self.dragging=None; return
        hit=self.hit_test(event)
        if hit:
            clip,mode,row=hit; self.selected=clip['id']; self.hover=(clip['id'],mode,row); self.dragging=(copy.deepcopy(clip),x,mode); self.refresh(); return
        self.selected=None; self.dragging=None; self.refresh()

    def edit_duration(self,event):
        lane=self.header_row(event)
        if lane is not None:self.edit_zone_name(lane); return 'break'
        self.dragging=None; self.scrubbing=False; self.snap_time=None
        if hasattr(self,'proposal'):del self.proposal
        x=self.canvas.canvasx(event.x); y=self.canvas.canvasy(event.y); px=self.pixels_per_second()
        old=next((c for c in reversed(self.items) if 85+c['start']*px<=x<=85+(c['start']+montage.length(c))*px and self.hits_row(c,y)),None)
        if old is None:return 'break'
        self.selected=old['id']; self.refresh()
        return self.open_properties()

    def open_properties(self):
        tools=getattr(self.app,'timeline_tools',None)
        ids=tools.selected_ids() if tools else {self.selected}
        selected=[c for c in self.items if c['id'] in ids]
        if not selected:return 'break'
        def validate(value):
            edited=value if isinstance(value,list) else [value]; replacements={c['id']:c for c in edited}
            montage.validate_items([replacements.get(c['id'],c) for c in self.items])
        dialog=ClipProperties(self.app.root,selected if len(selected)>1 else selected[0],validate,video_tracks=self.zone_names(),audio_tracks=self.app.audio_names())
        if dialog.result is not None:
            edited=dialog.result if isinstance(dialog.result,list) else [dialog.result]
            if edited!=selected:
                replacements={c['id']:c for c in edited}; proposed=[replacements.get(c['id'],c) for c in self.items]
                if len(edited)==1:self.commit(edited[0])
                elif tools and tools.commit(proposed):self.app.refresh_preview_audio()
        return 'break'

    def motion(self,event):
        if self.scrubbing:
            self.app.set_playhead((self.canvas.canvasx(event.x)-85)/self.pixels_per_second()); return
        if not self.dragging:return
        old,anchor,mode=self.dragging; clip=copy.deepcopy(old); delta=(self.canvas.canvasx(event.x)-anchor)/self.pixels_per_second()
        peers=[c for c in self.items if c['id']!=old['id'] and (c.get('kind')=='audio')==(old.get('kind')=='audio') and set(panorama.lanes(c)).intersection(panorama.lanes(old))]
        if mode=='move':
            clip['start']=max(0,old['start']+delta)
            row=max(0,int((self.canvas.canvasy(event.y)-28)//50))
            if clip.get('kind')=='audio':
                if self.zone_count<=row<self.zone_count+self.track_count:clip['lane']=row-self.zone_count
            elif row<self.zone_count and 'panorama' not in clip:clip['lane']=row
        elif mode=='in':
            previous=max((c['start']+montage.length(c) for c in peers if c['start']+montage.length(c)<=old['start']+1e-5),default=0.)
            delta=max(-old['start'],previous-old['start'],min(delta,montage.length(old)-1/30)) if montage.is_image(old) else max(-old['in'],-old['start'],previous-old['start'],min(delta,montage.length(old)-1/30))
            clip['start']+=delta
            clip['in']=max(0.,old['in']+delta)
            clip['out']=clip['in']+montage.length(old)-delta
        else:
            following=min((c['start'] for c in peers if c['start']>=old['start']+montage.length(old)-1e-5),default=float('inf'))
            clip['out']=max(clip['in']+1/30,min(float('inf') if montage.is_image(clip) else clip['duration'],following-old['start']+old['in'],old['out']+delta))
        self.snap_time=None
        if self.magnetic.get():clip,self.snap_time=montage.snap_clip(clip,self.items,mode,10/self.pixels_per_second(),[m['time'] for m in self.app.data.get('markers',[])])
        self.proposal=clip; self.draw([clip if c['id']==clip['id'] else c for c in self.items])
        if mode in ('in','out'):self.description.configure(text=f'Coupe {"du début" if mode=="in" else "de la fin"} • Début source : {clip["in"]:.3f} s • Fin source : {clip["out"]:.3f} s • Durée conservée : {montage.length(clip):.3f} s')

    def release(self,event):
        if self.scrubbing:self.scrubbing=False; return
        if not self.dragging:return
        self.dragging=None; self.snap_time=None
        if hasattr(self,'proposal'):
            clip=self.proposal; del self.proposal; self.commit(clip)

    def commit(self,clip):
        old=next((c for c in self.items if c['id']==clip['id']),None)
        volume_changed=old is not None and old['volume']!=clip['volume']
        proposed=[clip if c['id']==clip['id'] else c for c in self.items]
        try:montage.validate_items(proposed)
        except ValueError as e:self.app.status.set(str(e)); self.refresh(); return
        self.app.checkpoint(); self.app.data['clips']=[c for c in proposed if c.get('kind')!='audio']; self.app.data['audio_clips']=[c for c in proposed if c.get('kind')=='audio']; self.refresh()
        self.app.status.set('Montage modifié. Relancez l’aperçu pour voir le résultat.')
        if volume_changed:
            self.app.status.set(f'Volume appliqué : {clip["volume"]*100:g} %.')
            self.app.refresh_preview_audio()

    def apply(self):
        old=next((c for c in self.items if c['id']==self.selected),None)
        if not old:return
        clip=copy.deepcopy(old)
        try:
            for key,var in self.fields.items():
                if clip.get('kind')=='audio' and key in ('zoom','pan_x','pan_y'):continue
                clip[key]=float(var.get().replace('%','').replace(',','.'))/(100 if key in ('volume','zoom','pan_x','pan_y') else 1)
            if clip.get('kind')!='audio':clip['fit']=self.fit.get()
            self.commit(clip)
        except ValueError:self.app.status.set('Saisissez des nombres valides pour les réglages du clip.')

    def remove(self):
        if not self.selected:return
        self.app.checkpoint(); self.app.data['clips']=[c for c in self.clips if c['id']!=self.selected]; self.app.data['audio_clips']=[c for c in self.audio_clips if c['id']!=self.selected]; self.selected=None; self.refresh()

    def change_zoom(self,factor):
        old=next((c for c in self.clips if c['id']==self.selected),None)
        if old:
            clip=copy.deepcopy(old); clip['zoom']=min(4.,max(.25,clip.get('zoom',1.)*factor)); self.commit(clip)

    def reset_framing(self):
        old=next((c for c in self.clips if c['id']==self.selected),None)
        if old:
            clip=copy.deepcopy(old); clip.update(zoom=1.,pan_x=0.,pan_y=0.); self.commit(clip)


from editor_controls import guard_methods
guard_methods(Timeline,"drop_files add_audio_track import_audio import_files open_properties commit apply remove change_zoom reset_framing", "timeline")
