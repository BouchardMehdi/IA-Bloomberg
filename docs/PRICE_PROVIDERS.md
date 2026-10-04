# Collecte des clôtures : contrat commun

La collecte et PostgreSQL utilisent désormais une interface commune pour les
fournisseurs de cours. **Alpha Vantage est le seul adaptateur connecté** ; sa
couverture reste NYSE/Nasdaq, USD, facteur d'unité 1. Les clôtures internationales
restent fournies manuellement depuis `/international`. Cette infrastructure ne
reconstitue pas le WLS et n'active aucune nouvelle source de données.

## Contrat et contrôles

`app/market/providers.py` définit `PriceProvider`, `ProviderPolicy`, `QuoteIdentity`,
`DailyClose` et `QuoteBatch`. Un adaptateur déclare sa couverture avec `supports`
puis renvoie un lot avec `fetch`. Le service de collecte n'appelle plus directement
le format Alpha Vantage. CLI et scheduler passent par `provider_registry.py`, qui
active uniquement les adaptateurs implémentés et explicitement configurés.

Chaque requête désigne un **titre et sa cotation** : identifiant interne, ticker
exact (zéros initiaux conservés), marché, devise principale et facteur d'unité.
Le lot retourné doit correspondre exactement à cette identité et au fournisseur.
Il conserve aussi le symbole propre au fournisseur. Le contrat accepte les
devises prises en charge par la simulation et les facteurs explicites, notamment
0,01 pour des cours en pence ; aucun adaptateur international n'est encore activé.

Avant toute écriture, le service revalide le lot entier avec Pydantic :

- une à mille observations de clôtures **brutes**, sans ajustement ;
- dates de séance non futures et distinctes ;
- prix positifs et finis, représentables dans `Numeric(20,6)` ;
- volumes entiers publiés, positifs ou nuls, sans volume manquant remplacé par zéro ;
- titre, marché, devise et unité conformes à la requête ;
- URL HTTP(S) sans identifiants ni fragment. Les seuls paramètres actuellement
  acceptés sont la requête publique Alpha Vantage (`function`, `symbol`, `outputsize`),
  sans clé. Les futurs adaptateurs fourniront une référence documentaire publique.

Alpha Vantage vérifie le symbole de ses métadonnées. Le marché, la devise et
l'unité sont des conventions déclarées pour la cotation suivie ; la réponse
`TIME_SERIES_DAILY` ne les certifie pas indépendamment. Ce contrat contrôle les
incohérences d'un adaptateur, pas la véracité des données de son fournisseur.
Un nouvel adaptateur devra vérifier ses métadonnées et ses correspondances
explicites avant de construire ce lot ; recopier l'identité ne constitue pas une preuve.

## Quotas et reprises

La réservation PostgreSQL est enregistrée **avant** l'appel réseau. Les tentatives
échouées ou interrompues comptent aussi. Le verrou de réservation est partagé
entre scheduler et CLI ; les compteurs et caches sont séparés par fournisseur.
Le budget Alpha Vantage reste `MARKET_DAILY_REQUEST_BUDGET=20`, limité à 25.
Il porte sur la journée UTC et ne connaît pas les appels externes avec la même clé.

Le scheduler vérifie chaque fournisseur configuré toutes les heures, par lots de
cinq, en priorité les titres les moins récemment vérifiés. Les titres hors de la
couverture de l'adaptateur sont ignorés sans consommer son budget. Une réussite
reste en cache jusqu'au prochain jour UTC. Une erreur attend cinq minutes par défaut,
avec `retry_at` persistant. Une interruption conserve la réservation et attend
aussi ce délai avant reprise. Chaque appel est borné à 90 secondes au total.

Une réponse HTTP 429 ou un message de refus/quota suspend les appels de **tout le
fournisseur** jusqu'au prochain jour UTC. Ce délai conservateur peut être plus
long que nécessaire ; il évite de consommer le budget sur les autres titres.
Les codes d'erreur sont bornés et ne contiennent ni corps fournisseur ni secret.
Une exception inattendue de l'adaptateur devient `provider_internal_error`.
Les erreurs de base de données restent des erreurs de transaction.

Un lot invalide n'écrit aucun cours et laisse les anciens prix consultables.
Les écritures d'un lot réussi et sa réussite sont validées dans la même transaction.
Les doublons titre/date corrigent l'observation, sans réécrire les opérations
simulées déjà enregistrées. Les règles d'ancienneté continuent de bloquer une
nouvelle opération lorsque les prix ou taux sont trop anciens.

## Provenance et consultation

`daily_prices.provider` et `quote_context` conservent le fournisseur, la cotation,
devise, facteur, symbole fournisseur et convention de clôture brute. La date de
séance, l'URL et la date de consultation restent distinctes. La saisie manuelle
conserve le même contexte, sans inventer de symbole fournisseur.

`market_fetch_runs` conserve aussi fournisseur, contexte, code d'erreur et date de
reprise. La migration `0012` attribue les fournisseurs existants selon le mode de
collecte déjà enregistré ; elle laisse le contexte historique vide plutôt que
de fabriquer une preuve. Les nouvelles conversions d'opérations internationales
figent la provenance du cours avec celle du taux FX.

`GET /api/v1/market/price-collection` expose la couverture déclarée, activation,
budget, tentatives du jour UTC, quota restant, suspension et dernière tentative.
La page `/portfolio` affiche le budget et la suspension. L'historique
`GET /instruments/{id}/prices` expose fournisseur et contexte par observation ;
`GET /instruments` expose aussi `retry_at` pour le titre.

## Raccorder l'international ensuite

Lorsque l'export WLS et une source de cours autorisée seront disponibles, il
faudra choisir un fournisseur couvrant les cotations concernées, enregistrer et
vérifier ses correspondances exactes par titre/marché, puis ajouter son adaptateur
et sa configuration serveur. Ni suffixe de ticker, ni MIC, ni symbole Bloomberg,
ni devise/unité ne doivent être devinés. Aucun abonnement n'est requis pour
préparer ce socle ; aucune clé n'est exposée au navigateur.

## Vérifications

Les tests utilisent des transports et adaptateurs simulés, sans réseau.
Le contrôle PostgreSQL suivant annule toutes ses écritures, y compris après échec :

```powershell
docker compose exec backend python -m tests.smoke_price_providers
```

Il couvre l'indépendance et la persistance des quotas, le cache, les reprises,
la suspension globale du fournisseur, le rejet atomique d'un lot invalide,
la conservation des anciens prix, la provenance et les réponses API.
