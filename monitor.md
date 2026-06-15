# Patient Monitoring Board

Interface centrée sur un seul patient, accessible depuis la liste des patients.

## Objectif

Fournir une vue clinique unifiée regroupant :
- Les informations générales et biologiques du patient
- L'historique des actions sur le dossier
- Les résultats de prédiction IA (mortalité à 1 an)

## Structure — 3 colonnes

### Colonne 1 — Informations cliniques
- Identité du patient (nom, prénom, ID)
- Données démographiques (âge, sexe, couverture médicale)
- Paramètres biologiques essentiels (albumine, créatinine, PTH…)
- Score de risque à 1 an et zone (Faible / Modéré / Élevé) si une prédiction existe

### Colonne 2 — Historique des actions
- Consultation du dossier
- Ajout ou modification des données
- Lancement de prédictions
- Validations médicales

Affichage selon le rôle :
- **Super Administrateur / Chef de service** : audit complet (utilisateur, rôle, action, horodatage)
- **Professeur / Résident** : timeline simplifiée orientée lecture clinique

### Colonne 3 — Intelligence artificielle
- Score de risque SVM (% probabilité de décès à 1 an)
- Zone de risque (Faible / Modéré / Élevé)
- Top 5 facteurs contributifs (poids SVM)
- Recommandation clinique personnalisée
- Section vide si aucune prédiction n'a encore été lancée

## Principes

- Chargement à la demande après sélection du patient
- Affichage conditionnel selon l'existence des données
- Respect strict des droits d'accès par rôle (RBAC)
- Interface légère, lisible et centrée sur le parcours clinique du patient

## Fichier source

`frontend/src/pages/monitor/MonitorBoard.js`
