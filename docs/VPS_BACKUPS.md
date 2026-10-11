# Sauvegarder le VPS et vérifier une restauration sur le PC

Lancer **`Sauvegardes-VPS.bat` depuis le projet sur le PC personnel**, avec
Docker Desktop démarré. L'assistant effectue les opérations suivantes :

1. Créer une clé age si elle n'existe pas, sinon conserver la clé existante.
2. Se connecter en SSH et renseigner uniquement `BACKUP_RECIPIENT` dans le
   `.env` du VPS. Une clé publique différente déjà configurée bloque l'opération
   pour éviter de perdre l'accès aux anciennes archives.
3. Vérifier la configuration de production, créer une archive chiffrée, puis
   activer le service quotidien sans arrêter le site.
4. Télécharger cette archive et son checksum sur le PC, vérifier leur intégrité.
5. Déchiffrer et restaurer dans un PostgreSQL temporaire sur le PC, sans port
   publié, puis supprimer ce conteneur et son volume de test.

La clé privée reste sur le PC. Le VPS reçoit uniquement sa clé publique. Le test
ne contacte pas la base du VPS et ne restaure jamais par-dessus l'application.
Docker est nécessaire sur le PC personnel pour ce contrôle, **pas sur les PC
qui utilisent seulement l'IA portable**. Aucun appel LLM ou fournisseur financier.

## Première utilisation

Mettre d'abord cette version du projet sur le VPS avec votre procédure habituelle
de commit/push, puis, sur le VPS :

```sh
cd /home/projects/IA-Bloomberg
git pull
```

Le script construit seulement le service de sauvegarde. Il ne redéploie pas le
frontend, le backend ou Nginx.

Si la connexion SSH n'a jamais été établie depuis ce PC, ouvrir un terminal,
se connecter avec la commande habituelle et vérifier l'identité du serveur avant
d'accepter sa clé. L'assistant refuse les clés SSH inconnues ou modifiées ; il ne
les accepte pas automatiquement.

Lancer ensuite `Sauvegardes-VPS.bat`. Le mot de passe SSH est demandé dans le
terminal pour l'activation puis pour les deux transferts. Il n'est ni enregistré
par le script ni passé dans une commande. Les coordonnées de connexion, sans mot
de passe, sont conservées dans `private-data/vps-backup/connection.json`.
Le premier lancement demande l'adresse du serveur si ce fichier est absent.

Pour définir ou changer explicitement les coordonnées :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File deploy/Manage-VpsBackups.ps1 -Action Setup -Server ADRESSE_DU_VPS -Username root -Port 22 -ProjectPath /home/projects/IA-Bloomberg
```

L'assistant utilise le `.env` de production à la racine et le projet Compose
`market-ai-vps`. Une ancienne installation avec `private-data/vps.env` doit suivre
[la procédure manuelle](../deploy.md#7-sauvegardes-et-mises-à-jour).
Le `.env` du PC reste inchangé ; sur le VPS seule la ligne `BACKUP_RECIPIENT`
est ajoutée ou remplacée lorsqu'elle est vide ou identique.

## Où sont les fichiers ?

| Emplacement | Contenu |
| --- | --- |
| PC : `private-data/vps-backup/backup-identity.key` | **Clé privée**, indispensable pour déchiffrer |
| PC : `private-data/vps-backup/vps-backup.env` | Clé publique, seule valeur à transmettre au VPS |
| PC : `private-data/vps-backup/archives/` | Archives chiffrées téléchargées et checksums |
| PC : `private-data/vps-backup/last-verification.json` | Date UTC, archive, empreinte et réussite du dernier contrôle |
| VPS : `private-data/backups/` | Archives chiffrées générées automatiquement |

Conserver une copie de la **clé privée** dans un stockage personnel sécurisé
distinct du projet, ainsi qu'une copie des archives hors VPS. Ne pas partager
cette clé, la committer ou l'ajouter à la distribution USB de l'IA.
Elle est distincte des clés d'une éventuelle ancienne installation locale.
Sans la clé privée correspondante, une archive n'est pas restaurable.

Le rapport n'est écrit qu'après une restauration réussie ; contrôler sa date et
le nom de l'archive, car un échec ultérieur conserve le dernier rapport réussi.
La vérification affiche la version Alembic et les nombres d'articles,
portefeuilles et comptes restaurés. Elle confirme une restauration technique,
sans remplacer une validation fonctionnelle complète après une reprise réelle.

## Fréquence et contrôles

Par défaut, le VPS crée une archive immédiatement au démarrage du service, puis
toutes les 24 heures, avec une rétention de 14 jours après sauvegarde réussie.
Les variables `BACKUP_INTERVAL_SECONDS` et `BACKUP_RETENTION_DAYS` du `.env`
permettent d'adapter ces valeurs. Le service redémarre avec Docker après un arrêt
du serveur. Un échec conserve les anciennes archives.

Sur le VPS :

```sh
cd /home/projects/IA-Bloomberg
docker compose --profile backup ps backup
docker compose --profile backup logs --tail=50 backup
```

La **copie vers le PC et le test ne sont pas planifiés** : relancer régulièrement
`Sauvegardes-VPS.bat` pour créer et récupérer une archive récente, puis la tester.
Le PC conserve ses copies sans suppression automatique. Une archive laissée
uniquement sur le VPS ne protège pas d'une perte du serveur.

Pour revérifier la dernière copie locale sans connexion SSH :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File deploy/Manage-VpsBackups.ps1 -Action Verify
```

Pour choisir une copie précise, ajouter `-Archive` suivi du chemin de l'archive
`.dump.age`, avec son fichier `.sha256` à côté. Mauvaise clé, checksum invalide ou
base cible existante : le contrôle échoue sans modifier la base de production.
Le dump en clair reste dans un tmpfs de 1 Go pendant sauvegarde et restauration ;
une base dépassant cette capacité exige d'adapter les limites avant de réessayer.

## Périmètre

Le dump contient les données PostgreSQL : comptes, droits, documents, événements,
portefeuilles et historiques persistants. Il ne sauvegarde pas le `.env`, les
clés, les fichiers d'import originaux, la configuration Nginx ou les modèles IA.
Conserver séparément les fichiers privés utiles dans un stockage sécurisé.
Redis n'est pas la mémoire principale. Une reprise réelle sur un nouveau VPS
reste une opération d'administration explicite ; cet assistant ne la déclenche pas.

## Vérifications reproductibles

```powershell
python -m pytest deploy/tests -q
python deploy/tests/smoke_backups.py
```

Le second contrôle nécessite Docker et les images `market-ai-backend` et
`pgvector/pgvector:pg16`. Il applique les migrations réelles à une base neuve,
vérifie une sauvegarde concurrente et la conservation d'un compte et de son rôle,
puis les refus de clé incorrecte, archive altérée et cible existante. Sous Windows,
il teste aussi l'assistant PowerShell dans un dossier distinct.
Ses clés, archives et rapports sont des **fixtures de test**, conservées dans
`private-data/backup-tests/`, sans accès au VPS ou aux clés utilisateur.
