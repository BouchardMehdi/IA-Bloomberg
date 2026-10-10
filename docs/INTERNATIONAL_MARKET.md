# Titres internationaux et valorisation USD

La page <http://localhost:3000/international> permet de fournir des identités,
clôtures locales et taux provenant de sources que l’utilisateur est autorisé à
exploiter. Aucun exemple de titre, composition WLS ou taux n’est chargé dans la
base réelle. L’import WLS reste une opération séparée. Les
[taux de référence BCE sont collectés automatiquement](FX_COLLECTION.md).
La collecte automatique Alpha Vantage est désormais disponible pour les cotations
internationales avec une [correspondance fournisseur explicite et sourcée](PRICE_PROVIDERS.md).
Sans cette preuve ou disponibilité du marché, les clôtures restent manuelles.

## Identifier une cotation

Les champs obligatoires sont : ticker local, marché MIC (4 caractères), nom,
ISIN, devise, facteur d’unité du cours, date de validité et URL de source. Le
symbole Bloomberg exact et le CIK sont facultatifs. Le CIK n’est pas obligatoire
hors États-Unis et ne doit pas être déduit d’un nom. La clé de contrôle de l’ISIN
est validée ; cela ne certifie ni l’existence du titre ni l’origine de la saisie.
`asset_class=equity` désigne ici une action, pas un ETF ou une position Forex.

Le ticker peut commencer par un chiffre et conserver des zéros initiaux. Le MIC
doit être fourni explicitement ; l’application ne vérifie pas encore ce code
contre un référentiel mondial. Un ISIN peut avoir plusieurs cotations sur des
marchés différents, chacune avec son identité, devise et cours. Les doublons
ISIN/marché, ticker/marché et symbole Bloomberg sont contrôlés. Les identités et
conventions de cours déjà enregistrées ne sont pas modifiées par une nouvelle
saisie en conflit. NYSE/Nasdaq restent ajoutés via le référentiel SEC existant.

La date `identity_as_of` décrit la validité déclarée dans la source. La date
`registry_observed_at` décrit l’enregistrement dans Market AI. Elles ne doivent
pas être présentées comme une date de publication inventée.

Le rapprochement documentaire utilise encore les CIK : sans CIK connu, aucune
publication SEC n’est associée par défaut à un titre international. Les
référentiels d’émetteurs et sources officielles hors États-Unis restent à intégrer.

## Unités et taux

Les devises actuellement acceptées sont USD, EUR, GBP, HKD, JPY, CHF, CAD, AUD,
CNY, SGD, NZD, SEK, NOK, DKK, INR, KRW, TWD, BRL, ZAR et MXN. Cette sélection
ne constitue pas la couverture de tout le WLS.

`quote_multiplier` est obligatoire à la saisie. Il vaut 1 pour un cours dans la
devise principale, 0,01 pour un cours en pence correspondant à GBP. L’application
ne devine pas l’unité depuis le nom de la place ou le symbole. Les cours fournis
doivent respecter la devise et le facteur du titre ; les cours Alpha Vantage ne
peuvent pas être remplacés par cette route de saisie.

Le sens du taux est **USD pour 1 unité de la devise locale**. Le collecteur BCE
normalise ses taux depuis EUR et conserve les deux valeurs de référence. Les
taux complémentaires inverses ou croisés doivent être normalisés explicitement
avant leur saisie manuelle. Aucun taux
USD/USD n’est nécessaire : le facteur 1 est une identité arithmétique.

```text
prix USD par titre = clôture brute × facteur d’unité × USD par unité de devise
```

Le calcul utilise Decimal ; le prix USD est arrondi à 6 décimales, les montants et
frais au centime, avec arrondi HALF_UP. Une conversion nulle après arrondi ou hors
capacité du prix enregistré est refusée. Le volume publié doit être fourni, sans
remplacer un volume inconnu par zéro.

Les cours et taux conservent leur date effective, URL et date d’enregistrement.
La source doit être une URL HTTP(S) sans identifiants, query string ni fragment ;
utiliser une référence documentaire sans paramètres secrets. Une nouvelle saisie
pour le même titre/date ou la même devise/date corrige l’observation existante.
Les saisies manuelles de taux gardent priorité sur la collecte BCE pour leur date.
Le contrôle automatique ne certifie pas la véracité d’une donnée saisie.

## Valorisation et simulation

Une clôture est combinée uniquement avec le dernier taux fourni **au plus tard
à la date de séance**. Un taux postérieur n’est jamais utilisé pour ce cours.
Les nouvelles opérations exigent des données non futures et assez récentes :
`MARKET_MAX_PRICE_AGE_DAYS=7` et `MARKET_MAX_FX_AGE_DAYS=7` par défaut, en jours
calendaires UTC. Aucun cours ou taux manquant n’est remplacé par une valeur fictive.

Une valorisation ancienne peut être affichée avec son état `stale`. Si un taux
manque, le prix USD et la valeur totale du portefeuille deviennent indisponibles.
Les frais, le capital, les coûts de revient et gains/pertes sont tous en USD.
Cette conversion ne crée pas de position ni de solde en devise étrangère.

Chaque opération convertie conserve dans `paper_trades.conversion` la clôture
locale, devise, facteur, date/source de cours, taux, date/source FX et dates de
consultation. `paper_trades.price` est le prix **USD** effectivement simulé.
Les corrections ultérieures des observations ne réécrivent pas cet instantané ;
la reprise idempotente renvoie l’opération et sa conversion initiales.

Les nouveaux achats restent soumis au WLS, aux frais, au capital disponible et à
la concentration du portefeuille, calculée sur les valeurs USD. Une cotation
internationale fournie ne consomme pas le quota du collecteur américain.

Les règles de conversion Bloomberg (heure, taux et arrondi), frais de change,
calendriers et tailles de lots restent à confirmer. La simulation accepte des
[dividendes nets et splits déclarés](PORTFOLIO_TRACKING.md), sans supposer leur
traitement officiel dans le challenge.
Les dates quotidiennes ne permettent pas d’établir un ordre intrajournalier précis
entre publication du taux et clôture. Cette simulation n’est pas une reproduction
exacte du challenge ni un backtest historique.

## API et vérifications

Toutes les routes sont sous `/api/v1/market` :

| Route | Usage |
| --- | --- |
| POST /international-instruments | Identité explicite et provenance de la cotation |
| POST /instruments/{id}/prices | Clôture locale datée d’une cotation manuelle |
| GET /fx-rates | Dernier taux fourni par devise, date et source |
| GET /fx-collection | Dernière tentative et dernier succès de la collecte automatique |
| POST /fx-rates | Taux daté, `currency`, `usd_per_unit`, `as_of`, `source_url` |
| GET /instruments | Cours local et `usd_valuation` : état, prix USD, conversion |

Les modèles et champs sont détaillés dans <http://localhost:8000/docs>.
Les tests unitaires n’utilisent pas le réseau. Les contrôles PostgreSQL ci-dessous
utilisent des fixtures et annulent toutes leurs écritures, même en cas d’échec.
Les exécuter successivement, car ils partagent les tables et verrous de simulation.

```powershell
docker compose exec backend python -m tests.smoke_market_portfolio
docker compose exec backend python -m tests.smoke_international_market
```
