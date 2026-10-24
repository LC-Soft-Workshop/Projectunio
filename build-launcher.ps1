$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
& $compiler /nologo /target:winexe /platform:anycpu /reference:System.Windows.Forms.dll "/win32icon:$projectRoot\assets\projectunio.ico" "/out:$projectRoot\Projectunio.exe" "$projectRoot\ProjectunioLauncher.cs"
if ($LASTEXITCODE -ne 0) { throw 'La compilation du lanceur Projectunio a échoué.' }
