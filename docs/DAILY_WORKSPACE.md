# Collectes, briefing et journal

## Suivi des collectes

`/collections` lit les historiques persistants, sans appeler les fournisseurs.
Trois rubriques paginées par API : documents/résultats par source/CIK,
cours/calendrier par fournisseur/cotation/opération, et taux de référence BCE.
Une source jamais consultée n’a pas encore de ligne. Dernière tentative, réussite,
publication, consultation, séance de cours et date de référence restent distinctes.
Une réussite récente ne signifie pas que les résultats comptables sont nouveaux.
Les erreurs ne révèlent pas les corps fournisseur ni secrets.

La reprise est **au plus tôt** selon le cache/délai ou la réservation persistante
Alpha Vantage. Les boucles, quotas et lots peuvent la retarder. Une date passée
ne prouve pas qu’une nouvelle tentative a eu lieu. Une nouvelle version de
couverture SEC peut permettre une consultation anticipée.
Le scheduler conserve chaque minute un témoin d’activité : moins de cinq minutes
confirme une activité récente, pas la santé de chaque boucle. Les états distinguent
sources désactivées, en attente, en cours, anciennes et possiblement interrompues.

## Briefing quotidien

`/briefing` génère une liste de lecture pour une journée UTC, sans LLM, quota
fournisseur ni écriture. Quatre rubriques : nouvelles alertes détectées, résultats
prévisionnels sur 14 jours, chiffres SEC découverts et hypothèses à réexaminer.
Les décomptes ne sont pas des scores d’achat ou d’impact. Détection et publication
restent distinctes ; une nouvelle consultation peut découvrir une mesure ancienne.

Le calendrier réutilise les règles des fiches d’opportunité : dernière observation
par fournisseur/type/période avant filtrage des dates, résultats déjà déclarés et
contradictions conservés. Une date déplacée ne réactive pas une ancienne prévision.
Si la borne calendrier est atteinte, les prochaines échéances ne sont pas calculées
avec cet historique incomplet. Les dates de briefing futures sont refusées.

Bornes visibles : 500 titres, 1 000 alertes par journée, 5 000 observations
calendrier, 100 mesures financières et 100 dossiers. Alertes paginées par API,
autres listes paginées dans les données déjà chargées. Une borne atteinte est
signalée ; l’absence ne prouve pas l’absence de nouvelles.

La sélection d’une simulation marque ses **positions actuelles** et peut filtrer
ces titres. Elle ne reconstruit pas des positions historiques. Les révisions et
observations calendrier futures par rapport à la journée choisie sont exclues.
Un briefing historique est une vue bornée des données conservées, pas un document
figé certifiant tout ce qui était accessible à l’époque.

## Journal des décisions

`/journal` conserve des hypothèses manuelles : cotation exacte, simulation
facultative, hypothèse, risques, invalidation, horizon, date de réexamen,
observations de suivi et au moins une référence publique avec publication datée.
La confirmation distingue les notes des preuves certifiées et des ordres.
Statuts : À surveiller, En réflexion, Suivi d’une position (déclaré), Dossier clos,
Hypothèse invalidée. Un statut ne prouve pas une détention.

Chaque enregistrement ajoute une révision datée par le serveur et attribuée au
compte (`local` sans comptes). Aucune ancienne révision n’est écrasée, supprimée
ou antidatée. Cotation et simulation sont fixées à la création. Une opération
simulée peut être référencée seulement si elle appartient à cette cotation et
simulation ; aucune opération n’est créée ou modifiée. L’interface propose les
opérations récentes ; les références anciennes restent dans l’historique.

Un UUID stable rend les reprises réseau idempotentes. Un contenu différent sous
le même UUID est refusé. Une révision concurrente est refusée si la version
attendue a changé. Les filtres s’appliquent à la dernière révision sans faire
réapparaître un ancien statut. Seuls éditeurs/administrateurs enregistrent ;
les lecteurs consultent. L’espace reste partagé.

## Données automatiques supplémentaires

Le [flux officiel de la Banque d’Angleterre](https://www.bankofengland.co.uk/rss/news)
complète Airbus et AMF toutes les 30 minutes, sous `INTERNATIONAL_NEWS_ENABLED`.
Même contrat : HTTPS officiel, extraits RSS seulement, 2 Mo, 200 entrées,
4 000 caractères par extrait, aucun téléchargement des pages liées. Aucun impact
sur une action n’est déduit des annonces macroéconomiques.

L’[API SEC companyfacts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
fournit aussi des concepts IFRS pour les déposants étrangers à CIK vérifié.
`financial-v3-ifrs` ajoute `ifrs-full:Revenue`, `ProfitLoss` et
`CashAndCashEquivalents` dans leurs unités exactes. `ProfitLoss` a une mesure
distincte du résultat net US-GAAP : attribution et périmètres ne sont pas supposés
identiques. Aucun BPA IFRS, ratio ADR, total de dette ou conversion n’est ajouté.
Les comparaisons temporelles restent réservées aux concepts US-GAAP existants.
Les taxonomies, dépôts et définitions restent séparés. Ce n’est pas une couverture
de tous les marchés ou entreprises sans dépôt SEC.

## API et vérifications

- `GET /api/v1/workspace/collection-health?family=sources|market|fx`
- `GET /api/v1/workspace/briefing?day=AAAA-MM-JJ&portfolio_id=UUID&held_only=false`
- `GET|POST /api/v1/workspace/journal`
- `GET /api/v1/workspace/journal/{id}`
- `POST /api/v1/workspace/journal/{id}/revisions`

Migration `20261010_0021`. `pytest` utilise des fixtures sans réseau.
`python -m tests.verify_workspace_database` vérifie les migrations/API dans une
nouvelle base QA puis annule les fixtures. Les tests navigateur ne consomment
pas de quota et ne créent aucune opération réelle.
Voir [l’activation locale des comptes et sauvegardes](DEPLOYMENT.md).
