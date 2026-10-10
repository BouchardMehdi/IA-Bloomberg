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

## Identifier les sociétés et les titres

Le scheduler synchronise une fois par jour le référentiel officiel SEC des noms, CIK,
tickers et marchés, puis résout les identités toutes les minutes, par lots de 100.
Le téléchargement est limité à 5 Mo et 60 secondes. En cas d'erreur, le dernier
snapshot reste utilisable et une nouvelle vérification attend une heure.
`ENTITY_REGISTRY_ENABLED=false` désactive uniquement la synchronisation réseau.

```bash
docker compose exec backend python -m app.cli.resolve_entities --sync --limit 1000
```

L'API `/api/v1/events` et l'interface exposent `entity_resolution` : identité,
statut (`resolved`, `ambiguous`, `unresolved`, `unverified`), candidats, méthode et
citation. Les noms sont comparés exactement après normalisation de la casse et de la
ponctuation ; aucune correspondance approximative n'est validée automatiquement.
Les variantes présentes dans les dépôts SEC sont associées par CIK. Un ticker doit
être explicitement cité ; les cotations disponibles d'une société sont du contexte,
pas une affirmation que chacun de ses titres est concerné par le fait.

Les prochaines extractions peuvent préciser `subject`, `counterparty` ou `mention`,
avec une citation contenant le nom. Ces rôles sont proposés par le modèle ; le
contrôle vérifie la présence de la citation, sans garantir son interprétation.
Le déclarant du document reste distinct (`source_subject`). Les anciennes analyses
réussies `semantic-v5-passages` restent en cache pour le même texte, modèle et plan ;
leurs sociétés sont résolues comme simples mentions sans nouvel appel IA.

Les codes explicites USD, EUR, GBP, JPY, CHF, CAD, AUD et CNY sont reconnus. Un symbole
`$` seul ne détermine pas une devise. Les obligations restent des mentions non
résolues tant qu'un référentiel adapté n'est pas disponible. La SEC fournit des
associations ticker/émetteur/marché, sans garantir ici la classe du titre. Le snapshot
est daté par sa consultation ; sa date de publication et les cotations historiques
restent inconnues. Le lien et la date du document justificatif restent conservés
avec les sources de l'événement.

## Cours et portefeuille simulé

Le challenge annoncé dispose de **1 000 000 USD**, avec des actions en positions
longues uniquement, sans levier. L'univers WLS annoncé contient **10 426 titres**,
distincts des entreprises. Voir [les règles connues et l'import WLS](docs/CHALLENGE.md).
Les actions hors États-Unis et les cotations dans d'autres devises sont autorisées
selon les précisions reçues ; Bloomberg assure la conversion pour le challenge.
La page <http://localhost:3000/international> permet de fournir des identités,
clôtures locales et taux sourcés pour une valorisation et simulation en USD.
Voir [la procédure internationale](docs/INTERNATIONAL_MARKET.md). La collecte
automatique des cotations internationales exige désormais une correspondance
fournisseur explicite et sourcée, à enregistrer depuis `/coverage`. Le
[contrat commun des fournisseurs de cours](docs/PRICE_PROVIDERS.md) est prêt,
avec contrôles de cotation/devise/unité, quotas persistants et reprises après erreur. Les
[taux de référence BCE sont désormais collectés automatiquement](docs/FX_COLLECTION.md),
sans clé API, avec leur date, source et calcul de conversion vers USD.
Les nouveaux achats simulés sont bloqués tant que l'action n'est pas identifiée
dans un export WLS fourni ; la SEC ne constitue pas cet univers.

La page <http://localhost:3000/portfolio> permet de suivre des titres NYSE/Nasdaq,
créer une simulation en USD et consulter le capital, les positions, les frais et
les gains ou pertes. Le capital et les contraintes sont configurables ; les valeurs
du formulaire sont provisoires tant que le règlement du challenge est inconnu.

Ajouter une clé personnelle `ALPHA_VANTAGE_API_KEY` dans `.env`, puis relancer Docker
avec `docker compose --profile ai up -d --build` pour activer les cours quotidiens.
Sans clé, les cours restent indisponibles et aucune donnée fictive n'est injectée.
Les anciennes clôtures ne sont pas du temps réel ; une opération simulée conserve
son prix, sa date de cours et sa source. Il n'y a pas encore de recommandations IA.

Voir [la procédure et les limites](docs/MARKET_PORTFOLIO.md) pour le quota, les cours
bruts, les opérations idempotentes et les frais. Les dividendes et splits sourcés
peuvent être appliqués explicitement à une simulation ; ils ne sont pas collectés
automatiquement.

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

Les pipelines BCE, Fed et SEC collectent les flux puis le texte des documents officiels. L'extraction déterministe crée des publications sourcées ; Ollama peut produire plusieurs faits avec leurs preuves. Le regroupement exact conserve toutes les sources et le résolveur identifie les sociétés et les tickers explicites. La prochaine étape pourra utiliser ces identités pour des watchlists et des alertes ciblées.

## Analyses des titres

La [valorisation par les bénéfices](docs/VALUATION.md) calcule un PER annuel avec
clôture locale et BPA dilué sourcé explicitement compatible avec le titre. Une
référence sourcée permet de comparer les multiples ; données manquantes ou
incompatibles bloquent le calcul. Aucun seuil universel de prix attractif.

La [comparaison des résultats dans le temps](docs/FINANCIAL_TRENDS.md) présente
les variations du chiffre d'affaires et du résultat net entre périodes de même
durée dans le même dépôt SEC. Les unités, définitions et sources restent visibles ;
les ambiguïtés bloquent les calculs, les bases nulles/négatives bloquent les pourcentages.

Chaque titre suivi dispose d’une [fiche d’opportunité](docs/OPPORTUNITY_DOSSIERS.md)
dans `/analysis` : éléments favorables à examiner, risques documentés et questions
à vérifier, prochains résultats prévisionnels et données manquantes. Elle utilise
les observations conservées, sans appel IA supplémentaire ni score d’achat.

Les fiches collectent aussi des [observations chiffrées SEC XBRL](docs/FINANCIAL_RESULTS.md) :
chiffre d'affaires, résultat net, BPA, trésorerie, dette et flux de trésorerie US-GAAP,
avec distinction entre soldes à une date et flux sur une période, unités et
dépôts sourcés. Les définitions et valeurs republiées restent séparées ; aucun
écart au consensus n'est inventé.

Les fiches proposent une [collecte SEC ciblée des émetteurs suivis](docs/COMPANY_PUBLICATIONS.md),
en complément du flux général : dépôts annuels, trimestriels et annonces, avec
cache, historique et rapprochement par CIK. Les sociétés sans CIK restent hors
couverture de ce collecteur.

La page <http://localhost:3000/calendar> propose un [calendrier sourcé](docs/EARNINGS_CALENDAR.md),
des estimations de BPA et des résultats fournis. Le calendrier Alpha Vantage partage
le quota des cours ; les cotations internationales acceptent des observations
manuelles. Les résultats du calendrier ne sont pas alimentés automatiquement par
les BPA SEC : les conventions et la correspondance avec le titre restent à vérifier.

La page <http://localhost:3000/analysis> relie les titres suivis aux faits et
publications sourcés, avec distinction entre mention du titre et contexte de
l’émetteur. Voir [le fonctionnement et les limites](docs/INSTRUMENT_RESEARCH.md).
Elle propose aussi un [classement des titres à examiner](docs/RESEARCH_RANKING.md),
avec score explicable, preuves et points à vérifier, sans appel IA supplémentaire.
Les états des cours, taux et WLS sont affichés séparément ; ce classement ne
constitue pas une recommandation d'achat ni une prévision de rentabilité.

La page <http://localhost:3000/portfolio> permet aussi de consulter la
[liste WLS partielle fournie](docs/CHALLENGE.md), rechercher ses identifiants
Bloomberg et documenter leurs correspondances avec des cotations suivies.
La date de composition reste inconnue ; cette préparation ne débloque pas le
mode strict. Le fichier privé reste hors Git et se charge avec la commande
`app.cli.import_wls_candidates` décrite dans la documentation.

L'[identification automatique WLS](docs/WLS_AUTOMATION.md) enrichit désormais les
titres avec OpenFIGI, sans nouvelle clé ni appel LLM, et prépare une liste de
suivi US bornée. Une nouvelle simulation peut utiliser le mode provisoire sur la
liste déclarée une fois la cotation résolue ; les portefeuilles existants restent
stricts. Les sources, inconnues et preuves sont conservées. La composition WLS
n'est pas datée artificiellement et les données financières absentes restent
indisponibles.

Le [suivi historique du portefeuille](docs/PORTFOLIO_TRACKING.md) conserve des
instantanés datés et sourcés, avec courbe quotidienne et saisie contrôlée de
dividendes nets et splits. Les jours manquants ne sont pas reconstitués.
La page <http://localhost:3000/coverage> permet de filtrer les données manquantes,
préparer les preuves de valorisation et importer des observations complètes en lot.
Elle permet aussi de raccorder une cotation internationale à Alpha Vantage avec
une [correspondance fournisseur explicite et sourcée](docs/PRICE_PROVIDERS.md),
sans nouvelle clé ni suffixe deviné, dans le quota partagé existant.

L’[interface et sa navigation](docs/FRONTEND.md) donnent accès aux six pages depuis
un menu commun, adapté au mobile. L’analyse et le portefeuille sont organisés en
sections ; les longues listes sont paginées, les tableaux principaux deviennent
des cartes sur téléphone. Les contrôles navigateur se lancent avec
`npm run check:ui` depuis `frontend` et utilisent uniquement des données de test.
Chaque page propose aussi un encart **Mode d’emploi** pour les nouveaux utilisateurs,
affiché par défaut et désactivable. Le choix d’affichage est mémorisé dans le navigateur
et s’applique à toutes les pages ; le bouton permet de réactiver l’aide à tout moment.

## Alertes et espace partagé

La page `/alerts` conserve les nouvelles publications, faits, observations de
calendrier et erreurs de collecte, avec filtres, pagination et suivi de lecture.
Les flux officiels Airbus et AMF complètent la veille internationale. Voir
[les fonctionnalités et limites](docs/WORKSPACE.md).

`/portfolio` présente aussi les répartitions par titre, secteur, pays et devise,
avec les classifications documentées et les inconnues visibles. Une comparaison
à un historique d'indice USD importé exige les mêmes dates et conventions ; le
WLS privé n'est pas reconstitué.

`/settings` permet l'import de résultats, preuves de valorisation, cours/taux et
propositions de dividendes/splits. Un dossier local d'exports autorisés peut être
traité automatiquement ; les opérations sur titres exigent toujours une validation
explicite avant application à une simulation.

Les comptes en lecture, édition ou administration et les sauvegardes PostgreSQL
chiffrées sont prêts à activer. L'authentification reste désactivée par défaut en
local et le service de sauvegarde exige votre clé publique. Voir
[l'activation des accès, sauvegardes et restauration](docs/DEPLOYMENT.md).
