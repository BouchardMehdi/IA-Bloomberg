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

Les listings, marchés, watchlists et rapports seront ajoutés lorsque leur premier cas d'usage sera implémenté. Cela évite de figer prématurément un schéma inutilisé.

## Migrations

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "description"
```

Toute modification du modèle persistant doit être accompagnée d'une migration réversible.

La migration `0006` conserve le texte RSS et ajoute `full_content`, son hash, `document_url`, les états de récupération, les tentatives, l'erreur, la prochaine tentative et le marqueur de troncature. `merged_into_event_id` conserve l'identité des événements regroupés. Les liens des articles sont également ajoutés à l'événement conservé.

L'unicité des analyses inclut le hash d'entrée ; `input_text` et `source_url` préservent le contexte des preuves. Le downgrade de `0006` fonctionne tant qu'aucun groupe modèle/prompt/événement n'a plusieurs entrées. Dans ce dernier cas, il refuse d'effacer implicitement l'historique : exporter les analyses avant une restauration de sauvegarde.
