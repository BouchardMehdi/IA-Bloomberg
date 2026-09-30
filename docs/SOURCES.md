# Sources

Les sources doivent être publiques, accessibles légalement et traçables. Les premières intégrations viseront quelques sources primaires stables : BCE, Réserve fédérale, SEC et pages Investor Relations sélectionnées.

Chaque futur collector produira un même format normalisé : identifiant externe, URL canonique, titre, contenu autorisé, langue, auteur, date de publication et date de collecte. Les erreurs, durées et volumes seront journalisés.

## Banque centrale européenne

Le premier collector utilise le flux officiel des communiqués :

```text
https://www.ecb.europa.eu/rss/press.html
```

Commande manuelle :

```bash
docker compose exec backend python -m app.cli.collect_ecb
```

Le contenu RSS est testé à partir de `backend/tests/fixtures/ecb_press.xml`. Les tests ne dépendent donc pas du réseau. La déduplication exacte s'appuie sur deux contraintes PostgreSQL indépendantes : URL canonique et hash SHA-256 du titre et du contenu normalisés.

Le déclenchement reste volontairement une commande interne. Aucun endpoint public ne permet de lancer un collector.

Le service Docker `scheduler` lance aussi la collecte au démarrage puis selon `ECB_COLLECTION_INTERVAL_MINUTES`. Une erreur est journalisée et enregistrée dans `collection_runs`; elle n'arrête pas les exécutions suivantes.

## Réserve fédérale américaine

Le deuxième collector utilise le flux officiel de tous les communiqués du Board of Governors :

```text
https://www.federalreserve.gov/feeds/press_all.xml
```

Commande manuelle :

```bash
docker compose exec backend python -m app.cli.collect_fed
```

Le service `scheduler` lance ce collector dans une boucle indépendante selon `FED_COLLECTION_INTERVAL_MINUTES`. Une indisponibilité de la Fed ne bloque donc pas la collecte de la BCE, et inversement. La normalisation et la déduplication utilisent le même contrat que le collector BCE.
