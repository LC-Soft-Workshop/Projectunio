"""Canvas toolbar, coordinate dialog and per-document edit locks."""
import functools
import math
import tkinter as tk
from tkinter import ttk, messagebox


def guard_methods(cls,names,scope):
    for name in names.split():
        original=getattr(cls,name)
        @functools.wraps(original)
        def guarded(self,*args,_original=original,**kwargs):
            app=getattr(self,'app',self)
            if app.edit_locked(scope):return False
            return _original(self,*args,**kwargs)
        setattr(cls,name,guarded)


class EditorControls:
    def edit_locked(self,scope):
        locks=self.data.get('locks',{})
        locked=locks.get('project',False) or (any(locks.values()) if scope=='any' else locks.get(scope,False))
        if locked:self.status.set('Modification impossible : déverrouillez '+('le projet' if locks.get('project') else 'le mapping ou la timeline')+' dans la barre d’outils.')
        return locked

    def install_editor_toolbar(self):
        from toolbar import IconToolbar
        bar=self.icon_toolbar=IconToolbar(self.root); bar.pack(fill='x',before=self.canvas)
        for name,label,command in [('new','Nouveau projet — Ctrl+N',self.new_document),('open','Ouvrir un projet — Ctrl+O',self.load),('save','Enregistrer — Ctrl+S',self.save),('undo','Annuler',self.undo),('redo','Rétablir',self.restore)]:bar.add(name,label,command)
        bar.separator()
        bar.add('mapping','Modifier le mapping : coins et arêtes',self.draw,self.edit_mode,'mapping')
        bar.add('video','Déplacer et cadrer le média dans sa zone',self.draw,self.edit_mode,'video')
        bar.add('draw','Dessiner une zone — 4 clics ; clic droit ou Échap pour annuler',self.begin_zone,self.edit_mode,'draw')
        bar.add('grid','Afficher la grille du mapping',self.draw,self.mapping_grid)
        bar.separator()
        bar.add('panorama','Répartir le média sélectionné en panoramique',self.edit_panorama)
        bar.add('compare','Comparer la source et la répartition',self.open_source_view)
        bar.add('play','Lecture directe depuis le curseur',self.direct_play)
        bar.separator()
        self.lock_vars={key:tk.BooleanVar() for key in ('mapping','timeline','project')}
        for key,text in [('mapping','Verrou mapping'),('timeline','Verrou timeline'),('project','Verrou projet')]:
            bar.add('lock_'+key,text+' — activer / désactiver',lambda k=key:self.toggle_editor_lock(k),self.lock_vars[key])
        bar.separator()
        self.hdmi_vars={key:tk.BooleanVar() for key in ('mire','image')}
        bar.add('mire','Mire HDMI — ouvrir / fermer',lambda:self.projector(False),self.hdmi_vars['mire'])
        bar.add('image','Image HDMI — ouvrir / fermer',lambda:self.projector(True),self.hdmi_vars['image'])
        def update_mires():self.draw(); self.check_render_invalidation()
        bar.add('projection_grid','Grille des mires HDMI et USB',update_mires,self.mire_grid)
        bar.add('refresh','Actualiser la liste des écrans',self.refresh_screens)

    def sync_editor_locks(self):
        for key,var in getattr(self,'lock_vars',{}).items():var.set(bool(self.data.get('locks',{}).get(key,False)))
        if hasattr(self,'icon_toolbar'):
            blocked=any(self.data.get('locks',{}).get(key,False) for key in ('mapping','project'))
            self.icon_toolbar.buttons['draw'].state(['disabled'] if blocked else ['!disabled'])
        if hasattr(self,'name_entry'):self.name_entry.configure(state='disabled' if self.data.get('locks',{}).get('project') else 'normal')
        if hasattr(self,'resolution_selector'):self.resolution_selector.configure(state='disabled' if self.data.get('locks',{}).get('project') else 'readonly')

    def toggle_editor_lock(self,key):
        if key!='project' and self.data.get('locks',{}).get('project'):
            self.sync_editor_locks(); self.status.set('Déverrouillez d’abord le projet.'); return
        self.timeline.finish_name_edit()
        self.data.setdefault('locks',{})[key]=self.lock_vars[key].get()
        self.anchor=None; self.discard_video_proxy(); self.timeline.dragging=None; self.timeline.scrubbing=False
        self.timeline_tools.group=None
        for obj,attr in [(self.timeline,'proposal'),(self.timeline_tools,'group_proposal')]:
            if hasattr(obj,attr):delattr(obj,attr)
        self.cancel_zone(); self.refresh()

    def open_corner_properties(self,event):
        if self.edit_mode.get()!='mapping':return False
        ox,oy,w,h=self.viewport(self.canvas)
        candidates=[(math.hypot(event.x-ox-x*w,event.y-oy-y*h),lane,i) for lane,q in enumerate(self.data['zones']) for i,(x,y) in enumerate(q)]
        distance,lane,corner=min(candidates)
        if distance>12:return False
        if self.edit_locked('mapping'):return True
        self.end_mapping_gesture(); self.zone=lane; self.corner=corner; self.edge=None; self.refresh()
        dialog=tk.Toplevel(self.root); dialog.title(f'{self.zone_names()[lane]} — Coin {corner+1}'); dialog.transient(self.root); dialog.resizable(False,False)
        fields=[]
        for index,label in enumerate(('X (%)','Y (%)')):
            ttk.Label(dialog,text=label).grid(row=index,column=0,padx=12,pady=8)
            value=tk.StringVar(value=f'{self.data["zones"][lane][corner][index]*100:.3f}'); fields.append(value)
            entry=ttk.Entry(dialog,textvariable=value,width=14); entry.grid(row=index,column=1,padx=12,pady=8)
            if index==0:first=entry
        def apply():
            from app import valid
            if self.edit_locked('mapping'):return
            try:point=[float(v.get().replace(',','.'))/100 for v in fields]
            except ValueError:messagebox.showerror('Coordonnées','Saisissez deux pourcentages valides.',parent=dialog); return
            quad=[list(p) for p in self.data['zones'][lane]]; quad[corner]=point
            if not all(math.isfinite(v) for v in point) or not valid(quad):messagebox.showerror('Coordonnées','Ces coordonnées produisent une zone invalide.',parent=dialog); return
            if quad!=self.data['zones'][lane]:self.checkpoint(); self.data['zones'][lane]=quad; self.refresh()
            dialog.destroy()
        ttk.Button(dialog,text='Valider',command=apply).grid(row=2,column=0,padx=12,pady=12)
        ttk.Button(dialog,text='Annuler',command=dialog.destroy).grid(row=2,column=1,padx=12,pady=12)
        dialog.bind('<Return>',lambda e:apply()); dialog.bind('<Escape>',lambda e:dialog.destroy()); dialog.grab_set(); first.focus_set(); first.selection_range(0,'end'); self.root.wait_window(dialog)
        return True
