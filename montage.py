"""Small two-lane timeline model and FFmpeg composition builder."""
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import panorama


def is_image(clip):return clip.get('kind')=='image'


def image_path(path):return Path(path).suffix.lower() in ('.jpg','.jpeg','.png')


def probe_image(path,executable):
    info=media_info(path,executable)
    streams=[s for s in info.get('streams',[]) if s.get('codec_type')=='video']
    if not streams or streams[0].get('codec_name') not in ('png','mjpeg') or not streams[0].get('width') or not streams[0].get('height'):
        raise ValueError('Choisissez une image JPEG ou PNG valide.')
    return 5.,False


def visual_input(clip,seek,seconds):
    if is_image(clip):return ['-loop','1','-framerate','30','-t',f'{seconds:.9f}','-i',clip['path']]
    return ['-ss',f'{seek:.9f}','-t',f'{seconds:.9f}','-i',clip['path']]


def media_info(path,executable):
    tool=Path(executable).with_name('ffprobe.exe')
    if not tool.exists():tool=shutil.which('ffprobe') or 'ffprobe'
    info=json.loads(subprocess.check_output([str(tool),'-v','error','-show_format','-show_streams','-of','json',str(path)],timeout=15,creationflags=0x08000000))
    return info


def probe(path, executable):
    info=media_info(path,executable)
    videos=[s for s in info['streams'] if s['codec_type']=='video' and not s.get('disposition',{}).get('attached_pic')]
    if not videos:raise ValueError('Ce fichier ne contient pas de vidéo.')
    duration=float(videos[0].get('duration',info.get('format',{}).get('duration',0)))
    if not math.isfinite(duration) or duration<=0:raise ValueError('Durée vidéo inconnue ou invalide.')
    return duration,any(s['codec_type']=='audio' for s in info['streams'])


def probe_audio(path,executable):
    info=media_info(path,executable)
    streams=[s for s in info['streams'] if s['codec_type']=='audio']
    if not streams:raise ValueError('Ce fichier ne contient pas de son.')
    value=float(streams[0].get('duration',info.get('format',{}).get('duration',0)))
    if not math.isfinite(value) or value<=0:raise ValueError('Durée audio inconnue ou invalide.')
    return value


def length(clip):return clip['out']-clip['in']


def validate(clips,min_duration=1/30):
    if not isinstance(clips,list):raise ValueError('Timeline invalide.')
    ids=[]
    for clip in clips:
        if not isinstance(clip,dict):raise ValueError('Clip invalide.')
        if not isinstance(clip.get('id'),str) or not clip['id'] or clip['id'] in ids:raise ValueError('Identifiant de clip invalide ou dupliqué.')
        ids.append(clip['id'])
        if not isinstance(clip.get('audio'),bool):raise ValueError('Métadonnées audio invalides.')
        if type(clip.get('lane'))!=int or not 0<=clip['lane']<64:raise ValueError('Piste inconnue.')
        for key in ['start','in','out','duration','volume']:
            if not isinstance(clip[key],(int,float)) or not math.isfinite(clip[key]):raise ValueError('Valeur temporelle ou volume invalide.')
        if clip.get('kind') not in (None,'audio','image'):raise ValueError('Type de média inconnu.')
        if is_image(clip) and clip['audio']:raise ValueError('Une image ne contient pas de son.')
        if clip['duration']<=0 or clip['start']<0 or clip['in']<0 or length(clip)<min_duration-1e-8 or (not is_image(clip) and clip['out']>clip['duration']+.001) or not 0<=clip['volume']<=8:raise ValueError('Les durées ou le volume sont hors limites.')
        for fade in ('fade_in','fade_out'):
            value=clip.get(fade,0.)
            if not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=(max(clip['duration'],clip['out']) if is_image(clip) else clip['duration']):raise ValueError('Durée de fondu invalide.')
        if clip['fit'] not in ('Remplir','Contenir'):raise ValueError('Cadrage inconnu.')
        for key,default,low,high in [('zoom',1.,.25,4.),('pan_x',0.,-1.,1.),('pan_y',0.,-1.,1.)]:
            value=clip.get(key,default)
            if not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Zoom : 25 à 400 %, décalages : −100 à 100 %.')
        if not isinstance(clip['path'],str) or not clip['path']:raise ValueError('Chemin média invalide.')
        panorama.validate(clip)
    for lane in {lane for c in clips for lane in panorama.lanes(c)}:
        ordered=sorted((c for c in clips if lane in panorama.lanes(c)),key=lambda c:c['start'])
        for a,b in zip(ordered,ordered[1:]):
            if a['start']+length(a)>b['start']+.00001:raise ValueError('Deux clips se chevauchent sur la même piste. Déplacez ou raccourcissez le clip.')


def validate_audio(clips):
    if not isinstance(clips,list):raise ValueError('Pistes audio invalides.')
    converted=[]
    for c in clips:
        if not isinstance(c,dict) or c.get('kind')!='audio' or type(c.get('lane'))!=int or c['lane']<0:raise ValueError('Clip audio invalide.')
        # Reuse temporal and collision checks, separately for each audio lane.
        converted.append(dict(c,lane=0,audio=True,fit='Contenir'))
    for lane in {c['lane'] for c in clips}:validate([d for c,d in zip(clips,converted) if c['lane']==lane])
    if len({c['id'] for c in clips})!=len(clips):raise ValueError('Identifiant audio dupliqué.')


def validate_items(items):
    validate([c for c in items if c.get('kind')!='audio'])
    validate_audio([c for c in items if c.get('kind')=='audio'])
    if len({c['id'] for c in items})!=len(items):raise ValueError('Identifiant de clip dupliqué.')


def duration(clips):return max((c['start']+length(c) for c in clips),default=0)


def envelope(clip,audio=False,extra_offset=0.):
    """Evaluate fades in original clip time, including sliced playback windows."""
    fi=clip.get('fade_in',0.); fo=clip.get('fade_out',0.)
    if not fi and not fo:return ''
    offset=clip.get('_effect_offset',0.)+extra_offset
    d=clip.get('_effect_length',length(clip)); pts='asetpts' if audio else 'setpts'; effect='afade' if audio else 'fade'; alpha='' if audio else ':alpha=1'
    filters=[f'{pts}=PTS-STARTPTS+{offset:.9f}/TB']
    if fi:filters.append(f'{effect}=t=in:st=0:d={fi:.9f}{alpha}')
    if fo:filters.append(f'{effect}=t=out:st={max(0.,d-fo):.9f}:d={fo:.9f}{alpha}')
    filters.append(f'{pts}=PTS-STARTPTS')
    return ','.join(filters)+','


def audio_mix_args(clips,audio_clips,window=None):
    """Standalone mix for updating an open preview after a volume change."""
    validate_items(clips+audio_clips)
    total=duration(clips+audio_clips)
    if total<=0:raise ValueError('Le montage est vide.')
    sources=[c for c in clips if c.get('audio')]+audio_clips
    if window is not None:
        begin,end=window; total=end-begin
        if not 0<=begin<end:raise ValueError('Intervalle audio invalide.')
        sliced=[]
        for c in sources:
            first=max(begin,c['start']); last=min(end,c['start']+length(c))
            if last-first<.5/48000:continue
            source_in=c['in']+first-c['start']
            sliced.append(dict(c,start=first-begin,_effect_length=c.get('_effect_length',length(c)),_effect_offset=c.get('_effect_offset',0.)+first-c['start'],**{'in':source_in,'out':source_in+last-first}))
        sources=sliced
    inputs=[]; filters=[]; labels=[]
    for c in sources:
        if c['volume']<=0:continue
        source=c.get('_audio_path',c['path'])
        if not Path(source).is_file():raise ValueError('Audio introuvable : '+source)
        index=len(labels); name=f'a{index}'; labels.append(f'[{name}]')
        d=length(c); delay=round(c['start']*1000)
        inputs+=['-ss',f'{c["in"]:.9f}','-t',f'{d:.9f}','-i',source]
        filters.append(f'[{index}:a:0]asetpts=PTS-STARTPTS,atrim=duration={d:.6f},{envelope(c,True)}volume={c["volume"]:.8f},adelay={delay}:all=1[{name}]')
    if not labels:return ['-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(total)]
    ending=f'apad,atrim=duration={total:.6f}' if window is None else f'aresample=48000,apad,atrim=end_sample={round(total*48000)}'
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0:duration=longest,{ending}[mix]')
    return inputs+['-filter_complex',';'.join(filters),'-map','[mix]','-t',str(total)]


def snap_clip(clip,clips,mode,tolerance,extra_targets=()):
    """Snap the edited edge(s) to nearby clip boundaries on either lane."""
    targets={0.0}
    targets.update(extra_targets)
    for other in clips:
        if other['id']!=clip['id']:
            targets.update((other['start'],other['start']+length(other)))
    edges=[clip['start'],clip['start']+length(clip)] if mode=='move' else [clip['start'] if mode=='in' else clip['start']+length(clip)]
    candidates=sorted((abs(target-edge),target,edge) for target in targets for edge in edges if abs(target-edge)<=tolerance)
    for distance,target,edge in candidates:
        proposed=dict(clip); delta=target-edge
        if mode=='move':proposed['start']+=delta
        elif mode=='in':
            proposed['start']+=delta; proposed['in']=max(0.,clip['in']+delta) if is_image(clip) else clip['in']+delta
            proposed['out']=proposed['in']+length(clip)-delta
        else:proposed['out']+=delta
        # Do not magnetically create an illegal trim or same-lane collision.
        try:validate_items([proposed if c['id']==clip['id'] else c for c in clips])
        except ValueError:continue
        return proposed,target
    return clip,None


def render_args(clips,zones,folder,mask,graph,w=1280,h=720,still_at=None,audio_clips=None,window=None,playback=False):
    """Return input/filter/output arguments; both preview and MP4 use these."""
    validate(clips,min_duration=1/48000 if playback else 1/30)
    audio_clips=audio_clips or []; validate_audio(audio_clips)
    if any(lane>=len(zones) for c in clips for lane in panorama.lanes(c)):raise ValueError('Zone vidéo inexistante.')
    if not clips and not audio_clips and still_at is None and window is None:raise ValueError('Ajoutez au moins un média dans la timeline.')
    if still_at is not None:
        if not math.isfinite(still_at) or still_at<0:raise ValueError('Position de lecture invalide.')
        clips=[c for c in clips if c['start']<=still_at<c['start']+length(c)]
    total=.1 if still_at is not None else duration(clips+audio_clips)
    if window is not None:
        begin,end=window
        if not 0<=begin<end:raise ValueError('Intervalle de rendu invalide.')
        total=end-begin
        clips=[dict(c,start=c['start']-begin,_effect_length=c.get('_effect_length',length(c)),**{'out':min(c['out'],c['in']+end-c['start'])}) for c in clips]
    inputs=[]; filters=[]; audios=[]
    filters.append(f'color=black:s={w}x{h}:r=30:d={total:.6f},format=yuv420p[background]')
    previous='background'
    layers=[]
    for clip in clips:
        for part,(lane,view) in enumerate(panorama.views(clip,zones)):
            layers.append(dict(clip,lane=lane,_view=view,audio=clip.get('audio',False) and part==0))
    source_inputs={}; input_count=0
    for i,clip in enumerate(layers):
        if not Path(clip['path']).is_file():raise ValueError('Média introuvable : '+clip['path'])
        pgm=Path(folder)/f'mask-{i}.pgm'; mask(pgm,zones[clip['lane']],w,h)
        d=.1 if still_at is not None else length(clip); start=0 if still_at is not None else clip['start']
        seek=clip['in']+(still_at-clip['start'] if still_at is not None else 0)
        if clip['id'] not in source_inputs:
            index=input_count; input_count+=1
            inputs+=visual_input(clip,seek,d)
            count=len(panorama.lanes(clip))
            streams=[f'source{i}_{part}' for part in range(count)] if count>1 else [f'{index}:v']
            if count>1:filters.append(f'[{index}:v]split={count}'+''.join(f'[{name}]' for name in streams))
            source_inputs[clip['id']]=(index,streams)
        index,streams=source_inputs[clip['id']]; stream=streams.pop(0)
        mask_index=input_count; input_count+=1
        inputs+=['-loop','1','-t',f'{d:.9f}','-i',str(pgm)]
        options={} if clip['_view'] is None else dict(view=clip['_view'])
        text=graph(zones[clip['lane']],w,h,clip['fit'],clip.get('zoom',1.),clip.get('pan_x',0.),clip.get('pan_y',0.),**options)
        # Namespace the existing single-surface renderer without changing its geometry.
        def label(match):
            key=match.group(1)
            return f'[{stream}]' if key=='0:v' else f'[{mask_index}:v]' if key=='1:v' else f'[c{i}_{key}]'
        filters.append(re.sub(r'\[([^\]]+)\]',label,text))
        filters.append(f'[{mask_index}:v]format=gray[alpha{i}]')
        filters.append(f'[c{i}_out][alpha{i}]alphamerge,{envelope(clip,extra_offset=still_at-clip['start'] if still_at is not None else 0.)}trim=duration={d:.6f},setpts=PTS-STARTPTS+{start:.6f}/TB[layer{i}]')
        filters.append(f"[{previous}][layer{i}]overlay=eof_action=pass:repeatlast=0:enable='gte(t,{start:.6f})*lt(t,{start+d:.6f})'[mix{i}]")
        previous=f'mix{i}'
        if still_at is None and clip.get('audio') and clip['volume']>0:
            name=f'audio{i}'; delay=round(start*1000)
            filters.append(f'[{index}:a:0]asetpts=PTS-STARTPTS,atrim=duration={d:.6f},{envelope(clip,True)}volume={clip["volume"]:.6f},adelay={delay}:all=1[{name}]')
            audios.append(f'[{name}]')
    if still_at is None:
        for i,clip in enumerate(audio_clips):
            if not Path(clip['path']).is_file():raise ValueError('Audio introuvable : '+clip['path'])
            if clip['volume']<=0:continue
            index=input_count; input_count+=1
            d=length(clip); delay=round(clip['start']*1000); name=f'music{i}'
            inputs+=['-ss',str(clip['in']),'-t',str(d),'-i',clip['path']]
            filters.append(f'[{index}:a:0]asetpts=PTS-STARTPTS,atrim=duration={d:.6f},{envelope(clip,True)}volume={clip["volume"]:.6f},adelay={delay}:all=1[{name}]')
            audios.append(f'[{name}]')
    filters.append(f'[{previous}]format=yuv420p,setrange=limited[video]')
    maps=['-map','[video]']
    if audios:
        filters.append(''.join(audios)+f'amix=inputs={len(audios)}:normalize=0:duration=longest,apad,atrim=duration={total:.6f}[audio]')
        maps+=['-map','[audio]']
    else:maps+=['-an']
    # A second worker lets a longer audio tail advance after the video source ends.
    # Keep visual-only graphs serial and the mixed graph's worker count bounded.
    return inputs+['-filter_complex_threads','2' if audios else '1','-filter_complex',';'.join(filters)]+maps+['-t',str(total)]
