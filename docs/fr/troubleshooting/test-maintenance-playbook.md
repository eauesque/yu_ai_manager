# Playbook de Maintenance des Tests

Résumé des points à regarder en priorité quand pytest s'arrête sur une base de tests ancienne ou une dépendance d'environnement.

## Objectif

- Distinguer `failed` et `skipped`
- Distinguer les skips normaux liés à l'environnement et les tests obsolètes à réparer
- Fixer le chemin le plus court quand `pytest tests -q --maxfail=1` (broad run) s'arrête

## Commandes de Base

Vérification globale normale :

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

Vérifier aussi les raisons de skip :

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

Traiter le shared test server en strict :

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

Audit de licence :

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## Comment Lire les Skips Actuels

Dans le broad run au 2026-04-21, les causes principales de skip se concentrent sur les 5 familles suivantes.

### 1. Shared Test Server Non Démarré

Skip le plus fréquent. Le shared server de `tests/conftest.py` est en démarrage best-effort ; s'il ne peut pas démarrer, le groupe dépendant de browser/server est rabaissé en skip au lieu de fail.

Raisons représentatives :

- `Shared test server unavailable on port <PORT>`

Cibles principales :

- `tests/api/`
- Tests de browser UX review
- Tests dépendants de browser/server pour LAN Cowork / Fleet
- Tests de browser live utilisant `TARGET_URL` / `BASE` / `TARGET`
- Tests d'audit utilisant leur propre fixture Playwright/WebKit plutôt que la fixture `page`

Dans un run normal, c'est un **skip normal**. Mais à investiguer si :

- Des unit tests non dépendants du shared server deviennent skip pour la même raison
- Un test shared server qui passait avant devient soudainement un grand nombre de skips
- La cause ne se voit pas même avec `PYTEST_STRICT_AUTOSTART_SERVER=1`

### 2. Tests Spécifiques à l'OS

Groupes sandbox / AppArmor / isolation de processus réservés à Linux. Skip correct sur Windows.

Exemples représentatifs :

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

Raisons représentatives :

- `Linux only`
- `AppArmor est réservé à Linux`

C'est un **skip normal**.

### 3. Dépendances Optionnelles ou Composants Externes Manquants

Groupes de tests qui ne s'exécutent pas sans certains paquets ou nœuds externes.

Exemples représentatifs :

- E2E mDNS avec matériel réel : `optional zeroconf package is not installed`
- Lancement de browser : `Playwright unavailable`, `launch failed`
- ONNX / YAML / ComfyUI / nœud d'inférence externe non connecté

C'est un **skip normal**. Pas cible de réparation, juste l'environnement prérequis absent.

### 4. Manque de Données de Test

Tests browser nécessitant des images / résultats de recherche / logs de conversation / données multiples ; skip car non satisfait par une DB légère.

Raisons représentatives :

- `No search results available in database`
- `Skip car pas d'image dans la DB`
- `Au moins 2 fichiers requis`
- `No prompts to test copy`

C'est **globalement un skip normal**. Cependant, si la fixture devrait préparer les données nécessaires, suspecter une obsolescence.

### 5. Protection de Limite de Taux / API Externes

Une partie des intégrations skip en respect des services externes ou limites de taux.

Exemple représentatif :

- `Skip pour limite de taux atteinte`

C'est un **skip normal**.

### 6. Fuzz / Burn-in Longue Durée

Le burn-in sous `tests/fuzz/` sert à vérifier la résistance et la tolérance aux crashes, pas à la vérification de régression normale.

Par défaut, exclu via l'expression marker de `pytest.ini`.

Pour l'exécuter :

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

Si nécessaire :

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

**À ne pas mélanger au broad run normal**.

## Patterns à Traiter Comme Anormaux

Ne pas expédier comme « c'est un skip donc pas de problème » ; les traiter comme cibles de maintenance de tests.

### A. Un test léger qui passait avant tombe en setup skip

Exemples :

- API smoke censé se terminer sur fixture app/client tombe dans le prérequis shared server
- Unit test migration / schema / DB helper tombe sur prérequis d'initialisation runtime global state

Dans ce cas, suspecter un écart de prérequis entre test harness et implémentation.

### B. Le broad run passe, mais l'exécution isolée tombe

Exemples typiques :

- Dépend du process-global state
- Repose par hasard sur l'effet secondaire d'un test précédent initialisé pendant le broad run

Ramener aussi l'exécution isolée à un état reproductible.

### C. Raison de Skip Ambiguë

Mauvais exemples :

- `failed`
- `not ready`
- `something wrong`

La raison de skip doit indiquer en texte court « qu'est-ce qui manquait pour sauter ».

## Ordre de Priorité des Réparations

1. Réparer les hard failures qui arrêtent le broad run
2. Réparer les stale tests qui cassent seulement en exécution isolée
3. Ramener les skips shared server / browser à des skips sûrs plutôt que fail
4. Maintenir les optional skips pour les dépendances optionnelles et machine réelle

## Ce qui a Été Fixé dans Cette Maintenance

- Les dépendants browser/server unifient shared server unavailable en skip plutôt que fail
- L'audit de licence ne regarde que les dépendances déclarées dans `requirements*.txt`, pas tout le venv
- La test DB satisfait le prérequis path FTS du schéma de recherche actuel
- Les migrations 54 / 55 corrigées pour ne pas être fragiles à l'évolution du base schema ou à l'état runtime non initialisé

## Critères de Décision en Cas de Doute

- Si seul l'environnement prérequis est absent, skip convient
- Si c'est une ancienne attente n'ayant pas suivi l'implémentation actuelle, corriger le test
- Si cela dépend de l'effet secondaire du broad run, corriger l'implémentation ou le test
- Si un unit test exige un process-global state, suspecter le design
