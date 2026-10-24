"""Package the self-contained runtime without development caches or user data."""
from pathlib import Path
import argparse
import hashlib
import re
import zipfile

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'dist'/'Projectunio-Portable-Windows-x64'
ARCHIVE=ROOT/'dist'/'Projectunio-Portable-Windows-x64.zip'
FILES=('app.py project_tabs.py display_geometry.py editor_controls.py preview.py montage.py timeline_ui.py windows_drop.py '
       'mapping_still.py live_audio.py render_job.py export_settings.py render_segments.py '
       'diagnostics.py studio.py clip_properties.py timeline_tools.py direct_preview.py project_transfer.py panorama.py panorama_dialog.py '
       'advanced_features.py render_cache.py media_relink.py audio_analysis.py projection_output.py calibration_versions.py '
       'work_media.py work_features.py source_comparison.py mapping_loupe.py zone_drawing.py mapping_interaction.py unsaved_dialog.py session_recovery.py '
       'toolbar.py Lancer.cmd README.md VERSION THIRD_PARTY_NOTICES.md Projectunio.exe assets/projectunio.ico assets/projectunio.png').split()
from toolbar import ICON_NAMES
FILES += ['assets/toolbar/'+name+suffix+'.png' for name in ICON_NAMES for suffix in ('','-active')]


def package(version=None):
    if version and not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?',version):raise ValueError('Version invalide.')
    target=ROOT/'dist'/f'Projectunio-{version}-Portable-Windows-x64.zip' if version else ARCHIVE
    required=FILES+['runtime/ffmpeg.exe','runtime/ffprobe.exe','runtime/FFmpeg-LICENSE.txt','runtime/python/python.exe','runtime/python/pythonw.exe','runtime/python/LICENSE.txt']
    missing=[name for name in required if not (SOURCE/name).is_file()]
    if missing:raise FileNotFoundError('Version portable incomplète : '+', '.join(missing))
    pending=target.with_suffix('.zip.partial')
    try:
        with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name in FILES:archive.write(SOURCE/name,'Projectunio-Portable/'+name)
            archive.write(ROOT/'PORTABLE-LIRE-MOI.txt','Projectunio-Portable/LIRE-MOI.txt')
            for path in sorted((SOURCE/'runtime').rglob('*')):
                relative=path.relative_to(SOURCE)
                if not path.is_file() or any(p in ('__pycache__','site-packages','test','tests','idle_test') for p in relative.parts):continue
                if path.suffix in ('.pyc','.pyo'):continue
                archive.write(path,'Projectunio-Portable/'+relative.as_posix())
        with zipfile.ZipFile(pending) as archive:
            if archive.testzip() is not None:raise ValueError('Archive endommagée.')
        pending.replace(target)
    finally:pending.unlink(missing_ok=True)
    with target.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    target.with_suffix('.zip.sha256').write_text(checksum+'  '+target.name+'\n',encoding='ascii')
    print(f'{target} ({target.stat().st_size/1024**2:.1f} Mo)')
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Créer un ZIP portable Projectunio, sans installeur.')
    parser.add_argument('--version'); args=parser.parse_args(); package(args.version)
