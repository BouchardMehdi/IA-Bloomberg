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

La phase actuelle comprend la fondation, les collectors RSS de la BCE, de la Fed et des dépôts SEC 8-K, la récupération bornée des documents HTML officiels, leur scheduler, l'historique des collectes, l'extraction déterministe d'événements sourcés, l'identification des sociétés SEC par CIK, le regroupement exact avec conservation des sources et une analyse sémantique Ollama optionnelle. Les tests des collectors et de l'analyse utilisent des fixtures ou transports simulés et ne dépendent pas du réseau. Ne pas ajouter de fonction de trading sans demande explicite.

L'analyse sémantique découpe et sélectionne les passages dans un budget explicite, conserve la couverture et reprend les passages réussis. Les faits extraits sont des événements enfants ; le regroupement des publications ne doit jamais fusionner des faits différents issus du même document.

Les identités sont résolues sans appels LLM supplémentaires à partir des noms SEC,
CIK et tickers explicites. Conserver les candidats ambigus et les mentions non
vérifiées. Les liens `source_subject` du document ne prouvent pas le rôle d'une
société dans chaque fait. Le référentiel SEC est daté par sa consultation, pas par
une date de publication inventée ; ses cotations ne sont pas historiques.

Le portefeuille simulé et la collecte de clôtures Alpha Vantage sont autorisés dans
la phase actuelle. Ne pas transmettre d'ordres réels. Les paramètres du challenge
restent provisoires. Les simulations doivent conserver prix/date/source, contrôler
capital et positions, et rester idempotentes. Ne jamais compléter un cours manquant
avec une valeur inventée ; les clés fournisseur restent côté serveur.

Règles connues du challenge : 1 000 000 USD, actions en positions longues uniquement,
sans levier, Forex ou matières premières. WLS est un univers privé annoncé de
10 426 titres ; ne pas le reconstruire approximativement. L'éligibilité vient d'un
export autorisé par titre et cotation, jamais du CIK d'une entreprise. Les frais,
dates et limites restent à confirmer. Voir docs/CHALLENGE.md.

Les fiches `/analysis` rapprochent les titres suivis des documents et faits sans
appel LLM supplémentaire. Distinguer la mention du titre et de sa cotation du
contexte de l’émetteur. Ne pas transformer ce rapprochement en impact financier
avéré. Voir docs/INSTRUMENT_RESEARCH.md.
