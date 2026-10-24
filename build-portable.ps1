$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$destination = Join-Path $projectRoot 'dist\Projectunio-Portable-Windows-x64'
& (Join-Path $projectRoot 'build-launcher.ps1')
New-Item -ItemType Directory -Force -Path "$destination\runtime\python" | Out-Null
$pythonRoot = Split-Path (Get-Command python).Source
foreach ($name in @('python.exe','pythonw.exe','python3.dll','python315.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt','DLLs','Lib','tcl')) {
    Copy-Item -LiteralPath (Join-Path $pythonRoot $name) -Destination "$destination\runtime\python" -Recurse -Force
}
Copy-Item -LiteralPath (Get-Command ffmpeg).Source -Destination "$destination\runtime\ffmpeg.exe" -Force
Copy-Item -LiteralPath (Get-Command ffprobe).Source -Destination "$destination\runtime\ffprobe.exe" -Force
$ffmpegRoot = Split-Path (Split-Path (Get-Command ffmpeg).Source)
if (Test-Path (Join-Path $ffmpegRoot 'LICENSE')) {
    Copy-Item -LiteralPath (Join-Path $ffmpegRoot 'LICENSE') -Destination "$destination\runtime\FFmpeg-LICENSE.txt" -Force
}
foreach ($name in @('app.py','project_tabs.py','display_geometry.py','editor_controls.py','preview.py','montage.py','timeline_ui.py','windows_drop.py','mapping_still.py','live_audio.py','render_job.py','export_settings.py','render_segments.py','diagnostics.py','studio.py','clip_properties.py','timeline_tools.py','direct_preview.py','project_transfer.py','panorama.py','panorama_dialog.py','advanced_features.py','render_cache.py','media_relink.py','audio_analysis.py','projection_output.py','calibration_versions.py','work_media.py','work_features.py','source_comparison.py','mapping_loupe.py','zone_drawing.py','mapping_interaction.py','unsaved_dialog.py','session_recovery.py','Lancer.cmd','README.md')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination $destination -Force
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'PORTABLE-LIRE-MOI.txt') -Destination (Join-Path $destination 'LIRE-MOI.txt') -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'Projectunio.exe') -Destination $destination -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'toolbar.py') -Destination $destination -Force
foreach ($document in @('VERSION','THIRD_PARTY_NOTICES.md')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $document) -Destination $destination -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $destination 'assets') | Out-Null
foreach ($asset in @('projectunio.ico','projectunio.png')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot "assets\$asset") -Destination (Join-Path $destination 'assets') -Force
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'assets\toolbar') -Destination (Join-Path $destination 'assets') -Recurse -Force
Write-Output "Version portable : $destination"




