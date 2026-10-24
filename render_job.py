"""Bounded sequential rendering, with isolated cancellation and tagged results."""
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import montage
from render_segments import plan
from export_settings import valid_resolution


class Cancelled(Exception):pass


class RenderJob:
    def __init__(self,events,executable,zones,clips,audio_clips,signature,mask,graph,write_mire,output_options,preview=False,mire=False,destination=None,log_directory=None,resolution=(1280,720),cache_directory=None):
        self.events=events; self.executable=executable; self.zones=zones; self.clips=clips; self.audio_clips=audio_clips
        self.signature=signature; self.preview=preview; self.mire=mire; self.destination=destination
        self.mask=mask; self.graph=graph; self.write_mire=write_mire; self.output_options=output_options
        self.cancelled=threading.Event(); self.lock=threading.Lock(); self.proc=None
        self.last_progress=time.monotonic(); self.last_position=-1; self.progress_warning=False
        if not valid_resolution(resolution):raise ValueError('Résolution d’export inconnue.')
        self.width,self.height=resolution; self.mask_cache={}; self.encoded_segments=0; self.reused_segments=0
        self.log_directory=log_directory; self.log_path=None
        from render_cache import RenderCache,DEFAULT
        self.disk_cache=RenderCache(cache_directory if cache_directory is not None else DEFAULT)
        self.disk_reused=0; self.review_audio=False; self.audio_decision=threading.Event(); self.audio_gain=1.
        self.thread=threading.Thread(target=self.run,daemon=True)

    def check(self):
        if self.cancelled.is_set():raise Cancelled()

    def cancel(self):
        with self.lock:self.cancelled.set(); proc=self.proc
        if proc and proc.poll() is None:
            try:proc.terminate()
            except OSError:pass

    def checked_mask(self,path,q,w,h):
        self.check(); key=json.dumps([q,w,h]); cached=self.mask_cache.get(key)
        if cached is not None:shutil.copyfile(cached,path); return
        self.mask(path,q,w,h); self.check()
        cached=Path(path).parent/f'mask-cache-{len(self.mask_cache)}.pgm'
        shutil.copyfile(path,cached); self.mask_cache[key]=cached

    def stalled(self):
        proc=self.proc
        return proc is not None and proc.poll() is None and time.monotonic()-self.last_progress>45

    def execute(self,stage,args,output,options):
        self.check(); self.events.put((self,'progress',stage)); logging.info('Rendu : %s',stage)
        with self.log_path.open('a',encoding='utf-8') as log:
            log.write('\n=== '+stage+' ===\n'); log.flush()
            proc=subprocess.Popen([self.executable,'-hide_banner','-nostdin','-y',*args,*options,'-progress','pipe:1','-nostats',str(output)],stdout=subprocess.PIPE,stderr=log,text=True,creationflags=0x08000000 if os.name=='nt' else 0)
            with self.lock:
                self.proc=proc; self.last_position=-1; self.last_progress=time.monotonic()
                if self.cancelled.is_set():proc.terminate()
            try:
                for line in proc.stdout:
                    if line.startswith('out_time_us='):
                        try:position=int(line.strip().split('=',1)[1])
                        except ValueError:position=-1
                        if position>self.last_position:self.last_position=position; self.last_progress=time.monotonic()
                    if line.startswith('out_time='):self.events.put((self,'progress',stage+' — '+line.strip().split('=',1)[1]))
                code=proc.wait()
            finally:
                if proc.poll() is None:proc.terminate(); proc.wait()
                proc.stdout.close()
                with self.lock:self.proc=None
            self.check()
            if code:raise RuntimeError(f'Échec de l’étape « {stage} ». Journal : {self.log_path}')

    def compose(self,folder,movie):
        for c in self.clips+self.audio_clips:
            if not Path(c['path']).is_file():raise ValueError('Média introuvable : '+c['path'])
        segments=plan(self.clips,self.audio_clips); cache={}; playlist=[]; intermediates=[]
        from render_cache import digest,renderer_signature
        self.events.put((self,'progress','Vérification du cache des séquences…'))
        fingerprints={path:digest(path,self.check) for path in {c['path'] for c in self.clips}}
        source_stats={path:(Path(path).stat().st_size,Path(path).stat().st_mtime_ns) for path in fingerprints}
        def unchanged():
            for path,expected in source_stats.items():
                stat=Path(path).stat()
                if (stat.st_size,stat.st_mtime_ns)!=expected:raise ValueError('Média modifié pendant le rendu : '+path)
        renderer=renderer_signature(self.executable,self.graph,self.output_options(False),self.mask)
        for i,segment in enumerate(segments):
            self.check(); unchanged(); key=segment.key()
            if key not in cache:
                part=folder/f'part-{len(cache):04d}.mp4'
                disk_key=self.disk_cache.key(segment,self.zones,(self.width,self.height),renderer,fingerprints)
                if self.disk_cache.restore(disk_key,part,self.check):
                    self.disk_reused+=1; self.events.put((self,'progress',f'Vidéo {i+1}/{len(segments)} — cache d’un précédent export'))
                else:
                    args=montage.render_args(segment.clips,self.zones,folder,self.checked_mask,self.graph,self.width,self.height,window=segment.window)
                    self.execute(f'Vidéo {i+1}/{len(segments)}',args,part,[*self.output_options(False),'-an','-frames:v',str(segment.frames)])
                    unchanged(); self.encoded_segments+=1; self.disk_cache.store(disk_key,part,self.check)
                cache[key]=part; intermediates.append(part)
            else:
                self.reused_segments+=1; self.events.put((self,'progress',f'Vidéo {i+1}/{len(segments)} — séquence déjà calculée'))
            playlist.extend([f"file '{cache[key].name}'",f'duration {segment.frames/30:.12f}'])
        listing=folder/'video-list.txt'; listing.write_text('\n'.join(playlist)+'\n',encoding='utf-8'); intermediates.append(listing)
        has_audio=any(c.get('audio') and c['volume']>0 for c in self.clips) or any(c['volume']>0 for c in self.audio_clips)
        args=['-f','concat','-safe','1','-i',str(listing)]; total=segments[-1].last/30
        if has_audio:
            sources=sum(c.get('audio',False) and c['volume']>0 for c in self.clips)+sum(c['volume']>0 for c in self.audio_clips)
            if sources>4:
                audio_playlist=[]
                for i,segment in enumerate(segments):
                    sound=folder/f'audio-{i:04d}.wav'; intermediates.append(sound)
                    mix=montage.audio_mix_args(self.clips,self.audio_clips,window=segment.window)
                    self.execute(f'Mixage audio {i+1}/{len(segments)}',mix,sound,['-vn','-ar','48000','-ac','2','-c:a','pcm_s16le'])
                    audio_playlist.append(f"file '{sound.name}'")
                audio_list=folder/'audio-list.txt'; audio_list.write_text('\n'.join(audio_playlist)+'\n',encoding='utf-8'); intermediates.append(audio_list)
                args+=['-f','concat','-safe','1','-i',str(audio_list)]
            else:
                sound=folder/'mix.wav'; intermediates.append(sound)
                self.execute('Mixage audio',montage.audio_mix_args(self.clips,self.audio_clips),sound,['-vn','-ar','48000','-ac','2','-c:a','pcm_s16le'])
                args+=['-i',str(sound)]
            args+=['-map','0:v:0','-map','1:a:0','-af','apad','-t',str(total)]
            options=['-c:v','copy','-c:a','aac','-b:a','160k','-movflags','+faststart']
        else:
            args+=['-map','0:v:0','-t',str(total)]; options=['-c:v','copy','-an','-movflags','+faststart']
        self.execute('Assemblage MP4',args,movie,options)
        for path in intermediates:path.unlink(missing_ok=True)

    def run(self):
        owner=None; pending=None
        try:
            from project_transfer import check_media,check_resources
            data=dict(clips=self.clips,audio_clips=self.audio_clips,resolution=(self.width,self.height))
            self.events.put((self,'progress','Vérification des médias et de l’espace disque…'))
            if not self.mire:check_media(data,self.executable,self.check)
            check_resources(data,self.destination,self.preview,self.mire)
            if self.review_audio and not self.preview and not self.mire:
                from audio_analysis import analyse
                self.events.put((self,'progress','Analyse sonore avant export…'))
                report=analyse(self.clips,self.audio_clips,self.executable,self.cancelled)
                if report['peak']>=.99:
                    self.events.put((self,'audio_warning',report))
                    while not self.audio_decision.wait(.1):self.check()
                    self.check()
                    for clip in self.clips+self.audio_clips:clip['volume']*=self.audio_gain
            self.check(); owner=tempfile.TemporaryDirectory(prefix='projectunio-render-'); folder=Path(owner.name)
            log_folder=Path(self.log_directory) if self.log_directory else folder
            try:log_folder.mkdir(parents=True,exist_ok=True)
            except OSError:log_folder=folder
            self.log_path=log_folder/f'render-{uuid.uuid4().hex[:12]}.log'
            movie=folder/'result.mp4'
            if self.mire:
                image=folder/'mire.ppm'; self.write_mire(image,self.zones,self.width,self.height)
                self.execute('Mire USB',['-loop','1','-i',str(image),'-t','8','-an'],movie,self.output_options(False))
            else:self.compose(folder,movie)
            if self.preview:
                self.check(); self.events.put((self,'ready',(movie,owner))); owner=None
            else:
                destination=Path(self.destination); pending=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.partial')
                with movie.open('rb') as source,pending.open('wb') as target:
                    while True:
                        self.check(); chunk=source.read(1024*1024)
                        if not chunk:break
                        target.write(chunk)
                with self.lock:self.check(); os.replace(pending,destination)
                pending=None; self.events.put((self,'complete',str(destination)))
        except Cancelled:self.events.put((self,'cancelled',None))
        except Exception as e:self.events.put((self,'cancelled' if self.cancelled.is_set() else 'error',str(e)))
        finally:
            with self.lock:self.proc=None
            if owner:owner.cleanup()
            if pending:
                try:pending.unlink(missing_ok=True)
                except OSError:pass
