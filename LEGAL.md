# Mentions légales & usage responsable

> Ce document complète le [README](README.md) et la [LICENSE](LICENSE). Il décrit le cadre d'utilisation de **Subtext AI**, les limites de l'analyse et le traitement des données. Il ne constitue pas un avis juridique.

## 1. Avertissement sur l'analyse (non professionnelle)

Subtext AI produit une analyse **générée automatiquement par un modèle de langage (IA)**. Les résultats (score de tension, émotion, manipulation, dynamique de pouvoir, intention) sont :

- **indicatifs et faillibles** : un modèle de langage peut se tromper, inventer ou biaiser son analyse ;
- **sans valeur médicale, psychologique, clinique ou judiciaire** ;
- **non constitutifs d'un avis professionnel**.

Ils ne doivent **jamais** servir à diagnostiquer, évaluer ou prendre une décision concernant une personne réelle (recrutement, santé, justice, relations, etc.). Pour toute question relevant de la psychologie ou du droit, consultez un professionnel qualifié.

## 2. Transparence (IA & reconnaissance d'émotions)

Conformément à l'esprit du **règlement européen sur l'IA (AI Act)** :

- l'utilisateur est informé qu'il interagit avec un **système d'intelligence artificielle** ;
- l'outil réalise une forme de **reconnaissance d'émotions et de profilage** sur des dialogues, à des fins d'analyse narrative et éducative uniquement ;
- l'usage de ces techniques pour évaluer ou surveiller des **personnes physiques réelles** (notamment au travail, en éducation ou par les autorités) est encadré, voire interdit, par la réglementation. L'outil est destiné à l'analyse de **dialogues de fiction / contenus dont l'utilisateur dispose des droits**, pas à la surveillance de personnes.

## 3. Droits d'auteur sur les fichiers importés

Les fichiers de sous-titres (`.srt`) issus de films, séries ou autres œuvres sont généralement **protégés par le droit d'auteur**. En important un fichier, l'utilisateur **garantit disposer des droits nécessaires** (œuvre personnelle, contenu libre de droits, usage privé autorisé, etc.). L'auteur de Subtext AI **décline toute responsabilité** quant à l'usage de contenus protégés par les utilisateurs.

## 4. Données personnelles (RGPD)

Subtext AI est conçu pour fonctionner **100 % en local** :

- **Aucune transmission externe** : le contenu des fichiers et les analyses ne quittent pas la machine ; le traitement IA s'effectue via Ollama sur `localhost`. Aucune API tierce n'est appelée.
- **Stockage local** : les analyses sont conservées dans une base **SQLite locale** (`subtext.db`), non versionnée (exclue par `.gitignore`). Sont stockés : le nom du fichier, un horodatage, une empreinte MD5 du contenu et le résultat JSON de l'analyse.
- **Responsable de traitement** : l'utilisateur qui exécute l'application est seul responsable des éventuelles données personnelles qu'il choisit d'y soumettre.

### Minimisation, conservation et droit à l'effacement

- Ne soumettez **pas** de données personnelles ou sensibles réelles si ce n'est pas nécessaire.
- Aucune purge automatique n'est appliquée : les données restent jusqu'à suppression manuelle.
- **Droit à l'effacement** : les analyses peuvent être supprimées à tout moment via l'API —
  - `DELETE /history` : efface **toutes** les analyses ;
  - `DELETE /history/{id}` : efface une analyse précise ;
  - ou, plus radicalement, en supprimant le fichier `subtext.db`.

## 5. Limitation de responsabilité

Le logiciel est fourni « **en l'état** », sans garantie d'aucune sorte (voir la [LICENSE](LICENSE) MIT). L'auteur ne saurait être tenu responsable des décisions prises sur la base des analyses produites, ni de l'usage de contenus protégés ou de données personnelles par les utilisateurs.

## 6. Contact

Projet académique — Thomas Ferriere. Pour toute question relative à ce document, ouvrez une *issue* sur le dépôt.
