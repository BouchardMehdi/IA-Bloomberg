# Cours quotidiens et portefeuille simulé

Cette étape suit les [règles du challenge connues](CHALLENGE.md). Elle ne produit pas
encore de propositions d'investissement et ne transmet aucun ordre à un courtier.

Les [analyses des titres suivis](INSTRUMENT_RESEARCH.md) sont consultables dans
`/analysis` : documents et faits sourcés, cours disponible et points à examiner.

## Activer les cours

Créer une clé personnelle depuis <https://www.alphavantage.co/support/#api-key> puis
ajouter `ALPHA_VANTAGE_API_KEY` dans `.env`. La clé reste côté serveur et est
masquée dans les logs HTTP ; elle n'est pas stockée dans les URL de provenance.

```powershell
docker compose --profile ai up -d --build
```

Dans <http://localhost:3000/portfolio>, ajouter les tickers à suivre. Chaque ticker
doit correspondre sans ambiguïté à un émetteur du référentiel SEC et à une cotation
NYSE ou Nasdaq. Les valeurs sont suivies en USD. La classe du titre n'est pas
certifiée par ce référentiel ; l'éligibilité au challenge reste à confirmer.

Le scheduler vérifie les titres toutes les heures, par lots de cinq. Il priorise
ceux qui n'ont pas encore été vérifiés ou l'ont été le moins récemment. Une collecte
réussie reste en cache jusqu'au prochain jour UTC ; une erreur attend au moins une
heure. Une collecte manuelle utilise le même budget et le même cache :

```powershell
docker compose exec backend python -m app.cli.collect_market
```

Sans clé, la collecte est désactivée, l'interface l'indique et aucune donnée fictive
n'est insérée. Les ordres simulés nécessitent un cours disponible et assez récent.

## Source et limites des données

Le client utilise le [service officiel TIME_SERIES_DAILY](https://www.alphavantage.co/documentation/)
en mode `compact`, soit les 100 dernières séances. Seuls la clôture brute et le
volume sont conservés avec la date de séance, l'URL sans clé et la date de collecte.
Ce n'est pas un flux temps réel. La date de séance n'est pas une date de publication
de nouvelle. Les doublons titre/date sont mis à jour ; les observations historiques
peuvent être corrigées par le fournisseur.

L'[offre gratuite](https://www.alphavantage.co/support/) annonce 25 requêtes par jour.
`MARKET_DAILY_REQUEST_BUDGET=20` fixe un budget local persistant, partagé entre CLI
et scheduler avec un verrou PostgreSQL. Chaque tentative réservée compte, même si
elle échoue ou si le processus s'interrompt. Le budget ne connaît pas les appels
effectués en dehors de Market AI avec la même clé. Les erreurs du fournisseur sont
enregistrées sous forme de codes, sans recopier de réponse susceptible de contenir
un secret. Respecter les [conditions d'utilisation du fournisseur](https://www.alphavantage.co/terms_of_service/)
pour l'usage des données ; l'application actuelle est une installation locale.

## Paramétrer le portefeuille

Chaque création fixe ses règles : capital initial, frais par opération en points de
base, concentration maximale par titre, tickers autorisés et dates facultatives.
La devise prise en charge dans cette version est USD. Les valeurs proposées par le
formulaire utilisent désormais 1 000 000 USD, conformément au capital communiqué.
Les frais de 10 points de base et la limite de 25 % restent des exemples de
configuration à confirmer. Créer une nouvelle simulation
lorsque le règlement sera disponible ; les règles d'un historique existant restent
stables.

Un achat ou une vente est simulé immédiatement au dernier cours de clôture stocké.
`MARKET_MAX_PRICE_AGE_DAYS=7` borne son ancienneté en jours calendaires. La date du
cours et celle de l'enregistrement restent distinctes. Cette méthode n'est pas un
backtest et ne garantit pas qu'une exécution à ce prix aurait été possible.

- Les quantités sont entières ; pas de vente à découvert ni de levier.
- L'achat doit être couvert par le capital disponible, frais inclus.
- La concentration d'un achat est calculée sur la valeur du portefeuille après frais.
- La vente ne peut dépasser les titres détenus.
- Un cours manquant ou trop ancien bloque une opération. Une valorisation ancienne
  reste affichable avec un avertissement ; une valorisation manquante reste inconnue.
- Les autres positions doivent aussi être valorisables avec des cours assez récents
  pour vérifier la concentration d'un achat.

Les calculs monétaires utilisent `Decimal`, avec arrondi au centime. Les frais
d'achat entrent dans le coût de revient ; une vente partielle affecte ce coût
proportionnellement, et une vente totale solde le reliquat. Le gain réalisé inclut
les frais des deux côtés. La valeur totale correspond au capital disponible plus
les positions ; sa variation inclut les gains réalisés et latents.

Le portefeuille est verrouillé pendant une opération. Capital, position et ligne
du registre sont enregistrés dans une transaction unique. L'unicité du couple
portefeuille/identifiant d'ordre rend une reprise idempotente : le même ordre
renvoie sa ligne existante ; réutiliser son identifiant pour un ordre différent est
refusé. Les dividendes, splits, conversions de devises, taxes, glissement de prix,
frais minimaux et liquidité ne sont pas modélisés. Il faut les ajouter avant de
présenter la simulation comme une reproduction fidèle du challenge.

## API et vérifications

Toutes les routes sont sous `/api/v1/market` :

Les montants et cours sont des chaînes décimales dans les réponses JSON pour
conserver leur précision ; les quantités sont des entiers.

| Route | Usage |
| --- | --- |
| GET /instruments | Titres, dernière clôture, état de collecte et activation du fournisseur |
| POST /instruments | Ajouter un ticker identifié dans le référentiel SEC |
| GET /instruments/{id}/prices | Historique des clôtures et volumes, sources et dates |
| GET /portfolios | Simulations existantes |
| POST /portfolios | Créer une simulation et ses paramètres |
| GET /portfolios/{id} | Capital, positions, gains/pertes et 50 dernières opérations |
| POST /portfolios/{id}/orders | Enregistrer un achat ou une vente simulés |

Les tests utilisent des transports simulés et ne dépendent pas du réseau. Le
contrôle PostgreSQL ci-dessous annule toujours ses prix et opérations de test :

```powershell
docker compose exec backend python -m tests.smoke_market_portfolio
```
