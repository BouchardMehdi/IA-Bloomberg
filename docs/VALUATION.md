# Valorisation par les bénéfices

La rubrique `/analysis` « Valorisation : prix rapporté aux bénéfices » calcule le
PER annuel sur une clôture locale et un BPA annuel GAAP dilué par titre fourni
avec ses preuves. Elle ne consomme aucun appel IA, quota Alpha Vantage ou ordre.
Le [PER est le prix divisé par le bénéfice par action](https://www.investor.gov/introduction-investing/investing-basics/glossary/price-earnings-pe-ratio).

## Données nécessaires

Les BPA SEC actuels concernent l’émetteur. Un CIK, un ISIN ou une mention de ticker
ne prouvent pas l’unité économique d’une classe d’action, d’un ADR ou d’une
cotation. Aucun BPA SEC n’est donc injecté automatiquement dans la valorisation.
Le formulaire exige :

- Une période annuelle explicitement documentée de 350 à 378 jours, GAAP diluée,
  avec BPA **par un titre de cette cotation**, dans la devise locale.
- URL et date de publication du résultat, après la fin de période.
- URL, date et explication de la correspondance au titre, incluant classes,
  ADR et ajustements de divisions d’actions nécessaires à la séance désignée.
- Confirmation explicite de cette correspondance par la personne qui saisit.
- Date de séance couverte par ces preuves. Devise et multiplicateur viennent
  du titre suivi et sont revalidés côté serveur.

Ces preuves sont fournies manuellement : leur présence et cohérence sont
contrôlées, pas la vérité de leur contenu. Ce statut reste affiché. Le serveur
fige également l’identité du titre avec l’observation. Les valeurs ne sont jamais
attribuées à d’autres cotations de l’émetteur. Aucun ratio d’ADR n’est inventé.

## Calcul et blocages

Prix normalisé = clôture brute × multiplicateur de cotation. Le BPA est déjà
exprimé en devise par titre : le multiplicateur ne lui est pas appliqué.
PER = prix normalisé / BPA annuel. Rendement bénéficiaire comptable = BPA /
prix normalisé × 100. Il ne s’agit ni d’un rendement futur ni d’un dividende.
Les montants et calculs restent décimaux, sans conversion FX ni nombres flottants.

La clôture doit être récente selon `MARKET_MAX_PRICE_AGE_DAYS`, non future et
positive, et son contexte compatible quand disponible. La dernière observation
fournie doit porter sur cette exacte séance et identité, avec même devise et
unité. Un nouveau cours nécessite une nouvelle preuve couvrant la séance. Aucun
retour à une ancienne observation positive n’est tenté après une nouvelle perte.
Les observations simultanées ambiguës bloquent le calcul.

La période doit finir avant la séance et dater de moins de 551 jours à celle-ci.
Toutes les sources doivent être horodatées avec fuseau et publiées **avant le
jour UTC de la séance** : faute d’heure de clôture fiable, une publication du même
jour n’est pas utilisée. Cela n’invente aucune disponibilité historique : la
date de première consultation est distincte et cette rubrique n’est pas un backtest.
Les BPA nuls/négatifs restent conservés, mais leur PER et rendement bénéficiaire
ne sont pas calculés. Aucun trimestre n’est annualisé, ni cumul transformé en
douze mois glissants. Il s’agit d’un PER annuel fourni, pas d’un PER TTM automatique.

## Multiple élevé ou faible

Sans référence compatible, le ratio seul ne permet pas de qualifier le prix.
Une référence facultative exige valeur positive, périmètre, justification de
comparabilité, convention annuelle GAAP diluée, date et source publiée. Sa date
doit précéder ou égaler sa publication et la séance, et dater au plus de 30 jours
avant celle-ci. Les dates sont affichées ; une référence n’est pas reconstruite.

La comparaison affiche « multiple supérieur/inférieur/égal à cette référence »
et l’écart relatif au multiple fourni. Elle n’établit ni surévaluation intrinsèque,
ni sous-évaluation, ni cible de cours. Croissance attendue, risque, qualité des
bénéfices, secteur et conventions des pairs restent à analyser. Aucun seuil
universel, score d’achat ou changement du classement de recherche n’est ajouté.

## Persistance et API

`valuation_observations` conserve chaque saisie sourcée liée au titre. Un hash
empêche les doublons exacts ; une nouvelle saisie ne remplace pas la précédente.
Le GET affiche les vingt dernières observations et signale sa borne, tout en
conservant l’historique complet en PostgreSQL. Les sources ne doivent contenir
ni identifiants, ni clés, ni paramètres de requête.

- `GET /api/v1/market/instruments/{id}/valuation`
- `POST /api/v1/market/instruments/{id}/valuation`

Migration : `20261004_0017`. Vérifications : `tests/test_valuation.py` et contrôle
PostgreSQL/API sans réseau, toutes les fixtures annulées :

```powershell
docker compose run --rm --no-deps backend python -m tests.smoke_valuation
```
