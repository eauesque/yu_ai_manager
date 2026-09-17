# Premiers pas

YU AI Manager est une application WebUI pour gérer les métadonnées des images générées par IA.

## Installation

### Environnement requis

- Python 3.11 ou supérieur
- Node.js 18 ou supérieur (pour le build du frontend)

### Procédure de configuration

```bash
# Cloner le dépôt
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# Installer uv (première fois uniquement)
pip install uv

# Créer l'environnement virtuel Python et installer les paquets
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash : source venv/Scripts/activate
uv pip install -r requirements.txt

# Build du frontend
pnpm install
pnpm run build

# Optionnel : Accélération de la recherche sémantique (pour les grandes bibliothèques)
uv pip install faiss-cpu
```

## Démarrage

```bash
source venv/bin/activate  # Windows Git Bash : source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

Accéder à `http://localhost:5000` dans le navigateur.

## Configuration initiale

1. **Enregistrer les dossiers de scan** : Ajouter les dossiers contenant les images générées par IA dans Settings > onglet Scan
2. **Exécuter le scan** : Après l'ajout du dossier, le scan démarre automatiquement
3. **Parcourir les images** : Rechercher et parcourir les images depuis la page principale

## Accès LAN

Pour accéder depuis d'autres appareils :

1. Activer « LAN Access » dans l'onglet Settings > **Server**
2. Configurer l'authentification PIN (obligatoire pour la publication LAN)  
   Saisir un nombre (4 à 8 chiffres) dans le champ « Code PIN » de l'**onglet Settings > Server**
3. Redémarrer le serveur

Accéder depuis d'autres appareils LAN via `http://<IP_serveur>:5000`.
