# Directives de Sécurité de l'API

Utilisez ce document chaque fois que vous ajoutez ou modifiez un point de terminaison d'API.

## Première décision

Chaque point de terminaison doit être classé d'emblée comme l'un des suivants:

- `public`
- `session/user`
- `admin`
- `localhost-only`

Si vous n'êtes pas sûr, choisissez `admin`.

## Règles fondamentales

1. Ne supposez pas que `GET` est sûr.
2. Les `read-only API keys` sont destinées aux lectures simples uniquement.
3. Les chemins internes, inventaires, historique, contenu, journaux et résultats d'analyse sont `admin`.
4. Les vérifications localhost doivent utiliser des aides conscientes du proxy.
5. Les points de terminaison de configuration nécessitent des listes blanches et une validation stricte.
6. Les secrets doivent être chiffrés et expurgés via des aides partagées.

## Non sécurisé pour les clés en lecture seule

- chemins internes
- inventaires d'ID de fichier/membre
- prompts, annotations, transcriptions, journaux de discussion
- résultats OCR / analyse
- file d'attente, historique, audit, approbation, planificateur, état d'erreur de balayage
- état du backend d'extension / profil / sauvegarde / webhook / secret
- résultats récupérés avec des identifiants tiers stockés

## Vérifications localhost

N'utilisez pas directement:

```
request.remote_addr == "127.0.0.1"
```

Utilisez plutôt les aides existantes:

- `get_client_ip()`
- `is_local_request()`
- `is_loopback_request()`

## Règles de point de terminaison de configuration

Requis:

- liste blanche de clés
- validation de type stricte
- validation de plage / énumération / URL
- expurgation des secrets lors des lectures
- stockage chiffré pour les secrets

Interdit:

- `config.update(...)` aveugle
- `bool(value)` pour les booléens de demande
- fusions génériques qui contournent la gestion des secrets

## Secrets

- ne retournez jamais les valeurs de secret actuelles
- n'incluez jamais tokens/en-têtes/blobs secrets dans les points de terminaison de liste
- ne remplacez jamais les secrets existants par des espaces réservés masqués
- utilisez toujours un stockage dédié ou une aide partagée

## Demandes sortantes des APIs

Ne faites pas de sondes en amont ou d'extractions de découverte à partir de points de terminaison `GET`.

Si cela ne peut être évité:

- requiert `admin`
- gardez les délais d'expiration courts
- bloquer localhost / IP privée / cibles de métadonnées

## Tests minimaux

Pour les points de terminaison sensibles, ajoutez:

1. `read-only key -> 403`
2. `admin key -> 200`
3. `invalid input -> 400`
4. vérifications d'expurgation des secrets
5. tests de régression localhost conscients du proxy le cas échéant

## Liste de contrôle d'examen

- Est-ce que ce `GET` est vraiment sûr pour l'accès public/lecture seule?
- Expose-t-il des chemins, des inventaires, des prompts, des transcriptions, un historique ou des métadonnées brutes?
- Divulgue-t-il des secrets?
- Utilise-t-il des aides conscientes du proxy?
- Évite-t-il la coercition booléenne implicite?
- Évite-t-il les fusions de configuration aveugles?
- Évite-t-il les demandes sortantes involontaires?
- Comprend-il des tests de régression d'étendue administrative?

Politique par défaut: commencez étroit, puis ouvrez délibérément uniquement si nécessaire.
