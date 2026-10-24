"""Explicit save/discard/cancel buttons for closing a workspace session."""
from tkinter import ttk,simpledialog


class UnsavedDialog(simpledialog.Dialog):
    def __init__(self,parent,names):
        self.names=names
        super().__init__(parent,'Fermer Projectunio')

    def body(self,parent):
        ttk.Label(parent,text='Enregistrer les projets modifiés avant de fermer ?',padding=10).pack(anchor='w')
        ttk.Label(parent,text='\n'.join('• '+name for name in self.names),wraplength=500,padding=10).pack(anchor='w')

    def buttonbox(self):
        row=ttk.Frame(self,padding=10); row.pack()
        save=ttk.Button(row,text='Enregistrer',command=lambda:self.choose(True)); save.pack(side='left',padx=5)
        ttk.Button(row,text='Fermer sans enregistrer',command=lambda:self.choose(False)).pack(side='left',padx=5)
        ttk.Button(row,text='Annuler',command=self.cancel).pack(side='left',padx=5)
        self.bind('<Return>',lambda e:self.choose(True)); self.bind('<Escape>',self.cancel); save.focus_set()

    def choose(self,value):self.result=value; self.cancel()
