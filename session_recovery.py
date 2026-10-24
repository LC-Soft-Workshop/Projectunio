"""Atomic rolling session snapshots, independent from original project files."""
import json
import os
from pathlib import Path
from datetime import datetime,timezone


def process_alive(pid):
    if not isinstance(pid,int) or pid<=0:return False
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return False
        try:
            code=ctypes.c_ulong(); return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0); return True
    except OSError:return False


def interrupted_sessions(folder):
    result=[]
    for path in Path(folder).glob('session-*.json'):
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            if data.get('state')=='running' and data.get('dirty',True) and data.get('projects') and not process_alive(data.get('pid')):result.append(path)
        except (OSError,ValueError,TypeError,AttributeError):continue
    return sorted(result,key=lambda p:p.stat().st_mtime,reverse=True)


def store(path,payload,atomic,keep=10):
    path=Path(path); now=datetime.now(timezone.utc)
    data=dict(payload,updated=now.isoformat(),pid=os.getpid())
    atomic(path,data)
    history=path.parent/'history'/path.stem
    history.mkdir(parents=True,exist_ok=True)
    target=history/(now.strftime('%Y%m%d-%H%M%S-%f')+'.json')
    atomic(target,data)
    for old in sorted(history.glob('*.json'),reverse=True)[keep:]:old.unlink()
    return data['updated']


def settings(folder):
    try:
        data=json.loads((Path(folder)/'settings.json').read_text(encoding='utf-8'))
        if type(data['enabled'])==bool and data['interval'] in (15,30,60,120):return data
    except (OSError,ValueError,KeyError,TypeError):pass
    return dict(enabled=True,interval=15)
