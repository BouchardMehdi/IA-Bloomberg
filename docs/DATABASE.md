# Base de données

PostgreSQL est la source de vérité. La migration initiale active pgvector et crée `sources`, `articles`, `events` et `event_articles`. La migration suivante ajoute `collection_runs` pour l'observabilité des collectors. La troisième ajoute une clé stable de déduplication aux événements. La quatrième ajoute l'enrichissement structuré, `companies` et la relation `event_companies`. La cinquième ajoute `analysis_runs` pour les analyses sémantiques.

## Règles

- Les identifiants sont des UUID.
- Toutes les dates techniques sont en UTC.
- `articles.url` et `articles.content_hash` sont uniques pour bloquer les doublons exacts.
- `event_articles` permet de rattacher plusieurs preuves à un événement.
- `events.deduplication_key` empêche une nouvelle extraction de recréer le même événement.
- `companies.cik` identifie de manière unique les déclarants SEC.
- Un événement conserve la méthode et la version d'extraction, les données structurées et un extrait justificatif.
- `analysis_runs` conserve le résultat validé ou l'erreur sans utiliser le LLM comme mémoire.
- Un événement conserve des scores de veille ; ces scores ne sont pas des recommandations d'investissement.
- La suppression d'une source ne doit pas effacer silencieusement son historique.
- Une collecte est créée avec le statut `running` avant l'appel réseau, puis passe à `success` ou `failed` avec sa durée et ses compteurs.

Les watchlists et rapports seront ajoutés lorsque leur premier cas d'usage sera implémenté.

## Migrations

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "description"
```

Toute modification du modèle persistant doit être accompagnée d'une migration réversible.

La migration `0006` conserve le texte RSS et ajoute `full_content`, son hash, `document_url`, les états de récupération, les tentatives, l'erreur, la prochaine tentative et le marqueur de troncature. `merged_into_event_id` conserve l'identité des événements regroupés. Les liens des articles sont également ajoutés à l'événement conservé.

L'unicité des analyses inclut le hash d'entrée ; `input_text` et `source_url` préservent le contexte des preuves. Le downgrade de `0006` fonctionne tant qu'aucun groupe modèle/prompt/événement n'a plusieurs entrées. Dans ce dernier cas, il refuse d'effacer implicitement l'historique : exporter les analyses avant une restauration de sauvegarde.

La migration `0007` ajoute `analysis_runs.coverage`, `analysis_passages` et les relations `events.parent_event_id` / `fact_analysis_run_id`. Les passages ont une unicité `(run_id, passage_index)` et gardent leurs positions, texte transmis, hash, statut, résultat, erreurs, durée et tokens. Les faits précis partagent les sources de leur publication mais conservent leur propre preuve. Les anciens résultats restent consultables.

La migration `0008` ajoute `entity_registries` : snapshot SEC des noms, CIK, tickers
et marchés, URL, date de consultation et hash. Cette date n'est pas une date de
publication. Le snapshot validé remplace atomiquement le précédent ; une réponse
invalide ne l'efface pas.

`events.structured_data.entity_resolution` conserve les identités, rôles, citations,
candidats ambigus et le référentiel utilisé. Le cache dépend de la version du
résolveur, du contenu du référentiel et des noms connus par CIK. Un nouveau fait
invalide sa résolution. L'écriture compare les données initiales pour éviter
d'écraser une extraction concurrente. Les liens `event_companies` existants restent
la provenance du document ; ils ne représentent pas ses contreparties.

La migration `0009` ajoute `market_instruments`, `daily_prices`, `market_fetch_runs`,
`paper_portfolios`, `paper_positions` et `paper_trades`. Les cours sont uniques par
titre/date de séance ; les tentatives de collecte constituent le compteur de quota
persistant. Le registre des opérations conserve un identifiant unique par
portefeuille, le prix effectivement simulé, la date du cours, sa source, les frais
et le gain réalisé. Les montants utilisent `Numeric` et les calculs `Decimal`.
Une transaction verrouille le portefeuille avant de modifier le capital, la
position et le registre. Voir [la procédure de simulation](MARKET_PORTFOLIO.md).

La migration `0010` ajoute ISIN, symbole Bloomberg, validité de l'identité, facteur
de cotation et mode de collecte aux titres. Le CIK devient facultatif. Les lignes
existantes conservent leur devise, prix et identifiants ; le facteur vaut 1 et la
collecte reste Alpha Vantage. Les identités ISIN/marché et symboles Bloomberg sont
uniques. `fx_rates` conserve des taux USD par unité, uniques par devise/date.
`paper_trades.conversion` préserve l'instantané des preuves de chaque opération
convertie, sans modifier les anciennes opérations USD. Le downgrade refuse de
supprimer implicitement des titres internationaux ou des preuves de conversion.

La migration `0011` ajoute le fournisseur et la dérivation aux observations FX ;
les observations existantes restent manuelles. `fx_collection_runs` conserve
l'historique des collectes BCE et leur couverture. Les écritures sont atomiques,
le cache et le verrou PostgreSQL sont partagés entre CLI et scheduler. Les preuves
de dérivation sont figées dans la conversion des opérations, comme les taux.
