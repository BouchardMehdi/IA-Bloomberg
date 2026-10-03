# Collecte automatique des taux de référence BCE

Le scheduler récupère par défaut les taux de référence de la BCE au démarrage,
puis toutes les 60 minutes. Aucune clé fournisseur ni appel LLM n’est nécessaire.
Le fichier officiel utilisé est :
<https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml>.
Il fournit un historique récent pour les cours locaux datés avant la collecte.

La [BCE](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)
publie ces taux à titre informatif, généralement vers 16 h CET les jours ouvrés
hors fermetures TARGET. Ce sont des références de valorisation, pas des taux
d’exécution. Ils ne reproduisent pas nécessairement les conventions de Bloomberg.
La date conservée est la date de référence du fichier, pas une heure de publication
inventée. La date de collecte est enregistrée séparément en UTC.

## Calcul et provenance

Le fichier exprime les devises pour 1 EUR. Pour une même date :

```text
USD pour 1 unité locale = USD pour 1 EUR / unités locales pour 1 EUR
```

Pour EUR, le dénominateur 1 est une identité arithmétique. Aucun taux USD/USD n’est
stocké. Les calculs utilisent Decimal et HALF_UP à 10 décimales. Les deux valeurs
originales et la formule sont conservées dans `fx_rates.derivation`, avec le
fournisseur `ecb`, la date de référence, l’URL officielle et la date de collecte.
Ces preuves sont aussi copiées dans la conversion d’une opération simulée.

Seules les devises déjà prises en charge par Market AI et présentes dans le
fichier sont importées. La couverture réelle de la dernière publication récupérée
est affichée dans `/international`. Une devise absente n’est pas complétée ou
assimilée à une autre devise ; une source complémentaire reste nécessaire.

La valorisation continue de choisir un taux au plus tard à la date du cours et
de contrôler son ancienneté. L’import ne crée ni action, ni appartenance WLS, ni
position Forex. Les achats restent soumis aux règles de simulation existantes.

## Fiabilité et priorité des saisies

Une transaction et un verrou PostgreSQL partagé sérialisent les collectes CLI et
scheduler. Le cache persistant évite un nouvel appel pendant l’intervalle configuré,
y compris après une erreur. Le HTTP est limité à 60 secondes au total et 1 Mo de
contenu. XML invalide, DTD, dates futures ou dupliquées, taux non positifs, doublons
de devises ou USD absent entraînent le refus de tout le document.

Le lot validé est enregistré atomiquement. Une erreur HTTP ou XML ne supprime pas
les observations précédentes. Les erreurs HTTP/XML sont enregistrées avec un code
sans contenu brut. Une erreur de base de données annule la transaction et est
signalée dans les logs du scheduler. Une interruption du processus annule également
la transaction ; elle ne laisse pas un lot partiellement importé.

Les observations existantes sont marquées `manual` à la migration. Pour une même
devise/date, la collecte met à jour ses propres données mais ne remplace jamais
une saisie manuelle. Une saisie explicite via `/fx-rates` devient manuelle et retire
la dérivation automatique de l’observation remplacée. Les conversions des anciennes
opérations ne sont jamais réécrites.

`fx_collection_runs` conserve les succès et échecs HTTP/XML, leurs dates, le nombre
d’observations validées, les saisies manuelles préservées, la dernière date de
référence et les devises disponibles à cette date. Un succès de téléchargement ne
garantit pas que toutes les devises ou dates nécessaires au portefeuille existent.
L’API `GET /api/v1/market/fx-collection` expose la dernière tentative et le dernier
succès ; `/fx-rates` expose aussi fournisseur et dérivation.

## Configuration et contrôle

```dotenv
FX_COLLECTION_ENABLED=true
FX_COLLECTION_INTERVAL_MINUTES=60
MARKET_MAX_FX_AGE_DAYS=7
```

Le premier paramètre active le scheduler FX ; l’intervalle est compris entre 15 et
1 440 minutes. `SCHEDULER_RUN_ON_START=false` retarde la première collecte de cet
intervalle. Recréer backend et scheduler après un changement de configuration.

```powershell
docker compose --profile ai up -d --build
docker compose exec backend python -m app.cli.collect_fx
```

La commande manuelle utilise le même cache et le même verrou. Elle peut être
utilisée explicitement même lorsque le scheduler FX est désactivé. Le scheduler
reste nécessaire pour les mises à jour automatiques.

Les tests unitaires utilisent une fixture XML et un transport HTTP simulé, sans
réseau. Le contrôle PostgreSQL ci-dessous annule toutes ses écritures et conserve
le contenu réel de la base ; exécuter les contrôles de simulation successivement.

```powershell
docker compose exec backend python -m tests.smoke_fx_collection
```
