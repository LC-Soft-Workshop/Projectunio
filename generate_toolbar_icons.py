"""Build original, simple toolbar glyphs; Pillow is only needed for this build step."""
from pathlib import Path
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parent/'assets'/'toolbar'
NAMES='new open save undo redo mapping video draw grid lock_mapping lock_timeline lock_project panorama compare mire image refresh projection_grid play'.split()

def render(name,selected=False):
    im=Image.new('RGBA',(96,96)); d=ImageDraw.Draw(im); c='#007eab' if selected else '#344454'
    def points(p):return [(round(x*4),round(y*4)) for x,y in p]
    def line(p,width=1.7,color=None):d.line(points(p),fill=color or c,width=round(width*4),joint='curve')
    def box(rect,fill=None,radius=0):d.rounded_rectangle(tuple(round(x*4) for x in rect),radius=radius*4,outline=c,fill=fill,width=6)
    def oval(rect,fill=None):d.ellipse(tuple(round(x*4) for x in rect),outline=c,fill=fill,width=6)
    def poly(p,fill=None):d.polygon(points(p),fill=fill or c)
    if name=='new':
        line([(5,21),(5,3),(15,3),(19,7),(19,10)]); line([(15,3),(15,7),(19,7)]); line([(16,13),(16,21)]); line([(12,17),(20,17)])
    elif name=='open':
        line([(3,19),(3,5),(10,5),(12,8),(21,8)]); line([(3,19),(7,10),(22,10),(18,19),(3,19)])
    elif name=='save':
        box((4,3,20,21)); box((8,3,16,9)); box((8,14,16,21))
    elif name in ('undo','redo'):
        p=[(4,10),(13,10),(18,12),(20,16),(18,20),(13,21)]
        arrow=[(8,5),(3,10),(8,15)]
        if name=='redo':p=[(24-x,y) for x,y in p]; arrow=[(24-x,y) for x,y in arrow]
        line(p,2); line(arrow,2)
    elif name in ('mapping','draw'):
        line([(6,5),(19,3),(21,18),(3,21),(6,5)])
        if name=='mapping':
            for x,y in [(6,5),(19,3),(21,18),(3,21)]:oval((x-1.7,y-1.7,x+1.7,y+1.7),c)
        else:
            line([(10,16),(20,6)],3); line([(9,17),(9,14)]); line([(20,6),(22,8)])
    elif name=='video':
        box((3,4,21,20)); line([(12,7),(12,17)]); line([(7,12),(17,12)]); line([(9,9),(12,6),(15,9)]); line([(9,15),(12,18),(15,15)]); line([(9,9),(6,12),(9,15)]); line([(15,9),(18,12),(15,15)])
    elif name in ('grid','projection_grid'):
        box((3,3,21,21)); line([(9,3),(9,21)]); line([(15,3),(15,21)]); line([(3,9),(21,9)]); line([(3,15),(21,15)])
        if name=='projection_grid':poly([(14,15),(22,15),(22,23),(14,23)],'#f7f8fa'); line([(16,19),(22,19)]); line([(19,16),(19,22)])
    elif name.startswith('lock_'):
        box((8,10,21,22),radius=2)
        if selected:d.arc((40,8,76,60),180,360,fill=c,width=7)
        else:line([(12,10),(12,5),(15,2),(19,3)],2)
        oval((13,14,16,17),c); line([(14.5,17),(14.5,19)])
        if name=='lock_mapping':line([(1,3),(7,2),(7,8),(1,9),(1,3)],1.2)
        elif name=='lock_timeline':line([(1,3),(7,3)]); line([(1,6),(7,6)]); line([(1,9),(5,9)])
        else:line([(1,9),(1,2),(5,2),(7,4),(7,9),(1,9)],1.2)
    elif name=='panorama':
        box((2,5,22,19)); line([(8,5),(8,19)]); line([(16,5),(16,19)]); poly([(10,9),(15,12),(10,15)])
    elif name=='compare':
        box((2,4,10,20)); box((14,4,22,20)); line([(5,15),(7,12),(9,15)]); line([(16,15),(18,10),(21,15)])
    elif name in ('mire','image'):
        box((2,3,22,18)); line([(12,18),(12,22)]); line([(8,22),(16,22)])
        if name=='mire':oval((7,5,17,16)); line([(12,5),(12,16)]); line([(7,10.5),(17,10.5)])
        else:oval((6,6,9,9)); line([(4,15),(9,10),(13,14),(16,10),(20,15)])
    elif name=='refresh':
        d.arc((16,16,80,80),30,310,fill=c,width=8); line([(17,3),(19,8),(13,8)],2)
    elif name=='play':poly([(6,3),(21,12),(6,21)])
    return im.resize((24,24),Image.Resampling.LANCZOS)

if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    for name in NAMES:
        render(name).save(ROOT/(name+'.png')); render(name,True).save(ROOT/(name+'-active.png'))
    print(f'{len(NAMES)*2} icônes de barre d’outils créées.')
