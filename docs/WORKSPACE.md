# Alertes, imports et espace partagé

## Alertes persistantes

`/alerts` expose publications rapprochées des titres suivis, faits extraits,
observations du calendrier et échecs de collectes RSS, cours/calendrier/SEC et FX.
Les publications officielles internationales sont aussi signalées dans une
veille générale, sans association automatique à une cotation.

Le scheduler vérifie chaque minute, avec un curseur et au plus 100 éléments par
famille par passage. Le premier passage examine les 30 derniers jours conservés.
La clé de déduplication reste persistante ; actualiser ne crée pas de doublons.
Les changements de calendrier produisent des observations distinctes, sans
réactiver une ancienne date. Les alertes sont historiques, pas une liste de
prévisions encore actives ; ouvrir le calendrier pour voir les déplacements.

La détection et la publication restent deux dates différentes. Un échec technique
n'a pas de date de publication inventée. Les documents futurs sont exclus des
alertes documentaires. Les rapprochements héritent des limites de `/analysis` :
contexte d'émetteur, mention et impact financier restent distincts.

Filtres par type et non-lues, pagination serveur (20), badge actualisé chaque
minute et marqueurs de lecture idempotents sont disponibles. La lecture est
propre au compte ; en mode sans authentification, elle est partagée (`local`).
Aucun email, SMS ou message externe n'est envoyé.

## Sources internationales raccordées

Deux flux publics officiels complètent BCE, Fed et SEC toutes les 30 minutes :

- [Communiqués Airbus](https://www.airbus.com/en/rss-feeds) :
  `https://www.airbus.com/en/generate-rss-feeds?type=all-press-releases` ;
- [Actualités et publications AMF](https://www.amf-france.org/fr/abonnements-flux-rss) :
  `https://www.amf-france.org/fr/flux-rss/display/21`.

La collecte conserve uniquement les titres, dates et extraits RSS proposés par
l'éditeur, jusqu'à 200 entrées, 4 000 caractères par extrait et 2 Mo par réponse.
Redirections et liens restent sur le domaine HTTPS officiel. Les pages HTML et
PDF liées ne sont pas téléchargées par ces nouveaux collecteurs. Les erreurs
restent dans l'historique de collecte. Aucune couverture mondiale des entreprises
ou collecte automatique de tous leurs résultats n'est annoncée. L'AMF est une
source réglementaire française, pas une base de résultats des sociétés.
Le flux Airbus vérifié utilise actuellement des `pubDate` non standard, sans
fuseau explicite : elles ne sont pas converties arbitrairement en UTC. Ces documents
peuvent donc apparaître avec une date de publication indisponible et restent exclus
des alertes et rapprochements exigeant une publication datée. La consultation
du flux n'est pas transformée en date de publication.
Le contrôle depuis Docker a aussi reçu un HTTP 403 de l’AMF : le raccordement
reste soumis à l’accès accordé par le site. Ce refus est conservé comme échec
de collecte, sans contournement ni données de remplacement inventées.

`INTERNATIONAL_NEWS_ENABLED=false` désactive ces deux boucles.
`ALERTS_ENABLED=false` désactive la génération automatique, sans effacer l'historique.

## Imports autorisés et propositions

`/settings` permet de charger un JSON de 1 Mo maximum. Le modèle affiché contient
des valeurs à remplacer ; ce n'est pas un jeu de données financières utilisable.
Les schémas complets se trouvent dans `/docs` de l'API.

`POST /api/v1/workspace/imports` reçoit `DataBatch`, 100 lignes maximum :

```json
{"items": [{"kind": "earnings", "instrument_id": "UUID exact de la cotation", "observation": {"...": "tous les champs EarningsInput"}}]}
```

| kind | observation | Traitement |
| --- | --- | --- |
| earnings | EarningsInput | Calendrier, estimation ou résultat explicitement conventionné |
| valuation | ValuationInput | Preuve complète de BPA annuel dilué par titre, mêmes contrôles que `/analysis` |
| price | LocalPriceCreate | Cours de cotation manuelle, devise et unité exactes |
| fx | FxRateCreate | Taux daté vers USD ; sans instrument_id |
| corporate_action | CorporateActionInput | Proposition de dividende net ou split, sans écriture au portefeuille |

Le schéma entier doit être valide. Chaque ligne est ensuite acceptée ou refusée
avec un résultat ; les acceptations précédentes restent enregistrées. Les données
gardent leur statut déclaré. Rejouer des preuves identiques ne les duplique pas ;
les cours/taux manuels utilisent leurs règles existantes de correction par date.
Une estimation importée après un résultat ne devient jamais un consensus antérieur.

Les propositions sont paginées dans « Opérations proposées ». La source, le titre,
le montant net ou le ratio doivent être vérifiés avant de cocher la confirmation
et choisir une simulation. L'application réutilise tous les contrôles atomiques
et idempotents existants (détention, FX, fractions, opérations rétroactives).
La proposition reste visible pour pouvoir être appliquée à une autre simulation ;
un doublon identique sur la même simulation n'est pas appliqué deux fois.
Voir [les conventions des opérations](PORTFOLIO_TRACKING.md).

Pour automatiser l'ingestion d'exports d'une source autorisée, déposer les JSON
dans `private-data/imports/` et configurer `DATA_INBOX_DIRECTORY=/imports`.
Ce dossier est monté en lecture seule dans le scheduler. Le contenu déjà traité
est reconnu par son hash, avec résultat persistant dans `workspace_cursors`.
Un fichier refusé doit être corrigé ; son nouveau contenu sera retraité. Chaque
minute traite au plus 20 nouveaux fichiers parmi les 1 000 premiers noms triés.
Archiver les exports anciens hors du dossier actif. Liens symboliques et fichiers
de plus de 1 Mo sont ignorés. Aucun fichier n'est exécuté, supprimé ou envoyé à un LLM.
Ce mécanisme n'est pas un abonnement à un fournisseur et ne crée aucune donnée absente.

Import ponctuel dans un conteneur (chemin interne après `docker compose cp`) :

```powershell
docker compose exec backend python -m app.cli.import_data --file /tmp/export.json
```

## Bilan du portefeuille

`/portfolio` affiche la répartition par titre, secteur, pays et devise, en USD et
sur la valeur totale liquidités comprises. Les pays sont ceux de la classification
documentée, pas nécessairement ceux des revenus ou de la cotation. Secteur et pays
absents deviennent « Non documenté ». Ils ne sont jamais déduits du ticker.

`ProfileInput` conserve source, publication, date de validité, note et confirmation
dans un historique. La dernière déclaration saisie est utilisée pour la vue
courante, sans réécrire les instantanés du portefeuille. Des poids ne sont pas
calculés si une valorisation manque, est ancienne, ou si la valeur totale est nulle.

Les niveaux d'indice sont importés dans `/settings` avec `BenchmarkBatch` :
`{"items": ["objets BenchmarkInput complets"]}` (1 000 points maximum).
Identifiant de série, nom/version, USD, convention (`price`, `net_total_return`,
`gross_total_return`), séance, niveau positif et source datée sont obligatoires.
Une contradiction par série/séance ou un changement de convention est refusé,
sans écrasement. Les valeurs du WLS privé ne sont pas collectées ou reconstituées.

La comparaison exige des valeurs d'indice aux dates exactes du premier et du dernier
instantané de la fenêtre visible (1 000 jours maximum), avec valorisations utilisables
aux deux bornes. Aucun rapprochement au jour voisin ou interpolation. Il s'agit
d'instantanés observés, sans garantie d'heures de clôture synchronisées. Les revenus,
impôts, frais et opérations omises peuvent différer. Un indice de prix est présenté
séparément sans calcul d'écart de performance aux dividendes du portefeuille.
Les autres écarts sont descriptifs, sans certification de performance Bloomberg.

## Accès

Voir [la procédure d'activation et les sauvegardes](DEPLOYMENT.md). Les comptes
partagent les recherches, titres et simulations ; il ne s'agit pas d'espaces
privés par utilisateur. Les marqueurs de lecture sont individuels.

Migration `20261010_0020`. Tests unitaires sans réseau : `pytest`.
`python -m tests.verify_workspace_database` crée une base QA isolée si elle n'existe
pas, applique les migrations, vérifie l'API et annule les fixtures. Cette base est
conservée pour la vérification de restauration ; aucune base existante n'est écrasée.
Les tests navigateur utilisent exclusivement des réponses simulées.
