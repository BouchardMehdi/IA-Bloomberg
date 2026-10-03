# Priorité de recherche des titres suivis

La page `/analysis` classe désormais les titres suivis avant leurs fiches
documentaires. Le classement est calculé depuis PostgreSQL, sans appel LLM
supplémentaire, nouvelle collecte réseau, modification de portefeuille ou ordre.
Il ne parcourt pas tout le WLS et ne crée aucun titre de démonstration.

## Périmètre et preuves

La fenêtre est de 30 jours glissants, calculés à l'heure UTC de la requête.
Seuls les événements non fusionnés liés aux émetteurs suivis sont candidats.
Chaque rapprochement reprend les [règles des fiches](INSTRUMENT_RESEARCH.md) :
mention résolue du titre et de sa cotation, mention résolue de l'émetteur, ou
contexte documentaire. Les identités ambiguës ou non vérifiées ne suffisent pas.

Les sources doivent être datées et non futures. La récence vient de la plus
ancienne source primaire datée disponible, ou de la plus ancienne source datée
en l'absence de source primaire. Une source secondaire plus récente ne rajeunit
pas le fait. Date de collecte, date de création d'événement et échéance future
ne sont pas utilisées comme date de publication.

Seuls les faits enfants avec une preuve textuelle non vide et une mention résolue
(rôle `subject`, `counterparty` ou `mention`) contribuent au score. Un dépôt SEC,
une publication seule ou un lien `source_subject` ne prouvent pas le rôle de
l'émetteur dans un fait et n'obtiennent aucun point de fait. Les liens et rôles
extraits restent à vérifier dans les documents. Une mention d'émetteur n'établit
pas d'effet sur toutes ses classes d'actions.

Sans CIK connu, la couverture documentaire actuelle reste indisponible pour le
titre ; le classement le signale. Un score nul signifie une absence de faits
exploitables **dans cette couverture**, pas une absence de nouvelles ou de valeur
économique. Les sources internationales restent à raccorder.

## Score explicable de 0 à 100

La méthode `research-priority-v1` utilise des poids fixes, sans score de sentiment,
de confiance ou d'importance attribué par le modèle. Le **type déclaré du fait**
peut provenir d'une extraction déjà réalisée ; il reste provisoire et contrôlable.
Ces poids sont des choix de tri, pas des estimations statistiques de rendement.
Une mauvaise nouvelle peut donc obtenir autant de priorité qu'une bonne nouvelle.

| Critère | Points |
| --- | --- |
| Récence | 30 jusqu'à 48 h ; 20 jusqu'à 7 jours ; 10 jusqu'à 30 jours |
| Précision du lien | 30 pour le titre et sa cotation ; 15 pour l'émetteur |
| Type déclaré | 25 pour résultats, opérations d'entreprise ou procédures ; 15 pour réglementation ; 5 pour les autres types |
| Publications distinctes retenues | 5 chacune, au maximum 15 |

Un seul fait représentatif est retenu par publication parente. Son choix compare
la somme des trois premiers critères, puis sa date et son identifiant. Les trois
publications ayant les représentants les mieux classés sont retenues au maximum.
Les parents déjà regroupés utilisent leur publication conservée comme groupe de
score ; leurs faits restent séparés. La résolution suit au maximum 20 liens de
regroupement. Un groupe non résolu ne contribue pas au score et est signalé.
Si la publication conservée est plus ancienne, sa date sourcée est retenue pour
éviter qu'une republication rajeunisse le fait. `date_reference` conserve l'URL
et la date utilisées, affichées avec le fait ; ses sources de preuve restent distinctes.
Pour chacun des trois premiers critères, le score utilise la meilleure valeur
parmi ces représentants. Il ajoute 5 points par publication retenue. La somme
des quatre contributions correspond exactement au score affiché.

Chaque contribution référence les faits qui la justifient. Les faits présentés
conservent résumé, preuve, relation avec le titre, URL et date des sources.
Les autres faits restent distincts et consultables dans la fiche détaillée :
la sélection pour le score ne les fusionne pas. Plusieurs faits d'un même document
ne gonflent pas le nombre de publications retenues.

Le tri compare score décroissant, date de publication disponible la plus récente,
puis ticker, marché et identifiant interne. Les cours et l'éligibilité WLS ne
modifient pas le score de recherche. Le score ne certifie ni matérialité financière,
fiabilité des rôles, direction du cours, valorisation attractive ou horizon.

## Données et questions à vérifier

Chaque titre affiche séparément l'ancienneté de sa clôture locale, l'état du taux
nécessaire à cette date et son appartenance à l'export WLS. Ces états conservent
leurs sources et dates lorsqu'elles existent. Pour USD, aucun taux FX n'est requis ;
sans cours local, on ne déclare pas un taux exploitable pour une séance inconnue.
Les limites `MARKET_MAX_PRICE_AGE_DAYS` et `MARKET_MAX_FX_AGE_DAYS` restent utilisées.

Les points à vérifier sont des questions générales adaptées au type du fait :
résultats et attentes, conditions de l'opération, portée d'une procédure ou règle.
La couverture partielle, un document tronqué ou une couverture non documentée
sont signalés. Aucun risque propre au titre n'est présenté comme avéré sans source.
Un titre présent au WLS avec des cours disponibles n'est pas automatiquement
achetable : les règles du portefeuille et le règlement restent à appliquer.

## API et bornes

`GET /api/v1/market/research-ranking?limit=20&offset=0` renvoie rang, score,
contributions, faits représentatifs, points à vérifier et états des données.
`limit` vaut 1 à 50 ; `offset` vaut 0 à 20 000. La réponse contient date du calcul,
version de méthode, total des titres suivis et `next_offset`.

Au maximum 2 000 événements candidats sont examinés, avec leurs sources datées,
sans charger le texte intégral des articles. Les candidats sont ordonnés par
date de source, pas par date de création. Si la borne est dépassée,
`coverage.limited=true` et l'interface indique que le classement est partiel :
certains faits et scores peuvent manquer. Même sous la borne, la collecte,
l'extraction et la résolution peuvent être incomplètes.

Les titres sont classés avant pagination ; cours et valorisations sont ensuite
lus uniquement pour la page demandée. Chaque requête recalcule le classement
courant ; il ne s'agit ni d'un instantané historique figé, ni d'un backtest.
Aucune table ni migration supplémentaire n'est nécessaire.

## Vérifications

Les tests unitaires couvrent poids, preuves, dates, classes d'actions, absence
d'inflation par les faits d'un même document, séparation des données et borne API.
Le contrôle PostgreSQL couvre aussi les requêtes JSON, les événements fusionnés,
les exclusions de dates, le WLS par cotation, la pagination et la borne de couverture.
Toutes ses écritures de fixtures sont annulées, même en cas d'échec :

```powershell
docker compose exec backend python -m tests.smoke_research_ranking
```
