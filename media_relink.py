"""Find candidates without silently resolving duplicate filenames."""
import copy
import os
from pathlib import Path
import montage


def find_candidates(missing,folder,check=lambda:None,progress=lambda value:None):
    names={Path(path).name.casefold() for path in missing}; index={name:[] for name in names}; unreadable=[]
    def error(value):unreadable.append(str(value.filename))
    for root,dirs,files in os.walk(folder,followlinks=False,onerror=error):
        check(); progress(root); dirs[:]=[name for name in dirs if not Path(root,name).is_symlink()]
        for name in files:
            if name.casefold() in index:index[name.casefold()].append(str(Path(root,name).resolve()))
    return {path:sorted(index[Path(path).name.casefold()]) for path in missing},unreadable


def replacements(data,choices,executable,check=lambda:None):
    result=copy.deepcopy(data); probes={}
    for clip in result.get('clips',[])+result.get('audio_clips',[]):
        old=clip['path']
        if old not in choices:continue
        check(); path=str(Path(choices[old]).resolve())
        if montage.is_image(clip):
            key=(path,'image')
            if key not in probes:probes[key]=montage.probe_image(path,executable)
            clip['path']=path; continue
        audio=clip.get('kind')=='audio'; key=(path,audio)
        if key not in probes:probes[key]=(montage.probe_audio(path,executable),True) if audio else montage.probe(path,executable)
        duration,has_audio=probes[key]
        if duration+.001<clip['out']:raise ValueError('Fichier trop court : '+path)
        if clip.get('audio') and not has_audio:raise ValueError('Son attendu absent : '+path)
        clip['path']=path; clip['duration']=duration
    montage.validate_items(result.get('clips',[])+result.get('audio_clips',[])); return result
