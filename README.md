# ENTA Student Space – Dakhla

Portail étudiant Flask organisé autour des 7 matières suivantes :
1. Introduction aux sciences de l’ingénieur et aux technologies avancées
2. Mathématiques pour l’ingénieur
3. Physique pour les technologies avancées
4. Algorithmique et programmation Python
5. Outils numériques, programmation collaborative et culture digitale
6. Communication scientifique (Français) et culture académique
7. Développement personnel, méthodologie universitaire et soft skills

Chaque matière possède exactement trois rubriques : **Cours**, **TD** et **Corrigés**.
L'administrateur peut sélectionner plusieurs PDF et les publier en une seule opération.
Les étudiants peuvent ouvrir ou télécharger chaque document. Il n'y a pas de rubrique Contrôles.

## Installation Windows

```bat
py -m venv .venv
.venv\\Scripts\\activate
py -m pip install -r requirements.txt
py app.py
```

Ouvre ensuite http://127.0.0.1:5000 et crée le compte Admin une seule fois via
http://127.0.0.1:5000/setup. Le mot de passe doit contenir au moins 10 caractères.

## Ajouter les PDF

1. Connecte-toi sur `/admin/login`.
2. Dans « Publier des PDF pour une matière », sélectionne la matière.
3. Choisis Cours, TD ou Corrigés.
4. Sélectionne un ou plusieurs fichiers PDF en même temps.
5. Clique sur « Publier les PDF sélectionnés ».

Les documents sont enregistrés dans `static/uploads` et leurs informations dans `enta.db`.
Sauvegarde ces deux éléments régulièrement.

## Déploiement

Avant toute publication en ligne, configure `ENTA_SECRET_KEY`, HTTPS et un serveur WSGI de production.
Le serveur Flask intégré est destiné au développement.
