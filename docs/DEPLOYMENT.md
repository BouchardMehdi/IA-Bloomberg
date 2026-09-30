# Déploiement

Le déploiement cible un VPS Linux avec Docker Compose.

1. Installer Docker et le plugin Compose.
2. Cloner le dépôt.
3. Copier `.env.example` vers `.env` et remplacer tous les secrets.
4. Adapter le domaine dans `deploy/Caddyfile` pour activer HTTPS automatique.
5. Lancer `docker compose up -d --build`.
6. Vérifier `docker compose ps` et `/api/v1/health/ready`.

PostgreSQL et Redis n'exposent aucun port hôte. Seuls Caddy et, pour le développement initial, les ports 3000/8000 sont publiés. Sur un VPS, ces deux publications directes pourront être retirées afin que Caddy reste l'unique point d'entrée.

Les volumes Docker conservent les données. Une stratégie de sauvegarde PostgreSQL chiffrée et testée devra être ajoutée avant l'utilisation réelle.
