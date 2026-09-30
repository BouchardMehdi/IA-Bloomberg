# Market AI

Market AI transforme des sources économiques et financières en événements structurés, sourcés et persistants. Le socle technique comprend l'API, l'interface web, PostgreSQL avec pgvector, Redis, les migrations, l'environnement Docker et la collecte automatique de sources primaires.

## Prérequis

- Docker Desktop avec Docker Compose ;
- ou Python 3.12+ et Node.js 22+ pour un lancement hors Docker.

## Démarrage rapide

1. Copier `.env.example` vers `.env`.
2. Lancer `docker compose up --build`.
3. Ouvrir l'application sur <http://localhost:3000>, l'API sur <http://localhost:8000> ou le proxy Caddy sur <http://localhost>.

La migration Alembic est appliquée automatiquement au démarrage du backend. La documentation interactive de l'API est disponible sur <http://localhost:8000/docs>.

## Vérifications

```bash
docker compose config
docker compose run --rm backend pytest
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run build
```

Les endpoints suivants servent à l'orchestration :

- `GET /api/v1/health/live` vérifie que le processus répond ;
- `GET /api/v1/health/ready` vérifie PostgreSQL et Redis.
- `GET /api/v1/articles` retourne les articles récents avec pagination.
- `GET /api/v1/collection-runs` retourne l'historique des collectes.

## Collecter les publications des banques centrales

Une fois la stack démarrée, lancer :

```bash
docker compose exec backend python -m app.cli.collect_ecb
docker compose exec backend python -m app.cli.collect_fed
```

Les collectors utilisent les flux officiels des communiqués de la Banque centrale européenne et de la Réserve fédérale américaine. Ils normalisent les champs, retirent les paramètres de suivi des URL, calculent un hash SHA-256 puis ignorent les URL et contenus déjà enregistrés. Les commandes peuvent donc être relancées sans créer de doublons.

Le service `scheduler` exécute les deux collectes automatiquement, chacune dans sa propre boucle. Les intervalles et l'exécution immédiate au démarrage se règlent dans `.env` :

```dotenv
ECB_COLLECTION_INTERVAL_MINUTES=15
FED_COLLECTION_INTERVAL_MINUTES=15
SCHEDULER_RUN_ON_START=true
```

Chaque tentative est enregistrée avant l'appel réseau puis terminée avec son statut, sa durée et ses compteurs. Un échec reste ainsi visible dans l'API et sur le dashboard.

## Développement local

Backend :

```bash
cd backend
python -m venv .venv
# Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Frontend :

```bash
cd frontend
npm install
npm run dev
```

Pour exécuter le backend hors Docker tout en gardant les services de données dans Docker, lancer `docker compose up -d postgres redis`, puis adapter `DATABASE_URL` et `REDIS_URL` pour utiliser `localhost`.

## Organisation

- `backend/` : API FastAPI, modèles SQLAlchemy, Alembic et tests ;
- `frontend/` : interface Next.js responsive ;
- `docs/` : architecture, données, IA, développement et déploiement ;
- `deploy/` : configuration du reverse proxy ;
- `prompts/` : futurs prompts versionnés.

Le principe structurant est **Article != Event** : plusieurs articles peuvent documenter le même événement. PostgreSQL reste la mémoire permanente et les futurs workers Ollama ne recevront jamais ses identifiants.

Les pipelines BCE et Fed sont collectés automatiquement et observables. Aucun modèle Ollama, rapport ou moteur de scoring n'est encore implémenté. La prochaine étape recommandée est d'ajouter une source réglementaire primaire, puis de commencer l'extraction d'événements structurés.
