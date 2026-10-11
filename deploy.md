# Déployer Market AI sur le VPS Nginx + Docker + Certbot

Le site principal reste chez Hostinger. Seul le sous-domaine de ce projet pointe
vers le VPS. Ce guide prend `market-ai.bouchard-mehdi.fr` comme exemple modifiable.
Utiliser **l'adresse IP réelle du VPS** : les IP des exemples d'autres projets ne
sont pas utilisées automatiquement.

## Organisation et prérequis

```text
IA-Bloomberg/
  frontend/                    # front Next.js
  backend/                     # back FastAPI, migrations et tests
  docker-compose.yml           # développement local
  docker-compose.production.yml # services VPS, sans Caddy ni Ollama
  .env.example                 # paramètres locaux
  .env.production.example      # modèle du .env du VPS
  README.md
  deploy.md
  deploy/nginx.conf.template
```

VPS Linux avec Git, Nginx, Certbot et son plugin Nginx, Docker et
**Docker Compose 2.24.4+**. Nginx et Certbot restent installés sur l'hôte.
Les conteneurs appartiennent au projet `market-ai-vps` ; conserver ce nom pour
retrouver les mêmes volumes après une mise à jour. Ne pas utiliser `container_name`.
L'IA tourne sur le PC Windows avec le [dossier portable](docs/PORTABLE_AI.md).

## 1. DNS Hostinger et ports

Créer un enregistrement **A**, nom `market-ai`, pointant vers l'IP du VPS.
Ne pas modifier l'enregistrement du domaine principal. Le template fourni écoute
en IPv4 : retirer un éventuel AAAA de ce sous-domaine, ou configurer aussi les
écoutes IPv6 de son virtual host et vérifier HTTPS en IPv6 avant de le conserver.
Les ports publics 80/443 doivent parvenir au Nginx existant.

Avant de retenir les ports du projet, vérifier qu'ils sont libres :

```sh
sudo ss -ltnp
docker compose version
```

Valeurs proposées : frontend **127.0.0.1:8088**, backend **127.0.0.1:3008**.
Elles se règlent avec `VPS_FRONTEND_PORT` et `VPS_BACKEND_PORT` et doivent être
différentes des ports des autres projets. PostgreSQL et Redis n'ont aucun port
publié ; aucun conteneur de ce projet ne publie 80/443 ou Ollama.

## 2. Cloner et créer le .env serveur

Depuis le compte de déploiement disposant de l'accès Docker :

```sh
cd /home/projects
git clone <URL_DU_DEPOT> IA-Bloomberg
cd IA-Bloomberg
umask 077
test ! -e .env && cp .env.production.example .env
chmod 600 .env
nano .env
```

Si `.env` existe déjà, l'inspecter et le compléter, sans l'écraser.
**Ne pas transférer le `.env` du PC** ni son `docker-compose.override.yml`.
Renseigner :

| Variable | Valeur |
| --- | --- |
| `COMPOSE_FILE` | `docker-compose.production.yml` : conserver cette sélection |
| `COMPOSE_PROJECT_NAME` | `market-ai-vps` : conserver ce nom |
| `SITE_DOMAIN` | sous-domaine choisi, sans `https://` ni chemin |
| `VPS_FRONTEND_PORT`, `VPS_BACKEND_PORT` | ports libres, 8088 et 3008 par défaut |
| `ACME_EMAIL` | votre véritable email de contact Certbot |
| `POSTGRES_PASSWORD` | mot de passe aléatoire de **64 caractères hexadécimaux** |
| `AI_WORKER_TOKEN_SHA256` | empreinte générée par le dossier IA portable |
| `SEC_USER_AGENT` | `MarketAI/0.1 votre-email@votre-domaine.fr` |
| `ALPHA_VANTAGE_API_KEY` | votre clé, facultative pour démarrer le site |
| `BACKUP_RECIPIENT` | destinataire **public** age pour les sauvegardes |

`openssl rand -hex 32` permet de générer le mot de passe PostgreSQL, à conserver
uniquement dans ce fichier privé. Ne pas modifier ce mot de passe après création
du volume sans effectuer aussi une rotation dans PostgreSQL.

Sur le PC, lancer `Configurer-IA.bat` dans le dossier portable avec
`https://market-ai.bouchard-mehdi.fr` (ou votre domaine choisi). Reporter seulement
`AI_WORKER_TOKEN_SHA256` et `OLLAMA_MODEL` de `config/vps-worker.txt` dans le `.env`
du VPS. **Le jeton brut de `config/worker.json` reste sur le PC.**
Les accès utilisent des sessions opaques ; aucun `JWT_SECRET` n'est demandé.

## 3. Lancer les services

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend scheduler frontend
docker compose exec backend python -m app.cli.create_user administrateur
```

Le mot de passe administrateur est demandé sans apparaître dans la commande.
Le backend contrôle les paramètres de production puis applique les migrations.
Le scheduler attend son démarrage. Les comptes et cookies HTTPS sont obligatoires.
Le frontend s'exécute avec `NODE_ENV=production`.

Grâce à `COMPOSE_FILE` dans le `.env`, les commandes simples choisissent uniquement
le Compose de production, sans charger l'override local. Ne pas ajouter
`-f docker-compose.yml`, qui sélectionnerait le développement.
Les variables `COMPOSE_*` exportées dans votre shell peuvent aussi changer la
sélection : `docker compose config --services` doit donner backend, scheduler,
frontend, postgres et redis, sans reverse-proxy ni ollama (backup reste optionnel).

Contrôler depuis le VPS, en adaptant les ports s'ils ont changé :

```sh
curl -I http://127.0.0.1:8088
curl --fail http://127.0.0.1:3008/api/v1/health/ready
```

Le frontend peut rediriger vers la connexion. L'API de santé doit répondre.
Les volumes de production commencent vides : les données, exports WLS et comptes
du Docker local ne sont **pas transférés automatiquement**. Leur migration exige
une sauvegarde/restauration explicite, jamais l'écrasement d'une base existante.

## 4. Ajouter uniquement le virtual host de Market AI

Générer la configuration avec le domaine et les ports effectifs du `.env` :

```sh
sh deploy/vps.sh nginx > /tmp/market-ai.nginx.conf
cat /tmp/market-ai.nginx.conf
```

La génération n'affiche aucun secret. Vérifier le résultat avant installation :

```sh
if sudo test -e /etc/nginx/sites-available/market-ai || sudo test -L /etc/nginx/sites-enabled/market-ai; then
    echo 'Virtual host existant : sauvegarder et modifier manuellement, sans le remplacer.'
else
    sudo install -m 644 /tmp/market-ai.nginx.conf /etc/nginx/sites-available/market-ai &&
    sudo ln -s /etc/nginx/sites-available/market-ai /etc/nginx/sites-enabled/market-ai &&
    sudo nginx -t &&
    sudo systemctl reload nginx
fi
```

Si ce virtual host existe déjà, le bloc le conserve : le modifier après sauvegarde.
Ne pas supprimer le site par défaut, les autres virtual hosts ou leurs certificats.
La config transmet `/api/v1/...` au backend sans retirer le préfixe, et le reste
au frontend. Nginx remplace les en-têtes du client ; le backend utilise ces
en-têtes sur son réseau de confiance et son port lié à localhost uniquement.

## 5. HTTPS avec Certbot

Après propagation du DNS et validation Nginx :

```sh
sudo certbot --nginx -d market-ai.bouchard-mehdi.fr
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Remplacer le domaine si nécessaire, utiliser l'email déclaré dans `ACME_EMAIL`
et choisir la redirection HTTP vers HTTPS. Vérifier que le renouvellement
automatique de Certbot est actif sur le VPS. Ouvrir ensuite :

```text
https://market-ai.bouchard-mehdi.fr
```

Se connecter avec le compte créé. Ne pas régénérer puis réinstaller le template
HTTP par-dessus le virtual host après le passage de Certbot : conserver ses
directives TLS lors des modifications de ports.

## 6. Brancher l'IA et vérifier

Sur le PC, lancer `Demarrer-IA.bat`, puis consulter **Suivi des collectes** sur le
site : le heartbeat doit devenir récent. Tester ensuite une publication jusqu'à
son analyse et son affichage sourcé. PC éteint : le site et les collectes restent
disponibles, les analyses attendent. Aucun accès PostgreSQL/Redis n'est fourni au PC.

```sh
sh deploy/vps.sh ai-status
sh deploy/vps.sh logs scheduler
```

Les tests locaux ne remplacent pas ce test réel VPS/PC, encore à effectuer sur
votre infrastructure. L'IA ne transmet aucun ordre réel.

## 7. Sauvegardes et mises à jour

Depuis le PC Windows personnel, **`Sauvegardes-VPS.bat`** prépare la clé, active
le service via SSH, télécharge une archive chiffrée et teste sa restauration dans
un PostgreSQL temporaire local. Le mot de passe SSH reste interactif, la clé
privée reste sur le PC. Suivre [le mode d'emploi](docs/VPS_BACKUPS.md).

Pour une activation manuelle :

Avec votre destinataire public age renseigné, activer la sauvegarde :

```sh
sh deploy/vps.sh backup
docker compose --profile backup logs --tail=50 backup
```

Archives chiffrées dans `private-data/backups`, sauvegarde quotidienne et rétention
14 jours par défaut. Conserver la clé privée hors VPS, copier les archives hors
machine et vérifier une restauration dans une nouvelle base dédiée. Voir
[la procédure de sauvegarde/restauration](docs/DEPLOYMENT.md#sauvegardes-postgresql-chiffrées).
En production, utiliser `docker compose --profile backup` pour ces opérations,
sans ajouter le Compose local de cette procédure.

Pour les mises à jour :

```sh
cd /home/projects/IA-Bloomberg
git pull
docker compose up -d --build
docker compose logs --tail=50 backend scheduler frontend
```

Les volumes sont conservés. Pas de `docker compose down` pour une mise à jour
ordinaire et jamais de `down -v` pour conserver les données. Si le code de l'IA
change, reconstruire aussi sa distribution portable et conserver `config` et
`data/models` après arrêt. Un changement de port nécessite d'adapter ce seul
virtual host Nginx, puis `nginx -t` et un rechargement.

L'ancien helper `sh deploy/vps.sh` accepte aussi `private-data/vps.env` pour les
installations existantes. Le chemin recommandé pour les nouvelles installations
est le `.env` de production à la racine. Aucun fichier privé n'est déplacé par le helper.

Références : [sélection du fichier Compose](https://docs.docker.com/compose/how-tos/environment-variables/envvars/),
[proxy Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[Certbot Nginx](https://certbot.eff.org/instructions?ws=nginx&os=pip).

## Vérifications locales reproductibles

`python -m pytest deploy/tests -q` contrôle le rendu Nginx et la sélection réelle
de Compose, avec un override piège dans un dossier de test (aucun service démarré).
`python deploy/tests/smoke_nginx.py` utilise l'image officielle `nginx:1.28-alpine`
dans un conteneur sans réseau ni port publié : syntaxe, routage, préfixe API,
paramètres de requête et remplacement des en-têtes proxy sont vérifiés avec de
faux upstreams. Il ne contacte ni le VPS ni les fournisseurs financiers.
