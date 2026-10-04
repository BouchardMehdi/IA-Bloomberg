# Chiffres financiers SEC XBRL

La page `/analysis` affiche les observations chiffrées d'un émetteur identifié par
son CIK vérifié. La source est l'[API SEC companyfacts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
sans clé ni appel LLM. Plusieurs cotations partagent ces observations d'émetteur ;
elles ne constituent pas des mesures propres à chaque titre ni une preuve WLS.

## Mesures et unités

Taxonomie `us-gaap`, concepts explicitement pris en charge :

- Chiffre d'affaires : `RevenueFromContractWithCustomerExcludingAssessedTax`,
  `RevenueFromContractWithCustomerIncludingAssessedTax`, `Revenues`, `SalesRevenueNet`.
- Résultat net : `NetIncomeLoss`.
- BPA : `EarningsPerShareBasic` et `EarningsPerShareDiluted`.

Ces définitions ne sont ni fusionnées ni additionnées. Les taxonomies IFRS, les
extensions spécifiques et les autres concepts restent hors couverture. Une
absence n'est pas un zéro. Les montants restent décimaux exacts dans leur devise,
sans conversion FX ; les BPA gardent l'unité explicite `devise/shares`.
Les pertes et montants nuls sont valides.

Chaque mesure garde début et fin de période, valeur, unité, concept, accession,
formulaire, date du dépôt, contexte fiscal `fy/fp` et éventuel `frame` fournisseur.
`fp=Q3` désigne le contexte du dépôt : il ne prouve pas que la mesure couvre un
trimestre plutôt que neuf mois. Aucun trimestre ou montant annuel n'est déduit
par soustraction de cumuls. Les observations de dépôts successifs et les valeurs
différentes pour la même période sont conservées sans écrasement. Aucune valeur
« définitive » ni correction comptable n'est choisie automatiquement.

Le lien source pointe vers le dossier du dépôt SEC et conserve l'URL de l'API.
`filed` est une date, sans heure de publication inventée. La première consultation
est conservée séparément. La SEC peut reprendre des périodes comparatives déjà
publiées : une consultation récente ne rend pas le chiffre nouveau.

## Comparaisons

Les BPA SEC ne sont pas injectés dans le calendrier comme des résultats propres
au titre. Aucun écart automatique n'est calculé avec les estimations Alpha Vantage :
leur début de période, convention GAAP/ajustée et correspondance avec l'unité
économique du titre ne sont pas vérifiés. De plus, la première annonce doit être
identifiée pour empêcher une comparaison avec une estimation postérieure.
Ces motifs sont visibles sous chaque BPA. Les comparaisons manuelles déjà
documentées dans le calendrier restent disponibles sous leurs propres contrôles.

Ces observations ne modifient pas le classement de recherche et ne génèrent
aucun rendement attendu, signal d'achat ou événement sémantique artificiel.

## Collecte et API

`FINANCIAL_RESULTS_ENABLED=true` active un passage toutes les quinze minutes,
par trois émetteurs, en priorité les moins récemment consultés. Cache de 24 heures
après succès, cinq minutes après erreur. La réservation persistante partage le
verrou et l'exclusion de collecte active avec les publications ciblées SEC.
Aucun quota Alpha Vantage consommé. `SEC_USER_AGENT` garde un contact valide.

Une réponse est bornée à 12 Mo et 60 secondes, sans redirection ; 50 000 lignes
maximum examinées sur les concepts sélectionnés. Seules les dates de dépôt sur
365 jours et les fins de période sur 730 jours sont retenues, au maximum 2 000
observations. Les formulaires sont ceux documentés pour les publications ciblées.
Tous les éléments sélectionnés et les unités sont revalidés avant écriture.
Un échec conserve l'historique ; les erreurs sont des codes, sans corps fournisseur.
Une réponse vide réussie n'efface aucune observation. L'import est idempotent.

Les données restent dans `financial_facts`, en mémoire PostgreSQL. Ce sont des
observations numériques structurées, séparées des documents `Article` et des
faits extraits `Event`. Le JSON stocké est validé par Pydantic et contrôlé par règles.

- `GET /api/v1/market/instruments/{id}/financials?limit=50&offset=0`
- `POST /api/v1/market/instruments/{id}/financials/collect`

Le GET parcourt l'historique conservé, par fin de période puis date de dépôt,
avec pagination jusqu'à 100 observations par page. La couverture du dernier
appel ne doit pas être confondue avec tout l'historique. Les sociétés sans CIK,
IFRS et données propriétaires restent à connecter à une source autorisée.
