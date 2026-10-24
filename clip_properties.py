"""Unified properties dialog for one clip or a selection of timeline clips."""
import copy
import math
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog
import montage


class ClipProperties(simpledialog.Dialog):
    def __init__(self,parent,clip,validator,video_tracks=None,audio_tracks=None):
        self.multiple=isinstance(clip,list)
        self.clips=copy.deepcopy(clip if self.multiple else [clip]); self.clip=self.clips[0]
        self.validator=validator; self.video_tracks=video_tracks; self.audio_tracks=audio_tracks
        super().__init__(parent,'Propriétés de la sélection' if self.multiple else 'Propriétés du clip')

    def body(self,parent):
        videos=[c for c in self.clips if c.get('kind')!='audio']
        title=f'{len(self.clips)} éléments sélectionnés' if self.multiple else Path(self.clip['path']).name
        ttk.Label(parent,text=title,wraplength=460).grid(row=0,column=0,columnspan=2,sticky='w',pady=6)
        self.variables={}; self.initial={}; self.row=1
        def field(key,label,values,percent=False):
            value=values[0] if values and all(v==values[0] for v in values) else None
            text='' if value is None else f'{value*(100 if percent else 1):.12g}'
            var=tk.StringVar(value=text); self.variables[key]=var; self.initial[key]=text; setattr(self,key,var)
            ttk.Label(parent,text=label).grid(row=self.row,column=0,sticky='w',padx=6,pady=3)
            entry=ttk.Entry(parent,textvariable=var,width=16); entry.grid(row=self.row,column=1,padx=6); self.row+=1
            return entry
        field('start','Décalage du groupe (s)' if self.multiple else 'Position dans le montage (s)',[0.] if self.multiple else [self.clip['start']])
        if any(not montage.is_image(c) for c in self.clips):field('source_in','Début dans le fichier source (s)',[c['in'] for c in self.clips])
        focus=field('duration','Durée (s)',[montage.length(c) for c in self.clips])
        field('volume','Volume (%)',[c['volume'] for c in self.clips],True)
        kinds={c.get('kind')=='audio' for c in self.clips}
        tracks=self.audio_tracks if kinds=={True} else self.video_tracks if kinds=={False} else None
        self.track=None
        if tracks and not any('panorama' in c for c in videos):
            self.track_choices=[f'{i+1} — {name}' for i,name in enumerate(tracks)]
            lanes={c['lane'] for c in self.clips}; text=self.track_choices[next(iter(lanes))] if len(lanes)==1 else ''
            self.track=tk.StringVar(value=text); self.initial_track=text
            ttk.Label(parent,text='Piste de destination').grid(row=self.row,column=0,sticky='w',padx=6,pady=3)
            ttk.Combobox(parent,textvariable=self.track,values=self.track_choices,state='readonly',width=23).grid(row=self.row,column=1,padx=6); self.row+=1
        field('fade_in','Fondu d’apparition (s)',[c.get('fade_in',0.) for c in self.clips])
        field('fade_out','Fondu de disparition (s)',[c.get('fade_out',0.) for c in self.clips])
        self.fit=None
        if videos:
            fits={c.get('fit','Remplir') for c in videos}; self.fit=tk.StringVar(value=next(iter(fits)) if len(fits)==1 else ''); self.initial_fit=self.fit.get()
            ttk.Label(parent,text='Cadrage visuel').grid(row=self.row,column=0,sticky='w',padx=6,pady=3)
            ttk.Combobox(parent,textvariable=self.fit,values=['Remplir','Contenir'],state='readonly',width=16).grid(row=self.row,column=1,padx=6); self.row+=1
            for key,label,default in [('zoom','Zoom (%)',1.),('pan_x','Décalage horizontal (%)',0.),('pan_y','Décalage vertical (%)',0.)]:field(key,label,[c.get(key,default) for c in videos],True)
        note='Champs vides : valeurs différentes, conservées si non modifiées.' if self.multiple else 'Le volume reste constant sur toute la durée du clip.'
        if any('panorama' in c for c in videos):note+='\nPanoramique : réglages communs à toutes ses zones. Bouton Panoramique pour choisir les zones.'
        ttk.Label(parent,text=note+'\n0 % : muet • 100 % : niveau d’origine',wraplength=460).grid(row=self.row,column=0,columnspan=2,sticky='w',pady=6); self.row+=1
        self.error=tk.StringVar(); ttk.Label(parent,textvariable=self.error,foreground='#b02020',wraplength=460).grid(row=self.row,column=0,columnspan=2,pady=6)
        focus.selection_range(0,'end'); return focus

    def validate(self):
        try:
            changes={}
            for key,var in self.variables.items():
                text=var.get().strip()
                if text==self.initial[key] or (self.multiple and not text):continue
                try:value=float(text.replace('%','').replace(',','.'))
                except ValueError:raise ValueError('Saisissez des nombres valides pour les propriétés.') from None
                if not math.isfinite(value):raise ValueError('Les valeurs doivent être des nombres finis.')
                if key in ('volume','zoom','pan_x','pan_y'):value/=100
                if key=='duration' and value<1/30:raise ValueError('La durée minimale est une image (1/30 s).')
                changes[key]=value
            proposed=[]
            for original in self.clips:
                clip=copy.deepcopy(original); length=changes.get('duration',montage.length(clip))
                for key,value in changes.items():
                    if key in ('source_in','duration'):continue
                    if key in ('zoom','pan_x','pan_y') and clip.get('kind')=='audio':continue
                    clip[key]=original['start']+value if key=='start' and self.multiple else value
                if 'source_in' in changes and not montage.is_image(clip):clip['in']=changes['source_in']
                if 'source_in' in changes or 'duration' in changes:clip['out']=clip['in']+length
                if self.track is not None and self.track.get()!=self.initial_track:
                    if self.track.get() not in self.track_choices:raise ValueError('Choisissez une piste valide.')
                    clip['lane']=self.track_choices.index(self.track.get())
                if self.fit is not None and self.fit.get()!=self.initial_fit and clip.get('kind')!='audio':clip['fit']=self.fit.get()
                proposed.append(clip)
            self.validator(proposed if self.multiple else proposed[0]); self.proposal=proposed if self.multiple else proposed[0]; self.error.set(''); return True
        except ValueError as e:self.error.set(str(e)); return False

    def apply(self):self.result=self.proposal

    def buttonbox(self):
        row=ttk.Frame(self,padding=8); row.pack()
        ttk.Button(row,text='Appliquer',command=self.ok).pack(side='left',padx=5)
        ttk.Button(row,text='Annuler',command=self.cancel).pack(side='left',padx=5)
        self.bind('<Return>',self.ok); self.bind('<Escape>',self.cancel)
