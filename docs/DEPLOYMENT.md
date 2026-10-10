# Déploiement

Le déploiement cible un VPS Linux avec Docker Compose.

1. Installer Docker et le plugin Compose.
2. Cloner le dépôt.
3. Copier `.env.example` vers `.env` et remplacer tous les secrets.
4. Adapter le domaine dans `deploy/Caddyfile` pour activer HTTPS automatique.
5. Lancer `docker compose up -d --build`.
6. Vérifier `docker compose ps` et `/api/v1/health/ready`.

PostgreSQL et Redis n'exposent aucun port hôte. Seuls Caddy et, pour le développement initial, les ports 3000/8000 sont publiés. Sur un VPS, ces deux publications directes pourront être retirées afin que Caddy reste l'unique point d'entrée.

Les ports directs 3000, 8000 et 11434 sont désormais limités à l'interface locale.
Le proxy reste le point d'entrée réseau. Le frontend utilise `/api/v1` sur la même
origine par défaut ; son proxy interne rejoint le backend. Pour le développement
hors Docker, `API_INTERNAL_URL=http://localhost:8000` est la valeur par défaut.
Une ancienne valeur explicite `NEXT_PUBLIC_API_URL` reste prioritaire ; utiliser
`/api/v1` et reconstruire le frontend avant de partager le site sur un autre hôte.

## Comptes et rôles

L'authentification reste **désactivée par défaut en local** pour ne pas verrouiller
les installations existantes. Avant d'exposer des données sur un réseau partagé :

1. Créer un premier administrateur dans « Mon espace » sur l'installation locale,
   ou lancer la commande interactive (aucun mot de passe dans la commande) :

   ```powershell
   docker compose exec backend python -m app.cli.create_user administrateur
   ```

2. Configurer le domaine HTTPS de Caddy et `BACKEND_CORS_ORIGINS` avec les origines
   exactes autorisées (schéma + domaine + port, sans chemin).
3. Dans `.env`, activer `AUTH_ENABLED=true`, `AUTH_COOKIE_SECURE=true` et
   `ENVIRONMENT=production`. La configuration production refuse de démarrer sans
   authentification et cookies HTTPS. Pour tester uniquement sur HTTP local,
   garder `ENVIRONMENT=development` et `AUTH_COOKIE_SECURE=false`.
4. Recréer backend et scheduler, puis vérifier connexion, lecture et modification
   avec les rôles appropriés. Le frontend affiche automatiquement la connexion.

Les rôles sont `viewer` (lecture et marqueurs d'alertes), `editor` (modifications)
et `admin` (gestion des comptes en plus). L'espace est partagé : les rôles ne
créent pas de portefeuilles privés. Aucune inscription publique. Un administrateur
actif doit toujours être conservé. La modification d'un rôle ou la désactivation
révoque les sessions. Un changement de mot de passe exige l'ancien mot de passe et
ferme toutes les sessions du compte. La commande `--reset-password` peut réinitialiser
un mot de passe par accès administrateur au serveur ; elle ne change pas le rôle.

Les mots de passe sont hachés avec scrypt et sel aléatoire ; les jetons de session
opaques ne sont stockés qu'en SHA-256. Cookie HttpOnly, SameSite=Strict, expiration
12 heures et contrôles de l'origine sur les écritures. Les accès en lecture seule
sont contrôlés côté serveur. Les tentatives de connexion sont limitées par adresse
réseau et nom de compte via Redis (20 par fenêtre de 15 minutes) ; derrière le
proxy, la limite réseau peut être partagée. Une panne Redis refuse la connexion.
Pas de récupération par email, de SSO ou de second facteur dans cette version.

## Sauvegardes PostgreSQL chiffrées

Le fichier optionnel `docker-compose.backup.yml` ajoute une sauvegarde quotidienne
avec rétention de 14 jours, réglables. Il n'est pas activé par le Compose principal
et nécessite **votre destinataire public age**. L'archive PostgreSQL custom utilise
[pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html) puis le chiffrement
[age](https://github.com/FiloSottile/age). Aucune archive en clair n'est écrite sur
le disque hôte ; le dump transitoire reste dans le tmpfs du conteneur (1 Go).

Construire l'image et générer une clé dans un dossier privé existant :

```powershell
docker build -t market-ai-backup ./deploy/backup
New-Item -ItemType Directory -Force private-data/keys
docker run --rm -v "${PWD}/private-data/keys:/keys" --entrypoint age-keygen market-ai-backup -o /keys/backup-identity.key
```

Conserver la clé privée hors du serveur et hors Git, avec une copie de secours.
Seule la clé **publique** affichée va dans `BACKUP_RECIPIENT` dans `.env`.
Ne pas perdre la clé privée : aucune restauration ne sera possible sans elle.

```powershell
docker compose -f docker-compose.yml -f docker-compose.backup.yml up -d --build backup
docker compose -f docker-compose.yml -f docker-compose.backup.yml logs --tail 20 backup
```

Archives chiffrées et checksums restent dans `private-data/backups/`. L'échec d'une
sauvegarde conserve les anciennes ; la rétention est appliquée après succès,
uniquement aux fichiers `market-*.dump.age*` de ce dossier. Copier les archives
chiffrées vers un stockage séparé : le volume local seul ne protège pas d'une
perte de machine. Le rôle PostgreSQL doit pouvoir lire toutes les tables et créer
une base pour la vérification de restauration. Les identifiants de connexion
doivent correspondre à ceux utilisés par le backend ; adapter le fichier optionnel
si `DATABASE_URL` désigne un serveur distinct des variables `POSTGRES_*`.

## Vérifier une restauration sans écraser l'application

Le script vérifie le checksum, déchiffre puis utilise
[pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html) dans une **nouvelle**
base explicitement nommée avec le suffixe `_restore_check`. Il refuse une base
existante et ne contient ni suppression de base ni option `--clean`.

Remplacer l'archive et le chemin absolu de la clé privée :

```powershell
docker compose -f docker-compose.yml -f docker-compose.backup.yml run --rm --no-deps -e RESTORE_DATABASE=market_ai_restore_check -v "C:/chemin/backup-identity.key:/run/secrets/backup_identity:ro" --entrypoint /bin/sh backup /opt/backup/restore-check.sh /backups/market-DATE.dump.age
```

La base de vérification est conservée pour inspection. Le script affiche la
version de migration et les compteurs d'articles/portefeuilles. Une migration vers
un serveur de remplacement reste une opération explicite d'administration ; ce
script ne bascule pas l'application. Les clés, la configuration et les fichiers
privés WLS nécessitent leurs propres sauvegardes sécurisées ; ils ne sont pas
inclus dans le dump PostgreSQL. Redis n'est pas la mémoire principale.
