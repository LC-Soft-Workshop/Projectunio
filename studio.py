"""Project tabs, recovery, mapping tools and project-wide sound controls."""
import copy
import json
import math
import os
import subprocess
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import uuid
import queue
import threading
from types import SimpleNamespace
import montage
import panorama
from export_settings import valid_resolution
from advanced_features import AdvancedFeatures


def atomic_json(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+'.tmp')
    pending.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(pending,path)


def effective_items(data):
    """Apply the mixer to copies; never bake gains into editable source clips."""
    settings=data.get('mixer',{}); solo={k for k,v in settings.items() if v.get('solo')}
    result=[]
    for c in data.get('clips',[])+data.get('audio_clips',[]):
        key=('a' if c.get('kind')=='audio' else 'v')+str(c['lane']); track=settings.get(key,{})
        gain=0. if track.get('mute') or (solo and key not in solo) else track.get('volume',1.)
        result.append(dict(c,volume=c['volume']*gain*data.get('master_volume',1.)))
    return [c for c in result if c.get('kind')!='audio'],[c for c in result if c.get('kind')=='audio']


def consolidate_levels(data):
    # Preserve the audible gain of projects created with the former mixer.
    master=data.get('master_volume',1.)
    mixer=data.get('mixer',{})
    for c in data.get('clips',[])+data.get('audio_clips',[]):
        key=('a' if c.get('kind')=='audio' else 'v')+str(c['lane'])
        c['volume']*=master*mixer.get(key,{}).get('volume',1.)
    data['master_volume']=1.
    for settings in mixer.values():settings['volume']=1.


def validate_extras(data):
    from calibration_versions import validate
    validate(data.get('calibration_versions',[]))
    for clip in data.get('clips',[]):panorama.validate(clip,len(data['zones']))
    locks=data.get('locks',{})
    if not isinstance(locks,dict) or any(k not in ('mapping','timeline','project') or type(v)!=bool for k,v in locks.items()):raise ValueError('Verrous invalides.')
    audio_names=data.get('audio_track_names')
    if audio_names is not None and (not isinstance(audio_names,list) or len(audio_names)!=data.get('audio_track_count',1) or any(not isinstance(n,str) or not n.strip() for n in audio_names)):raise ValueError('Noms de pistes audio invalides.')
    names=data.get('zone_names')
    if names is not None and (not isinstance(names,list) or len(names)!=len(data['zones']) or any(not isinstance(n,str) or not n.strip() for n in names)):raise ValueError('Noms de zones invalides.')
    gain=data.get('master_volume',1.)
    if not isinstance(gain,(int,float)) or not math.isfinite(gain) or not 0<=gain<=2:raise ValueError('Volume général invalide.')
    mixer=data.get('mixer',{})
    if not isinstance(mixer,dict):raise ValueError('Mixeur invalide.')
    for k,v in mixer.items():
        if not isinstance(k,str) or len(k)<2 or k[0] not in 'av' or not k[1:].isdigit() or not isinstance(v,dict):raise ValueError('Piste de mixage invalide.')
        volume=v.get('volume',1.)
        if not isinstance(volume,(float,int)) or not math.isfinite(volume) or not 0<=volume<=2 or any(type(v.get(b,False))!=bool for b in ('mute','solo')):raise ValueError('Réglage de mixage invalide.')
    markers=data.get('markers',[])
    if not isinstance(markers,list) or any(not isinstance(m,dict) or not isinstance(m.get('time'),(int,float)) or not math.isfinite(m['time']) or m['time']<0 or not isinstance(m.get('name'),str) for m in markers):raise ValueError('Repères invalides.')


class StudioFeatures(AdvancedFeatures):
    def audio_names(self):
        names=self.data.get('audio_track_names',[])
        return [names[i] if i<len(names) else f'Audio {i+1}' for i in range(self.data.get('audio_track_count',1))]

    def zone_names(self):
        return list(self.data.get('zone_names',[f'Zone {i+1}' for i in range(len(self.data['zones']))]))

    @staticmethod
    def edge_distance(p,a,b,w,h):
        px,py=p[0]*w,p[1]*h; ax,ay=a[0]*w,a[1]*h; dx,dy=(b[0]-a[0])*w,(b[1]-a[1])*h
        t=max(0.,min(1.,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy or 1.)))
        return math.hypot(px-ax-t*dx,py-ay-t*dy)

    def install_studio(self):
        from timeline_tools import TimelineTools
        self.documents=[]; self.active_document=None; self.switching=False; self.direct_player=None
        self.installation_counter=0; self.data['name']=self.next_project_name(); self.name.set(self.data['name'])
        self.session_id=uuid.uuid4().hex; self.recovery_path=Path(os.environ.get('PROJECTUNIO_RECOVERY_DIR',Path(__file__).parent/'recovery'))/('session-'+self.session_id+'.json')
        self.autosaved=None; self.last_recovery=None; self.drawing_zone=None
        from session_recovery import settings,interrupted_sessions
        self.recovery_settings=settings(self.recovery_path.parent)
        self.interrupted=interrupted_sessions(self.recovery_path.parent)
        recovery_dir=self.recovery_path.parent
        self.recoveries=sorted(recovery_dir.glob('session-*.json'),key=lambda p:p.stat().st_mtime,reverse=True) if recovery_dir.exists() else []
        from project_tabs import ProjectTabs
        self.tabs=ProjectTabs(self.root,self.close_document,self.new_document); self.tabs.pack(side='top',fill='x',before=self.root.winfo_children()[0])
        self.tabs.bind('<<NotebookTabChanged>>',self.change_document)
        menu=tk.Menu(self.root); self.root.configure(menu=menu)
        projects=tk.Menu(menu,tearoff=False); menu.add_cascade(label='Projets',menu=projects)
        for label,fn in [('Nouveau projet',self.new_document),('Ouvrir dans un onglet',self.load),('Enregistrer',self.save),('Rassembler le projet et ses médias…',self.gather_project),('Récupérer une session',self.recover_session),('Fermer cet onglet',self.close_document)]:projects.add_command(label=label,command=fn)
        projects.add_command(label='Sauvegardes automatiques…',command=self.recovery_manager)
        mapping=tk.Menu(menu,tearoff=False); menu.add_cascade(label='Mapping',menu=mapping)
        for label,fn in [('Dessiner une zone (4 clics)',self.begin_zone),('Nombre de zones…',self.choose_zone_count),('Renommer la zone',self.rename_zone),('Dupliquer la zone',self.duplicate_zone),('Supprimer la zone',self.delete_zone),('Enregistrer un préréglage',self.save_mapping),('Charger un préréglage',self.load_mapping)]:mapping.add_command(label=label,command=fn)
        mapping.add_command(label='Versions de calibration…',command=self.calibration_versions)
        mapping.add_command(label='Loupe du mapping',command=self.toggle_loupe)
        self.timeline_tools=TimelineTools(self)
        sound=tk.Menu(menu,tearoff=False); menu.add_cascade(label='Audio',menu=sound)
        sound.add_command(label='Muet et Solo par piste',command=self.open_mixer)
        sound.add_command(label='Analyser le niveau sonore…',command=self.analyse_audio)
        render=tk.Menu(menu,tearoff=False); menu.add_cascade(label='Lecture et export',menu=render)
        render.add_command(label='Lecture directe depuis le curseur',command=self.direct_play)
        render.add_command(label='Vérifier le projet / retrouver les médias',command=self.preflight)
        render.add_command(label='Projeter le montage en HDMI',command=self.direct_projector)
        render.add_command(label='Retrouver les médias dans un dossier…',command=self.find_media_folder)
        render.add_command(label='Cache des rendus…',command=self.cache_manager)
        render.add_command(label='Copies de travail légères…',command=self.proxy_manager)
        render.add_command(label='Source / Répartition',command=self.open_source_view)
        self.attach_document()
        self.install_mapping_interaction()
        self.name.trace_add('write',lambda *args:self.update_project_title())
        self.canvas.bind('<Button-1>',self.zone_click,add='+')
        self.canvas.bind('<Motion>',self.zone_motion,add='+')
        self.canvas.bind('<BackSpace>',self.undo_drawing_point,add='+')
        self.canvas.bind('<Button-3>',self.cancel_mapping_pointer)
        self.root.bind('<Escape>',self.cancel_zone,add='+')
        self.root.bind('<Control-s>',lambda e:self.save())
        self.root.bind('<Control-o>',lambda e:self.load())
        self.root.bind('<Control-n>',lambda e:self.new_document())
        self.root.bind('<F8>',lambda e:self.toggle_projection_mode('black')); self.root.bind('<F9>',lambda e:self.toggle_projection_mode('frozen'))
        self.autosave_timer=self.root.after(self.recovery_settings['interval']*1000,self.autosave)
        self.root.bind('<Destroy>',self.stop_studio,add='+')
        if self.recoveries:self.status.set('Une session sauvegardée est disponible : Projets → Récupérer une session.')
        if self.interrupted:
            self.recovery_notice=ttk.Frame(self.root,padding=6); self.recovery_notice.pack(fill='x',before=self.tabs)
            ttk.Label(self.recovery_notice,text='Une session interrompue a été retrouvée. Vos projets peuvent être récupérés.').pack(side='left')
            ttk.Button(self.recovery_notice,text='Récupérer',command=lambda:self.recover_session(self.interrupted[0])).pack(side='left',padx=8)
            ttk.Button(self.recovery_notice,text='Voir les sauvegardes',command=self.recovery_manager).pack(side='left')
            ttk.Button(self.recovery_notice,text='Plus tard',command=self.recovery_notice.destroy).pack(side='right')

    def snapshot_document(self):
        if self.active_document:
            self.data['name']=self.name.get()
            self.active_document.update(data=self.data,history=self.history,redo=self.redo,project=self.project,playhead=self.playhead,zone=self.zone,selected=self.timeline.selected,selection=set(self.timeline_tools.selection),scale=self.timeline.scale.get(),xview=self.timeline.canvas.xview()[0],yview=self.timeline.canvas.yview()[0])
            self.tabs.tab(self.active_document['tab'],text=self.name.get() or 'Sans titre')

    def attach_document(self):
        self.switching=True
        tab=ttk.Frame(self.tabs); self.tabs.add(tab,text=self.name.get() or 'Sans titre')
        state=dict(saved_data=copy.deepcopy(self.data),tab=tab,data=self.data,history=self.history,redo=self.redo,project=self.project,playhead=self.playhead,zone=self.zone,selected=self.timeline.selected,selection=set(),scale=self.timeline.scale.get(),xview=0.,yview=0.)
        self.documents.append(state); self.active_document=state; self.tabs.select(tab); self.switching=False

    def change_document(self,event=None):
        if self.switching or not self.tabs.select():return
        target=next((d for d in self.documents if str(d['tab'])==self.tabs.select()),None)
        if target is None or target is self.active_document:return
        self.timeline.finish_name_edit()
        self.snapshot_document(); self.cancel(); self.close_previews(); self.stop_direct(); self.cancel_zone(); self.discard_video_proxy()
        self.active_document=target
        for key in ('data','history','redo','project','playhead','zone'):setattr(self,key,target[key])
        self.name.set(self.data['name']); self.timeline.selected=target['selected']; self.timeline_tools.selection=set(target['selection'])
        self.timeline.scale.set(target['scale']); self.still_frame=None; self.still_images.clear(); self._still_wanted_key=None
        self.refresh(); self.timeline.canvas.xview_moveto(target['xview']); self.timeline.canvas.yview_moveto(target['yview'])

    def update_project_title(self):
        if self.active_document and self.active_document['data'] is self.data:
            self.tabs.tab(self.active_document['tab'],text=self.name.get() or 'Sans titre')

    def next_project_name(self):
        used={d['data'].get('name') for d in self.documents}
        while True:
            self.installation_counter+=1; name=f'Installation {self.installation_counter}'
            if name not in used:return name

    def new_document(self):
        from app import DEFAULT
        data=copy.deepcopy(DEFAULT); data['name']=self.next_project_name()
        self.open_document(data,None)

    def open_document(self,data,path):
        self.timeline.finish_name_edit()
        self.cancel_zone()
        if hasattr(self,'documents'):
            self.snapshot_document(); self.cancel(); self.close_previews(); self.stop_direct(); self.discard_video_proxy()
        consolidate_levels(data)
        self.data=data; self.project=path; self.history=[]; self.redo=[]; self.playhead=0.; self.zone=0; self.corner=0; self.name.set(data.get('name','Installation'))
        self.timeline.selected=None; self.timeline.scale.set('Auto')
        if hasattr(self,'timeline_tools'):self.timeline_tools.selection.clear()
        self.still_frame=None; self.still_images.clear(); self._still_wanted_key=None
        if hasattr(self,'documents'):self.attach_document()
        self.refresh()
        self.active_document['saved_data']=copy.deepcopy(self.data)

    def close_document(self,tab=None):
        previous=self.active_document
        old=next((d for d in self.documents if str(d['tab'])==str(tab)),None) if tab is not None else previous
        if old is None:return
        self.timeline.finish_name_edit()
        if old is not self.active_document:self.tabs.select(old['tab']); self.change_document()
        self.snapshot_document()
        choice=messagebox.askyesnocancel('Fermer le projet',f'Enregistrer « {self.name.get()} » avant de fermer ?\nOui : enregistrer • Non : fermer sans enregistrer • Annuler : garder le projet ouvert.',parent=self.root) if old.get('saved_data')!=old['data'] else False
        if choice is None or (choice and not self.save()):
            if previous is not self.active_document:self.tabs.select(previous['tab']); self.change_document()
            return False
        self.snapshot_document(); self.write_recovery()
        atomic_json(self.recovery_path.with_name('session-closed-'+uuid.uuid4().hex+'.json'),json.loads(self.recovery_path.read_text(encoding='utf-8')))
        if len(self.documents)==1:self.new_document()
        elif old is self.active_document:
            replacement=previous if previous is not old else next(d for d in self.documents if d is not old)
            self.tabs.select(replacement['tab']); self.change_document()
        self.documents.remove(old); self.tabs.forget(old['tab']); old['tab'].destroy()
        self.write_recovery()
        return True

    def confirm_unsaved(self,documents):
        from unsaved_dialog import UnsavedDialog
        return UnsavedDialog(self.root,[d['data'].get('name','Sans titre') for d in documents]).result

    def save_open_documents(self):
        self.timeline.finish_name_edit(); self.end_mapping_gesture(); self.snapshot_document()
        pending=[d for d in self.documents if d.get('saved_data')!=d['data']]
        if not pending:return True
        choice=self.confirm_unsaved(pending)
        if choice is None:return False
        if not choice:return True
        previous=self.active_document
        try:
            for document in pending:
                if document is not self.active_document:
                    self.tabs.select(document['tab']); self.change_document()
                if not self.save(self.project):return False
            return True
        finally:
            if previous is not self.active_document:
                self.tabs.select(previous['tab']); self.change_document()

    def write_recovery(self,state='running',force=False):
        from session_recovery import store
        self.snapshot_document()
        payload=dict(version=1,state=state,dirty=any(d.get('saved_data')!=d['data'] for d in self.documents),active=self.documents.index(self.active_document),projects=[dict(data=d['data'],project=str(d['project']) if d['project'] else None,playhead=d['playhead']) for d in self.documents])
        serialized=json.dumps(payload,sort_keys=True)
        if force or serialized!=self.autosaved:
            self.last_recovery=store(self.recovery_path,payload,atomic_json); self.autosaved=serialized

    def autosave(self):
        if self.closing:return
        try:
            if self.recovery_settings['enabled']:self.write_recovery()
        except OSError as e:self.status.set('Sauvegarde de récupération impossible : '+str(e))
        self.autosave_timer=self.root.after(self.recovery_settings['interval']*1000,self.autosave)

    def recovery_manager(self):
        from datetime import datetime
        win=tk.Toplevel(self.root); win.title('Sauvegardes automatiques'); win.geometry('760x460'); win.transient(self.root)
        bar=ttk.Frame(win,padding=10); bar.pack(fill='x')
        enabled=tk.BooleanVar(value=self.recovery_settings['enabled']); interval=tk.StringVar(value=str(self.recovery_settings['interval']))
        ttk.Checkbutton(bar,text='Activer les sauvegardes automatiques',variable=enabled).pack(side='left')
        ttk.Label(bar,text='Toutes les').pack(side='left',padx=8)
        ttk.Combobox(bar,textvariable=interval,values=['15','30','60','120'],state='readonly',width=5).pack(side='left')
        ttk.Label(bar,text='secondes').pack(side='left',padx=4)
        status=ttk.Label(win,padding=10,wraplength=720); status.pack(fill='x')
        def apply():
            settings=dict(enabled=enabled.get(),interval=int(interval.get()))
            try:atomic_json(self.recovery_path.parent/'settings.json',settings)
            except OSError as e:messagebox.showerror('Sauvegardes automatiques',str(e),parent=win); return
            self.recovery_settings=settings
            self.root.after_cancel(self.autosave_timer); self.autosave_timer=self.root.after(settings['interval']*1000,self.autosave)
            status.configure(text='Réglages enregistrés. '+('Protection automatique active.' if settings['enabled'] else 'Protection automatique désactivée.'))
        ttk.Button(bar,text='Appliquer',command=apply).pack(side='right')
        status.configure(text='Dix versions conservées par session, en plus de la copie la plus récente. Les médias restent dans leurs dossiers.\nDernière copie de cette session : '+(datetime.fromisoformat(self.last_recovery).astimezone().strftime('%d/%m/%Y %H:%M:%S') if self.last_recovery else 'pas encore créée'))
        area=ttk.Frame(win,padding=(10,0)); area.pack(fill='both',expand=True)
        tree=ttk.Treeview(area,columns=('date','projects','state'),show='headings',selectmode='browse')
        for key,title,width in [('date','Date',150),('projects','Projets',360),('state','État',140)]:tree.heading(key,text=title); tree.column(key,width=width)
        scroll=ttk.Scrollbar(area,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=scroll.set); tree.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')
        paths={}
        def refresh():
            tree.delete(*tree.get_children()); paths.clear()
            folder=self.recovery_path.parent
            candidates=list(folder.glob('session-*.json'))+list((folder/'history').glob('*/*.json'))
            for path in sorted(candidates,key=lambda p:p.stat().st_mtime,reverse=True):
                try:
                    payload=json.loads(path.read_text(encoding='utf-8')); projects=payload['projects']
                    date=datetime.fromisoformat(payload['updated']).astimezone().strftime('%d/%m/%Y %H:%M:%S') if payload.get('updated') else datetime.fromtimestamp(path.stat().st_mtime).strftime('%d/%m/%Y %H:%M:%S')
                    names=', '.join(d['data'].get('name','Sans titre') for d in projects)
                    label='Historique' if path.parent.name.startswith('session-') else {'closed':'Fermée normalement','recovered':'Récupérée','running':'Copie automatique'}.get(payload.get('state'),'Ancienne session')
                    item=tree.insert('','end',values=(date,names,label)); paths[item]=path
                except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
        def recover():
            selection=tree.selection()
            if selection:self.recover_session(paths[selection[0]])
        def save_now():
            try:self.write_recovery(force=True); refresh(); status.configure(text='Copie de récupération créée. Les fichiers de projet restent inchangés.')
            except OSError as e:status.configure(text='Copie impossible : '+str(e))
        buttons=ttk.Frame(win,padding=10); buttons.pack(fill='x')
        ttk.Button(buttons,text='Récupérer la sélection',command=recover).pack(side='left')
        ttk.Button(buttons,text='Créer une copie maintenant',command=save_now).pack(side='left',padx=8)
        ttk.Button(buttons,text='Actualiser',command=refresh).pack(side='left')
        ttk.Button(buttons,text='Fermer',command=win.destroy).pack(side='right')
        refresh()

    def recover_session(self,path=None):
        from app import valid
        choices=sorted(self.recovery_path.parent.glob('session-*.json'),key=lambda p:p.stat().st_mtime,reverse=True) if self.recovery_path.parent.exists() else []
        path=path or filedialog.askopenfilename(title='Récupérer une session',initialdir=str(self.recovery_path.parent),initialfile=choices[0].name if choices else '',filetypes=[('Session','*.json')])
        if not path:return
        try:
            payload=json.loads(Path(path).read_text(encoding='utf-8')); projects=payload['projects']
            if not isinstance(projects,list) or not projects:raise ValueError('Session vide.')
            for d in projects:
                data=d['data']; montage.validate_items(data['clips']+data['audio_clips']); validate_extras(data)
                if not valid_resolution(data.get('resolution')) or type(data.get('audio_track_count'))!=int or not 0<=data['audio_track_count']<=64 or any(c['lane']>=data['audio_track_count'] for c in data['audio_clips']):raise ValueError('Paramètres de projet invalides.')
                if not 1<=len(data['zones'])<=64 or not all(valid(q) for q in data['zones']) or any(c['lane']>=len(data['zones']) for c in data['clips']):raise ValueError('Mapping invalide.')
            restored=[]
            for d in projects:
                self.open_document(d['data'],Path(d['project']) if d['project'] else None); self.set_playhead(d.get('playhead',0.))
                self.active_document['saved_data']=None
                restored.append(self.active_document)
            active=payload.get('active',len(restored)-1)
            if type(active)==int and 0<=active<len(restored):self.tabs.select(restored[active]['tab']); self.change_document()
            self.status.set(f'{len(projects)} projet(s) récupéré(s) dans de nouveaux onglets.')
            if payload.get('state')=='running':
                payload['state']='recovered'; atomic_json(path,payload)
            if hasattr(self,'recovery_notice') and self.recovery_notice.winfo_exists():self.recovery_notice.destroy()
        except (ValueError,OSError,KeyError,TypeError) as e:messagebox.showerror('Récupération',str(e),parent=self.root)

    def stop_studio(self,event):
        if event.widget!=self.root:return
        self.stop_direct(); self.timeline_tools.close()
        for name in ('mapping_loupe','source_comparison'):
            tool=getattr(self,name,None)
            if tool and not tool.closed:tool.close()
        try:self.root.after_cancel(self.autosave_timer)
        except tk.TclError:pass

    def begin_zone(self):
        if len(self.data['zones'])>=64:self.status.set('Limite : 64 zones.'); return
        self.edit_mode.set('draw'); self.drawing_zone=[]; self.canvas.focus_set(); self.status.set('Cliquez les quatre coins de la zone. Retour arrière retire le dernier point ; clic droit ou Échap annule le dessin.')

    def cancel_mapping_pointer(self,event=None):
        if self.edit_mode.get()=='draw' or self.drawing_zone is not None:
            self.cancel_zone(); self.status.set('Dessin annulé.'); return 'break'
        if getattr(self,'mapping_latched',False):self.end_mapping_gesture(); return 'break'

    def zone_click(self,event):
        if self.drawing_zone is None:return
        from app import valid
        ox,oy,w,h=self.viewport(self.canvas); p=[(event.x-ox)/w,(event.y-oy)/h]
        if not all(0<=v<=1 for v in p):return 'break'
        self.drawing_zone.append(p)
        if len(self.drawing_zone)==4:
            from zone_drawing import ordered_quad
            q=ordered_quad(self.drawing_zone)
            if q is not None and valid(q):
                self.add_zone(q); self.cancel_zone(); self.status.set('Zone créée. Déplacez ses coins ou ses arêtes pour l’ajuster.')
            else:
                self.drawing_zone.pop(); self.status.set('Ce quatrième coin ne forme pas une zone convexe. Les trois premiers coins sont conservés : choisissez un autre emplacement, ou Échap pour annuler.')
        self.zone_motion(event); return 'break'

    def zone_motion(self,event):
        self.canvas.delete('new_zone')
        if not self.drawing_zone:return
        ox,oy,w,h=self.viewport(self.canvas); points=[v for x,y in self.drawing_zone for v in (ox+x*w,oy+y*h)]+[event.x,event.y]
        self.canvas.create_line(*points,fill='#8bff8b',width=3,tags='new_zone')
        for i,(x,y) in enumerate(self.drawing_zone):
            x=ox+x*w; y=oy+y*h; self.canvas.create_oval(x-4,y-4,x+4,y+4,fill='#8bff8b',outline='white',tags='new_zone'); self.canvas.create_text(x+10,y-10,text=str(i+1),fill='white',tags='new_zone')

    def undo_drawing_point(self,event=None):
        if self.drawing_zone is None:return
        if self.edit_locked('mapping'):return 'break'
        if self.drawing_zone:self.drawing_zone.pop()
        self.canvas.delete('new_zone')
        if self.drawing_zone:
            ox,oy,w,h=self.viewport(self.canvas); x,y=self.drawing_zone[-1]
            self.zone_motion(SimpleNamespace(x=ox+x*w,y=oy+y*h))
        self.status.set(f'{len(self.drawing_zone)} coin(s) saisi(s). Cliquez le suivant ; Échap annule.'); return 'break'

    def cancel_zone(self,event=None):
        self.end_mapping_gesture()
        self.drawing_zone=None
        if self.edit_mode.get()=='draw':self.edit_mode.set('mapping')
        self.canvas.delete('new_zone')

    def add_zone(self,q):
        names=self.zone_names()+[f'Zone {len(self.data["zones"])+1}']; self.checkpoint()
        self.data['zones'].append(copy.deepcopy(q)); self.data['zone_names']=names; self.zone=len(names)-1; self.refresh()

    def choose_zone_count(self):
        number=simpledialog.askinteger('Zones','Nombre de zones (1 à 64)',initialvalue=len(self.data['zones']),minvalue=1,maxvalue=64,parent=self.root)
        if number is None:return
        if number<len(self.data['zones']):
            if any(max(panorama.lanes(c))>=number for c in self.data['clips']):messagebox.showerror('Zones utilisées','Supprimez ou déplacez les clips des zones à retirer.',parent=self.root); return
            self.checkpoint(); self.data['zone_names']=self.zone_names()[:number]; self.data['zones']=self.data['zones'][:number]; self.trim_mixer(number); self.refresh()
        while len(self.data['zones'])<number:
            i=len(self.data['zones']); col=i%4; row=(i//4)%4
            x=.02+col*.245; y=.02+row*.245; self.add_zone([[x,y],[x+.22,y],[x+.22,y+.22],[x,y+.22]])

    def rename_zone(self):
        self.timeline.canvas.yview_moveto(max(0.,(28+self.zone*50-30)/(30+(len(self.data['zones'])+self.data['audio_track_count'])*50)))
        self.timeline.edit_zone_name(self.zone)

    def duplicate_zone(self):
        if len(self.data['zones'])<64:self.add_zone(self.data['zones'][self.zone])

    def delete_zone(self):
        self.delete_timeline_track(self.zone)

    def delete_timeline_track(self,row):
        zones=len(self.data['zones']); audio=row>=zones; lane=row-zones if audio else row
        if self.edit_locked('timeline' if audio else 'any'):return
        names=self.audio_names() if audio else self.zone_names()
        if not 0<=lane<len(names):return
        if not audio and zones==1:self.status.set('Conservez au moins une zone de mapping.'); return
        key='audio_clips' if audio else 'clips'; name=names[lane]
        count=sum((c['lane']==lane if audio else lane in panorama.lanes(c)) for c in self.data[key])
        warning='\nLes clips panoramiques utilisant cette zone seront retirés de toutes leurs zones.' if not audio and any('panorama' in c and lane in panorama.lanes(c) for c in self.data[key]) else ''
        if count and not messagebox.askyesno('Supprimer la piste' if audio else 'Supprimer la zone',f'Supprimer « {name} » et ses {count} élément(s) de la timeline ?{warning}\nLes fichiers sources seront conservés.',parent=self.root):return
        self.checkpoint(); del names[lane]
        self.data['audio_track_names' if audio else 'zone_names']=names
        if audio:self.data['audio_track_count']=len(names); self.timeline.audio_lane.set(str(max(1,len(names))))
        else:del self.data['zones'][lane]
        self.data[key]=[panorama.reindex(c,lane) for c in self.data[key] if (c['lane']!=lane if audio else lane not in panorama.lanes(c))]
        prefix='a' if audio else 'v'
        self.data['mixer']={(prefix+str(int(k[1:])-1) if k.startswith(prefix) and int(k[1:])>lane else k):v for k,v in self.data.get('mixer',{}).items() if k!=prefix+str(lane)}
        self.zone=min(self.zone,len(self.data['zones'])-1); self.refresh(); self.refresh_preview_audio()
        self.status.set('Piste supprimée : '+name)

    def save_mapping(self):
        path=filedialog.asksaveasfilename(title='Préréglage de mapping',defaultextension='.mapping.json',filetypes=[('Mapping','*.json')])
        if path:
            try:atomic_json(path,dict(zones=self.data['zones'],zone_names=self.zone_names()))
            except OSError as e:messagebox.showerror('Mapping',str(e),parent=self.root)

    def trim_mixer(self,count):
        self.data['mixer']={k:v for k,v in self.data.get('mixer',{}).items() if k.startswith('a') or int(k[1:])<count}

    def load_mapping(self):
        from app import valid
        path=filedialog.askopenfilename(title='Préréglage de mapping',filetypes=[('Mapping','*.json')])
        if not path:return
        try:
            d=json.loads(Path(path).read_text(encoding='utf-8'))
            if not 1<=len(d['zones'])<=64 or not all(valid(q) for q in d['zones']) or any(max(panorama.lanes(c))>=len(d['zones']) for c in self.data['clips']):raise ValueError('Préréglage incompatible avec les pistes utilisées.')
            validate_extras(d); self.checkpoint(); self.data['zones']=d['zones']; self.data['zone_names']=d.get('zone_names',[f'Zone {i+1}' for i in range(len(d['zones']))]); self.trim_mixer(len(d['zones'])); self.refresh()
        except (OSError,ValueError,KeyError,TypeError) as e:messagebox.showerror('Mapping',str(e),parent=self.root)

    def copy_framing(self):
        c=next((c for c in self.data['clips'] if c['id']==self.timeline.selected),None)
        if c:self.framing={k:c.get(k,1. if k=='zoom' else 0.) for k in ('fit','zoom','pan_x','pan_y')}; self.status.set('Cadrage copié.')

    def paste_framing(self):
        if not hasattr(self,'framing'):return
        ids=self.timeline_tools.selected_ids(); targets=[c for c in self.data['clips'] if c['id'] in ids]
        if targets:
            self.checkpoint()
            for c in targets:c.update(self.framing)
            self.refresh()

    def open_mixer(self):
        win=tk.Toplevel(self.root); win.title('Muet et Solo par piste'); win.transient(self.root); win.grab_set(); win.geometry('480x500'); win.minsize(420,240)
        footer=ttk.Frame(win,padding=10); footer.pack(side='bottom',fill='x')
        area=ttk.Frame(win); area.pack(fill='both',expand=True)
        canvas=tk.Canvas(area,highlightthickness=0); canvas.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(area,orient='vertical',command=canvas.yview); scroll.pack(side='right',fill='y'); canvas.configure(yscrollcommand=scroll.set)
        body=ttk.Frame(canvas,padding=12); body_window=canvas.create_window(0,0,window=body,anchor='nw')
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(body_window,width=e.width)); body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        ttk.Label(body,text='Muet').grid(row=0,column=1); ttk.Label(body,text='Solo').grid(row=0,column=2)
        ttk.Label(body,text='Pour le volume : double-cliquez sur un clip.').grid(row=1,column=0,columnspan=3,pady=8)
        rows=[]
        keys=[('v'+str(i),name) for i,name in enumerate(self.zone_names())]+[('a'+str(i),name) for i,name in enumerate(self.audio_names())]
        for row,(key,name) in enumerate(keys,2):
            settings=self.data.get('mixer',{}).get(key,{})
            mute=tk.BooleanVar(value=settings.get('mute',False)); solo=tk.BooleanVar(value=settings.get('solo',False))
            ttk.Label(body,text=name).grid(row=row,column=0,sticky='w'); ttk.Checkbutton(body,variable=mute).grid(row=row,column=1); ttk.Checkbutton(body,variable=solo).grid(row=row,column=2); rows.append((key,mute,solo))
        def apply():
            try:
                mixer={k:dict(self.data.get('mixer',{}).get(k,{}),mute=m.get(),solo=s.get()) for k,m,s in rows}
                validate_extras(dict(zones=self.data['zones'],mixer=mixer)); self.checkpoint(); self.data['mixer']=mixer; self.refresh(); self.refresh_preview_audio(); win.destroy()
            except ValueError as e:messagebox.showerror('Pistes audio',str(e),parent=win)
        ttk.Button(footer,text='Appliquer',command=apply).pack()

    def gather_project(self):
        from project_transfer import gather_project
        self.timeline.finish_name_edit()
        parent=filedialog.askdirectory(title='Choisir le dossier qui recevra le projet regroupé')
        if not parent:return
        name=simpledialog.askstring('Rassembler le projet','Nom du nouveau dossier :',initialvalue='Projet-regroupé',parent=self.root)
        if not name:return
        if name in ('.','..') or any(c in name for c in '<>:"/\\|?*') or name.endswith((' ','.')):
            messagebox.showerror('Regroupement','Choisissez un nom de dossier simple.',parent=self.root); return
        data=copy.deepcopy(self.data); data['name']=self.name.get()
        events=queue.Queue(); win=tk.Toplevel(self.root); win.title('Regroupement du projet')
        label=ttk.Label(win,text='Préparation…',padding=20); label.pack()
        win.protocol('WM_DELETE_WINDOW',lambda:None)
        def work():
            try:events.put(('done',gather_project(data,Path(parent)/name,lambda value:events.put(('progress',value)))))
            except Exception as e:events.put(('error',str(e)))
        def poll():
            if not win.winfo_exists():return
            try:
                while True:
                    kind,value=events.get_nowait()
                    if kind=='progress':label.configure(text=value)
                    else:
                        win.destroy()
                        if kind=='done':messagebox.showinfo('Projet regroupé','Projet prêt à transférer :\n'+str(value)+'\n\nCopiez tout le dossier. L’application portable reste à copier séparément.',parent=self.root)
                        else:messagebox.showerror('Regroupement',value,parent=self.root)
                        return
            except queue.Empty:pass
            win.after(100,poll)
        threading.Thread(target=work,daemon=True).start(); poll()

    def preflight(self):
        win=tk.Toplevel(self.root); win.title('Vérification avant export'); win.geometry('700x430')
        text=tk.Text(win,wrap='word',height=16); text.pack(fill='both',expand=True,padx=12,pady=12)
        def refresh():
            missing=sorted({c['path'] for c in self.timeline.items if not Path(c['path']).is_file()}); total=montage.duration(self.timeline.items)
            w,h=self.data['resolution']; bitrate=4_000_000*(w*h)/(1280*720); size=total*(bitrate+160_000)/8/1024**2
            content=f'{self.name.get()}\n{len(self.data["zones"])} zones • {total:.2f} s\nMP4 • H.264 • {w} × {h} • 30 images/s\nAudio AAC stéréo si présent\nPoids indicatif : environ {size:.1f} Mo à {bitrate/1_000_000:g} Mbit/s (le poids réel dépend des images).\n\n'
            try:montage.validate_items(self.timeline.items); validate_extras(self.data); content+='Structure du montage : valide.\n'
            except ValueError as e:content+='Erreur : '+str(e)+'\n'
            from project_transfer import check_resources
            try:
                temporary,movie=check_resources(self.data)
                content+=f'Espace temporaire disponible (budget prudent : {temporary/1024**2:.0f} Mo).\nLes médias et la destination seront contrôlés automatiquement au lancement de l’export.\n'
            except (OSError,ValueError) as e:content+='Erreur disque : '+str(e)+'\n'
            content+=('\nFichiers introuvables :\n'+'\n'.join(missing)) if missing else '\nTous les fichiers référencés sont disponibles.'
            text.configure(state='normal'); text.delete('1.0','end'); text.insert('end',content); text.configure(state='disabled')
            return missing
        def relink():
            if self.edit_locked('timeline'):return
            missing=refresh()
            updates={}
            for old in missing:
                path=filedialog.askopenfilename(title='Retrouver '+Path(old).name,parent=win)
                if not path:continue
                try:
                    affected=[c for c in self.timeline.items if c['path']==old]
                    for c in affected:
                        if montage.is_image(c):montage.probe_image(path,self.executable); length=c['duration']
                        elif c.get('kind')=='audio':length=montage.probe_audio(path,self.executable)
                        else:
                            length,has_audio=montage.probe(path,self.executable)
                            if c.get('audio') and not has_audio:raise ValueError('La vidéo choisie ne contient pas le son attendu.')
                        if not montage.is_image(c) and length+.001<c['out']:raise ValueError('Le fichier choisi est trop court pour les coupes existantes.')
                    updates[old]=(str(Path(path).resolve()),length)
                except (ValueError,OSError,subprocess.SubprocessError) as e:messagebox.showerror('Média incompatible',str(e),parent=win)
            if updates:
                self.checkpoint()
                for c in self.timeline.items:
                    if c['path'] in updates:c['path'],c['duration']=updates[c['path']]
                self.refresh()
            refresh()
        refresh(); ttk.Button(win,text='Retrouver les fichiers manquants…',command=relink).pack(pady=8)
        ttk.Button(win,text='Rechercher dans un dossier…',command=lambda:self.find_media_folder(lambda:refresh() if win.winfo_exists() else None)).pack(pady=4)
        ttk.Button(win,text='Analyser le niveau sonore…',command=self.analyse_audio).pack(pady=4)

    def stop_direct(self):
        if getattr(self,'direct_player',None):self.direct_player.close(); self.direct_player=None

    def direct_play(self):
        from direct_preview import DirectPreview
        if self.direct_player and not self.direct_player.closed:self.stop_direct(); return
        clips,audio=effective_items(self.data); total=montage.duration(clips+audio)
        if total<=0:self.status.set('Ajoutez des médias avant de lancer la lecture.'); return
        from app import mask,graph,project
        self.direct_signature=self.render_signature(preview=True)
        clips=self.media_work.resolve(clips)
        self.direct_player=DirectPreview(self.root,self.executable,self.data['zones'],clips,audio,min(self.playhead,max(0.,total-1/30)),mask,graph,project)
        player=self.direct_player; player.projection_request=lambda:self.project_player(player)

    def edit_panorama(self):
        if self.edit_locked('timeline'):return
        from panorama_dialog import PanoramaDialog
        selected=[c for c in self.timeline.clips if c['id'] in self.timeline_tools.selected_ids()]
        if len(selected)!=1:
            messagebox.showinfo('Vidéo panoramique','Sélectionnez une seule vidéo dans la timeline, puis choisissez Panoramique.',parent=self.root); return
        if len(self.data['zones'])<2:
            messagebox.showinfo('Vidéo panoramique','Ajoutez au moins deux zones de mapping.',parent=self.root); return
        clip=selected[0]
        def validate(value):
            panorama.validate(value,len(self.data['zones']))
            montage.validate([value if c['id']==clip['id'] else c for c in self.timeline.clips])
        dialog=PanoramaDialog(self.root,clip,self.data['zones'],self.zone_names(),validate)
        if dialog.result is not None and dialog.result!=clip:
            self.timeline.commit(dialog.result); self.refresh()
            self.status.set('Panoramique appliqué. Position vidéo : déplacez ou zoomez l’image commune dans une des zones.')


from editor_controls import guard_methods
guard_methods(StudioFeatures,"begin_zone zone_click add_zone choose_zone_count rename_zone duplicate_zone load_mapping", "mapping")

guard_methods(StudioFeatures,"paste_framing open_mixer", "timeline")
