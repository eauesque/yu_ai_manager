# Spécification d'accès MCP LAN et point de terminaison Help

**Version d'implémentation** : 3.1.0
**Documentation connexe** : `docs/en/features/mcp-integration-guide.md`
**Fichiers connexes** : `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## Aperçu

1. **Accès MCP LAN** — Permettre aux clients MCP sur le LAN de se connecter au point de terminaison MCP par adresse IP quand le mode partage LAN est activé
2. **Point de terminaison `/help`** — Fournir un manuel web intégré pour l'application (également publié en tant que ressource MCP)

---

## 1. Accès MCP LAN

### 1-1. Architecture

Sur le LAN, les clients MCP se connectent directement au point de terminaison YU AI Manager `/mcp` en utilisant le transport HTTP/SSE.

### 1-2. Point de terminaison MCP SSE

| Élément | Détails |
|------|------|
| Point de terminaison | `/mcp` (SSE + envoi de messages) |
| Transport | HTTP + Server-Sent Events (SSE) |
| Authentification | Non requise depuis localhost. Clé API requise depuis les IP LAN |

### 1-3. Authentification par clé API

Le mécanisme de gestion des clés API existant (`/api/keys`) est réutilisé.

### 1-4. Interface utilisateur des paramètres

Un extrait de configuration de connexion MCP LAN (version HTTP) est ajouté à l'onglet Paramètres > Clés API.

---

## 2. Point de terminaison `/help`

### 2-1. Principes de conception

- Complètement hors ligne
- Double usage en tant que ressource MCP
- Aucune authentification requise

### 2-2. Points de terminaison

| Point de terminaison | Contenu |
|----------------|------|
| `GET /help` | Page de couverture du manuel |
| `GET /help/<section>` | Page spécifique à la section |
| `GET /api/help/toc` | JSON de la table des matières |
| `GET /api/help/content/<section>` | JSON du corps de la section |

### 2-3. Outils MCP

- `help_search` : Recherche par mot-clé
- `help_get_section` : Récupération de la section
