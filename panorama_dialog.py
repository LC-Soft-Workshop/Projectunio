"""Choose a panorama once; all timeline occurrences remain a single clip."""
import copy
import tkinter as tk
from tkinter import ttk, simpledialog
import panorama


class PanoramaDialog(simpledialog.Dialog):
    def __init__(self,parent,clip,zones,names,validator):
        self.clip=copy.deepcopy(clip); self.zones=zones; self.names=names; self.validator=validator
        selected=panorama.lanes(clip) if 'panorama' in clip else sorted(range(len(zones)),key=lambda i:sum(p[0] for p in zones[i]))
        self.order=selected+[i for i in range(len(zones)) if i not in selected]
        self.initial_selected=set(selected)
        super().__init__(parent,'Vidéo panoramique')

    def body(self,parent):
        ttk.Label(parent,text='Une seule vidéo, un cadrage commun, plusieurs zones.',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=5)
        ttk.Label(parent,text='Sélectionnez les zones à utiliser (Ctrl+clic). En automatique, leur position\nhorizontale et verticale est conservée. En manuel, elles forment une bande.',wraplength=540).pack(anchor='w',pady=5)
        row=ttk.Frame(parent); row.pack(fill='x')
        self.list=tk.Listbox(row,selectmode='extended',exportselection=False,height=min(8,len(self.order)),width=42)
        self.list.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(row,orient='vertical',command=self.list.yview); scroll.pack(side='left',fill='y'); self.list.configure(yscrollcommand=scroll.set)
        buttons=ttk.Frame(row); buttons.pack(side='left',padx=10)
        self.order_buttons=[]
        for text,direction in [('← Avant',-1),('Après →',1)]:
            button=ttk.Button(buttons,text=text,command=lambda d=direction:self.move(d)); button.pack(pady=4); self.order_buttons.append(button)
        for index,lane in enumerate(self.order):
            self.list.insert('end',self.names[lane])
            if lane in self.initial_selected:self.list.selection_set(index)
        self.list.bind('<<ListboxSelect>>',lambda e:self.preview())
        settings=self.clip.get('panorama',{})
        self.auto_gap=tk.BooleanVar(value=settings.get('gap_mode')=='auto' if settings else True)
        ttk.Checkbutton(parent,text='Respecter la disposition du mapping (écarts automatiques)',variable=self.auto_gap,command=self.auto_changed).pack(anchor='w',pady=(10,0))
        line=ttk.Frame(parent); line.pack(fill='x',pady=10)
        ttk.Label(line,text='Espace entre zones (%)').pack(side='left')
        self.gap=tk.StringVar(value=f'{self.clip.get("panorama",{}).get("gap",0.)*100:g}')
        self.gap_entry=ttk.Entry(line,textvariable=self.gap,width=8); self.gap_entry.pack(side='left',padx=8)
        self.gap_summary=tk.StringVar(); ttk.Label(parent,textvariable=self.gap_summary,wraplength=540).pack(anchor='w')
        self.gap.trace_add('write',lambda *a:self.preview())
        ttk.Label(parent,text='En manuel seulement : l’ordre de la liste forme une bande horizontale.\n0 % : bords accolés ; 100 % : espace égal à la largeur moyenne d’une zone.',wraplength=540).pack(anchor='w')
        self.strip=tk.Canvas(parent,width=520,height=150,bg='#17212a',highlightthickness=0); self.strip.pack(pady=10)
        ttk.Label(parent,text='Zoom, déplacement, durée, coupes, fondus et volume restent communs.\nLe son est joué une seule fois, rattaché à la première zone.\nLes clips déjà présents sur les zones choisies sont conservés ; tout chevauchement est refusé.',wraplength=540).pack(anchor='w')
        self.error=tk.StringVar(); ttk.Label(parent,textvariable=self.error,foreground='#b02020',wraplength=540).pack(pady=5)
        self.preview(); return self.list

    def selected(self):return [self.order[i] for i in self.list.curselection()]

    def move(self,direction):
        selected=set(self.selected()); indices=list(self.list.curselection())
        for i in (indices if direction<0 else reversed(indices)):
            target=i+direction
            if 0<=target<len(self.order) and self.order[target] not in selected:self.order[i],self.order[target]=self.order[target],self.order[i]
        self.list.delete(0,'end')
        for i,lane in enumerate(self.order):
            self.list.insert('end',self.names[lane])
            if lane in selected:self.list.selection_set(i)
        self.preview()

    def proposal(self):
        selected=self.selected()
        clip=copy.deepcopy(self.clip)
        try:gap=0. if self.auto_gap.get() else float(self.gap.get().replace(',','.'))/100
        except ValueError:raise ValueError('Saisissez un espace entre 0 et 100 %.') from None
        clip['panorama']=dict(lanes=selected,gap=gap)
        if self.auto_gap.get():clip['panorama']['gap_mode']='auto'
        if selected:clip['lane']=selected[0]
        panorama.validate(clip,len(self.zones)); return clip

    def preview(self):
        if not hasattr(self,'strip'):return
        self.gap_entry.configure(state='disabled' if self.auto_gap.get() else 'normal')
        for button in self.order_buttons:button.configure(state='disabled' if self.auto_gap.get() else 'normal')
        self.strip.delete('all')
        try:clip=self.proposal()
        except ValueError:
            self.gap_summary.set('Choisissez au moins deux zones pour afficher l’estimation.'); return
        if self.auto_gap.get():
            self.gap_summary.set('Disposition 2D : chaque zone prélève l’image à sa position dans le mapping, y compris en hauteur. Les espaces sont conservés automatiquement.')
            selected=self.selected(); points=[p for lane in selected for p in self.zones[lane]]
            left=min(x for x,y in points); right=max(x for x,y in points); top=min(y for x,y in points); bottom=max(y for x,y in points)
            scale=min(500/((right-left)*16/9),130/(bottom-top)); ox=(520-(right-left)*16/9*scale)/2; oy=(150-(bottom-top)*scale)/2
            for lane in selected:
                q=self.zones[lane]; coordinates=[v for x,y in q for v in (ox+(x-left)*16/9*scale,oy+(y-top)*scale)]
                self.strip.create_polygon(*coordinates,fill='#21768b',outline='#41d8ff',width=2,tags=('panorama_zone',f'panorama_zone_{lane}'))
                self.strip.create_text(sum(coordinates[0::2])/4,sum(coordinates[1::2])/4,text=self.names[lane],fill='white',width=max(20,(max(coordinates[0::2])-min(coordinates[0::2]))-4))
            return
        else:self.gap_summary.set('Écart manuel commun à toutes les séparations.')
        for lane,(left,width,total) in panorama.views(clip,self.zones):
            x=5+510*left/total; end=5+510*(left+width)/total
            self.strip.create_rectangle(x,48,end,102,fill='#21768b',outline='#41d8ff')
            self.strip.create_text((x+end)/2,75,text=self.names[lane],fill='white',width=max(1,end-x-4))

    def auto_changed(self):
        if not self.auto_gap.get() and len(self.selected())>=2:
            widths=panorama.logical_widths(self.zones,self.selected()); gaps=panorama.estimated_gaps(self.zones,self.selected(),widths)
            equivalent=sum(gaps)/len(gaps)/(sum(widths)/len(widths))
            self.gap.set(f'{min(1.,equivalent)*100:.6g}')
        self.preview()

    def validate(self):
        try:self.proposed=self.proposal(); self.validator(self.proposed); self.error.set(''); return True
        except ValueError as e:self.error.set(str(e)); return False

    def apply(self):self.result=self.proposed

    def disable(self):
        clip=copy.deepcopy(self.clip); clip.pop('panorama',None)
        try:self.validator(clip)
        except ValueError as e:self.error.set(str(e)); return
        self.result=clip; self.cancel()

    def buttonbox(self):
        row=ttk.Frame(self,padding=8); row.pack()
        ttk.Button(row,text='Appliquer',command=self.ok).pack(side='left',padx=5)
        if 'panorama' in self.clip:ttk.Button(row,text='Revenir à une seule zone',command=self.disable).pack(side='left',padx=5)
        ttk.Button(row,text='Annuler',command=self.cancel).pack(side='left',padx=5)
        self.bind('<Return>',self.ok); self.bind('<Escape>',self.cancel)
