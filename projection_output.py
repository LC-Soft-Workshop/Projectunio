"""Borderless video-only output; transport stays in the control window."""
import tkinter as tk
from tkinter import ttk
from display_geometry import place_projector_window,monitor_rectangles
from mapping_still import resize_ppm


class ProjectionOutput:
    def __init__(self,parent,rectangle,on_close=lambda:None):
        self.rectangle=tuple(rectangle); self.on_close=on_close; self.closed=False; self.frame=None; self.latest=None; self.image=None; self.black=False; self.frozen=False
        self.win=tk.Toplevel(parent); self.win.overrideredirect(True); self.win.configure(bg='black')
        x,y,w,h=rectangle; self.win.geometry(f'{w}x{h}{x:+d}{y:+d}')
        self.canvas=tk.Canvas(self.win,bg='black',highlightthickness=0); self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.render()); self.win.bind('<Escape>',lambda e:self.close())
        self.win.bind('<Destroy>',lambda e:self.close() if e.widget==self.win and not self.closed else None)
        self.win.protocol('WM_DELETE_WINDOW',self.close)
        place_projector_window(self.win,rectangle); self.timer=self.win.after(1000,self.check_monitor)

    def show(self,frame):
        if self.closed:return
        self.latest=frame
        held=self.frozen and self.frame is not None
        if not self.frozen or self.frame is None:self.frame=frame
        if held or self.black:return
        self.render()

    def set_black(self,value):self.black=bool(value); self.render()

    def set_frozen(self,value):
        self.frozen=bool(value)
        if not self.frozen:self.frame=self.latest
        self.render()

    def render(self):
        if self.closed:return
        self.canvas.delete('all')
        if self.black or self.frame is None:self.image=None; return
        w=max(1,self.canvas.winfo_width()); h=max(1,self.canvas.winfo_height()); scale=min(w/16,h/9)
        iw=max(1,round(16*scale)); ih=max(1,round(9*scale))
        self.image=tk.PhotoImage(data=resize_ppm(self.frame,iw,ih)); self.canvas.create_image(w/2,h/2,image=self.image)

    def check_monitor(self):
        if self.closed:return
        try:
            if self.rectangle not in monitor_rectangles():self.close(); return
        except OSError:self.close(); return
        self.timer=self.win.after(1000,self.check_monitor)

    def close(self):
        if self.closed:return
        self.closed=True
        self.image=None; self.frame=None; self.latest=None
        try:
            if hasattr(self,'timer'):self.win.after_cancel(self.timer)
            self.win.destroy()
        except tk.TclError:pass
        self.on_close()


class ProjectionControls:
    def __init__(self,player):
        self.player=player; self.black=tk.BooleanVar(value=False); self.frozen=tk.BooleanVar(value=False)
        row=ttk.Frame(player.win,padding=(8,2)); row.pack(fill='x')
        ttk.Label(row,text='Sortie HDMI :').pack(side='left')
        ttk.Checkbutton(row,text='Noir (F8)',variable=self.black,command=self.sync,style='Toolbutton').pack(side='left',padx=4)
        ttk.Checkbutton(row,text='Figer (F9)',variable=self.frozen,command=self.sync,style='Toolbutton').pack(side='left',padx=4)
        self.label=ttk.Label(row,text='Noir et Figer ne coupent pas le son.'); self.label.pack(side='left',padx=10)
        player.win.bind('<F8>',lambda e:self.toggle('black')); player.win.bind('<F9>',lambda e:self.toggle('frozen'))

    def toggle(self,mode):
        variable=getattr(self,mode); variable.set(not variable.get()); self.sync(); return 'break'

    def sync(self):
        output=getattr(self.player,'projection',None)
        if output and not output.closed:
            output.set_frozen(self.frozen.get()); output.set_black(self.black.get())
            text='Image noire' if self.black.get() else 'Image figée' if self.frozen.get() else 'Image en direct'
            self.label.configure(text=text+' • le son continue.')
        else:self.label.configure(text='Sortie fermée • Noir et Figer ne coupent pas le son.')
