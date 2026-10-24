"""Projector output and reviewable project maintenance tools."""
import copy
import json
import math
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
import montage
from work_features import WorkFeatures


class AdvancedFeatures(WorkFeatures):
    def run_background(self,title,work,done):
        events=queue.Queue(); cancel=threading.Event(); win=tk.Toplevel(self.root); win.title(title); win.transient(self.root)
        label=ttk.Label(win,text='Préparation…',padding=18,wraplength=500); label.pack()
        def stop():cancel.set(); win.destroy()
        ttk.Button(win,text='Annuler',command=stop).pack(pady=8); win.protocol('WM_DELETE_WINDOW',stop)
        win.bind('<Destroy>',lambda e:cancel.set() if e.widget==win else None)
        last=[0.]
        def progress(value):
            now=time.monotonic()
            if now-last[0]>.1:last[0]=now; events.put(('progress',str(value)))
        def worker():
            try:events.put(('done',work(cancel,progress)))
            except Exception as e:events.put(('error',str(e)))
        def poll():
            if not win.winfo_exists():return
            try:
                while True:
                    kind,value=events.get_nowait()
                    if kind=='progress':label.configure(text=value)
                    else:
                        cancelled=cancel.is_set(); win.destroy()
                        if not cancelled:
                            if kind=='done':done(value)
                            else:messagebox.showerror(title,value,parent=self.root)
                        return
            except queue.Empty:pass
            win.after(80,poll)
        threading.Thread(target=worker,daemon=True).start(); poll(); return cancel

    @staticmethod
    def check_task(cancel):
        if cancel.is_set():raise RuntimeError('Opération annulée.')

    def current_snapshot(self,data,state):
        if self.data is not data or json.dumps(data,sort_keys=True)!=state:
            messagebox.showinfo('Projet modifié','Le projet a changé pendant cette opération. Relancez-la pour utiliser son état actuel.',parent=self.root); return False
        return True

    def project_player(self,player):
        if player.closed:return
        if player.projection and not player.projection.closed:player.projection.close(); player.projection=None; return
        from projection_output import ProjectionOutput
        self.refresh_screens()
        if len(self.monitors)<2:
            messagebox.showinfo('Projection HDMI','Branchez le projecteur, puis choisissez Windows + P → Étendre et sélectionnez son écran.',parent=self.root); return
        if self.output and self.output.winfo_exists():self.output.destroy()
        # Only one animation owns the physical output at a time.
        for other in [getattr(self,'direct_player',None)]+[p for p,s in self.previews]:
            if other is not None and other is not player and getattr(other,'projection',None):other.projection.close()
        rectangle=self.monitors[self.screen.current()]
        try:
            player.projection=ProjectionOutput(player.win,rectangle,on_close=lambda:player.projection_controls.sync() if hasattr(player,'projection_controls') else None)
            player.redraw(); self.status.set('Projection animée HDMI active. Échap sur le projecteur ou Projeter HDMI ferme la sortie ; les commandes restent sur le portable.')
            if hasattr(player,'projection_controls'):player.projection_controls.sync()
        except (OSError,tk.TclError) as e:messagebox.showerror('Projection HDMI',str(e),parent=self.root)

    def direct_projector(self):
        if not self.direct_player or self.direct_player.closed:self.direct_play()
        if self.direct_player and not self.direct_player.closed:self.project_player(self.direct_player)

    def cache_manager(self):
        from render_cache import RenderCache
        cache=RenderCache(); win=tk.Toplevel(self.root); win.title('Cache des rendus')
        label=ttk.Label(win,padding=18,wraplength=500); label.pack()
        def refresh():
            try:
                count,size=cache.usage(); label.configure(text=f'{count} séquence(s) • {size/1024**2:.1f} Mo\nLimite : 2 Go ; les séquences les plus anciennes sont retirées automatiquement.\nVider le cache conserve vos projets et vos médias.')
            except OSError as e:label.configure(text=str(e))
        def clear():
            if self.active_render is not None:messagebox.showinfo('Cache','Attendez la fin du rendu ou arrêtez-le avant de vider le cache.',parent=win); return
            self.run_background('Vider le cache',lambda cancel,progress:cache.clear(),lambda value:refresh() if win.winfo_exists() else None)
        ttk.Button(win,text='Vider le cache',command=clear).pack(pady=8); refresh()

    def find_media_folder(self,on_done=lambda:None):
        if self.edit_locked('timeline'):return
        self.timeline.finish_name_edit()
        data=self.data; state=json.dumps(data,sort_keys=True); snapshot=copy.deepcopy(data)
        missing=sorted({c['path'] for c in self.timeline.items if not Path(c['path']).is_file()})
        if not missing:messagebox.showinfo('Médias','Tous les médias sont disponibles.',parent=self.root); return
        folder=filedialog.askdirectory(title='Rechercher les médias dans ce dossier et ses sous-dossiers')
        if not folder:return
        from media_relink import find_candidates,replacements
        executable=self.executable; check_task=AdvancedFeatures.check_task
        def show(result):
            if not self.current_snapshot(data,state):return
            candidates,unreadable=result; win=tk.Toplevel(self.root); win.title('Correspondances des médias'); win.geometry('850x420')
            ttk.Label(win,text='Les correspondances uniques sont proposées. Choisissez explicitement les fichiers ambigus, puis appliquez.',wraplength=810,padding=10).pack(fill='x')
            tree=ttk.Treeview(win,columns=('old','new'),show='headings',height=9); tree.heading('old',text='Fichier absent'); tree.heading('new',text='Fichier proposé'); tree.pack(fill='both',expand=True,padx=10)
            choices={old:values[0] for old,values in candidates.items() if len(values)==1}
            for i,old in enumerate(missing):tree.insert('','end',iid=str(i),values=(old,choices.get(old,'Plusieurs correspondances : choisir' if candidates[old] else 'Introuvable')))
            row=ttk.Frame(win,padding=10); row.pack(fill='x'); selected=tk.StringVar()
            combo=ttk.Combobox(row,textvariable=selected,state='readonly',width=65); combo.pack(side='left',fill='x',expand=True)
            def pick(event=None):
                if not tree.selection():return
                old=missing[int(tree.selection()[0])]; combo.configure(values=candidates[old]); selected.set(choices.get(old,''))
            def choose(event=None):
                if tree.selection() and selected.get():
                    i=tree.selection()[0]; old=missing[int(i)]; choices[old]=selected.get(); tree.item(i,values=(old,selected.get()))
            def browse():
                if not tree.selection():return
                i=tree.selection()[0]; old=missing[int(i)]; path=filedialog.askopenfilename(title='Retrouver '+Path(old).name,parent=win)
                if path:choices[old]=path; candidates[old]=[path]+candidates[old]; tree.item(i,values=(old,path)); pick()
            tree.bind('<<TreeviewSelect>>',pick); combo.bind('<<ComboboxSelected>>',choose)
            ttk.Button(row,text='Choisir un fichier…',command=browse).pack(side='left',padx=5)
            footer=ttk.Frame(win,padding=10); footer.pack(fill='x')
            ttk.Label(footer,text=f'{len(unreadable)} dossier(s) inaccessible(s).' if unreadable else 'Les coupes, cadrages et volumes sont conservés.').pack(side='left')
            def apply():
                if not choices:return
                if self.edit_locked('timeline') or not self.current_snapshot(data,state):return
                picked=dict(choices)
                def done(proposed):
                    if self.edit_locked('timeline') or not self.current_snapshot(data,state):return
                    self.checkpoint(); data.update(proposed); self.refresh(); on_done()
                    if win.winfo_exists():win.destroy()
                    self.status.set(f'{len(picked)} média(s) réassocié(s). Annuler restaure les anciens chemins.')
                self.run_background('Vérification des médias',lambda cancel,progress:replacements(snapshot,picked,executable,lambda:check_task(cancel)),done)
            ttk.Button(footer,text='Appliquer les correspondances',command=apply).pack(side='right')
        self.run_background('Recherche des médias',lambda cancel,progress:find_candidates(missing,folder,lambda:check_task(cancel),progress),show)

    def analyse_audio(self):
        from studio import effective_items
        from audio_analysis import analyse,describe
        self.timeline.finish_name_edit()
        data=self.data; state=json.dumps(data,sort_keys=True); clips,audio=effective_items(data); executable=self.executable
        if montage.duration(clips+audio)<=0:messagebox.showinfo('Analyse sonore','Ajoutez des médias au montage.',parent=self.root); return
        def done(report):
            if not self.current_snapshot(data,state):return
            win=tk.Toplevel(self.root); win.title('Analyse sonore du montage')
            ttk.Label(win,text=describe(report),padding=18,wraplength=650).pack()
            def apply():
                if self.edit_locked('timeline') or not self.current_snapshot(data,state):return
                self.checkpoint()
                for clip in data.get('clips',[])+data.get('audio_clips',[]):clip['volume']*=report['gain']
                self.refresh(); self.refresh_preview_audio(); win.destroy(); self.status.set('Réduction sonore appliquée à tous les clips. Annuler restaure les volumes précédents.')
            if report['peak']>=.99:ttk.Button(win,text='Appliquer la réduction au projet',command=apply).pack(pady=8)
        self.run_background('Analyse sonore',lambda cancel,progress:analyse(clips,audio,executable,cancel,lambda at:progress(f'Analyse : {at:.1f} s')),done)

    def calibration_versions(self):
        from calibration_versions import snapshot,restore
        self.timeline.finish_name_edit()
        data=self.data; owner=self.active_document; win=tk.Toplevel(self.root); win.title('Versions de calibration'); win.geometry('850x600')
        ttk.Label(win,text='Comparer sans modifier ; Restaurer applique les coins et les noms, en conservant le montage.',padding=8).pack()
        tree=ttk.Treeview(win,columns=('name','date'),show='headings',height=5); tree.heading('name',text='Version'); tree.heading('date',text='Date'); tree.pack(fill='x',padx=10)
        canvas=tk.Canvas(win,bg='#17212a',height=260,highlightthickness=0); canvas.pack(fill='both',expand=True,padx=10,pady=8)
        ttk.Label(win,text='Bleu : calibration actuelle • Jaune pointillé : version sélectionnée. La comparaison respecte le format 16:9.').pack()
        def current():
            nonlocal data
            if self.active_document is not owner:messagebox.showinfo('Calibration','Revenez au projet qui a ouvert cette fenêtre.',parent=win); return False
            data=self.data
            return True
        def versions():return data.get('calibration_versions',[])
        def selected():return next((v for v in versions() if v['id'] in tree.selection()),None)
        def draw(event=None):
            nonlocal data
            if self.active_document is owner:data=self.data
            canvas.delete('all'); width=max(1,canvas.winfo_width()); height=max(1,canvas.winfo_height()); scale=min(width/16,height/9); w=16*scale; h=9*scale; ox=(width-w)/2; oy=(height-h)/2
            v=selected()
            for zones,color,dash in [(data['zones'],'#41d8ff',()),(v['zones'] if v else [],'#ffd268',(5,3))]:
                for i,q in enumerate(zones):
                    canvas.create_polygon(*[coordinate for x,y in q for coordinate in (ox+x*w,oy+y*h)],outline=color,fill='',width=2,dash=dash)
                    canvas.create_text(ox+sum(p[0] for p in q)/4*w,oy+sum(p[1] for p in q)/4*h,text=str(i+1),fill=color)
        def refresh(chosen=None):
            tree.delete(*tree.get_children())
            for v in versions():tree.insert('','end',iid=v['id'],values=(v['name'],v['created'][:19].replace('T',' ')+' UTC'))
            if chosen and tree.exists(chosen):tree.selection_set(chosen)
            draw()
        def save():
            if not current() or self.edit_locked('mapping'):return
            if len(versions())>=200:messagebox.showinfo('Calibration','Limite de 200 versions atteinte.',parent=win); return
            name=simpledialog.askstring('Nouvelle version','Nom de la calibration :',initialvalue='Calibration validée',parent=win)
            if name and name.strip():
                version=snapshot(data,name); self.checkpoint(); data.setdefault('calibration_versions',[]).append(version); self.refresh(); refresh(version['id'])
        def rename():
            if not current() or self.edit_locked('mapping'):return
            v=selected()
            if not v:return
            name=simpledialog.askstring('Renommer','Nom de la version :',initialvalue=v['name'],parent=win)
            if name and name.strip():self.checkpoint(); v['name']=name.strip(); self.refresh(); refresh(v['id'])
        def remove():
            if not current() or self.edit_locked('mapping'):return
            v=selected()
            if v:self.checkpoint(); data['calibration_versions']=[item for item in versions() if item['id']!=v['id']]; self.refresh(); refresh()
        def apply():
            if not current() or self.edit_locked('mapping'):return
            v=selected()
            if not v:return
            try:result=restore(data,v)
            except ValueError as e:messagebox.showerror('Calibration incompatible',str(e),parent=win); return
            self.checkpoint(); data.update(result); self.refresh(); refresh(v['id']); self.status.set('Calibration restaurée : '+v['name']+'. Le montage est conservé ; Annuler revient à la géométrie précédente.')
        row=ttk.Frame(win,padding=10); row.pack(fill='x')
        for label,fn in [('Enregistrer l’actuelle…',save),('Renommer…',rename),('Supprimer',remove),('Restaurer la sélection',apply)]:ttk.Button(row,text=label,command=fn).pack(side='left',padx=4)
        tree.bind('<<TreeviewSelect>>',draw); canvas.bind('<Configure>',draw); refresh()
