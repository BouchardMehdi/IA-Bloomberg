# IA Windows transportable sur clé USB, sans Docker

Le dossier préparé embarque Ollama, le worker, Python et ses dépendances. Le PC
qui l'exécute n'a besoin ni de Docker, ni d'un Python installé, ni d'un service
Windows. Le site, les collectes, PostgreSQL et Redis restent sur le VPS.

## Dossier prêt à copier

Depuis le dépôt sur votre **PC personnel Windows x64**, lancer
`Preparer-Cle-USB.bat`. Python 3.12+ x64 et Internet sont nécessaires uniquement
à cette préparation. Le script utilise un environnement isolé dans
`private-data/portable-build` et ne modifie ni `.env` ni les services Docker.

Il télécharge la version épinglée d'Ollama depuis son dépôt officiel, vérifie son
SHA-256, construit un exécutable du worker, puis télécharge le modèle dans le
dossier de sortie. Les téléchargements représentent plusieurs Go. Une préparation
interrompue conserve le cache ; un dossier de sortie existant n'est jamais écrasé.

La sortie est **`out/Market-AI-Portable`** :

```text
Market-AI-Portable/
  Configurer-IA.bat
  Demarrer-IA.bat
  Arreter-IA.bat
  Etat-IA.bat
  Preparer-Modele.bat
  LIRE-MOI.txt
  versions.json
  runtime/
    worker/       # exécutable + Python et bibliothèques intégrés
    ollama/       # archive officielle extraite, bibliothèques incluses
  config/
    worker.json   # créé lors de la configuration, jeton privé
    vps-worker.txt # empreinte à reporter sur le VPS
  data/
    models/       # modèle téléchargé une seule fois, conservé après arrêt
    logs/
    state.json    # état technique, jamais une preuve de connexion au VPS
```

Copier **uniquement ce dossier entier** sur la clé USB, puis de préférence sur
le disque du PC de destination. Ne pas copier tout le dépôt avec ses sauvegardes,
ses exports WLS, son `.env` ou `private-data`. La préparation suit une liste
explicite de fichiers autorisés et n'inclut aucun de ces secrets/données serveur.
Le dossier produit est ignoré par Git ; il faut conserver la distribution ou la
reconstruire après un nouveau clone du dépôt.

Pour préparer les exécutables sans télécharger immédiatement le modèle :

```powershell
python deploy/portable/build.py --skip-model
```

Puis lancer `Preparer-Modele.bat` avant le transfert. Sans cela, le premier
`Demarrer-IA.bat` téléchargera le modèle sur le PC de destination.

## Configurer une seule fois

1. Lancer `Configurer-IA.bat` dans le dossier portable et saisir l'origine HTTPS
   du site, sans chemin (par exemple `https://market.votre-domaine.fr`).
2. Reporter `AI_WORKER_TOKEN_SHA256` et `OLLAMA_MODEL` de `config/vps-worker.txt`
   dans `private-data/vps.env` **sur le VPS**, puis recréer ses services avec
   `sh deploy/vps.sh up`. Voir [installation VPS](HYBRID_DEPLOYMENT.md).
3. Conserver le jeton brut de `config/worker.json` uniquement avec le dossier
   portable. Il ne doit pas être transmis au VPS ni affiché dans les logs.

`Configurer-IA.bat` conserve une configuration existante. Un nouveau PC n'impose
pas de nouveau jeton : copier aussi `config` et `data/models`, puis démarrer.
Un nouveau dossier configuré séparément génère un nouveau jeton et impose donc
de mettre à jour son empreinte sur le VPS. Protéger la clé USB et ne pas partager
le dossier configuré ; le jeton autorise les tâches d'analyse, pas l'accès aux
comptes web, aux opérations du portefeuille ou aux bases de données.

Si vous avez déjà `private-data/worker.env` de l'ancienne préparation Docker,
il n'est pas importé automatiquement. Conserver l'ancien jeton en renseignant
manuellement les trois champs `site_url`, `token`, `model` dans le fichier JSON
portable, ou utiliser une nouvelle configuration et mettre à jour le VPS.
Ne pas faire fonctionner volontairement les deux anciens/nouveaux workers ensemble.

## Utilisation sur l'autre PC

- `Demarrer-IA.bat` démarre Ollama et le worker en arrière-plan. Si le modèle
  manque, il est téléchargé avant que le worker commence à prendre des tâches.
  Fermer cette fenêtre laisse l'IA en marche.
- `Etat-IA.bat` affiche si le processus est actif, la phase du lancement et les
  derniers messages. « Actif » indique un processus local ; la connexion au VPS
  se contrôle dans **Suivi des collectes** sur le site.
- `Arreter-IA.bat` demande l'arrêt du worker puis ferme son groupe de processus
  Ollama, y compris les sous-processus du modèle. Il préserve les poids du modèle.

Toujours arrêter l'IA **avant** de déplacer, copier ou débrancher le dossier.
Un état copié d'un autre PC ou un PID réutilisé ne permet pas d'arrêter un
processus inconnu : identité de l'exécutable, date de création, lancement et
démarrage du système sont contrôlés. Un verrou système refuse deux lancements
simultanés dans le même dossier. Le port **127.0.0.1:11435** est réservé à cette
instance ; s'il est pris, le lancement refuse de rejoindre ou d'arrêter l'autre
application. Les autres services Ollama/Docker restent indépendants.

Le worker contacte uniquement le VPS en HTTPS, avec la vérification TLS active.
L'API locale d'Ollama n'est pas exposée au réseau. Ses fonctions cloud sont
désactivées. Le téléchargement des poids nécessite un accès Internet au registre
Ollama. Il n'existe aucun LLM de secours sur le VPS.

## Compatibilité et limites pratiques

Cette distribution cible **Windows x64, Windows 10 22H2+ ou Windows 11**. Elle ne
vise pas Windows ARM natif, macOS ou Linux. Prévoir plusieurs Go de stockage et
assez de RAM pour le modèle 4B et Windows (16 Go préférables ; un PC avec 8 Go
peut être limité selon les autres programmes). Une clé 16 Go ou plus et un
format exFAT/NTFS sont conseillés. L'exécution depuis le disque local sera
généralement plus confortable que depuis une clé lente.

Aucun administrateur, registre, PATH ou service n'est configuré par les lanceurs.
Ils ne nécessitent pas PowerShell sur le PC de destination. Le Python de
préparation est intégré à l'exécutable produit. Ollama peut créer ses propres
fichiers techniques dans le profil Windows (`.ollama`, clés locales notamment) ;
les modèles, journaux Market AI et jeton du worker restent dans le dossier.
Les paramètres de la session Windows ne sont pas réécrits.

L'établissement doit autoriser l'exécution des programmes. AppLocker, antivirus,
réseau ou manque de mémoire peuvent empêcher leur fonctionnement : ce dossier
ne contourne pas ces restrictions. Un pilote GPU adapté est nécessaire pour
l'accélération matérielle ; la configuration ne l'installe pas. Le PC doit rester
éveillé ; hors ligne, la file persistante du VPS attend son retour.

## Mise à jour et vérification

Reconstruire dans un **nouveau dossier** avec `--output out/Market-AI-Portable-v2`,
ou conserver l'ancienne sortie hors du chemin par défaut avant de reconstruire.
Après arrêt, transférer `config` et `data/models` dans la nouvelle distribution.
Mettre à jour le serveur et le worker ensemble pour garder la même version de
prompt. `versions.json` conserve la version Ollama et les empreintes utilisées.

Les tests sous `deploy/portable/tests` vérifient les secrets, la copie vers un
chemin différent, les collisions de port, les PID périmés et le groupe de processus
Windows. La construction appelle `self-test` sur l'exécutable réel. Un test de
lancement/arrêt complète ces vérifications avec Ollama autonome :
`private-data/portable-build/venv/Scripts/python.exe deploy/portable/smoke.py`.
Ce test exige le dossier de sortie non configuré et le modèle déjà téléchargé.
Il déplace temporairement la distribution vers un chemin avec espaces, retire
Python et Docker du PATH de ses sous-processus, teste un vrai lanceur `.bat`,
puis vérifie l'arrêt ciblé et restaure le dossier sans ses identifiants de test.
Son faux VPS est l'adresse locale HTTPS `127.0.0.1:9` ; aucune analyse ou connexion
à un serveur externe n'est effectuée. Aucun ordre réel n'est transmis.

Sources techniques : [Ollama Windows autonome](https://docs.ollama.com/windows#standalone-cli),
[distribution PyInstaller en dossier](https://pyinstaller.org/en/stable/operating-mode.html#bundling-to-one-folder).
