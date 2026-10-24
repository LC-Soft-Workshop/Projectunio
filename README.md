# Projectunio — mapping et montage multizone

**Windows x64 · ZIP portable · Sans installeur**

[Télécharger la version portable](https://github.com/LC-Soft-Workshop/Projectunio/releases/latest) · [Historique](CHANGELOG.md) · [Développement](CONTRIBUTING.md) · [Composants tiers](THIRD_PARTY_NOTICES.md)

Pour utiliser le logiciel, télécharger le **ZIP portable** dans les versions GitHub, l’extraire entièrement, puis ouvrir **Projectunio.exe**. Les archives « Source code » proposées automatiquement par GitHub contiennent les sources de développement et pas le runtime portable.

Application portable Windows 11 x64 — LC Soft Workshop. Projectunio permet de calibrer des surfaces de projection, monter des vidéos et des sons, répartir une vidéo panoramique sur plusieurs vantaux, puis projeter le montage en HDMI ou exporter un MP4 pour la lecture USB.

Les projets utilisent un canevas 16:9, jusqu’à 64 zones vidéo et 64 pistes audio. Les zones sont des quadrilatères convexes ; les formes à plus de quatre coins ne sont pas prises en charge. Le rendu fonctionne sur CPU. La compatibilité USB et la fluidité HDMI doivent être vérifiées sur le projecteur et le portable réels.

## Lancer et transférer l’application

Double-cliquer sur **Projectunio.exe**, reconnaissable au P blanc, bleu et violet, dans `dist/Projectunio-Portable-Windows-x64`. **Lancer.cmd** reste utilisable. Copier tout ce dossier pour utiliser l’application sur un autre ordinateur : lanceur, sources, dossiers `assets` et `runtime`, et licences. Python/Tkinter et FFmpeg/FFprobe sont inclus ; aucun environnement de développement ni droit administrateur n’est requis. Fermer l’application avant de remplacer une ancienne copie.

Pour travailler depuis une clé USB, copier de préférence l’application et les médias sur le disque du portable. Le dossier de l’application doit être accessible en écriture pour la récupération, les journaux et le cache. Les rendus utilisent aussi le dossier temporaire Windows.

En développement : `python app.py` avec Python/Tkinter et FFmpeg/FFprobe disponibles. `build-portable.ps1` actualise le dossier portable depuis le Python 3.15 x64 de la machine. `python package_portable.py --version 0.1.0` crée ensuite le ZIP de distribution et son empreinte SHA-256. Aucun installeur n’est produit.

## Projets et enregistrement

Chaque projet s’ouvre dans un onglet indépendant. Le bouton **+** après les onglets ou **Projets → Nouveau projet** crée Installation 1, Installation 2, etc. Modifier le champ Installation renomme l’onglet. La croix ferme l’onglet et propose d’enregistrer s’il a été modifié ; fermer le dernier onglet crée un nouveau projet vide.

**Enregistrer** conserve le mapping, les clips vidéo et audio, les noms, les repères, la résolution, les verrous et les versions de calibration. La sauvegarde est atomique ; un fichier `.bak` conserve l’état précédent. Les médias sont référencés par des chemins relatifs lorsque possible ; ils ne sont pas incorporés au JSON.

Les formats 1 à 9 sont lisibles. Les projets classiques s’enregistrent au format 4 ; ceux contenant un panoramique manuel au format 5 ; ceux contenant des versions de calibration au format 6 ; ceux contenant un panoramique automatique en deux dimensions au format 8 ; ceux contenant des images au format 9. Les panoramiques automatiques du format 7 utilisent désormais aussi la disposition 2D. Utiliser cette version de l’application pour ouvrir les formats récents.

Une copie de récupération de tous les projets ouverts est écrite toutes les quinze secondes par défaut, lorsqu’il y a des changements, et avant une fermeture normale. Les fichiers sont remplacés de manière atomique pour conserver la dernière copie valide en cas d’interruption. Les dix dernières versions sont conservées par session, en plus de la copie principale, dans `recovery/history`.

**Projets → Sauvegardes automatiques…** permet d’activer la protection, de choisir 15, 30, 60 ou 120 secondes, de consulter les versions datées, de créer une copie immédiatement et de récupérer la sélection. Les réglages sont conservés pour les prochains lancements. Après une fermeture anormale avec des modifications non enregistrées, un bandeau au démarrage propose de récupérer la session ou de consulter les sauvegardes. Une session encore ouverte dans une autre instance ne déclenche pas ce bandeau.

**Projets → Récupérer une session** permet aussi de choisir directement un fichier. La récupération ouvre les projets dans de nouveaux onglets sans remplacer les projets déjà ouverts ni leurs fichiers. Elle conserve le mapping, le montage, les réglages et le curseur ; elle ne copie pas les médias. Les projets récupérés sont proposés à l’enregistrement. La protection couvre l’état de la dernière copie réussie ; les changements plus récents peuvent être perdus lors d’un plantage. Elle ne remplace pas l’enregistrement habituel ni une copie externe des médias.

À la fermeture de l’application ou d’un onglet, seuls les projets comportant des modifications non enregistrées déclenchent une demande. Un projet vierge inchangé, un document ouvert sans modification ou un projet revenu à son état initial avec Annuler ne déclenche aucune demande. **Enregistrer** sauvegarde les projets modifiés, en demandant un emplacement uniquement pour ceux qui n’en ont pas encore ; **Fermer sans enregistrer** quitte sans modifier leurs fichiers ; **Annuler** conserve les onglets ouverts. Annuler le choix d’un emplacement ou rencontrer une erreur d’enregistrement interrompt la fermeture ; les projets déjà enregistrés le restent.

## Préparer le projecteur

Brancher HDMI, choisir **Windows + P → Étendre**, puis sélectionner l’écran du projecteur dans Projectunio. **Actualiser écrans** relit la configuration Windows ; l’ouverture d’une mire ou d’une projection animée actualise aussi cette liste. Les positions et dimensions utilisent les pixels physiques, avec prise en charge des écrans ayant des mises à l’échelle différentes.

La liste affiche le mode Windows actif, pas une résolution native garantie du projecteur. Projectunio ne change pas les modes vidéo Windows. Le format d’export MP4 est indépendant du mode HDMI. Sur un écran autre que 16:9, l’image est centrée avec des bandes noires.

**Mire HDMI** affiche les zones et les repères de calibration. **Image HDMI** affiche l’image arrêtée choisie dans la timeline. Un second clic sur le même bouton ferme la sortie ; cliquer sur l’autre bouton change le contenu affiché. **Échap** ferme aussi la sortie correspondante. La case **Grille des mires HDMI / USB** agit sur la mire HDMI et les prochains MP4 de mire USB ; la grille du canevas est un réglage séparé.

## Dessiner et ajuster le mapping

La barre d’outils à icônes se trouve au-dessus du mapping. Elle regroupe les fichiers et l’annulation, les modes Mapping / Position vidéo / Dessin, les grilles, le panoramique, la comparaison source/répartition, la lecture directe, les trois verrous et les sorties HDMI. Survoler une icône ou lui donner le focus au clavier affiche son nom et ses raccourcis. Le bleu et l’état enfoncé signalent un mode ou une option activée ; les cadenas ouverts ou fermés distinguent les verrous. Les menus conservent les commandes détaillées. Le panoramique et la comparaison s’ouvrent désormais depuis cette barre ; les options propres à la timeline restent près des pistes.

L’outil **Mapping** permet de déplacer un coin, une arête ou toute une zone. L’icône **Dessiner une zone**, également accessible dans Mapping, demande quatre coins : ils sont remis dans un ordre convexe à la validation, même si vous avez cliqué les coins du bas dans l’ordre inverse. Si le quatrième point ne permet pas une zone convexe, les trois premiers restent visibles pour réessayer. **Retour arrière** retire le dernier point ; **clic droit ou Échap** annule tout le dessin, sans créer de zone. Les formes dégénérées, les points intérieurs et les coins hors du canevas sont refusés.

Le pointeur devient une croix pendant le dessin. En édition, maintenir le clic permet de glisser un coin, une arête ou une zone, même si la souris sort du canevas : la sélection reste limitée aux bords, sans magnétisme, et repart dès que la souris revient. Un clic bref sur un coin ou une arête l’attache à la souris sans maintenir le bouton ; le clic suivant le dépose. **Échap** arrête ce suivi à la position actuelle. Une opération correspond à une seule étape d’annulation. La forme reste convexe pendant le déplacement.

- Glisser un rond déplace un coin ; glisser une arête déplace ses deux coins ; glisser à l’intérieur déplace toute la zone.
- Flèches : un pixel dans la résolution d’export choisie ; Maj + flèches : dix pixels.
- Double-cliquer sur un coin ouvre sa saisie X/Y en pourcentage.
- **Grille** affiche ou masque les lignes internes sans masquer les contours et les poignées.
- Double-cliquer sur le nom d’une zone dans la timeline permet de la renommer sur place : Entrée ou clic ailleurs valide, Échap annule. Un nom vide conserve l’ancien.

Les menus Mapping permettent aussi d’ajouter, dupliquer ou supprimer des zones. La suppression d’une zone contenant des clips demande confirmation. Si un clip panoramique utilise cette zone, il est retiré de toutes ses zones ; Annuler le restaure. Au moins une zone doit être conservée.

**Mapping → Loupe du mapping** agrandit le coin sélectionné à ×4, ×8 ou ×16. Cet outil de précision reste dans le menu et n’occupe plus la barre principale. Le repère et les coordonnées suivent les ajustements. Les flèches dans cette fenêtre déplacent le coin d’un pixel de sortie, ou de dix avec Maj, en respectant les verrous. La loupe est une aide de travail et ne figure pas dans l’export.

**Enregistrer / Charger un préréglage** échange le mapping et les noms dans un fichier séparé. Un préréglage incompatible avec les pistes utilisées est refusé. Le ratio logique de cadrage reste estimé d’après les bords des quadrilatères : contrôler visuellement l’image après une modification de géométrie.

## Conserver et comparer des calibrations

Ouvrir **Mapping → Versions de calibration…**, puis **Enregistrer l’actuelle…** et donner un nom, par exemple HDMI validé ou Essai USB.

Sélectionner une version pour comparer ses contours jaunes pointillés aux contours bleus de la calibration actuelle. La comparaison ne modifie pas le projet. **Restaurer la sélection** applique les coins et les noms en conservant le montage, ses cadrages et la résolution d’export ; l’opération est annulable. La version doit comporter le même nombre de zones que le projet actuel.

Les versions peuvent être renommées ou supprimées ; ces actions sont annulables. Elles sont enregistrées dans le projet et dans la récupération de session. La limite est de 200 versions par projet. Les dates affichées sont en UTC.

## Importer et monter des médias

Déposer les fichiers depuis l’Explorateur sur la piste vidéo ou audio souhaitée. La position du dépôt définit le début du premier clip ; les fichiers multiples sont ajoutés à la suite, dans les espaces disponibles. Les fichiers compatibles sont ajoutés ensemble ; les erreurs des autres sont signalées. Annuler retire le groupe ajouté. Un clic droit dans une piste permet aussi d’importer à cet emplacement.

Chaque zone possède une piste visuelle acceptant vidéos et images **JPEG (.jpg, .jpeg) ou PNG**. **+ Piste audio** ajoute une piste indépendante. Les formats audio acceptés comprennent MP3, WAV, M4A/AAC, FLAC et OGG, ainsi que les vidéos contenant du son, selon les codecs de FFmpeg. Une piste audio attend un média contenant du son.

Une image est ajoutée pour **5 secondes**. Glisser son bord droit pour prolonger ou raccourcir sa présence ; le bord gauche ajuste son début en gardant sa fin en place. Un double-clic ouvre les propriétés pour saisir la durée exacte. Les images n’ont pas de durée source maximale : seuls le début du montage et les clips voisins limitent les bords. Elles utilisent le même cadrage, zoom, déplacement, fondus et mode panoramique que les vidéos. Elles sont muettes et restent fixes pendant leur durée, dans les aperçus, la projection et le MP4. Les copies vidéo légères ne sont pas nécessaires pour les images.

- Cliquer sur un clip le sélectionne ; le halo jaune indique la sélection. Ctrl+clic ajoute ou retire un élément ; Ctrl+A sélectionne tout lorsque la timeline a le focus.
- Glisser le centre déplace le clip ; survoler un bord affiche des poignées sur le clip et un curseur horizontal de redimensionnement. Glisser le bord gauche retire ou révèle le début de la source, en gardant la fin en place ; le bord droit règle la fin. La saisie du bord a priorité sur le déplacement d’un groupe sélectionné. Les durées source et les voisins limitent l’extension. Un groupe pris par son centre se déplace dans le temps en conservant ses pistes et ses intervalles.
- Le magnétisme aligne débuts et fins sur les autres clips, les repères et zéro ; un trait jaune indique l’accrochage. Sa portée reste de dix pixels quel que soit le zoom.
- Le zoom **Auto** montre toute la durée du montage. Choisir un zoom numérique pour travailler de près ; les barres permettent le défilement horizontal et vertical.
- Le clic droit donne accès aux Propriétés, à Couper au curseur, Copier, Coller, Dupliquer et Supprimer. Raccourcis : Ctrl+C, Ctrl+V, Ctrl+D et Suppr dans la timeline.
- **+ Repère** ajoute un repère nommé au curseur. Clic droit près de sa ligne pour s’y rendre ou le supprimer.

Les chevauchements sur une même piste sont refusés sans modification partielle. Les espaces restent noirs ; la durée finale suit le dernier clip vidéo ou audio. Après la dernière vidéo, l’image reste noire si l’audio continue. Les fichiers sources ne sont jamais modifiés.

Double-cliquer sur un nom de piste audio permet de le renommer. Le clic droit sur un nom permet de renommer ou supprimer la ligne. La suppression d’une ligne occupée demande confirmation et reste annulable.

## Propriétés et cadrage des clips

Double-cliquer sur un clip ou choisir **Clic droit → Propriétés** ouvre le même formulaire : position dans le montage, début dans la source, durée, volume, piste, fondus ; pour une vidéo, Remplir/Contenir, zoom et décalages X/Y.

La position dans le montage et le début source sont distincts : Position 5, Début source 2 et Durée 4 placent les secondes 2 à 6 de la source entre les secondes 5 et 9 du montage. Les points de coupe et les clips voisins limitent les durées. Les virgules décimales sont acceptées.

Pour une sélection multiple, les champs vides représentent des valeurs différentes ; laissés vides, ils ne changent rien. Seuls les champs modifiés sont appliqués. Le décalage du groupe est relatif. Une modification invalide est refusée pour tout le groupe ; une validation correspond à une étape d’annulation.

Le volume est propre à chaque occurrence : 0 % coupe le son, 100 % conserve son niveau d’origine. Les fondus d’apparition et de disparition agissent sur l’image et le son. L’onde audio décrit le fichier source, avant réglage du volume.

L’onde audio reste affichée pendant les coupes, avec les nouveaux points de début et de fin ; la ligne sous la timeline indique les temps source et la durée conservée. Les originaux ne sont pas raccourcis. La case **Miniatures** affiche des images dans les clips vidéo suffisamment larges ; elles se calculent en arrière-plan et suivent les points de coupe. Augmenter le zoom de la timeline pour voir les clips très courts plus clairement.

Cliquer dans la règle de temps, saisir un instant puis **Afficher**, ou utiliser **Image précédente/suivante** choisit une image arrêtée, sans démarrer de lecture ni de son. Le recalcul tient compte des coupes et des intervalles noirs.

Avec l’outil **Position vidéo**, glisser dans une zone déplace le contenu sans changer ses coins ; la molette règle le zoom. Les propriétés permettent un zoom de 25 à 400 % et des décalages de −100 à 100 %. Pendant le glissement, un repère simplifié remplace l’image ; au relâchement, un seul calcul rétablit l’image exacte. Double-cliquer dans une zone ouvre les propriétés du clip actif à cet instant. Copier/Coller le cadrage et Réinitialiser le cadrage sont accessibles par clic droit sur les clips.

## Vidéo panoramique sur plusieurs vantaux

Importer une vidéo, sélectionner son clip puis cliquer sur **Panoramique…** au-dessus de la timeline, ou **Clic droit → Vidéo panoramique…**.

Les zones sont proposées selon leur position sur le mapping. Ctrl+clic choisit les zones. Le mode **Respecter la disposition du mapping (écarts automatiques)** conserve leur position horizontale et verticale : une troisième zone au-dessus de la deuxième prélève le haut de l’image commune, sans devenir un troisième segment à droite. Le schéma représente les quadrilatères à leurs positions réelles. L’ordre de la liste ne déplace pas les zones dans ce mode.

L’image commune occupe le rectangle englobant les zones sélectionnées. Chaque zone prélève la portion rectangulaire correspondant à son emplacement, puis l’adapte à son quadrilatère par la perspective. Les espaces horizontaux et verticaux restent masqués ; les portions ne sont pas accolées artificiellement. La position de prélèvement suit les changements de mapping, dans l’image arrêtée, les lectures et l’export. Le zoom et les décalages agissent sur l’image commune, y compris quand on les règle depuis une petite zone en hauteur.

Le mode manuel conserve l’ancienne bande horizontale : **Avant / Après** change l’ordre des segments et **Espace entre zones** règle un écart commun, de 0 à 100 % de la largeur moyenne des zones choisies. Ce mode est distinct de la disposition 2D. Les anciens panoramiques manuels gardent leurs réglages ; cocher le mode automatique pour utiliser leur disposition spatiale. Les coordonnées restent celles de l’image projetée, sans mesure physique de la scène ; vérifier le cadrage sur les surfaces réelles.

**Source / Répartition**, au-dessus de la timeline et dans Lecture et export, ouvre deux vues de la même image arrêtée : la source cadrée avant les fondus, avec les portions colorées attribuées aux zones, et le résultat après perspective et masques. La fenêtre suit le curseur, le clip actif et le mapping. Elle n’émet aucun son ; les anciens calculs sont abandonnés si vous choisissez un autre instant.

Le panoramique reste un seul clip, visible sur chaque piste concernée avec le signe ↔. Déplacer, couper, raccourcir, dupliquer ou supprimer une partie agit sur ce même clip. Durée, points de coupe, fondus, cadrage et volume sont communs ; le son est joué une seule fois. Muet/Solo suit la première zone dans l’ordre choisi.

**Position vidéo** déplace ou zoome l’image commune depuis n’importe laquelle de ses zones. En automatique, les portions suivent les emplacements et dimensions des zones dans le rectangle commun ; en manuel, les largeurs sont réparties selon les proportions logiques estimées des quadrilatères. Chaque portion est adaptée à sa perspective. La source vidéo est décodée une seule fois pour ses différentes zones. Les chevauchements avec d’autres clips sont refusés sur toutes les zones utilisées.

Pour changer les zones, rouvrir Panoramique. **Revenir à une seule zone** conserve le clip sur la première zone, avec ses propriétés actuelles. Cette opération est annulable. Vérifier la continuité sur les vantaux réels.

## Lecture, boucle et projection animée HDMI

**▶ Lecture directe** démarre depuis le curseur sans préparer un MP4. Pause/lecture, Recommencer au début, déplacement dans le temps, grille et qualité 480 × 270, 640 × 360 ou 1280 × 720 sont disponibles. Une qualité supérieure demande davantage de calcul. Le niveau audio affiché mesure le signal envoyé à Windows. Modifier le montage ou le mapping arrête cette lecture ; la relancer depuis le curseur.

Pour répéter un passage, cocher **Boucle**, définir **Entrée / Sortie** et cliquer sur **Appliquer**. Les boutons au curseur reprennent la position de lecture. Les bornes sont ajustées aux images à 30 images/s. Pause suspend la répétition ; décocher Boucle continue vers la fin du montage. Un nouveau décodage peut créer une courte attente entre deux tours. La boucle concerne la lecture directe, sans modifier le MP4 exporté.

**Aperçu du montage** prépare une vidéo de travail en 720p, puis la lit dans une fenêtre dédiée, avec pause, retour au début et grille facultative. L’affichage de cette fenêtre décode en 960 × 540. Recommencer conserve la fenêtre et ses réglages. Les changements de volume peuvent actualiser le son en arrière-plan ; les autres changements nécessitent un nouvel aperçu.

Pour projeter une animation :

1. Sélectionner l’écran du projecteur, en bureau étendu.
2. Choisir **Lecture et export → Projeter le montage en HDMI**, ou **Projeter HDMI** dans la fenêtre de lecture directe ou d’aperçu calculé.
3. La sortie affiche uniquement l’image, centrée en 16:9 sur fond noir. Les commandes et la grille de travail restent sur le portable ; la grille de travail n’est pas envoyée sur la sortie animée.
4. Cliquer de nouveau sur Projeter HDMI, ou appuyer sur Échap dans la sortie, pour la fermer sans arrêter les commandes de lecture.

Une seule animation utilise la sortie à la fois. Fermer la lecture ou changer de projet ferme sa sortie. La disparition de l’écran choisi ferme aussi la sortie. La qualité dépend de la lecture utilisée ; pour un résultat encodé, utiliser l’aperçu calculé ou le MP4 final. La fluidité et la synchronisation doivent être évaluées sur le portable réel.

Les commandes **Noir (F8)** et **Figer (F9)** se trouvent dans les fenêtres de lecture. Elles agissent uniquement sur l’image de la sortie HDMI : Noir masque l’image ; Figer conserve l’image actuelle pendant que la lecture continue. Le son continue dans les deux cas. F8/F9 fonctionnent aussi depuis la fenêtre principale lorsqu’une sortie animée est ouverte. Enlever Noir ou Figer retrouve l’image courante ; aucun changement n’est appliqué au montage ni au MP4.

## Copies de travail légères

**Lecture et export → Copies de travail légères… → Préparer les vidéos du projet** crée des copies vidéo limitées à 640 × 360, en conservant le rapport d’image et la durée. La préparation s’effectue en arrière-plan et peut être annulée. Les copies disponibles accélèrent l’image arrêtée, la comparaison source/répartition et la lecture directe ; leur utilisation peut être désactivée dans la même fenêtre.

Le projet garde les chemins des originaux. Le mixage audio, l’aperçu calculé et l’export MP4 utilisent toujours les sources originales. Une source modifiée, une copie supprimée ou une copie non disponible revient automatiquement à l’original. Les copies sont conservées dans `work-media`, avec une limite de 4 Go, et peuvent être vidées sans toucher aux sources. Après un redémarrage, Préparer réactive les copies conservées sans les réencoder. Copier les originaux reste nécessaire pour transférer ou exporter un projet.

## Son et analyse avant export

Les sons des vidéos et des pistes audio sont mélangés. **Audio → Muet et Solo par piste** permet de les isoler ; plusieurs solos peuvent être actifs. Le volume reste réglé par clip, dans ses propriétés.

**Audio → Analyser le niveau sonore…** mesure le mixage complet en arrière-plan et signale les passages proches de la saturation. Le résultat indique la crête, les intervalles concernés et une réduction commune proposée pour viser −1 dBFS. **Appliquer la réduction au projet** ajuste les volumes en conservant leurs rapports ; Annuler restaure les valeurs précédentes. Une réduction ne répare pas une source déjà saturée.

L’export MP4 lance aussi cette analyse automatiquement. Si le niveau est trop élevé, le choix est explicite : réduire pour cet export seulement, exporter les niveaux actuels, ou annuler pour corriger le projet. La réduction propre à l’export ne change pas les volumes enregistrés dans le projet. L’aperçu calculé et la mire n’ouvrent pas ce dialogue.

## Export MP4 et mire USB

La liste **Résolution**, à côté d’Exporter, propose 720p (1280 × 720), Full HD (1920 × 1080) et 4K UHD (3840 × 2160). Le choix est propre au projet, enregistré et annulable. Les mappings restent proportionnels ; les résolutions élevées ne recréent pas les détails absents des sources.

**Exporter le montage MP4** produit un MP4 H.264/AAC à 30 images/s, avec fond noir hors des zones. **Mire USB** produit une mire MP4 de huit secondes dans la résolution choisie. Sa grille suit la case Grille des mires HDMI / USB au moment de l’export.

Avant le calcul, l’application vérifie les médias, leur durée réelle, la présence du son attendu, l’accès à la destination et un budget prudent d’espace temporaire et final. Un média source ne peut pas servir de destination. Le poids et l’espace de travail restent des estimations ; la disponibilité future du disque n’est pas garantie.

La progression distingue vidéo, mixage audio et assemblage. Un calcul lent n’est pas arrêté automatiquement : **Arrêter le rendu** reste disponible. Un fichier incomplet ne remplace pas la destination. Le remplacement d’un export existant est confirmé dans le sélecteur Windows. Un fichier `.partial` peut subsister si une opération disque échoue.

## Cache entre les exports

Les séquences vidéo déjà calculées peuvent être réutilisées lors d’un export ou d’un aperçu ultérieur. Le cache tient compte du contenu des médias, des coupes, du cadrage, des fondus, du panoramique, des zones utilisées, de la résolution et du moteur de rendu. Un média modifié ou une entrée de cache corrompue entraîne un nouveau calcul.

Le cache est conservé dans `render-cache` à côté de l’application, avec une limite de 2 Go. Les séquences les plus anciennes sont retirées automatiquement. **Lecture et export → Cache des rendus…** affiche son occupation et permet de le vider hors rendu en cours. Cela ne supprime aucun projet ni média source. Si le cache n’est pas accessible en écriture, l’export fonctionne sans le conserver. Le son est recalculé pour appliquer les volumes actuels.

## Médias manquants et regroupement pour transfert

**Lecture et export → Vérifier le projet / retrouver les médias** affiche la durée, la résolution, un poids indicatif, l’espace temporaire estimé et les fichiers absents. La recherche individuelle permet de réassocier un fichier à toutes ses occurrences.

**Rechercher dans un dossier…**, également disponible directement dans Lecture et export, parcourt le dossier choisi et ses sous-dossiers. Les correspondances uniques par nom sont proposées ; les doublons ne sont pas choisis automatiquement. Sélectionner une ligne puis une proposition, ou choisir un fichier manuellement. **Appliquer les correspondances** vérifie la durée et le son attendu, puis applique l’ensemble en une étape d’annulation. Les médias non retrouvés restent signalés. Le projet ne doit pas avoir changé pendant la recherche.

**Projets → Rassembler le projet et ses médias…** crée un nouveau dossier contenant `installation.projectunio.json` et `medias`. Chaque source utilisée est copiée une seule fois ; les fichiers portant le même nom restent distincts. Le regroupement inclut les modifications non enregistrées, sans changer le fichier de travail. Copier ensuite tout ce nouveau dossier, ainsi que l’application portable séparément. Les chemins relatifs permettent de changer de dossier ou de lettre de lecteur.

## Verrous, journaux et dépannage

**Verrou mapping** protège la géométrie et ses noms ; **Verrou timeline** protège montage, cadrages et pistes ; **Verrou projet** protège l’ensemble. Lecture, navigation, grille, sauvegarde et export restent disponibles. Les verrous sont propres à chaque projet et conservés dans le fichier. Annuler/Rétablir est bloqué tant qu’un verrou est actif.

Les journaux sont dans `logs/projectunio.log`, `logs/crash.log` et `logs/render-….log`. Si le dossier application est protégé, les journaux généraux peuvent utiliser le dossier temporaire Projectunio-logs. Une erreur de média, de copie ou de disque n’altère pas les originaux.

Les tests locaux couvrent géométrie, montage, cadrages, panoramique, volumes et fondus, sauvegarde et récupération, imports Windows, rendus et annulation, cache, recherche de médias, calibrations et gestion de la sortie animée. Ils ne remplacent pas les essais HDMI/USB matériels.

## Essai matériel conseillé pour le Yoton Y3

Fixer la position, le zoom et la correction interne du projecteur. En bureau étendu, calibrer avec Mire HDMI, enregistrer une version nommée, fermer et rouvrir le projet. Vérifier ensuite Image HDMI et la projection animée : coins, cadrage, noir hors zones, passages noirs, audio et continuité panoramique.

Exporter Mire USB et la lire sur le projecteur depuis une clé ; comparer contours et intersections avec HDMI. En cas de différence d’échelle, conserver une calibration d’essai séparée au lieu de modifier silencieusement la version validée. Tester ensuite le MP4 complet et noter les réglages matériels et les résultats pour chaque installation.

Aucune compatibilité USB réelle Yoton Y3 n’est revendiquée sans cet essai. Les pixels noirs peuvent encore émettre de la lumière. Déplacer le projecteur ou changer son zoom, son mode image ou sa correction interne exige une vérification de calibration.
