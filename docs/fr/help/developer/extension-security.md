# Modèle de sécurité des Extensions

Ce logiciel se caractérise par sa capacité à permettre « à n'importe qui de créer des Extensions avec l'IA ».
En même temps, un mécanisme est intégré pour protéger votre système contre les Extensions malveillantes.

Cette page explique ce mécanisme.
Elle est écrite pour être compréhensible même sans être technicien.

---

## Concept de base

Les Extensions fonctionnent dans un **monde protégé**.

Dans ce monde protégé, les Extensions peuvent se comporter relativement librement.
Ajouter des pages, afficher des données, traiter des images — c'est le travail des Extensions.

Cependant, ce qui se trouve **en dehors** du monde protégé — le cœur du système (core), les autres Extensions, tous les fichiers de votre PC — est hors de portée.
Ce n'est pas « interdit par règle », mais une structure où **physiquement inaccessible**.

---

## Mécanisme des permissions

Les Extensions ont besoin de **permissions** pour faire quoi que ce soit.

Les permissions sont conçues selon le même modèle que les permissions d'applications sur smartphone.

- Il est normal qu'une application appareil photo demande l'accès à l'appareil photo
- Il est anormal qu'une application appareil photo demande l'accès aux contacts

Les Extensions sont pareil. Si une Extension ajoutant des filigranes aux images demande l'accès réseau, il faut s'en méfier.

### Flux d'approbation

1. Installer l'Extension (ou la faire créer par une IA)
2. YU AI Manager scanne automatiquement le code et inspecte ce qu'il essaie de faire
3. La liste des permissions demandées par l'Extension s'affiche
4. **L'Extension ne fonctionne pas jusqu'à ce que vous l'approuviez**

Lisez attentivement les informations affichées à l'écran d'approbation.
Portez une attention particulière aux permissions affichées en rouge.

### Après l'approbation des permissions

L'Extension fonctionne dans le cadre des permissions approuvées.
Les permissions non approuvées ne peuvent pas être utilisées, peu importe les efforts de l'Extension.
Ce n'est pas « refusé quand essayé », mais « tout simplement invisible ».

---

## 3 surveillances indépendantes

Votre Extension est surveillée par 3 mécanismes indépendants.
Ces 3 mécanismes sont indépendants les uns des autres ; si l'un est trompé, les 2 autres fonctionnent.

### 1. Scan du code

Le code de l'Extension est automatiquement analysé pour détecter les patterns dangereux.
Exécution de programmes externes, manipulation directe de la base de données, exécution de code dynamique — ceux-ci sont détectés instantanément.

### 2. Contrôle des permissions

Quand une Extension appelle une API, on vérifie qu'elle possède une « licence » valide.
Les licences ne sont émises que lorsque vous approuvez les permissions.
L'Extension elle-même ne peut pas falsifier les licences.

### 3. Journal d'audit

Toutes les opérations de l'Extension sont enregistrées.
Ces enregistrements sont sauvegardés dans un endroit indépendant que l'Extension elle-même ne peut pas modifier.

En cas de détection d'anomalie — par exemple si elle essaie un comportement non déclaré — une notification arrive automatiquement, et si nécessaire, la licence de l'Extension est invalidée.

---

## Créer des Extensions avec l'IA

Quand vous créez des Extensions depuis Claude Desktop, les Extensions créées sont automatiquement enregistrées au **niveau de restriction le plus élevé**.

C'est comme ne pas donner la clé du coffre-fort à un nouvel employé dès le premier jour.
Faites d'abord fonctionner avec des permissions limitées, vérifiez qu'il n'y a pas de problème, puis ajoutez des permissions si nécessaire.

### Ce que peut faire une Extension créée par IA

**Utilisable sans approbation :**
- Affichage en lecture seule des données
- Ajout de pages à l'UI
- Ajout d'écrans de paramètres

**Nécessite une approbation :**
- Communication avec des services externes
- Écriture dans la base de données
- Lecture de fichiers

**Impossible peu importe ce qui est fait :**
- Lecture ou modification du cœur du système (core)
- Lecture ou modification des autres Extensions
- Exécution de programmes externes
- Falsification des licences

---

## Inspections régulières

Une fois approuvée, ce n'est pas la fin.

Si le code est modifié et que la quantité de changements dépasse un certain seuil, une **re-approbation** est demandée.
C'est pour prévenir la technique de modifier un peu à la fois jusqu'à ce que l'on réalise que c'est devenu quelque chose de complètement différent.

De plus, une réinspection périodique du code est exécutée automatiquement.
Même s'il n'y avait pas de problème au moment de l'approbation, des problèmes peuvent être trouvés avec de nouvelles règles d'inspection.

---

## Ce que vous devriez faire

1. **Lisez correctement l'écran d'approbation des permissions** — Comprenez ce qui est demandé avant d'approuver
2. **Refusez les demandes de permissions anormales** — Le réseau n'est pas nécessaire pour le traitement d'images
3. **Ne pas ignorer les notifications** — Vérifiez quand une anomalie est détectée
4. **Ne pas installer d'Extensions de sources non fiables** — C'est évident

En revanche, si vous faites cela, vous êtes en sécurité.
Le reste, c'est le mécanisme qui vous protège.
