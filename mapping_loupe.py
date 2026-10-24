"""Pixel-centered calibration loupe with vector handles and live coordinates."""
import tkinter as tk
from tkinter import ttk


def magnified_pixels(frame,center,size,output,zoom):
    width,height=size; rw,rh=output; cx,cy=center
    sw,sh,pixels=frame if frame is not None else (1,1,b'\0\0\0')
    xs=[round((cx+(x-width/2)/(zoom*rw))*sw) for x in range(width)]
    rows={}; result=[]
    for y in range(height):
        sy=round((cy+(y-height/2)/(zoom*rh))*sh)
        if sy not in rows:
            rows[sy]=b''.join(pixels[(sy*sw+x)*3:(sy*sw+x)*3+3] if 0<=sy<sh and 0<=x<sw else b'\0\0\0' for x in xs)
        result.append(rows[sy])
    return f'P6\n{width} {height}\n255\n'.encode()+b''.join(result)


class MappingLoupe:
    def __init__(self,app):
        self.app=app; self.closed=False; self.key=None; self.image=None
        self.win=tk.Toplevel(app.root); self.win.title('Loupe du mapping'); self.win.transient(app.root); self.win.resizable(False,False)
        row=ttk.Frame(self.win,padding=6); row.pack(fill='x'); ttk.Label(row,text='Grossissement').pack(side='left')
        self.zoom=tk.StringVar(value='8'); ttk.Combobox(row,textvariable=self.zoom,values=['4','8','16'],width=5,state='readonly').pack(side='left',padx=8)
        self.canvas=tk.Canvas(self.win,width=300,height=240,bg='black',highlightthickness=0); self.canvas.pack()
        self.label=ttk.Label(self.win,padding=8,wraplength=300); self.label.pack()
        ttk.Label(self.win,text='Flèches : 1 pixel • Maj : 10 pixels\nSélectionnez un coin dans le canevas principal.',padding=6).pack()
        self.win.bind('<KeyPress>',self.nudge); self.win.bind('<Escape>',lambda e:self.close()); self.win.protocol('WM_DELETE_WINDOW',self.close)
        self.win.bind('<Destroy>',lambda e:self.close() if e.widget==self.win and not self.closed else None)
        self.poll()

    def nudge(self,event):
        if event.keysym in ('Left','Right','Up','Down'):
            self.app.key(event); self.key=None; return 'break'

    def poll(self):
        if self.closed:return
        a=self.app; q=a.data['zones'][a.zone]; center=q[a.corner]; resolution=tuple(a.data['resolution']); zoom=int(self.zoom.get())
        key=(id(a.data),a.zone,a.corner,repr(q),resolution,zoom,id(a.still_frame))
        if key!=self.key:
            self.key=key; c=self.canvas; c.delete('all')
            self.image=tk.PhotoImage(data=magnified_pixels(a.still_frame,center,(300,240),resolution,zoom)); c.create_image(150,120,image=self.image)
            def point(p):return (150+(p[0]-center[0])*resolution[0]*zoom,120+(p[1]-center[1])*resolution[1]*zoom)
            points=[v for p in q for v in point(p)]; c.create_polygon(*points,outline='#41d8ff',fill='',width=2)
            c.create_line(135,120,165,120,fill='white'); c.create_line(150,105,150,135,fill='white')
            c.create_oval(144,114,156,126,outline='#ffe275',width=2)
            self.label.configure(text=f'{a.zone_names()[a.zone]} • Coin {a.corner+1}\nX : {center[0]*100:.3f} % • Y : {center[1]*100:.3f} %\n{center[0]*resolution[0]:.1f} × {center[1]*resolution[1]:.1f} pixels de sortie')
        self.timer=self.win.after(70,self.poll)

    def close(self):
        if self.closed:return
        self.closed=True; self.image=None
        try:
            if hasattr(self,'timer'):self.win.after_cancel(self.timer)
            self.win.destroy()
        except tk.TclError:pass
