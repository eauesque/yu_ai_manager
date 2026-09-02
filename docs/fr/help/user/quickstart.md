# Démarrer avec YU AI Manager en 5 Minutes

## Qu'est-ce que YU AI Manager

YU AI Manager est une application WebUI qui permet de gérer de manière centralisée les métadonnées des images générées par IA (Stable Diffusion / NovelAI / ComfyUI, etc.). Elle extrait automatiquement les prompts et informations de modèle intégrés aux images, et rend efficace la recherche par tag, la consultation et l'organisation.

---

## Environnement d'Exécution

| Élément | Exigence |
|------|------|
| Python | 3.11 ou supérieur |
| Node.js | 18 ou supérieur (pour la compilation du frontend) |
| OS | Windows 10/11, macOS, Linux |
| Navigateur | Chrome / Firefox / Edge (dernière version recommandée) |

---

## Procédure d'Installation

### 1. Cloner le Dépôt

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. Créer un Environnement Virtuel Python

**macOS / Linux :**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell) :**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash) :**

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3. Installer les Dépendances Python

```bash
uv pip install -r requirements.txt
```

> Si `uv` n'est pas installé, installez-le d'abord avec `pip install uv`.

### 4. Compiler le Frontend

```bash
pnpm install
pnpm run build
```

> Si `pnpm` n'est pas installé, installez-le d'abord avec `npm install -g pnpm`.

L'installation est terminée.

---

## Premier Démarrage

### 1. Lancer le Serveur

```bash
# Activer d'abord le venv si ce n'est pas déjà fait
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. Accéder depuis le Navigateur

Après le démarrage, ouvrez l'URL suivante dans votre navigateur :

```
http://localhost:5000
```

*(Capture d'écran de l'écran principal)*

---

## Premières Choses à Faire

### Étape 1 : Enregistrer un Dossier d'Images pour le Scan

Enregistrez un dossier contenant des images générées par IA pour lire leurs métadonnées.

1. Ouvrez **Settings** depuis le menu hamburger en haut à droite
2. Sélectionnez l'onglet **Scan**
3. Ajoutez le chemin du dossier à scanner
4. Le scan démarre automatiquement après l'ajout du dossier

*(Capture d'écran de l'enregistrement du dossier de scan)*

Pendant le scan, une barre de progression s'affiche en haut de l'écran. Si le nombre d'images est important, cela peut prendre plusieurs minutes, mais la recherche et la consultation restent possibles pendant le scan.

### Étape 2 : Voir les Images dans la Grille de Miniatures

Une fois le scan terminé, la grille de miniatures s'affiche sur la page principale.

*(Capture d'écran de l'affichage de la grille de miniatures)*

- **Défilement** : affichage fluide d'un grand nombre d'images grâce au défilement virtuel
- **Tri** : basculer entre ordre par date, par note, etc., dans le menu de tri en haut de l'écran
- **Clic droit** : enregistrer en favori ou ajouter à une collection via le menu contextuel

### Étape 3 : Affiner les Images par Recherche de Tags

En saisissant des tags séparés par des virgules dans la barre de recherche, seules les images correspondantes s'affichent.

```
1girl, blue_eyes, school_uniform
```

*(Capture d'écran de la recherche par tag)*

- **Autocomplétion** : les tags candidats s'affichent pendant la saisie
- **Filtre** : affinage possible par plage de dates, format de fichier, note en étoiles, etc.
- **Recherche dans le prompt** : il est aussi possible de rechercher le texte intégral du prompt

### Étape 4 : Vérifier les Informations de l'Image dans la Modale de Détail

En cliquant sur une miniature, la modale de détail s'ouvre.

*(Capture d'écran de la modale de détail)*

- **Onglet Info** : vérifier le prompt, le prompt négatif, le nom du modèle, les paramètres de génération, etc.
- **Onglet AI Analysis** : affiche les résultats d'étiquetage automatique par WD-Tagger (si configuré)
- **Note en étoiles** : vous pouvez attribuer une note de 1 à 5 étoiles à l'image
- **Favori** : enregistrer en favori via l'icône cœur
- **Édition de tags** : ajout/suppression de tags utilisateur possible
- **Raccourcis clavier** : flèches gauche/droite pour naviguer entre les images

---

## Résumé des Opérations Fréquentes

| Ce que vous voulez faire | Opération |
|-------------|------|
| Chercher une image | Saisir un tag dans la barre de recherche |
| Voir les détails de l'image | Cliquer sur la miniature |
| Ajouter aux favoris | Icône cœur dans la modale de détail, ou menu clic droit |
| Attribuer une note en étoiles | Icône étoile dans la modale de détail |
| Ajouter à une collection | Menu clic droit > Ajouter à la collection |
| Sélectionner plusieurs images | Ctrl+clic (ou Shift+clic) pour sélection de plage |
| Scanner un nouveau dossier | Settings > Onglet Scan |

---

## Étapes Suivantes

Une fois les opérations de base maîtrisées, essayez aussi les fonctionnalités suivantes.

### Settings (Paramètres)

La page Settings permet la personnalisation de l'apparence, la configuration du fuseau horaire, la publication LAN, etc. Pour plus de détails, consultez le [guide Settings](settings.md).

### Bridge (Intégration avec des Outils de Génération d'Images)

Intégration avec SD WebUI / ComfyUI / API NovelAI pour envoyer et recevoir des prompts. Pour plus de détails, consultez le [guide Bridge](bridges.md).

### Extensions (Fonctionnalités d'Extension)

De nombreuses extensions sont disponibles comme WD-Tagger (étiquetage automatique), bibliothèque de prompts, visualiseur de journal de chat, etc. Gestion depuis l'onglet Settings > Extensions.

### Recherche Sémantique

En configurant le modèle CLIP, vous pouvez rechercher des images en langage naturel comme « une fille regardant le coucher de soleil au bord de la mer ». Pour plus de détails, consultez le [guide de recherche](search.md).

### Serveur MCP

Vous pouvez contrôler YU AI Manager depuis des agents IA comme Claude Desktop. Connexion via le transport stdio.

---

## Dépannage

En cas de problème, consultez le [guide de dépannage](troubleshooting.md).

Problèmes courants :

- **Commande `uv` introuvable** : installer avec `pip install uv`
- **Commande `pnpm` introuvable** : installer avec `npm install -g pnpm`
- **Port 5000 utilisé** : spécifier un autre port avec `python web_ui.py --port 5100`
- **Les images ne s'affichent pas** : vérifier que le chemin du dossier de scan est correct et que les fichiers image existent réellement
