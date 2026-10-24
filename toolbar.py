"""Native icon buttons, selected-state glyphs and delayed accessible tooltips."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

ICON_NAMES='new open save undo redo mapping video draw grid lock_mapping lock_timeline lock_project panorama compare mire image refresh projection_grid play'.split()


class Tooltip:
    def __init__(self,widget,text):
        self.widget=widget; self.text=text; self.timer=None; self.window=None
        widget.bind('<Enter>',self.schedule,add='+'); widget.bind('<FocusIn>',self.schedule,add='+')
        for event in ('<Leave>','<FocusOut>','<ButtonPress>','<Destroy>'):widget.bind(event,self.hide,add='+')

    def schedule(self,event=None):
        self.hide(); self.timer=self.widget.after(450,self.show)

    def show(self):
        self.timer=None
        if not self.widget.winfo_exists():return
        self.window=tk.Toplevel(self.widget); self.window.overrideredirect(True); self.window.attributes('-topmost',True)
        ttk.Label(self.window,text=self.text,padding=7,relief='solid',borderwidth=1).pack()
        self.window.update_idletasks()
        x=min(self.widget.winfo_rootx(),self.widget.winfo_screenwidth()-self.window.winfo_reqwidth()-8)
        y=min(self.widget.winfo_rooty()+self.widget.winfo_height()+5,self.widget.winfo_screenheight()-self.window.winfo_reqheight()-8)
        self.window.geometry(f'+{max(0,x)}+{max(0,y)}')

    def hide(self,event=None):
        if self.timer:self.widget.after_cancel(self.timer); self.timer=None
        if self.window:self.window.destroy(); self.window=None


class IconToolbar(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent,padding=(10,5))
        self.images={}; self.buttons={}; self.tooltips=[]
        style=ttk.Style(parent); style.configure('Icon.TButton',padding=5); style.configure('Icon.Toolbutton',padding=5)
        for name in ICON_NAMES:
            for suffix in ('','-active'):
                self.images[name+suffix]=tk.PhotoImage(master=self,file=str(Path(__file__).parent/'assets'/'toolbar'/(name+suffix+'.png')))
        self.bind('<Destroy>',self.release_images,add='+')

    def release_images(self,event):
        if event.widget is self:
            for tip in self.tooltips:tip.hide()
            self.images.clear(); self.tooltips.clear()

    def separator(self):ttk.Separator(self,orient='vertical').pack(side='left',fill='y',padx=7,pady=3)

    def add(self,name,label,command,variable=None,value=None):
        options=dict(image=(self.images[name],'selected',self.images[name+'-active']),text=label,compound='image',command=command,takefocus=True)
        if variable is None:button=ttk.Button(self,style='Icon.TButton',**options)
        elif value is None:button=ttk.Checkbutton(self,variable=variable,style='Icon.Toolbutton',**options)
        else:button=ttk.Radiobutton(self,variable=variable,value=value,style='Icon.Toolbutton',**options)
        button.pack(side='left',padx=1); self.buttons[name]=button; self.tooltips.append(Tooltip(button,label)); return button
