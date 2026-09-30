# Market AI

Market AI transforme des sources économiques et financières en événements structurés, sourcés et persistants. Cette première étape installe uniquement le socle technique : API, interface web, base PostgreSQL avec pgvector, Redis, migrations et environnement Docker.

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

## Collecter les publications de la BCE

Une fois la stack démarrée, lancer :

```bash
docker compose exec backend python -m app.cli.collect_ecb
```

Le collector utilise le flux officiel des communiqués de la Banque centrale européenne. Il normalise les champs, retire les paramètres de suivi des URL, calcule un hash SHA-256 puis ignore les URL et contenus déjà enregistrés. La commande peut donc être relancée sans créer de doublons.

Le service `scheduler` exécute aussi cette collecte automatiquement toutes les 15 minutes. L'intervalle et l'exécution immédiate au démarrage se règlent dans `.env` :

```dotenv
ECB_COLLECTION_INTERVAL_MINUTES=15
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

Le pipeline BCE est collecté automatiquement et observable. Aucun modèle Ollama, rapport ou moteur de scoring n'est encore implémenté. La prochaine étape recommandée est d'ajouter une deuxième source primaire en réutilisant le même contrat de collecte.
