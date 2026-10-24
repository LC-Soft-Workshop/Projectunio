"""One editable clip shared across ordered mapped surfaces."""
import math


def lanes(clip):
    return clip.get('panorama',{}).get('lanes',[clip['lane']])


def validate(clip,zone_count=64):
    if 'panorama' not in clip:return
    value=clip['panorama']
    if clip.get('kind')=='audio' or not isinstance(value,dict):raise ValueError('Panoramique vidéo invalide.')
    selected=value.get('lanes'); gap=value.get('gap',0.)
    if value.get('gap_mode','manual') not in ('manual','auto'):raise ValueError('Mode d’écart panoramique inconnu.')
    if not isinstance(selected,list) or not 2<=len(selected)<=64 or any(type(i)!=int or not 0<=i<zone_count for i in selected) or len(set(selected))!=len(selected) or clip['lane']!=selected[0]:
        raise ValueError('Choisissez au moins deux zones distinctes et existantes pour le panoramique.')
    if type(gap) not in (int,float) or not math.isfinite(gap) or not 0<=gap<=1:raise ValueError('L’espace entre zones doit être compris entre 0 et 100 %.')


def logical_widths(zones,selected):
    widths=[]
    for lane in selected:
        q=zones[lane]
        widths.append((math.dist(q[0],q[1])+math.dist(q[3],q[2]))*16/9/(math.dist(q[0],q[3])+math.dist(q[1],q[2])))
    return widths


def estimated_gaps(zones,selected,widths=None):
    """Project facing edge midpoints onto the pair's shared horizontal axis.

    Use the physical 16:9 image metric, not a distance in square normalized
    coordinates. Vertical offsets do not become an artificial horizontal gap.
    Each adjacent pair gets its own gap; reversing the order preserves it.
    """
    widths=logical_widths(zones,selected) if widths is None else widths
    points=[[(x*16/9,y) for x,y in zones[lane]] for lane in selected]
    gaps=[]
    def middle(a,b):return ((a[0]+b[0])/2,(a[1]+b[1])/2)
    def dot(a,b):return a[0]*b[0]+a[1]*b[1]
    def vector(a,b):return (b[0]-a[0],b[1]-a[1])
    for i,(a,b) in enumerate(zip(points,points[1:])):
        edges=[vector(q[0],q[1]) for q in (a,b)]+[vector(q[3],q[2]) for q in (a,b)]
        aligned=[v if dot(v,edges[0])>=0 else (-v[0],-v[1]) for v in edges]
        axis=(sum(v[0] for v in aligned),sum(v[1] for v in aligned)); size=math.hypot(*axis)
        axis=(axis[0]/size,axis[1]/size)
        ac=middle(middle(a[0],a[1]),middle(a[3],a[2])); bc=middle(middle(b[0],b[1]),middle(b[3],b[2]))
        if dot(vector(ac,bc),axis)<0:axis=(-axis[0],-axis[1])
        first=max((middle(a[1],a[2]),middle(a[0],a[3])),key=lambda p:dot(p,axis))
        second=min((middle(b[0],b[3]),middle(b[1],b[2])),key=lambda p:dot(p,axis))
        distance=max(0.,dot(vector(first,second),axis))
        average_width=sum(abs(dot(edge,axis)) for edge in edges)/4
        gaps.append(distance/max(average_width,1e-12)*(widths[i]+widths[i+1])/2)
    return gaps


def layout(clip,zones):
    """Horizontal strip measurements for manual mode and legacy conversion."""
    validate(clip,len(zones)); selected=lanes(clip); widths=logical_widths(zones,selected)
    if clip['panorama'].get('gap_mode')=='auto':gaps=estimated_gaps(zones,selected,widths)
    else:gaps=[sum(widths)/len(widths)*clip['panorama'].get('gap',0.)]*(len(widths)-1)
    return widths,gaps


def views(clip,zones):
    """2D source rectangles in automatic mode, horizontal slices in manual mode."""
    validate(clip,len(zones))
    if 'panorama' not in clip:return [(clip['lane'],None)]
    if clip['panorama'].get('gap_mode')=='auto':
        selected=lanes(clip)
        left=min(x for lane in selected for x,y in zones[lane]); right=max(x for lane in selected for x,y in zones[lane])
        top=min(y for lane in selected for x,y in zones[lane]); bottom=max(y for lane in selected for x,y in zones[lane])
        unit=bottom-top; total=(right-left)*16/9/unit; result=[]
        for lane in selected:
            q=zones[lane]; x0=min(x for x,y in q); x1=max(x for x,y in q); y0=min(y for x,y in q); y1=max(y for x,y in q)
            # A rectangle in the common 2D source, then perspective-mapped onto q.
            result.append((lane,((x0-left)*16/9/unit,(x1-x0)*16/9/unit,total,(y0-top)/unit,(y1-y0)/unit,1.)))
        return result
    selected=lanes(clip); widths,gaps=layout(clip,zones)
    total=sum(widths)+sum(gaps); cursor=0.; result=[]
    for i,(lane,width) in enumerate(zip(selected,widths)):
        result.append((lane,(cursor,width,total))); cursor+=width+(gaps[i] if i<len(gaps) else 0.)
    return result


def reindex(clip,removed):
    """Called only for clips that do not use the deleted zone."""
    result=dict(clip,lane=clip['lane']-int(clip['lane']>removed))
    if 'panorama' in clip:result['panorama']=dict(clip['panorama'],lanes=[i-int(i>removed) for i in lanes(clip)])
    return result
