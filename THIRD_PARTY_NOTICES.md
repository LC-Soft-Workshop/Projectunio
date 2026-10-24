# Composants tiers de la version portable

Projectunio est distribué en ZIP portable pour Windows x64. `Projectunio.exe` est un lanceur : il démarre l’application depuis le dossier extrait et n’installe rien.

Les composants ci-dessous conservent leurs droits et licences propres. Ils ne sont pas la propriété de LC Software Workshop. Le dépôt public ne définit pas, à lui seul, une licence de réutilisation pour le code spécifique à Projectunio.

## Python, Tcl et Tk

La version portable embarque Python 3.15 et Tcl/Tk. Le texte des licences et les attributions livrés avec Python sont conservés dans `runtime/python/LICENSE.txt` et les fichiers de licence du runtime.

- Projet Python : https://www.python.org/
- Sources Python 3.15 : https://github.com/python/cpython/tree/3.15
- Licences Python et composants embarqués : https://docs.python.org/3/license.html
- Tcl/Tk : https://www.tcl.tk/software/tcltk/license.html

## FFmpeg et FFprobe

La version portable utilise les exécutables non modifiés de Gyan Doshi :

`2026-05-06-git-f2e5eff3ff-full_build-www.gyan.dev`

Cette compilation statique active `--enable-gpl` et `--enable-version3`. Elle est distribuée sous GNU GPL version 3 ; le texte est fourni dans `runtime/FFmpeg-LICENSE.txt`. Les bibliothèques incorporées conservent leurs attributions et licences propres.

- Projet et sources FFmpeg : https://ffmpeg.org/
- Révision correspondant aux exécutables : https://github.com/FFmpeg/FFmpeg/commit/f2e5eff3ff
- Archive des sources FFmpeg à cette révision : https://github.com/FFmpeg/FFmpeg/archive/f2e5eff3ff.zip
- Origine des exécutables et liste des bibliothèques : https://www.gyan.dev/ffmpeg/builds/
- Informations de licence : https://ffmpeg.org/legal.html

La version exacte, les bibliothèques activées et les options de compilation sont consultables avec `runtime/ffmpeg.exe -version` et `runtime/ffmpeg.exe -buildconf`. Le logiciel appelle ces exécutables comme processus séparés.

## Visuels

Le monogramme P de Projectunio a été créé pour ce projet avec un outil de génération d’images puis choisi par son auteur. Les icônes de la barre d’outils sont des dessins originaux produits par `generate_toolbar_icons.py` ; Pillow est nécessaire uniquement pour les régénérer, pas pour utiliser l’application.
