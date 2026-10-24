# Développement et publication

Ce dépôt est réservé à Projectunio. Les projets utilisateur, médias, journaux, sauvegardes de récupération, caches, runtimes locaux et fichiers de distribution sont exclus de Git.

## Développement Windows

- Python 3.15 avec Tkinter.
- FFmpeg et FFprobe dans le PATH, ou dans `runtime/`.
- Lancer : `python app.py`.
- Les dépendances de l’application sont celles de la bibliothèque standard Python ; Pillow ne sert qu’à régénérer les icônes.

Pour les tests, utiliser des dossiers temporaires distincts de ceux des projets réels :

```powershell
New-Item -ItemType Directory -Force test-output | Out-Null
$env:TEMP = (Resolve-Path test-output).Path
$env:TMP = $env:TEMP
$env:PROJECTUNIO_RECOVERY_DIR = Join-Path $env:TEMP 'test-recovery'
python -m unittest discover -p 'test_*.py'
```

## Version portable

1. Mettre à jour `VERSION` et `CHANGELOG.md`.
2. Exécuter `build-portable.ps1` sur Windows x64 ; le script prépare le dossier autonome et compile le lanceur avec .NET Framework.
3. Exécuter `python package_portable.py --version 0.1.0`.
4. Vérifier le ZIP avec `python verify_portable_package.py dist/Projectunio-0.1.0-Portable-Windows-x64.zip`.
5. Joindre le ZIP et son empreinte SHA-256 à une version GitHub, avec les notices et sources des composants tiers applicables.

Le dossier `dist/` reste local. Les téléchargements utilisateurs sont les ZIP portables des versions GitHub, jamais un installeur ni le ZIP automatique des seules sources du dépôt.
