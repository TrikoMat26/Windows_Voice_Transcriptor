# Instructions pour l'intégration Windows de l'Enregistreur Vocal

Ce guide vous explique comment configurer l'application Enregistreur Vocal pour un accès facile sous Windows.

## 1. Créer un raccourci pour lancer l'application

L'application est lancée via le fichier `Lancer_Transcription.bat`. Pour un accès plus facile, nous allons créer un raccourci Windows :

1.  Naviguez dans l'explorateur de fichiers jusqu'au dossier où se trouve `Lancer_Transcription.bat`.
2.  Faites un clic droit sur `Lancer_Transcription.bat`.
3.  Sélectionnez "Afficher plus d'options" (Windows 11) si nécessaire, puis "Envoyer vers" > "Bureau (créer un raccourci)".
4.  Vous trouverez un nouveau raccourci sur votre bureau, nommé `Lancer_Transcription.bat - Raccourci`. Vous pouvez le renommer si vous le souhaitez (par exemple, "Transcription Vocale").

## 2. Assigner un raccourci clavier pour lancer l'application

Vous pouvez assigner un raccourci clavier (par exemple, `Ctrl+Alt+T`) à ce nouveau raccourci pour lancer l'application rapidement :

1.  Faites un clic droit sur le raccourci que vous venez de créer (par exemple, "Transcription Vocale" sur votre bureau).
2.  Sélectionnez "Propriétés".
3.  Allez dans l'onglet "Raccourci".
4.  Cliquez dans le champ "Touche de raccourci".
5.  Pressez la combinaison de touches que vous souhaitez utiliser (par exemple, `Ctrl+Alt+T`). Windows ajoutera automatiquement `Ctrl+Alt` si vous tapez juste une lettre.
6.  Cliquez sur "Appliquer" puis "OK".

Maintenant, en utilisant cette combinaison de touches (par exemple, `Ctrl+Alt+T`), vous pourrez lancer l'application si elle n'est pas déjà en cours d'exécution.

## 3. Utiliser l'application (Afficher/Masquer et Transcription)

Une fois l'application lancée (elle démarrera minimisée dans la barre d'état système, près de l'horloge) :

*   **Appuyez sur la touche `F9` de votre clavier.**
    *   Cela affichera la fenêtre de l'application si elle est masquée.
    *   Cela démarrera ou arrêtera l'enregistrement vocal pour la transcription.
*   Vous pouvez également cliquer sur l'icône de l'application dans la barre d'état système pour afficher la fenêtre.

Le tooltip de l'icône dans la barre d'état système a été mis à jour pour rappeler l'utilisation de la touche `F9` : "Enregistreur Vocal (F9 pour Afficher/Masquer & Démarrer/Arrêter)".

## 4. Démarrer l'application avec Windows (Optionnel)

Si vous souhaitez que l'application démarre automatiquement lorsque vous allumez votre ordinateur :

1.  Ouvrez l'Explorateur de fichiers.
2.  Dans la barre d'adresse, tapez `shell:startup` et appuyez sur Entrée. Cela ouvrira le dossier Démarrage de Windows.
3.  Copiez le raccourci que vous avez créé à l'étape 1 (par exemple, "Transcription Vocale" depuis votre bureau) et collez-le dans ce dossier Démarrage.

L'application se lancera désormais automatiquement et discrètement (dans la barre d'état système) à chaque démarrage de Windows. Vous pourrez alors utiliser la touche `F9` pour l'activer.

---

Si vous avez compilé l'application en un fichier `.EXE` unique, vous pouvez créer le raccourci (étape 1) directement vers cet `.EXE` et suivre les mêmes instructions pour le raccourci clavier (étape 2) et le démarrage automatique (étape 4). La touche `F9` fonctionnera de la même manière une fois l'application `.EXE` lancée.
