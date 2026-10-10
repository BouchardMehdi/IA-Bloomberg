# Exploiter la liste WLS fournie sans compléter les inconnues

Le 10 octobre 2026, l'utilisateur indique qu'il n'obtiendra pas les informations
manquantes et demande de poursuivre directement. La liste de 3 000 identifiants
reste un export WLS partiel déclaré, sans date de composition connue. Cette date
n'est pas déduite de la création du classeur, de son import ou d'OpenFIGI.

## Identification automatique

Le scheduler consulte l'[API publique OpenFIGI](https://www.openfigi.com/api/documentation)
sans clé et sans LLM. Une requête porte sur cinq identifiants maximum, avec le
ticker et le code Bloomberg exacts du fichier, `marketSecDes=Equity` et exclusion
des titres non cotés. Aucun suffixe fournisseur n'est inventé. Les titres suivis
passent avant les autres titres US, puis le reste de la liste, sans classement
d'investissement.

La réservation PostgreSQL précède l'appel HTTP : le registre partagé
`wls_openfigi_state` coordonne CLI, API et scheduler. Un appel a un délai total de
25 secondes et une réponse limitée à 1 Mo ; aucun corps d'erreur arbitraire n'est
conservé. Le prochain appel attend au moins cinq secondes après la réponse.
HTTP 429 impose au moins une minute, selon `ratelimit-reset` borné à un jour.
Une interruption conserve une réservation de cinq minutes. Les erreurs techniques
attendent cinq minutes ; les erreurs de traitement par identifiant attendent un
jour. Les observations réussies, ambiguës ou absentes sont conservées sept jours
avant nouvelle consultation. Un résultat plus récent manquant ou ambigu ne
réactive pas une ancienne correspondance réussie.

Les observations sont enregistrées séparément dans `wls_identity_observations` :
hash du fichier, identifiant original, requête exacte, consultation, statut,
FIGI, FIGI composite, classe d'action et type de titre retourné. La consultation
ne devient pas une date de publication. Un résultat multiple reste ambigu ; un
ETF, fonds, ADR ou autre type ne devient pas une action ordinaire par assimilation.

Un FIGI composite ne prouve pas une cotation. Pour un titre suivi, le système
interroge aussi son MIC et sa devise avec `COMPOSITE_ID_BB_GLOBAL`. Le lien exige
un résultat unique d'action ordinaire, même FIGI composite, même classe et ticker
exact. NYSE correspond à XNYS ; les trois segments Nasdaq XNGS, XNMS et XNCM sont
tous consultés, sans choix arbitraire. Références :
[registre MIC ISO](https://www.iso20022.org/market-identifier-codes) et
[codes OpenFIGI](https://www.openfigi.com/docs/OpenFIGI-exchange-codes.csv).
Pour les cotations internationales, seul un MIC et un identifiant Bloomberg
déjà documentés sur le titre peuvent être utilisés ; ils ne sont pas devinés.
Toutes les preuves doivent avoir au plus sept jours et correspondre à la requête
actuelle. Les identités existantes ne sont pas réécrites.

## Liste de suivi bornée

`WLS_IDENTITY_ENABLED=true` active la collecte automatique. `WLS_AUTO_WATCH_LIMIT=20`
permet de préparer une sélection de recherche US, dans la limite de vingt titres
suivis au total par défaut. `0` désactive cet ajout automatique. Aucune position
ni opération n'est créée. Un ajout exige une observation OpenFIGI univoque
d'action ordinaire US et un seul ticker/cotation NYSE ou Nasdaq dans le référentiel
SEC consulté depuis moins de sept jours. Le CIK reste celui de cette source ; il
ne prouve pas l'éligibilité WLS. Les cotations ambiguës sont ignorées.

Cette sélection suit l'ordre de la liste fournie, sans score d'achat. Les
collecteurs existants peuvent ensuite récupérer cours Alpha Vantage, publications
SEC et observations chiffrées pour les titres pris en charge. Le quota Alpha
Vantage reste partagé avec le calendrier ; aucun budget n'est augmenté. Les prix
et taux absents bloquent toujours une opération. OpenFIGI ne fournit pas les cours,
les bénéfices ni les constituants WLS.

## Simulation provisoire explicite

Chaque portefeuille conserve `wls_policy` :

- `verified` : comportement existant, export WLS daté et cotation rapprochée requis ;
- `declared_partial` : simulation exploratoire sur la liste déclarée, après
  résolution technique actuelle du titre, de sa classe ordinaire et de sa cotation.

Les portefeuilles existants et le défaut API restent stricts. Le formulaire de
création propose désormais le mode provisoire, avec ses limites visibles. Ce
choix répond à la demande de poursuivre avec le fichier disponible ; il ne
certifie pas son actualité ou sa conformité au challenge. Le statut d'éligibilité
stricte n'est jamais transformé en `verified` à partir d'OpenFIGI.

Chaque achat conserve `paper_trades.universe_evidence` : politique appliquée,
hash de l'export et, pour le mode provisoire, identifiant Bloomberg, FIGI de
cotation, preuves de correspondance et dates de consultation. Les preuves sont
figées à l'achat ; un nouvel export ne réécrit pas une ancienne opération. Les
reprises d'un même ordre restent idempotentes. Les limites de capital, frais,
concentration, ancienneté des cours/taux et l'interdiction des positions courtes
restent appliquées. Les ventes permettent de réduire une position existante.

## Lots et historique des exports

`POST /api/v1/market/wls-candidates/collect` traite un lot borné ; l'état partagé
peut répondre `waiting`. Le scheduler poursuit la liste en arrière-plan.
`POST /api/v1/market/wls-candidates/mappings/batch` accepte jusqu'à cent déclarations
manuelles documentées, avec un résultat par ligne. Les lignes validées sont
conservées même si une autre correspondance est refusée. La validation structurelle
du lot entier précède toute écriture. Les déclarations restent non certifiées et
ne remplacent pas les preuves techniques du mode provisoire.

Un nouvel import via `app.cli.import_wls_candidates` archive l'ancien manifeste
complet dans `wls_archive_<hash>`, avec ses correspondances. La reprise du même
hash est idempotente ; le retour à un export archivé restaure ses déclarations.
Les observations OpenFIGI restent distinctes par hash. L'interface affiche les
dix derniers fichiers, les autres restent en base. Ces instantanés permettent
d'auditer les fichiers reçus, sans dater les entrées/sorties officielles du WLS.

Pour un prochain classeur à un onglet et une colonne d'identifiants textuels,
la commande de préparation est reproductible. Elle refuse formules, identifiants
numériques, doublons et classeurs trop volumineux, sans exécuter leur contenu :

```powershell
docker compose cp ./nouveau-wls.xlsx backend:/tmp/nouveau-wls.xlsx
docker compose exec backend python -m app.cli.prepare_wls --file /tmp/nouveau-wls.xlsx --output /tmp/nouveau-wls.json --origin "Liste WLS fournie par l'utilisateur"
docker compose exec backend python -m app.cli.import_wls_candidates --file /tmp/nouveau-wls.json
```

La préparation n'écrase pas un fichier de sortie existant. Le classeur et le
manifeste privé restent hors Git ; la source originale et son hash sont conservés.

## Limites de données

L'automatisation ne reconstitue pas les quelque 7 400 titres manquants. Elle ne
connecte pas de nouveau fournisseur de cours internationaux et n'invente ni prix,
devise, unité, ratio ADR, BPA par titre ou référence de valorisation. La couverture
automatique de cours reste NYSE/Nasdaq USD ; les cotations internationales restent
fournies par une source autorisée avec leurs conventions exactes. Les contrôles de
valorisation et des comparaisons financières restent ceux de leurs documentations.
La performance est celle de notre simulation, sans équivalence certifiée avec le
challenge ou son benchmark privé.

## Vérifications

Les tests OpenFIGI utilisent des transports HTTP simulés. Le scénario
`python -m tests.smoke_wls_automation` vérifie les réservations, la reprise,
l'historique et un achat provisoire avec preuves, puis annule ses fixtures en base.
