"""Measure the unclipped floating-point mix in bounded memory."""
import array
import math
import os
import subprocess
import tempfile
import threading
import time
import montage


class AnalysisCancelled(Exception):pass


def _analyse_window(clips,audio,executable,cancel=None,progress=lambda value:None,window=None):
    cancel=cancel or threading.Event(); total=montage.duration(clips+audio)
    audible=any(c.get('audio') and c['volume']>0 for c in clips) or any(c['volume']>0 for c in audio)
    if not audible:return dict(peak=0.,db=None,gain=1.,ranges=[],duration=total)
    args=montage.audio_mix_args(clips,audio,window=window)
    with tempfile.TemporaryFile() as errors:
        proc=subprocess.Popen([executable,'-v','error',*args,'-vn','-ac','2','-ar','48000','-f','f32le','pipe:1'],stdout=subprocess.PIPE,stderr=errors,creationflags=0x08000000 if os.name=='nt' else 0)
        finished=threading.Event(); deadline=time.monotonic()+max(300,total*10)
        def watch():
            while not finished.wait(.05):
                if cancel.is_set() or time.monotonic()>deadline:
                    if proc.poll() is None:proc.terminate()
                    return
        watcher=threading.Thread(target=watch,daemon=True); watcher.start()
        peak=0.; offset=0; ranges=[]
        try:
            while True:
                if cancel.is_set():raise AnalysisCancelled()
                block=proc.stdout.read(4096*8)
                if not block:break
                values=array.array('f',block); value=max((abs(x) for x in values),default=0.)
                if not math.isfinite(value):raise ValueError('Le mixage contient un niveau sonore invalide.')
                end=(offset+len(values)//2)/48000
                if value>=.99:
                    begin=offset/48000
                    if ranges and begin-ranges[-1][1]<.1:ranges[-1][1]=end
                    elif len(ranges)<200:ranges.append([begin,end])
                peak=max(peak,value); offset+=len(values)//2; progress(min(total,end))
            code=proc.wait()
            if cancel.is_set():raise AnalysisCancelled()
            if code:
                errors.seek(0); raise ValueError('Analyse sonore impossible : '+errors.read().decode(errors='replace')[-600:])
            return dict(peak=peak,db=20*math.log10(peak) if peak else None,gain=min(1.,10**(-1/20)/peak) if peak else 1.,ranges=ranges,duration=offset/48000)
        finally:
            finished.set()
            if proc.poll() is None:proc.terminate()
            proc.wait(); proc.stdout.close(); watcher.join(1)


def analyse(clips,audio,executable,cancel=None,progress=lambda value:None):
    cancel=cancel or threading.Event()
    sources=[c for c in clips if c.get('audio') and c['volume']>0]+[c for c in audio if c['volume']>0]
    if len(sources)<=16:return _analyse_window(clips,audio,executable,cancel,progress)
    # Long montages do not open all their media at once. At a boundary only the
    # simultaneously audible clips are decoded, with the same fades and cuts.
    montage.validate_items(clips+audio); total=montage.duration(clips+audio)
    # Quantize boundaries to PCM samples, avoiding spurious sub-sample gaps
    # introduced by floating-point positions such as 0.4 + 0.8.
    boundaries=sorted({0,round(total*48000)}|{round(at*48000) for c in sources for at in (c['start'],c['start']+montage.length(c))})
    peak=0.; ranges=[]
    for first,last in zip(boundaries,boundaries[1:]):
        begin,end=first/48000,last/48000
        if cancel.is_set():raise AnalysisCancelled()
        if not any(c['start']<end and c['start']+montage.length(c)>begin for c in sources):progress(end); continue
        report=_analyse_window(clips,audio,executable,cancel,lambda at:progress(begin+at),window=(begin,end))
        peak=max(peak,report['peak'])
        for a,b in report['ranges']:
            a+=begin; b+=begin
            if ranges and a-ranges[-1][1]<.1:ranges[-1][1]=b
            elif len(ranges)<200:ranges.append([a,b])
    return dict(peak=peak,db=20*math.log10(peak) if peak else None,gain=min(1.,10**(-1/20)/peak) if peak else 1.,ranges=ranges,duration=total)


def describe(report):
    if report['db'] is None:return 'Le mixage est silencieux.'
    text=f'Crête mesurée : {report["db"]:+.2f} dBFS.\n'
    if report['peak']<.99:return text+'Aucun passage proche de la saturation détecté.'
    text+='Passages à contrôler : '+', '.join(f'{a:.2f}–{b:.2f} s' for a,b in report['ranges'][:20])
    return text+f'\nRéduction proposée : {20*math.log10(report["gain"]):.2f} dB, pour viser une crête à −1 dBFS.\nCette réduction préserve les équilibres ; elle ne répare pas une source déjà saturée.'
