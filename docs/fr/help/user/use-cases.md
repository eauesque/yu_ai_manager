# Collection de Cas d'Usage

Les usages représentatifs de YU AI Manager, résumés au format « dans ce cas, faites ceci ».

---

## 1. Organiser une grande quantité d'images IA

Quand vous avez des milliers d'images générées par NovelAI ou Stable Diffusion accumulées dans des dossiers et difficiles à consulter.

### Procédure

1. Enregistrez un dossier de scan dans l'onglet **Settings > Scan** (plusieurs possibles)
2. Le scan démarre automatiquement après l'ajout. Les contenus de ZIP/7z peuvent aussi être scannés
3. Après le scan, affinez les images sur la page principale par recherche de tags (ex : `1girl, blue_eyes`) ou par tri
4. Sélectionnez les images appréciées, clic droit > **Ajouter à la collection** pour grouper
5. Consultation par groupe possible à tout moment depuis la barre latérale de collections

### Astuces

- Recherche et consultation restent possibles pendant le scan (pas de conflit grâce à la connexion DB en lecture seule)
- En activant l'extension Auto Scan Watcher, les nouveaux ajouts aux dossiers sont détectés automatiquement
- Même à l'échelle d'un million d'éléments, Keyset Pagination permet une pagination rapide

---

## 2. Rechercher des images générées avec un prompt spécifique

Quand vous ne vous souvenez plus « c'était quoi le prompt de cette composition ».

### Procédure

1. Basculez la cible de recherche de la barre de recherche sur **in_prompt**
2. Saisissez un mot-clé dont vous vous souvenez (ex : `cherry blossom`) et cherchez
3. Les expressions régulières permettent un affinage plus flexible (ex : `masterpiece.*cherry`)

### Astuces

- Si FTS (recherche en texte intégral) est activé, la recherche reste rapide même avec beaucoup de prompts
- Combiner avec les filtres de plage de dates et format de fichier est efficace
- Le tri `random` permet aussi de redécouvrir des images oubliées

---

## 3. Trouver des images de composition similaire

Quand vous voulez chercher « il devait y avoir d'autres images avec une ambiance similaire à celle-ci ».

### Procédure A : Recherche par similarité pHash (composition, couleurs)

1. Ouvrez la modale de détail de l'image
2. Cliquez sur **Rechercher images similaires**
3. Les images de composition proche par pHash (hash perceptuel) s'affichent en liste dans le panneau latéral

### Procédure B : Recherche sémantique CLIP (sens, concept)

1. Cliquez sur **Recherche sémantique** à droite de la barre de recherche
2. Saisissez une description en langage naturel (ex : « fille debout au bord de la mer », « paysage urbain au coucher du soleil »)
3. CLIP comprend le sens des images et affiche par ordre de similarité

### Astuces

- La recherche sémantique nécessite une configuration préalable d'un modèle CLIP (ONNX ou Hailo-10H)
- Pour les grandes bibliothèques (plus de 100 000 éléments), installer `faiss-cpu` améliore considérablement la vitesse de recherche
- pHash pour la correspondance de composition, CLIP pour la similarité sémantique : leurs domaines d'expertise diffèrent. Essayez les deux pour plus de découvertes

---

## 4. Gérer ses images favorites

Quand vous voulez pouvoir accéder rapidement aux chef-d'œuvres parmi de nombreuses images.

### Procédure

1. Enregistrez en favori avec le **bouton cœur** de la carte image ou de la modale de détail
2. Dans la modale, évaluez la qualité avec la **note en étoiles** (1 à 5)
3. Laissez des notes libres dans **Annotation** (ex : « candidat à retouche », « déjà publié sur SNS »)
4. Affinez avec les filtres de recherche « favoris uniquement », « 4 étoiles et plus », etc.

### Astuces

- Le tri par note (`rating_desc`) permet de consulter en groupe les images les mieux notées
- Les opérations favoris/notes sont aussi possibles depuis le menu contextuel (clic droit)

---

## 5. Envoyer le prompt d'une image à un autre outil

Quand vous voulez réutiliser le prompt d'une ancienne image pour la régénérer ou créer des variations dans un autre outil.

### Procédure

1. Ouvrez la modale de détail de l'image et vérifiez les informations de prompt
2. Cliquez sur **Envoyer à SD WebUI** / **Envoyer à ComfyUI** / **Envoyer à NAI**
3. La page Bridge s'ouvre et le prompt est pré-rempli automatiquement
4. Éditez le prompt si besoin et exécutez côté outil de génération

### Astuces

- La syntaxe de poids `()` et `{}` est convertie automatiquement entre SD ↔ NAI
- Le bouton **QP** de la barre d'outils Bridge permet d'insérer un preset qualité en un clic
- Il est aussi possible d'envoyer vers chaque Bridge depuis Prompt Converter ou Prompt Simulator

---

## 6. Consulter les images d'une archive ZIP/7z

Quand un lot d'images téléchargé est regroupé en ZIP et que vous voulez voir le contenu sans l'extraire.

### Procédure

1. Enregistrez dans Settings > Scan un dossier contenant des fichiers ZIP/7z
2. Activez **Scanner l'intérieur des ZIP/7z** dans les options de scan
3. Après le scan, les images dans les archives sont recherchables/consultables sur la page principale comme des images normales
4. La modale de détail affiche le nom de l'archive et le chemin interne

### Astuces

- Les vidéos dans les archives sont extraites dans un cache temp (LRU 2 Go), donc les lectures répétées sont fluides
- Les ZIP imbriqués (ZIP-in-ZIP) sont aussi supportés
- La fonction de téléchargement par lot permet aussi de regrouper les images d'archive dans un nouveau ZIP

---

## 7. Partager des images avec l'équipe ou la famille

Quand vous voulez permettre la consultation d'images depuis d'autres appareils (smartphone, tablette, etc.) du même Wi-Fi.

### Procédure

1. Activez « LAN Access » dans l'onglet **Settings > Server**
2. Définissez un **code PIN** (obligatoire en publication LAN)
3. Redémarrez le serveur
4. Accédez à `http://<IP du serveur>:5000` depuis les autres appareils du LAN
5. Saisissez le PIN pour vous connecter

### Astuces

- En émettant un **token LAN Share** (chemin `/s/`), vous pouvez partager un lien d'accès invité sans PIN
- Un QR code s'affiche sur l'écran serveur, accessible en le scannant avec la caméra du smartphone
- L'authentification Trusted Proxy via reverse proxy est aussi supportée

---

## 8. Étiqueter automatiquement

Quand l'étiquetage manuel est fastidieux et que vous voulez faire analyser les images par IA pour étiqueter automatiquement.

### Procédure A : WD-Tagger (rapide, spécialisé tags)

1. Téléchargez le modèle ONNX WD-Tagger dans **Settings**
2. Cliquez sur **Exécuter WD-Tagger** depuis la page Tools ou la modale de détail
3. Des tags style Danbooru sont attribués automatiquement

### Procédure B : AI Analysis (langage naturel, haute précision)

1. Ajoutez Ollama ou un serveur compatible OpenAI dans **Settings > AI Analysis**
2. Exécutez l'analyse depuis l'**onglet AI Analysis** de la modale de détail de l'image
3. Une description d'image en langage naturel est générée

### Astuces

- WD-Tagger supporte aussi le mode composite avec un moteur VLM (compatible API OpenAI)
- Des post-traitements comme le filtre NSFW et la normalisation de tags s'appliquent automatiquement
- L'écriture de tags dans les métadonnées XMP est aussi supportée, facilitant l'intégration avec d'autres outils

---

## 9. Voir les statistiques et rapports

Quand vous voulez comprendre les tendances et la croissance de votre bibliothèque d'images.

### Procédure

1. Ouvrez la page **Stats** depuis la navigation pour voir les statistiques globales
2. Consultez les rapports détaillés mensuels sur la page **Monthly Report**
   - Nombre de fichiers mensuels, comparaison avec le mois précédent, TOP 20 tags, nouveaux tags, distribution par source, compte quotidien
3. Vérifiez les trophées de réussite dans la section **Trophies**

### Astuces

- Les trophées sont débloqués progressivement sur 6 catégories (milestone / streak / diversity / source / hidden) et 4 niveaux (bronze à platinum)
- Si le fuseau horaire est correctement configuré (Settings > Appearance), les statistiques quotidiennes sont précises

---

## 10. Intégrer avec un agent IA via MCP

Quand vous voulez contrôler votre bibliothèque d'images depuis Claude Desktop ou d'autres outils IA compatibles MCP.

### Procédure

1. Enregistrez le serveur MCP de YU AI Manager dans la configuration du client MCP (Claude Desktop, etc.)
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. Donnez des instructions en langage naturel à l'IA comme « cherche des images », « ajoute aux favoris »
3. Plus de 60 outils sont disponibles : `search_images`, `add_favorite`, `trigger_scan`, etc.

### Astuces

- Depuis l'extension client MCP, vous pouvez aussi vous connecter à des serveurs MCP externes (stdio / SSE / Streamable HTTP)
- En configurant l'authentification API Key, vous pouvez aussi appeler directement l'API REST depuis des outils externes sans l'en-tête CSRF
- Avec l'extension Hailo GenAI, l'intégration est possible via un endpoint compatible OpenAI SDK

---

## 11. Utiliser Hailo-10H comme serveur compatible OpenAI

Quand vous voulez, dans un environnement équipé du NPU Hailo-10H, l'utiliser comme serveur IA local compatible OpenAI SDK. Open WebUI, Continue.dev, scripts personnalisés et autres outils externes peuvent utiliser tel quel les LLM / VLM / reconnaissance vocale / embeddings CLIP de Hailo.

### Endpoints Supportés

| Endpoint | Fonction | API OpenAI correspondante |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | Liste des modèles téléchargés | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | Génération de texte, compréhension d'image (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | Transcription audio | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | Conversion texte → vecteur (CLIP) | Embeddings |

### Procédure

1. Vérifiez que l'extension Hailo GenAI est activée sur la page **Extensions > GenAI**
2. Téléchargez le modèle souhaité (LLM : `qwen2.5-1.5b-chat`, etc., VLM : `llava-v1.6-vicuna-7b`, etc.)
3. Dans les paramètres de connexion de l'outil externe, définissez **Base URL** :
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   (Adaptez le numéro de port à la configuration de démarrage de YU AI Manager)
4. Pas de clé API nécessaire (accès local). Si l'outil requiert une clé API, saisissez une valeur factice (ex : `dummy`)

### Exemples de Connexion avec Outils Externes

#### Open WebUI

Ajouter dans Settings > Connections > OpenAI API :
- **URL** : `http://localhost:5000/ext/hailo-genai/v1`
- **API Key** : `dummy`

#### Continue.dev (assistant IA VS Code)

Ajouter dans `~/.continue/config.json` :
```json
{
  "models": [{
    "title": "Hailo Qwen2.5",
    "provider": "openai",
    "model": "qwen2.5-1.5b-chat",
    "apiBase": "http://localhost:5000/ext/hailo-genai/v1",
    "apiKey": "dummy"
  }]
}
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# Génération de texte
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# Compréhension d'image (VLM) — joindre une image base64
import base64
with open("image.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

res = client.chat.completions.create(
    model="llava-v1.6-vicuna-7b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
)

# Transcription audio
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# Embedding de texte (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### Paramètres Supportés

- **Chat Completions** : `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions** : `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings** : `model`, `input` (chaîne ou tableau de chaînes)
- **Alias de modèles** : `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### Remarques

- **Exclusivité du périphérique** : Hailo-10H ne peut charger qu'un seul modèle GenAI à la fois (LLM ou VLM ou S2T). Le changement de mode se fait sur la page GenAI
- **Restriction d'URL d'image** : pour la sécurité, les spécifications d'image par URL `http://` sont bloquées. Utilisez le format `data:image/...;base64,...` ou le format `file_id:` de YU AI Manager
- **Embedding CLIP** : seule la conversion texte → vecteur est supportée. Image → vecteur est utilisable via l'endpoint `/api/semantic/`
- **Format audio** : les formats autres que WAV (MP3, M4A, OGG, etc.) nécessitent ffmpeg
- **Champ `usage`** : le comptage de tokens retourne toujours 0 (contrainte du NPU Hailo)
