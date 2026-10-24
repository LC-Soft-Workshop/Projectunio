"""Pointer gestures for bounded mapping edits and click-to-follow handles."""
import math


class MappingInteraction:
    def install_mapping_interaction(self):
        self.mapping_latched=False; self.mapping_moved=False
        self.canvas.bind('<ButtonRelease-1>',self.mapping_release)
        self.canvas.bind('<Motion>',self.mapping_motion,add='+')
        self.edit_mode.trace_add('write',lambda *args:self.mapping_mode_changed())
        self.mapping_mode_changed()

    def mapping_mode_changed(self):
        self.end_mapping_gesture()
        if self.edit_mode.get()!='draw':
            self.drawing_zone=None; self.canvas.delete('new_zone')
        self.canvas.configure(cursor='crosshair' if self.edit_mode.get()=='draw' else '')

    def begin_mapping_gesture(self,event):
        self.mapping_latched=False; self.mapping_moved=False; self.mapping_press=(event.x,event.y)
        self.canvas.grab_set()

    def end_mapping_gesture(self):
        self.mapping_latched=False; self.anchor=None
        if self.canvas.grab_current()==self.canvas:self.canvas.grab_release()

    def mapping_release(self,event=None):
        if self.edit_mode.get()=='video':return self.finish_video_drag(event)
        if self.edit_mode.get()!='mapping' or not getattr(self,'anchor',None):return
        if not self.mapping_moved and not self.whole:
            self.mapping_latched=True
            self.status.set('Le coin ou l’arête suit la souris. Cliquez pour déposer ; Échap pour arrêter.')
        else:self.end_mapping_gesture()

    def mapping_motion(self,event):
        if self.mapping_latched and self.edit_mode.get()=='mapping':self.drag(event)

    def bounded_mapping_quad(self,event):
        from app import valid
        ox,oy,w,h=self.viewport(self.canvas); p=((event.x-ox)/w,(event.y-oy)/h)
        if math.hypot(event.x-self.mapping_press[0],event.y-self.mapping_press[1])>=3:self.mapping_moved=True
        q=[list(v) for v in self.start[self.zone]]
        indices=list(range(4)) if self.whole else [self.edge,(self.edge+1)%4] if self.edge is not None else [self.corner]
        if len(indices)==1:q[self.corner]=[max(0.,min(1.,v)) for v in p]
        else:
            dx=max(-min(q[i][0] for i in indices),min(1-max(q[i][0] for i in indices),p[0]-self.anchor[0]))
            dy=max(-min(q[i][1] for i in indices),min(1-max(q[i][1] for i in indices),p[1]-self.anchor[1]))
            for i in indices:q[i]=[q[i][0]+dx,q[i][1]+dy]
        if valid(q):return q
        # Stop at the last valid shape when a handle would cross another edge.
        previous=self.data['zones'][self.zone]; low=0.; high=1.
        for _ in range(30):
            middle=(low+high)/2; candidate=[[a+(b-a)*middle for a,b in zip(v,target)] for v,target in zip(previous,q)]
            if valid(candidate):low=middle
            else:high=middle
        return [[a+(b-a)*low for a,b in zip(v,target)] for v,target in zip(previous,q)]
