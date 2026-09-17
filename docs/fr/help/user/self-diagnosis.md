# Autodiagnostic et signalement en cas de problème

Si yu_ai_manager ne fonctionne pas ou se comporte de façon inhabituelle, vous pouvez collecter vous-même les indices pour identifier le problème et le signaler aux développeurs. Aucune connaissance en ligne de commande ou Git n'est requise.

## 1. Commencez par appuyer sur « Signaler un problème »

1. Ouvrez l'application dans votre navigateur et sélectionnez **Diagnostics** dans le menu en haut à droite.
2. Appuyez sur le bouton **« Signaler un problème »**.
3. Après un moment, un dossier `repair/2026XXXX-HHMMSS/` est créé. Il contient l'ensemble de rapports automatiques suivant :
   - Informations d'environnement, journaux récents et paramètres (les informations personnelles et les jetons sont masqués)
   - Modèles de prompts pour la réparation par IA

Appuyez sur **« Ouvrir le dossier »** pour ouvrir le dossier dans l'Explorateur. **« Créer un ZIP »** regroupe tout en un seul fichier zip.

> À propos du masquage : les noms d'utilisateur, les e-mails, les chaînes ressemblant à des clés API, les adresses IP, etc. sont automatiquement remplacés par `<REDACTED>`. Ce processus n'est pas parfait, veuillez donc vérifier le contenu avant de le partager.

## 2. Partagez le rapport

Joignez le fichier ZIP au développeur, au support ou à Discord. Le bouton **« Copier le message pour Discord »** vous prépare un court message à coller directement.

## 3. Mesures provisoires que vous pouvez essayer vous-même

### 3-A. Vérification de l'environnement (doctor)

Appuyez sur le bouton **« Diagnostic d'environnement »** dans l'écran de diagnostic pour afficher l'état de Python, du GPU, de la base de données, etc. au format markdown. Essayez les suggestions `fix_hint` listées pour chaque élément en rouge (ERROR) ou jaune (WARN).

### 3-B. Redémarrer en Safe Mode

Si le démarrage normal ne fonctionne pas, l'application plante ou les chargements sont infinis, vous pouvez démarrer en **Safe Mode**.

- Windows : double-cliquez sur `start.bat --safe-mode` (ou ajoutez ` --safe-mode` à la fin du raccourci)
- macOS / Linux : exécutez `./start.sh --safe-mode` dans le terminal

En Safe Mode, vous pouvez :

- Vérifier les paramètres
- Utiliser « Signaler un problème » et « Diagnostic d'environnement »
- Appliquer un **paquet de mise à jour sécurisé (update.zip)** fourni par le développeur (remplacement de fichiers uniquement – les scripts de réparation automatique sont désactivés)

Le Safe Mode persiste jusqu'au prochain démarrage normal. Un redémarrage ordinaire ramène le mode normal.

### 3-C. Appliquer un paquet de mise à jour (update.zip)

Si vous recevez un `update.zip` du développeur :

1. Allez à Diagnostics → section **« Appliquer la mise à jour »**
2. Sélectionnez le fichier et vérifiez que la **Vérification (Verify)** devient verte
3. Appuyez sur **Appliquer** dans la boîte de dialogue de confirmation
4. Suivez les instructions affichées pour redémarrer

> N'appliquez jamais un zip dont la vérification est rouge. Il pourrait être altéré ou destiné à une autre application.

Si quelque chose se passe mal, vous pouvez revenir à l'état précédent avec **« Annuler la mise à jour précédente (Rollback) »**.

## 4. Choses à ne pas faire

- Ne collez pas les logs bruts (avant masquage) sur les réseaux sociaux ou les forums publics
- N'appliquez pas un `update.zip` d'origine inconnue
- Ne modifiez pas manuellement le dossier `data/` ou `tags.db`

## Si vous êtes bloqué

Si rien n'y fait, joignez le ZIP à votre signalement avec une description : « Qu'ai-je fait et qu'est-il arrivé ? ». Le côté IA chargera `prompt_for_codex.md` / `prompt_for_claude.md` et proposera un correctif.
