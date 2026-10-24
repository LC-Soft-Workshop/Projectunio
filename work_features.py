"""Editing aids and optional work copies, without changing saved source paths."""
import tkinter as tk
from tkinter import ttk,messagebox


class WorkFeatures:
    def toggle_loupe(self):
        if getattr(self,'mapping_loupe',None) and not self.mapping_loupe.closed:self.mapping_loupe.close(); return
        from mapping_loupe import MappingLoupe
        self.edit_mode.set('mapping'); self.discard_video_proxy(); self.draw()
        self.mapping_loupe=MappingLoupe(self)

    def open_source_view(self):
        if getattr(self,'source_comparison',None) and not self.source_comparison.closed:self.source_comparison.win.lift(); return
        from source_comparison import SourceComparison
        self.source_comparison=SourceComparison(self)

    def toggle_projection_mode(self,mode):
        players=[getattr(self,'direct_player',None)]+[p for p,s in self.previews]
        player=next((p for p in players if p and not p.closed and getattr(p,'projection',None) and not p.projection.closed),None)
        if player and hasattr(player,'projection_controls'):player.projection_controls.toggle(mode)
        else:self.status.set('Ouvrez une projection HDMI animée pour utiliser Noir ou Figer.')
        return 'break'

    def proxy_manager(self):
        from work_media import PROXY_ROOT,prepare_proxies
        from render_cache import RenderCache
        service=self.media_work; win=tk.Toplevel(self.root); win.title('Copies de travail légères')
        ttk.Label(win,text='Les copies vidéo légères servent à l’image arrêtée et à la lecture directe.\nLe son et les exports utilisent les originaux. Le projet conserve leurs chemins.',padding=12,wraplength=560).pack()
        label=ttk.Label(win,padding=8); label.pack()
        def refresh():
            if not win.winfo_exists():return
            count,size=RenderCache(PROXY_ROOT).usage(); label.configure(text=f'{len(service.records)} source(s) prête(s) pour cette session • {size/1024**2:.1f} Mo conservés • limite 4 Go')
        def changed():
            self.stop_direct(); self.still_renderer.cancel_pending(); self._still_wanted_key=None; self._still_request_key=None; self.schedule_still()
        ttk.Checkbutton(win,text='Utiliser les copies disponibles',variable=service.enabled,command=changed).pack(pady=6)
        def prepare():
            paths=[c['path'] for c in self.data.get('clips',[])]; executable=self.executable
            if not paths:messagebox.showinfo('Copies de travail','Importez des vidéos dans le projet.',parent=win); return
            def done(result):
                records,errors=result; service.records.update(records); changed(); refresh()
                if errors:messagebox.showerror('Certaines copies n’ont pas été préparées','\n\n'.join(errors),parent=self.root)
                else:self.status.set('Copies de travail prêtes. Les originaux restent utilisés pour l’export.')
            self.run_background('Préparer les copies de travail',lambda cancel,progress:prepare_proxies(paths,executable,cancel,progress),done)
        def clear():
            was_enabled=service.enabled.get(); service.enabled.set(False); changed()
            def work(cancel,progress):
                for attempt in range(15):
                    try:RenderCache(PROXY_ROOT).clear(); return
                    except PermissionError:
                        if cancel.wait(.1):raise RuntimeError('Opération annulée.')
                raise ValueError('Une copie est encore utilisée. Fermez les lectures et réessayez.')
            def done(value):service.records.clear(); service.enabled.set(was_enabled); changed(); refresh()
            self.run_background('Vider les copies de travail',work,done)
        row=ttk.Frame(win,padding=10); row.pack()
        ttk.Button(row,text='Préparer les vidéos du projet',command=prepare).pack(side='left',padx=5)
        ttk.Button(row,text='Vider les copies',command=clear).pack(side='left',padx=5)
        ttk.Label(win,text='Après un redémarrage, Préparer réactive les copies conservées sans les réencoder.\nUne source modifiée ou une copie absente utilise automatiquement l’original.',padding=10,wraplength=560).pack()
        refresh()
