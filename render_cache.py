"""Disposable, bounded persistent video cache. Originals are never removed."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import uuid

LOCK=threading.RLock()
DEFAULT=Path(__file__).resolve().parent/'render-cache'


def digest(path,check=lambda:None):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while True:
            check(); block=stream.read(1024*1024)
            if not block:break
            result.update(block)
    return result.hexdigest()


def renderer_signature(executable,graph,options,mask=None):
    import montage,panorama
    tool=Path(shutil.which(str(executable)) or executable)
    stat=tool.stat()
    sources=[Path(montage.__file__).read_bytes(),Path(panorama.__file__).read_bytes()]
    try:sources.append(inspect.getsource(graph).encode())
    except (TypeError,OSError):sources.append(repr(graph).encode())
    if mask is not None:
        try:sources.append(inspect.getsource(mask).encode())
        except (TypeError,OSError):sources.append(repr(mask).encode())
    return hashlib.sha256(b''.join(sources)+repr((str(tool.resolve()),stat.st_size,stat.st_mtime_ns,options)).encode()).hexdigest()


class RenderCache:
    def __init__(self,root=DEFAULT,limit=2*1024**3):
        self.root=Path(root); self.limit=limit

    def key(self,segment,zones,resolution,renderer,fingerprints):
        # Only used zones invalidate a segment, so changing another zone preserves it.
        import panorama
        lanes=sorted({lane for c in segment.clips for lane in panorama.lanes(c)})
        payload=[1,segment.key(),[(lane,zones[lane]) for lane in lanes],resolution,renderer,
                 {c['path']:fingerprints[c['path']] for c in segment.clips}]
        return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

    def files(self):
        if not self.root.exists():return []
        return [p for p in self.root.iterdir() if re.fullmatch(r'[0-9a-f]{64}\.mp4',p.name) and p.is_file() and not p.is_symlink()]

    def restore(self,key,target,check=lambda:None):
        try:
            with LOCK:
                movie=self.root/(key+'.mp4'); meta=self.root/(key+'.json')
                info=json.loads(meta.read_text(encoding='utf-8'))
                if movie.stat().st_size!=info['size'] or digest(movie,check)!=info['sha256']:return False
                check(); shutil.copyfile(movie,target); movie.touch(); return True
        except (OSError,ValueError,KeyError):return False

    def store(self,key,source,check=lambda:None):
        size=Path(source).stat().st_size
        if size>self.limit:return
        try:
            with LOCK:
                self.root.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='pending-',dir=self.root) as folder:
                    movie=Path(folder)/'part.mp4'; shutil.copyfile(source,movie)
                    info=dict(size=size,sha256=digest(movie,check))
                    meta=Path(folder)/'part.json'; meta.write_text(json.dumps(info),encoding='utf-8')
                    check(); os.replace(movie,self.root/(key+'.mp4')); os.replace(meta,self.root/(key+'.json'))
                files=sorted(self.files(),key=lambda p:p.stat().st_mtime_ns); total=sum(p.stat().st_size for p in files)
                for path in files:
                    if total<=self.limit:break
                    total-=path.stat().st_size; path.unlink(); path.with_suffix('.json').unlink(missing_ok=True)
        except OSError:pass  # An unavailable cache never prevents an export.

    def usage(self):
        files=self.files(); total=0; count=0
        for path in files:
            try:total+=path.stat().st_size; count+=1
            except FileNotFoundError:pass
        return count,total

    def clear(self):
        with LOCK:
            for path in self.files():path.unlink(); path.with_suffix('.json').unlink(missing_ok=True)
