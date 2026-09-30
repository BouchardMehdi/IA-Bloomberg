# Base de données

PostgreSQL est la source de vérité. La migration initiale active pgvector et crée `sources`, `articles`, `events` et `event_articles`. La migration suivante ajoute `collection_runs` pour l'observabilité des collectors.

## Règles

- Les identifiants sont des UUID.
- Toutes les dates techniques sont en UTC.
- `articles.url` et `articles.content_hash` sont uniques pour bloquer les doublons exacts.
- `event_articles` permet de rattacher plusieurs preuves à un événement.
- Un événement conserve des scores de veille ; ces scores ne sont pas des recommandations d'investissement.
- La suppression d'une source ne doit pas effacer silencieusement son historique.
- Une collecte est créée avec le statut `running` avant l'appel réseau, puis passe à `success` ou `failed` avec sa durée et ses compteurs.

Les sociétés, listings, marchés, watchlists et rapports seront ajoutés lorsque leur premier cas d'usage sera implémenté. Cela évite de figer prématurément un schéma inutilisé.

## Migrations

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "description"
```

Toute modification du modèle persistant doit être accompagnée d'une migration réversible.
