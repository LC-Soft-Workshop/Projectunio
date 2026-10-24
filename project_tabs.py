"""Notebook tabs with a real close target separate from tab selection."""
import tkinter as tk
from tkinter import ttk


class ProjectTabs(ttk.Notebook):
    def __init__(self,parent,on_close,on_new=None,**kwargs):
        style=ttk.Style(parent)
        self.icons=[]
        for color in ('#666666','#d02929'):
            icon=tk.PhotoImage(master=parent,width=14,height=14)
            for n in range(3,11):
                for offset in (0,1):
                    icon.put(color,(n,n+offset)); icon.put(color,(n,13-n+offset))
            self.icons.append(icon)
        if 'ProjectTab.close' not in style.element_names():
            style.element_create('ProjectTab.close','image',self.icons[0],('active',self.icons[1]),border=2,sticky='')
        style.layout('ProjectTabs.TNotebook.Tab',[
            ('Notebook.tab',dict(sticky='nswe',children=[
                ('Notebook.padding',dict(side='top',sticky='nswe',children=[
                    ('Notebook.focus',dict(side='left',sticky='nswe',children=[
                        ('Notebook.label',dict(side='left',sticky='')),
                        ('ProjectTab.close',dict(side='left',sticky=''))]))]))]))])
        super().__init__(parent,style='ProjectTabs.TNotebook',**kwargs)
        self.on_close=on_close; self.close_target=None
        self.bind('<ButtonPress-1>',self.close_press)
        self.bind('<ButtonRelease-1>',self.close_release)
        self.add_button=ttk.Button(self,text='+',width=3,command=on_new,takefocus=True)
        self.position_timer=None
        self.bind('<Destroy>',self.cancel_position,add='+')
        self.bind('<Configure>',lambda e:self.position_add_button(),add='+')

    def cancel_position(self,event):
        if event.widget==self and self.position_timer:
            self.after_cancel(self.position_timer); self.position_timer=None

    def schedule_position(self):
        if self.position_timer is None:self.position_timer=self.after_idle(self.update_position)

    def update_position(self):
        self.position_timer=None; self.position_add_button()

    def position_add_button(self):
        if not hasattr(self,'add_button'):return
        width=self.winfo_width(); last=0
        for x in range(width):
            try:self.index(f'@{x},10'); last=x+1
            except tk.TclError:pass
        self.add_button.place(x=min(last+4,max(0,width-34)),y=1,width=30,height=24)

    def add(self,*args,**kwargs):
        result=super().add(*args,**kwargs); self.schedule_position(); return result

    def forget(self,*args,**kwargs):
        result=super().forget(*args,**kwargs); self.schedule_position(); return result

    def tab(self,*args,**kwargs):
        result=super().tab(*args,**kwargs)
        if kwargs:self.schedule_position()
        return result

    def close_press(self,event):
        self.close_target=None
        if self.identify(event.x,event.y)=='ProjectTab.close':
            self.close_target=self.tabs()[self.index(f'@{event.x},{event.y}')]; return 'break'

    def close_release(self,event):
        target=self.close_target; self.close_target=None
        if target is not None:
            if self.identify(event.x,event.y)=='ProjectTab.close' and self.tabs()[self.index(f'@{event.x},{event.y}')]==target:self.on_close(target)
            return 'break'
