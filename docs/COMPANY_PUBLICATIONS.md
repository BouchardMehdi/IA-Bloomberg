# Publications ciblées des émetteurs suivis

Le flux SEC 8-K général ne couvre que ses dernières entrées. Le collecteur ciblé
consulte aussi l'[API officielle des submissions SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
pour chaque CIK vérifié des titres suivis. Plusieurs cotations du même émetteur
partagent une consultation, sans devenir un seul titre ni une preuve WLS.

## Couverture et provenance

`https://data.sec.gov/submissions/CIK##########.json`, sans clé. Seule la liste
`filings.recent` est utilisée ; les fichiers d'archives supplémentaires ne sont
pas téléchargés. Formulaires : 8-K, 10-Q, 10-K, 6-K, 20-F, 40-F et amendements.
La fenêtre couvre 365 jours ; au plus 50 documents HTML récents sont retenus par
émetteur. Ce n'est pas une couverture exhaustive de ses nouvelles.

La date d'acceptation SEC, avec fuseau explicite, date la publication du dépôt.
Elle n'est ni la date du fait économique ni la date de l'annonce originale.
Les dépôts futurs sont exclus. La réponse, les listes alignées, le CIK, les
accessions et les noms de fichiers sont validés avant toute insertion d'article.
Le téléchargement est borné à 4 Mo et 45 secondes, sans suivre de redirection.
Les URL sont construites uniquement avec des identifiants validés vers les
archives officielles, jamais depuis une URL fournie par le document.

La récupération du texte utilise ensuite le pipeline HTML existant, avec ses
bornes et reprises. Les métadonnées du catalogue ne sont pas le texte intégral.
Le worker de texte réserve jusqu'à deux places par lot aux publications ciblées,
puis utilise les places restantes pour le flux général. Le plafond total du lot
reste inchangé ; un défaut d'accès ne bloque pas la création de la fiche.
Les articles et publications sont reliés au CIK en contexte `source_subject`,
sans prouver un rôle dans chaque fait ou un effet sur chaque classe d'action.
L'extraction sémantique éventuelle conserve ses budgets et ses preuves habituels.
Le regroupement exact par accession conserve les sources du flux général et de
la collecte ciblée. Les faits enfants restent séparés.

## Exécution et reprise

`COMPANY_PUBLICATIONS_ENABLED=true` active un passage toutes les quinze minutes,
au plus cinq émetteurs, en priorité les moins récemment consultés. Aucun appel
Alpha Vantage et aucun appel LLM pour cette collecte. `SEC_USER_AGENT` doit
identifier l'application avec une adresse de contact valide.

Une réussite reste en cache une heure ; un échec attend cinq minutes. La
réservation est enregistrée dans `collection_runs` avant l'appel. Un verrou et
une vérification de la réservation empêchent des collectes ciblées simultanées.
Une réservation interrompue bloque les autres émetteurs au plus deux minutes et
le même émetteur cinq minutes. Les requêtes sont espacées d'au moins 250 ms.
Une erreur conserve l'historique et un code borné, sans corps fournisseur.

Dans `/analysis`, le panneau de collecte affiche l'état, les bornes et permet une
consultation manuelle. Le pipeline d'extraction rapproche les nouveaux documents
lors du prochain cycle, normalement une minute. Recharger la fiche pour les voir.
Un score de recherche peut rester nul même avec des publications : le score
demande des faits exploitables sourcés sur 30 jours, pas simplement des documents.

- `GET /api/v1/market/instruments/{id}/publications/collection`
- `POST /api/v1/market/instruments/{id}/publications/collect`

Les sociétés sans CIK restent hors couverture automatique. Il faudra une source
autorisée et des identités exactes pour les annonces hors SEC ; aucun site de
relations investisseurs, ISIN ou mapping Bloomberg n'est deviné.
