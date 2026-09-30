# Instructions pour les agents

## But du projet

Market AI collecte des informations financières, les normalise puis crée des événements structurés et traçables. La priorité est : pipeline fiable, qualité des sources, puis complexité IA.

## Invariants

- Un `Article` est une source documentaire ; un `Event` est un fait structuré. Plusieurs articles peuvent être liés au même événement.
- PostgreSQL est la mémoire principale. Un LLM ne sert jamais de base de données.
- Toute affirmation présentée à l'utilisateur doit pouvoir être reliée à une URL et à une date de publication.
- Les workers externes accèdent aux tâches via une API dédiée. Ils ne reçoivent pas les identifiants PostgreSQL ou Redis.
- Ne jamais committer `.env`, mot de passe, token ou clé API.
- Ne pas contourner les paywalls ni stocker du contenu non autorisé.

## Architecture

- `backend/app/api` : routes HTTP ;
- `backend/app/core` : configuration ;
- `backend/app/db` : session et base SQLAlchemy ;
- `backend/app/models` : modèles persistants ;
- `backend/migrations` : migrations Alembic ;
- `frontend/app` : application Next.js ;
- `docs` : décisions et procédures.

Les routes ne contiennent pas de logique métier complexe. Les futurs collectors partagent une interface commune. Les sorties IA sont contraintes par JSON Schema, validées par Pydantic puis contrôlées avec des règles déterministes.

## Commandes

```bash
docker compose up --build
docker compose config
docker compose run --rm backend pytest
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run build
```

## Méthode de travail

Avant une modification, lire ce fichier et la documentation concernée. Limiter chaque changement à une fonctionnalité cohérente, ajouter les tests utiles, exécuter les vérifications adaptées et mettre à jour la documentation si le comportement change.

La phase actuelle comprend la fondation, les collectors RSS de la BCE, de la Fed et des dépôts SEC 8-K, leur scheduler, l'historique des collectes et la première extraction déterministe d'événements sourcés. Les tests des collectors utilisent des fixtures locales et ne dépendent pas du réseau. Ne pas ajouter d'intégration Ollama ou de fonction de trading sans demande explicite.
