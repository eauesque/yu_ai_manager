# Exemples de prompts de triage GitHub

Les prompts de triage sont les instructions envoyées à l'IA pour classer les issues / PR / discussions GitHub. Ils peuvent être librement modifiés dans **GitHub Integration > Settings > Triage Prompts**.

Copiez et personnalisez les exemples suivants.

---

## Prompts pour Issues

### Par défaut (anglais, strict)

```
Review the following GitHub issue and determine whether it is a technically valid bug report.

Valid (valid) criteria:
- Concrete reproduction steps are provided
- Error log or stack trace is included
- Environment info (OS, version, etc.) is present

Invalid (invalid) criteria:
- Emotional text only, no technical facts
- Feature request, not a bug
- Written in a language other than English
- No actionable technical information

Return your verdict (valid / invalid) and the reason.
```

### Version française

```
Examinez l'issue GitHub suivante et déterminez si elle constitue un rapport de bug techniquement valide.

Critères valides (valid) :
- Les étapes de reproduction sont décrites concrètement
- Un log d'erreur ou une trace de pile est inclus
- Les informations d'environnement (OS, version, etc.) sont présentes

Critères invalides (invalid) :
- Texte émotionnel uniquement, sans faits techniques
- Demande de fonctionnalité, pas un bug
- Aucune information technique exploitable

Retournez votre verdict (valid / invalid) et la raison.
```

### Critères souples (accepte aussi les demandes de fonctionnalités)

```
Classifiez l'issue GitHub suivante.

Catégories :
- valid_bug : Il y a des étapes de reproduction, des informations d'erreur, ou une description claire d'un comportement inattendu.
- feature_request : Demande de nouvelle fonctionnalité ou d'amélioration. Traiter comme valide.
- needs_info : Potentiellement valide mais manque d'informations importantes. Traiter comme valide avec une note.
- invalid : Spam, hors sujet, ou texte émotionnel uniquement sans contenu technique.

Retournez la catégorie et la raison en une ligne.
```

### Strict (axé sécurité)

```
Évaluez cette issue GitHub du point de vue de l'impact sécurité et de la validité technique.

CRITICAL (action immédiate) :
- Rapports de vulnérabilité sécurité, fuite de données, contournement d'authentification
- Contient des détails PoC ou d'exploitation

VALID (bug ordinaire) :
- Bug technique avec étapes de reproduction et preuves d'erreur

INVALID (à rejeter) :
- Demandes de fonctionnalités, questions, insatisfaction émotionnelle, hors anglais, sans faits techniques

Retournez CRITICAL / VALID / INVALID et la raison.
Si CRITICAL, indiquer qu'une revue humaine immédiate est nécessaire.
```

### Multilingue (accepte les langues non-anglaises)

```
Quelle que soit la langue, déterminez si cette issue GitHub est un rapport de bug valide.

Valide : Des étapes de reproduction, des logs d'erreur, ou une description technique claire dans n'importe quelle langue.
Invalide : Émotionnel uniquement, spam, sans contenu technique.

Retournez le verdict et la raison en anglais.
```

---

## Prompts pour PR

### Par défaut (tout rejeter)

```
Do not accept pull requests. Close automatically.
```

### Acceptation avec revue

```
Reviewez la qualité du code et la pertinence de cette pull request.

Acceptable (valid) :
- Correction d'un bug documenté ou réponse à une issue ouverte
- Code conforme aux conventions du projet
- Inclut des tests ou un plan de test

À rejeter (invalid) :
- Changements sans rapport ou extension du périmètre
- Pas de référence à une issue
- Casse des fonctionnalités existantes

Retournez accept / reject et la raison.
```

### Accepter uniquement les corrections de bugs

```
Accepter uniquement les pull requests de correction de bug.

Valide : Référence à une issue ouverte, correction ciblée, périmètre minimal.
Invalide : Ajout de fonctionnalités, refactoring, documentation uniquement, changements sans rapport.

Retournez le verdict et la raison.
```

---

## Prompts pour Discussions

### Par défaut (tout fermer)

```
Discussions are closed. No action required.
```

### Surveillance des rapports de bugs

```
Vérifiez si cette Discussion contient un bug non encore signalé.

Si un bug reproductible avec des détails d'erreur est décrit,
le signaler comme "potential_bug" pour la création d'une issue.
Sinon, "no_action".

Retournez potential_bug / no_action et la raison.
```

### Engagement communautaire

```
Classifiez cette Discussion :

- question : Utilisateur cherchant de l'aide. Si la documentation a une réponse claire, répondre.
- bug_report : Description d'un bug. Signaler pour création d'issue.
- feature_idea : Proposition de fonctionnalité intéressante. Signaler pour revue.
- off_topic : Sans rapport avec le projet. Aucune action nécessaire.

Retournez la catégorie et l'action recommandée (le cas échéant).
```
