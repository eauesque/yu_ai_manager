# LLM Router

> Version cible : v4.55.0 ou ultérieure

## Qu'est-ce que LLM Router

LLM Router est un **proxy LLM compatible avec OpenAI** intégré à yu_ai_manager.  
Il regroupe plusieurs backends LLM locaux tels que Ollama, LM Studio et llama.cpp,  
et les fournit comme un **point d'accès unique** aux clients tels que Claude Code, Continue et Open WebUI.

```
Client (Claude Code / Continue, etc.)
          │  (API compatible avec OpenAI)
          ▼
    yu_ai_manager
    ┌─────────────────────────────────────────┐
    │           LLM Router                   │
    │                                         │
    │  alias: "claude-opus-4-7" ──► large    │
    │  alias: "local-coder" ──► ollama-mac/…│
    │                                         │
    │  [BackendCatalog]                       │
    │   ollama-mac  ─── 192.168.1.10:11434   │
    │   ollama-pi5  ─── 192.168.1.20:11434   │
    │   mdns-win01  ─── Backends détectés automatiquement par mDNS (alias : "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### Capacités

| Caractéristique | Caractéristique |
|---|---|
| **Regroupement de plusieurs backends** | Enregistrez n'importe quel nombre d'instances Ollama sur le LAN |
| **Abstraction par alias** | Masquez les vrais noms de modèles avec `"model": "fast"` |
| **Découverte automatique mDNS** | Enregistrez automatiquement les nœuds yu_ai_manager sur le même LAN sans configuration |
| **Intégration Claude Code** | Implémentez `/v1/messages` compatible avec Anthropic. Aucun proxy supplémentaire nécessaire |
| **Contrôle dynamique activer/désactiver** | Basculez les backends immédiatement depuis l'interface Web. Aucun redémarrage requis |
| **Routage par catégorie** | Sélectionnez automatiquement les modèles optimaux via les backends virtuels `large` / `fast` / `vision` |

---

## Architecture

```
Client (Claude Code / Continue, etc.)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── Résolution d'alias ──► Backend + nom du modèle
    │
    ├─ Backends enregistrés manuellement (écrits dans config.json)
    └─ Backends détectés automatiquement par mDNS (alias : "mdns-<prefix>")
```

**Flux de requête :**

1. Le client demande avec `"model": "claude-opus-4-7"`
2. Le routeur résout `"claude-opus-4-7"` → `"large"` dans la table `aliases`
3. Sélectionnez un backend valide dans la catégorie `large`
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## Index de la documentation

| Caractéristique | Caractéristique |
|---|---|
| [Configuration](setup.md) | Comment écrire config.json, intégration avec Claude Code/Continue, configuration mDNS |
| [Interface Web](webui.md) | Comment utiliser le tableau de bord `/llm-router` |
| [Découverte automatique Hailo](hailo-auto-discovery.md) | Enregistrement automatique des pairs avec Hailo NPU |
| [Gestion des pairs inaccessibles](mdns-peer-unreachable.md) | Dépannage lorsque les pairs détectés par mDNS deviennent `unreachable` |

---

## Gateway Différence avec Gateway

| | LLM Router | Gateway |
|---|---|---|
| **Portée** | LLM uniquement (Ollama, etc.) | SD WebUI, ComfyUI, Ollama ensemble |
| **Limite d'authentification** | Local peut être contourné. api_key requis en dehors du LAN | Authentification Bearer basée sur la portée pour tous les backends |
| **Points de terminaison** | `/v1/*` (compatible avec OpenAI/Anthropic) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **Cas d'usage principal** | Backend pour les outils de codage IA | Exposez en toute sécurité les outils de génération aux clients externes |

Les deux fonctionnalités fonctionnent indépendamment. Si vous utilisez uniquement LLM, LLM Router seul suffit.

---

## Relation avec LAN Cowork

Lorsque [LAN Cowork](../lan-cowork/README.md) est activé,  
les pairs sur le même LAN sont découverts automatiquement via mDNS et enregistrés automatiquement  
dans LLM Router avec des alias comme `mdns-<node_id[:8]>`.  
Un environnement LLM multi-nœuds est mis en place sans configuration.
