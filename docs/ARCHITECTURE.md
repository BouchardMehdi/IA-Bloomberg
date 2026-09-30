# Architecture

## Vue d'ensemble

```text
Sources → Collecte → Normalisation → Déduplication → Extraction IA
                                                        ↓
Interface ← Rapports ← Classement ← PostgreSQL ← Article / Event
                                      ↑
                              Workers via API limitée
```

La fondation actuelle contient le frontend, l'API, PostgreSQL, Redis, Caddy et un scheduler léger. Le scheduler exécute les collectors dans un processus séparé et enregistre chaque tentative dans PostgreSQL. Les blocs d'IA seront ajoutés progressivement.

## Responsabilités

- FastAPI expose l'API et contrôle les accès aux données.
- PostgreSQL conserve les articles, événements, relations et résultats structurés.
- pgvector accueillera les embeddings utiles au regroupement sémantique.
- Redis servira de file de travail et de stockage éphémère.
- Next.js fournit une interface responsive et deviendra une PWA.
- Caddy fournit le point d'entrée HTTP et, sur le VPS, terminera HTTPS.
- Le scheduler orchestre chaque source dans une boucle périodique indépendante, sans exposer de route publique de déclenchement.

Les workers IA distants utiliseront ultérieurement des endpoints authentifiés pour réserver une tâche, publier un résultat et envoyer un heartbeat. Ils ne se connecteront jamais directement aux services de données.

## Décisions initiales

Le projet reste un monolithe modulaire. Cette approche réduit le coût opérationnel et garde les transactions Article/Event simples. Les workers sont séparés uniquement parce qu'ils peuvent s'exécuter sur d'autres machines.

Le temps est stocké en UTC. Les heures de marché seront calculées avec une bibliothèque de calendriers boursiers plutôt qu'avec des horaires fixes.
