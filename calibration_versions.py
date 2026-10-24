"""Named calibration snapshots, with geometry validation and safe restore."""
import copy
from datetime import datetime,timezone
import uuid


def validate(versions):
    from app import valid
    if not isinstance(versions,list) or len(versions)>200:raise ValueError('Historique de calibration invalide (200 versions maximum).')
    ids=set()
    for version in versions:
        if not isinstance(version,dict) or not isinstance(version.get('id'),str) or version['id'] in ids or not isinstance(version.get('name'),str) or not version['name'].strip() or not isinstance(version.get('created'),str):raise ValueError('Version de calibration invalide.')
        ids.add(version['id']); zones=version.get('zones'); names=version.get('zone_names')
        if not isinstance(zones,list) or not 1<=len(zones)<=64 or not all(valid(q) for q in zones):raise ValueError('Géométrie de calibration invalide.')
        if not isinstance(names,list) or len(names)!=len(zones) or any(not isinstance(n,str) or not n.strip() for n in names):raise ValueError('Noms de calibration invalides.')


def snapshot(data,name):
    version=dict(id=uuid.uuid4().hex,name=name.strip(),created=datetime.now(timezone.utc).isoformat(),zones=copy.deepcopy(data['zones']),zone_names=list(data.get('zone_names',[f'Zone {i+1}' for i in range(len(data['zones']))])))
    validate([version]); return version


def restore(data,version):
    validate([version])
    if len(version['zones'])!=len(data['zones']):raise ValueError('Cette version comporte un autre nombre de zones. Utilisez un préréglage dans un projet séparé pour changer leur nombre.')
    result=copy.deepcopy(data); result['zones']=copy.deepcopy(version['zones']); result['zone_names']=list(version['zone_names']); return result


def format_version(data):
    if any(c.get('kind')=='image' for c in data.get('clips',[])):return 9
    if any(c.get('panorama',{}).get('gap_mode')=='auto' for c in data.get('clips',[])):return 8
    if data.get('calibration_versions'):return 6
    if any('panorama' in c for c in data.get('clips',[])):return 5
    return 4
