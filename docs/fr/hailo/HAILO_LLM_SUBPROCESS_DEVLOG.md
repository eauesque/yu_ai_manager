# Hailo LLM Subprocess GIL Unblock — Journal de Développement d'Implémentation

- **Cible** : Résolution du problème où l'event loop Quart se fige en raison du GIL pendant le cold_load (~71 secondes) du binding Python HailoRT
- **Méthode** : Isolation de l'inférence de chat LLM dans un subprocess sous `core/inference_worker/`
- **spec** : `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **Phases terminées** : 0a / 0b / 1 (vérifiées sur matériel réel)

Ce document résume les défaillances non évidentes et les solutions rencontrées pendant l'implémentation. La chute SSE à 60 secondes en particulier a nécessité un temps d'investigation considérable, c'est pourquoi elle est documentée ici pour éviter que d'autres tombent dans le même piège.

---

## 1. SSE se coupe toujours à 60 secondes ("Stream interrupted: network error")

### Symptôme

La réponse SSE de `/ext/hailo-genai/api/chat/send` entraîne une **déconnexion TCP exactement à 60 secondes**, quelle que soit la situation (cold_load en cours ou génération de tokens).

- Navigateur : `Stream interrupted: network error`
- curl : `curl: (18) transfer closed with outstanding read data remaining`
- Log d'accès : `POST ... 1.1 - - 60236944` (status `-`, durée 60,2 secondes)

Même lorsque les données circulent en continu (p.ex. 30 tok/s), la connexion est interrompue — il ne s'agit donc pas d'un idle timeout.

### Isolation

1. **Se coupe également sur le loopback local** (`http://127.0.0.1:5000/...` avec curl sur le Pi) → pas un problème réseau intermédiaire, mais du côté Pi
2. **Origine du FIN confirmée via Wireshark** — FIN envoyé de 192.168.50.4 (Pi) → 192.168.50.247 (client) à `connection_start + 60.006s`. **Origine côté Pi confirmée**
3. Aucun des timeouts documentés de Hypercorn (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s`, etc.) ne s'applique aux réponses actives

### Cause Racine

**Le paramètre `RESPONSE_TIMEOUT` de Quart (par défaut 60 secondes)**

`quart/asgi.py:117` :

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← après 60s, l'envoi de la réponse est interrompu → TCP close
```

Le paramètre par défaut n'anticipe pas les réponses SSE / streaming de longue durée. `RESPONSE_TIMEOUT=60` est destiné à prévenir les APIs non-streaming incontrôlées, mais est fatal pour SSE.

### Solution

Définir une **substitution de timeout par réponse** sur l'objet `Response` de Quart :

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

La valeur par défaut de `Response.timeout` est `Ellipsis`, et `app.config["RESPONSE_TIMEOUT"]` n'est utilisé que lorsque la valeur est `Ellipsis` (`asgi.py:112-115`). Définir explicitement `None` désactive le timeout entièrement.

**Commit de correction** : `b35ed46cc`

Emplacements appliqués :
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — streaming compatible OpenAI (×2)

Les routes non-SSE ne sont pas touchées (le timeout de 60 secondes y est utile comme mécanisme de protection).

### Leçons Apprises

- **Le `RESPONSE_TIMEOUT` de Quart est fatal pour SSE**. Lors de l'ajout d'un nouvel endpoint SSE, toujours définir `resp.timeout = None`.
- Quand "les données circulent mais la connexion est interrompue", ne pas suspecter un idle timeout. Suspecter une durée maximale fixe.
- La méthode la plus rapide d'isolation est de **regarder l'IP d'origine du FIN dans Wireshark**. Avec tcpdump, le filtre `tcp[tcpflags] & tcp-fin != 0` fonctionne aussi.

---

## 2. Keepalive SSE pendant cold_load (Mesure préventive indépendante du problème des 60 secondes)

### Prévention des Symptômes

Même après avoir désactivé `RESPONSE_TIMEOUT`, il existe toujours la possibilité séparée que les **réseaux intermédiaires (routeurs grand public / pare-feux / APIs stream des navigateurs)** coupent les connexions idle de longue durée. Les ~71 secondes de silence pendant cold_load peuvent être jugées "mortes" par les équipements intermédiaires.

### Contre-mesure

Envelopper `HailoLLMSubprocessClient.stream()` avec `stream_with_keepalive()` pour envoyer des **événements de données keepalive à intervalles de 5 secondes** :

```python
async def stream_with_keepalive(async_iter, ping_interval: float = 5.0):
    ...
    while True:
        next_task = asyncio.ensure_future(it.__anext__())
        try:
            while True:
                try:
                    value = await asyncio.wait_for(asyncio.shield(next_task), timeout=ping_interval)
                    yield ("token", value)
                    break
                except asyncio.TimeoutError:
                    yield ("ping", None)   # keepalive après 5s de silence
```

Quand la route reçoit `("ping", None)`, elle émet `data: {"keepalive": true}\n\n`. Le client (chat UI) ignore silencieusement les événements qui ne correspondent pas à `d.token` / `d.error` / `d.done`.

### Pourquoi utiliser des événements `data:` plutôt que des commentaires SSE (`: keepalive`)

`: keepalive\n\n` (commentaire SSE) a d'abord été essayé, mais s'est révélé inefficace dans l'environnement de test. Le passage à `data: {"keepalive":true}` (vrai événement de données) a résolu le problème. Bien que les commentaires SSE soient valides selon la spécification, certains équipements intermédiaires et implémentations de navigateurs traitent les lignes de commentaires comme des "métadonnées ignorables" et jugent quand même la connexion comme idle lorsqu'aucune donnée réelle n'arrive. Les vrais événements sont plus universellement compatibles.

**Commits de correction** : `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. Le Subprocess Worker se termine immédiatement après le démarrage en boucle

### Symptôme

`logs/inference_worker.log` :

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← arrêt normal après 2 secondes
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

Le worker démarre, "s'arrête proprement" après 2 secondes, le processus parent détecte `is_alive=False` → redémarre 3 fois et abandonne ; le pool d'auto-redémarrage est épuisé.

### Cause Racine

La boucle principale de `worker_process.worker_main` :

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` retourne `None` quand aucune tâche n'est disponible. Ceci était traité de la même manière que `ShutdownSentinel`, provoquant un break. Le worker attend 2 secondes pour une tâche → l'obtention échoue, retourne `None` → mal interprété comme une "commande de shutdown" → break → le parent détecte `is_alive=False` → boucle de redémarrage.

### Solution

```python
if task is None:
    continue                            # timeout → continuer le polling
if isinstance(task, ShutdownSentinel):
    break                                # break uniquement sur shutdown explicite
```

**Commit de correction** : `af19f16de`

### Leçons Apprises

- `None` de `multiprocessing.Queue.get(timeout=...)` signifie "timeout", pas "fin de la queue". "Fin de la queue" doit être exprimé via un sentinel explicite comme `ShutdownSentinel`. Ne pas confondre les deux.

---

## 4. Le Worker ne peut pas lancer le Subprocess interne de hailo_platform car daemon=True

### Symptôme

Log `Worker crashed` au premier chat sur matériel réel. Cause inconnue car pas de capture stderr.

### Hypothèse de Cause Racine

`bridge.start()` :

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← problème
    ...
)
```

`multiprocessing.Process(daemon=True)` tue automatiquement les enfants quand le parent se termine, mais **les processus démonisés ne peuvent pas spawner leurs propres processus enfants** (`AssertionError: daemonic processes are not allowed to have children`). Cela échoue si HailoRT lance en interne un quelconque processus ou thread auxiliaire.

### Solution

```python
daemon=False
```

À la place, appeler explicitement `inference_bridge.stop(timeout=5.0)` dans `@app.after_serving` pour un arrêt propre.

**Commit de correction** : `cf49a42a2` (combiné avec l'ajout de diagnostics de logging du worker)

### Leçons Apprises

- Les subprocesses utilisant des bibliothèques basées sur des extensions C comme HailoRT doivent utiliser `daemon=False`.
- Le nettoyage des subprocesses doit être effectué explicitement dans `@app.after_serving`.

---

## 5. La sortie stderr / logger du Subprocess Worker spawné n'est pas capturée

### Symptôme

Les tracebacks d'exception à l'intérieur du subprocess worker **ne sont conservés nulle part**. stdout/stderr n'est pas routé vers le processus parent, et la configuration du logger n'est pas héritée (une caractéristique de spawn).

### Solution

Attacher un **handler de logging dédié** au début de `worker_main` :

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

De plus, envelopper tout `worker_main` avec `try/except BaseException: logger.critical(traceback.format_exc())` pour capturer aussi les erreurs à l'import.

**Commit de correction** : `cf49a42a2`

### Leçons Apprises

- `multiprocessing.get_context("spawn").Process` n'hérite pas de la configuration de logging du parent. **La configurer explicitement du côté spawné**.
- Les exceptions dans les threads daemon sont aussi avalées silencieusement par défaut (comportement par défaut de `threading.Thread`). Ajouter try/except + log dans les control daemons également.

---

## 6. Le timeout inter-token de bridge.iter_stream est trop court pour cold_load

### Symptôme

Au premier chat, `[WARN] Stream timeout for task ...` apparaît dans le log, et SSE se termine avant que les tokens n'arrivent.

### Cause Racine

Le timeout de `queue.get` dans `bridge.iter_stream` était **fixé à 10 secondes**, de sorte que le premier token n'arrive pas pendant cold_load (71 secondes), déclenchant un timeout.

### Solution

Conformément à la politique de la spec §3.4 :

- `first_token_timeout = 120.0` (cold_load 71s + 50s de marge)
- `inter_token_timeout = 30.0` (intervalle maximum entre tokens)
- Passer à un timeout court après réception du premier token

**Commit de correction** : `35d556150`

---

## 7. handler_hailo_llm saute la normalisation du Prompt, causant une HailoRT InvalidOperation

### Symptôme

`HailoRTInvalidOperationException` lors du deuxième envoi de chat et des suivants. Log HailoRT :

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### Cause Racine

Le handler du subprocess passait les messages bruts directement à `llm.generate(prompt=messages)`, sautant le prétraitement de `HailoLLM._prepare_prompt` dans le processus interne :

- L'aplatissement du contenu structuré `[{"type":"text","text":"..."}]` → string plat manquait
- La suppression du rôle système lors de la continuation du contexte (à partir du tour 2) manquait

Le template de chat HailoRT suppose ces deux transformations.

### Solution

Partager `_normalise_prompt` via import commun + supprimer le rôle système lors de la continuation du contexte :

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**Commit de correction** : `cdd9e26fe`

### Leçons Apprises

- Lors de l'implémentation des deux chemins (en processus et subprocess), confirmer au moment de la conception que le pré/post-traitement effectué côté en processus est **appliqué également sur les deux chemins**. Comme pour la contre-mesure de division d'état parent-enfant du device_manager dans spec §3.5, la factorisation en bibliothèque partagée est préférable.

---

## 8. L'annulation pendant cold_load est retardée par une condition de course

### Symptôme (Latent)

Pendant cold_load (71s), l'extension C HailoRT maintient le GIL, empêchant le thread du control daemon du worker de s'exécuter. Par conséquent, `ControlMessage(op="cancel")` lors d'une déconnexion utilisateur n'est pas traité. Si `generate()` est appelé immédiatement après la fin de cold_load, la génération de tokens commence pour une tâche abandonnée.

### Solution

Après la fin de `acquire_genai()`, attendre 50ms → donner au control daemon le temps de traiter les annulations en attente → vérifier `cancel_flags[task_id]` → si True, sauter generate() :

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**Commit de correction** : `5fbb02d95`

---

## 9. Aucun chemin de code en production n'appelle inference_worker.start()

### Symptôme

Même avec `hailo_genai.llm_subprocess: true` dans la configuration, l'envoi d'un message de chat résulte en `RuntimeError("Failed to submit LLM task to worker")`.

### Cause Racine

Seul `bind_event_loop(loop)` était exécuté dans `@app.before_serving` ; l'appel critique à `inference_bridge.start(db_path, config)` **n'existait pas en production**. Le processus worker n'était jamais spawné.

### Solution

Exécuter `start()` → `bind_event_loop()` dans l'ordre dans `@app.before_serving`, et `stop()` dans `@app.after_serving` :

```python
@app.before_serving
async def start_inference_bridge() -> None:
    from core.inference_worker.bridge import inference_bridge
    from core.services_core.db_state import get_db_path
    inference_bridge.start(str(get_db_path()), config)
    inference_bridge.bind_event_loop(asyncio.get_running_loop())

@app.after_serving
async def stop_inference_bridge() -> None:
    inference_bridge.stop(timeout=5.0)
```

**Commit de correction** : `9053f2f72`

---

## Liste Complète des Corrections (Chronologique)

| Commit | Description |
|--------|-------------|
| `9053f2f72` | Appeler inference_bridge.start() dans app.before_serving |
| `cf49a42a2` | Diagnostics de logging du worker + daemon=False + rétention de db_path pour auto-redémarrage |
| `af19f16de` | Corriger le timeout de queue en continue |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | Introduire le commentaire keepalive SSE |
| `cdd9e26fe` | Ajouter la normalisation de prompt au handler |
| `213b9c962` | Intervalle keepalive 15s → 5s + logs de diagnostic |
| `dff60989c` | Convertir keepalive de `: comment` → événement `data:` |
| `b35ed46cc` | **Désactiver Quart RESPONSE_TIMEOUT 60s pour SSE (correction de la cause racine)** |
| `5fbb02d95` | Vérification anticipée de l'annulation après cold_load |

---

## Documents Associés

- Spec principale : `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- Associé (REJECTED) : `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak : `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice sharing : `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
