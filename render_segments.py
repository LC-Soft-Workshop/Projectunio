"""Frame-aligned video intervals: never more than two active video sources."""
from dataclasses import dataclass
import json
import math
import montage


def frame_at_or_after(time,fps=30):return max(0,math.ceil(time*fps-1e-8))


@dataclass
class Segment:
    first: int
    last: int
    clips: list

    @property
    def frames(self):return self.last-self.first

    @property
    def window(self):return self.first/30,self.last/30

    def key(self):
        begin,end=self.window
        sources=[]
        for c in self.clips:
            sources.append(dict(path=c['path'],lane=c['lane'],source_in=round(c['in'],9) or 0.,source_out=round(min(c['out'],c['in']+end-c['start']),9),position=round(c['start']-begin,9) or 0.,fit=c['fit'],zoom=float(c.get('zoom',1.)),pan_x=float(c.get('pan_x',0.)) or 0.,pan_y=float(c.get('pan_y',0.)) or 0.,fade_in=c.get('fade_in',0.),fade_out=c.get('fade_out',0.),effect_length=montage.length(c) if c.get('fade_in') or c.get('fade_out') else 0.))
        for source,clip in zip(sources,self.clips):
            if montage.is_image(clip):source['kind']='image'
            if 'panorama' in clip:source['panorama']=clip['panorama']
        return json.dumps([self.frames,sources],sort_keys=True)


def plan(clips,audio_clips):
    montage.validate_items(clips+audio_clips)
    last=frame_at_or_after(montage.duration(clips+audio_clips))
    if last<=0:raise ValueError('Le montage est vide.')
    boundaries={0,last}; ranges=[]
    for c in clips:
        first,end=frame_at_or_after(c['start']),frame_at_or_after(c['start']+montage.length(c))
        boundaries.update((first,end)); ranges.append((first,end,c))
    points=sorted(boundaries)
    return [Segment(a,b,[dict(c,audio=False) for start,end,c in ranges if start<=a<end]) for a,b in zip(points,points[1:]) if b>a]
