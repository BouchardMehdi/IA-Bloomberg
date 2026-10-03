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
- `GET /api/v1/articles/{id}` retourne aussi le texte du document et son état de récupération.
- `GET /api/v1/events` retourne les événements détectés avec leur source primaire.
- `GET /api/v1/events/{id}/analysis` retourne les passages transmis, leur état et leurs résultats.
- `GET /api/v1/collection-runs` retourne l'historique des collectes.

## Collecter les publications des banques centrales

Une fois la stack démarrée, lancer :

```bash
docker compose exec backend python -m app.cli.collect_ecb
docker compose exec backend python -m app.cli.collect_fed
docker compose exec backend python -m app.cli.collect_sec
```

Les collectors utilisent les flux officiels de la Banque centrale européenne, de la Réserve fédérale américaine et des dépôts `8-K` de la SEC. Ils normalisent les champs, retirent les paramètres de suivi des URL, calculent un hash SHA-256 puis ignorent les URL et contenus déjà enregistrés. Les commandes peuvent donc être relancées sans créer de doublons.

Le service `scheduler` exécute les trois collectes automatiquement, chacune dans sa propre boucle. Les intervalles et l'exécution immédiate au démarrage se règlent dans `.env` :

```dotenv
ECB_COLLECTION_INTERVAL_MINUTES=15
FED_COLLECTION_INTERVAL_MINUTES=15
SEC_COLLECTION_INTERVAL_MINUTES=15
SEC_USER_AGENT=MarketAI/0.1 your-email@example.com
SCHEDULER_RUN_ON_START=true
```

La SEC exige que les accès automatisés déclarent une identité et un contact dans le `User-Agent`. Remplacer l'adresse d'exemple de `SEC_USER_AGENT` avant de démarrer le scheduler.

Chaque tentative est enregistrée avant l'appel réseau puis terminée avec son statut, sa durée et ses compteurs. Un échec reste ainsi visible dans l'API et sur le dashboard.

## Extraire les premiers événements

Le scheduler transforme automatiquement chaque nouvel article primaire en événement traçable. Cette première passe déterministe distingue les annonces de banques centrales des dépôts réglementaires SEC et rattache toujours l'événement à son URL source. Elle peut aussi être lancée manuellement :

```bash
docker compose exec backend python -m app.cli.extract_events
```

Cette étape ne résume pas encore les faits contenus dans un document et ne remplace pas la future extraction IA. Elle fournit une file d'événements idempotente et consultable sur laquelle les enrichissements suivants pourront travailler.

Les dépôts SEC sont ensuite enrichis avec le formulaire, le numéro d'accession lorsqu'il est disponible, le nom de la société et son CIK. Les sociétés sont conservées dans un registre dédié et reliées aux événements. Chaque enrichissement garde aussi un extrait justificatif issu de l'article primaire et la version de l'extracteur utilisé.

## Activer l'analyse sémantique locale

L'analyse sémantique utilise Ollama avec un JSON Schema strict, une température nulle et une validation Pydantic. Les citations produites par le modèle sont rejetées si elles ne figurent pas dans le texte source. Chaque tentative conserve son modèle, sa version de prompt, sa durée, ses compteurs de tokens, son résultat ou son erreur.

Le modèle compact par défaut est `qwen3:4b-instruct`. L'analyse reste désactivée tant que le service et le modèle ne sont pas prêts :

```bash
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull qwen3:4b-instruct
```

Renseigner ensuite `AI_ANALYSIS_ENABLED=true` dans `.env` et recréer le scheduler. Une analyse manuelle limitée peut être lancée avec :

```bash
docker compose --profile ai up -d backend scheduler ollama
docker compose exec backend python -m app.cli.analyze_events --limit 3
```

Le résultat contient un résumé, une catégorie sémantique, les sociétés et actifs cités, les dates, les montants, les scores de sentiment, d'importance, d'urgence et de confiance, ainsi que les preuves textuelles.

## Récupérer les documents et regrouper les événements

Le scheduler récupère automatiquement le texte HTML des publications officielles BCE, Fed et SEC. Pour une page d'index SEC, il sélectionne le document principal `8-K` ou `8-K/A`, en conservant son URL exacte. Le RSS d'origine reste conservé séparément. Les PDF et les pièces jointes ne sont pas extraits dans cette version.

```bash
docker compose exec backend python -m app.cli.fetch_documents --limit 5
docker compose exec backend python -m app.cli.fetch_documents --source ecb --limit 1
```

La récupération est séquentielle : cinq documents par cycle d'une minute, au plus 2 Mo par téléchargement, 60 000 caractères conservés et 90 secondes par document. Une erreur est enregistrée ; deux nouvelles tentatives sont possibles après 5 puis 10 minutes. Les redirections restent dans le domaine officiel et les pages non prises en charge sont signalées. Ces limites sont configurables via les variables `DOCUMENT_*` de `.env.example`.

L'analyse attend la récupération ou son échec définitif. Elle découpe l'ensemble du texte conservé et sélectionne des passages selon des indices financiers déterministes (montants, décisions, acquisitions, résultats, sections SEC). Les mentions légales sont moins prioritaires. En l'absence de signal, la sélection échantillonne plusieurs positions dans le document. Après un échec définitif de récupération, l'extrait RSS reste utilisable.

Par défaut, le budget est de trois passages de 3 000 caractères au maximum, avec un total de 9 000 caractères hors titre et instructions. `AI_PASSAGE_CHARS`, `AI_MAX_PASSAGES` et `AI_INPUT_BUDGET_CHARS` règlent ces limites. La sélection utilise des règles simples ; elle peut manquer un fait pertinent. La couverture affichée porte sur le texte conservé, qui peut lui-même avoir été limité lors de la récupération.

Chaque passage peut produire zéro à trois faits distincts. Un fait devient un événement lié à la publication d'origine via `parent_event_id`, avec sa citation, son passage et son URL. La publication reste conservée. Le regroupement des publications n'agrège pas ces faits différents. La même preuve et le même type, dans une publication donnée, réutilisent le même événement ; des formulations ou preuves différentes peuvent encore créer des faits proches.

`analysis_runs` conserve le document d'entrée, son hash, l'URL et la couverture. `analysis_passages` conserve les passages choisis, leurs positions, résultats, erreurs et tokens. Une citation absente du passage transmis est rejetée. Les passages réussis sont réutilisés après un échec, et une analyse partielle reste visible. Un changement de texte, de prompt ou de paramètres de sélection permet une nouvelle analyse sans effacer la précédente.

Sur CPU, un document plus long peut demander plusieurs minutes d'analyse. `OLLAMA_TIMEOUT_SECONDS` autorise jusqu'à 600 secondes par appel par défaut ; la durée réelle d'un cycle peut dépasser l'intervalle configuré, sans chevauchement des cycles du scheduler.

Un contrôle optionnel vérifie les écritures PostgreSQL avec un modèle simulé et annule toutes ses données de test :

```bash
docker compose exec backend python -m tests.smoke_passage_pipeline
```

Les événements correspondant au même numéro de dépôt SEC sont regroupés. Pour les autres publications, le regroupement exige un texte intégral identique d'au moins 500 caractères, la même source et la même date de publication ; un texte tronqué ne suffit pas. Les événements regroupés et leurs historiques restent en base, tandis que l'API expose l'événement conservé avec toutes ses sources. Des articles simplement proches par leur sujet restent distincts.

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

Les pipelines BCE, Fed et SEC collectent les flux puis le texte des documents officiels. L'extraction déterministe crée des événements sourcés et identifie les sociétés déclarantes des dépôts SEC. Le regroupement exact conserve toutes les sources ; l'analyse Ollama optionnelle garde ses preuves et métriques. La prochaine étape pourra étendre la couverture des documents, puis le rapprochement des faits décrit différemment par plusieurs sources.
