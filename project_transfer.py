"""Self-contained project copies and render resource checks."""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import montage


def resource_estimate(data, preview=False, mire=False):
    """Conservative working-space budget, not a promise of encoded size."""
    seconds=8. if mire else montage.duration(data.get('clips',[])+data.get('audio_clips',[]))
    w,h=(1280,720) if preview else data['resolution']
    movie=math.ceil(seconds*(4_000_000*w*h/(1280*720)+160_000)/8*2)
    pcm=math.ceil(seconds*192000)
    temporary=3*movie+2*pcm+64*1024**2
    return temporary,movie


def check_resources(data, destination=None, preview=False, mire=False):
    temporary,movie=resource_estimate(data,preview,mire)
    scratch=Path(tempfile.gettempdir())
    if shutil.disk_usage(scratch).free<temporary:
        raise ValueError(f'Espace temporaire insuffisant : prévoir environ {temporary/1024**2:.0f} Mo dans {scratch}.')
    if destination:
        dest=Path(destination).resolve()
        if not dest.parent.is_dir():raise ValueError('Le dossier de destination n’existe pas.')
        if any(Path(c['path']).resolve()==dest for c in data.get('clips',[])+data.get('audio_clips',[])):
            raise ValueError('La destination est un média source : choisissez un autre fichier.')
        if dest.exists() and not dest.is_file():raise ValueError('La destination n’est pas un fichier.')
        required=movie+(temporary if dest.drive.lower()==scratch.resolve().drive.lower() else 0)
        if shutil.disk_usage(dest.parent).free<required:
            raise ValueError(f'Espace insuffisant à destination : prévoir environ {required/1024**2:.0f} Mo.')
        # Test the directory using a separate file; never truncate an existing export.
        with tempfile.TemporaryFile(dir=dest.parent):pass
        if dest.exists():
            with dest.open('r+b'):pass
    return temporary,movie


def check_media(data, executable, check=lambda:None):
    montage.validate_items(data.get('clips',[])+data.get('audio_clips',[]))
    cache={}
    for clip in data.get('clips',[])+data.get('audio_clips',[]):
        check(); path=Path(clip['path'])
        if not path.is_file():raise ValueError('Média introuvable : '+str(path))
        if montage.is_image(clip):
            image_key=(str(path),'image')
            if image_key not in cache:cache[image_key]=montage.probe_image(path,executable)
            continue
        key=(str(path),clip.get('kind')=='audio')
        if key not in cache:
            cache[key]=(montage.probe_audio(path,executable),True) if key[1] else montage.probe(path,executable)
        duration,audio=cache[key]
        if clip['out']>duration+.001:raise ValueError('Média trop court pour les coupes : '+str(path))
        if clip.get('audio') and not audio:raise ValueError('Son attendu absent : '+str(path))


def gather_project(data, destination, progress=lambda value:None):
    """Publish a new directory only once all sources and JSON are copied."""
    dest=Path(destination)
    if dest.exists():raise ValueError('Choisissez un nouveau dossier pour le regroupement.')
    from calibration_versions import format_version
    saved=copy.deepcopy(data); saved['version']=format_version(saved)
    sources={}
    for clip in saved.get('clips',[])+saved.get('audio_clips',[]):
        source=Path(clip['path']).resolve()
        if not source.is_file():raise ValueError('Média introuvable : '+str(source))
        sources.setdefault(source,None)
    needed=sum(p.stat().st_size for p in sources)+1024**2
    if shutil.disk_usage(dest.parent).free<needed:raise ValueError('Espace insuffisant pour copier les médias.')
    with tempfile.TemporaryDirectory(prefix='.projectunio-transfer-',dir=dest.parent) as folder:
        stage=Path(folder)/'projet'; media=stage/'medias'; media.mkdir(parents=True)
        for index,source in enumerate(sources,1):
            name=f'{index:04d}-{source.name}'
            progress(f'Copie {index}/{len(sources)} : {source.name}')
            shutil.copy2(source,media/name); sources[source]='medias/'+name
        for clip in saved.get('clips',[])+saved.get('audio_clips',[]):clip['path']=sources[Path(clip['path']).resolve()]
        (stage/'installation.projectunio.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
        os.rename(stage,dest)
    return dest/'installation.projectunio.json'
