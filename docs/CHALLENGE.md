# Règles du challenge communiquées par l'utilisateur

Informations reçues depuis le 3 octobre 2026 ; le règlement reste à fournir.
Une liste WLS partielle a été transmise le 10 octobre 2026 (voir ci-dessous).

- Capital initial : 1 000 000 USD.
- Actions uniquement, positions longues ; pas de levier, de vente à découvert,
  de trading de devises ou de matières premières.
- Univers : WLS, non public, annoncé comme 10 426 **titres**, couvrant l'essentiel
  des grandes capitalisations. Ce nombre vient de l'utilisateur et n'est pas une
  composition récupérée ou vérifiée par Market AI.
- Une société peut avoir plusieurs titres : une identité d'émetteur ne suffit pas
  à identifier un instrument achetable.
- Précision transmise par l'utilisateur d'après son collègue : les actions hors
  États-Unis sont autorisées et les titres ne sont pas nécessairement cotés en USD.
  L'interdiction concerne le trading Forex ; elle n'interdit pas l'achat d'actions
  cotées dans une autre devise. Bloomberg effectue la conversion pour le challenge.
  Les exemples cités (`2600hk`, Sega, Total, Airbus) ne sont pas des identifiants
  validés dans Market AI et ne remplacent pas l'export WLS.

Les frais, dates, plafonds par position, traitement des dividendes/splits et marchés
précis restent à confirmer. Les taux, horaires et conventions de conversion utilisés
par Bloomberg ne sont pas encore connus. La liste complète et les dates de
composition des exports restent à fournir.

## Liens publics de l'indice

Liens transmis le 4 octobre 2026 :
[Bloomberg WORLD](https://www.bloomberg.com/professional/products/indices/quote/WORLD:IND)
et [TradingView BBG:WLS](https://fr.tradingview.com/chart/?symbol=BBG%3AWLS).
WORLD et WLS ne désignent pas le même périmètre : WLS inclut les petites
capitalisations, contrairement à WORLD. Voir la
[méthodologie Bloomberg](https://data.bloomberglp.com/professional/sites/10/Bloomberg-Global-Equity-Indices-Methodology.pdf).
Le caractère public de ces pages ne fournit pas un export autorisé et daté des
titres éligibles. L'univers du challenge reste à importer depuis la liste fournie
par l'utilisateur. La variante exacte de benchmark (prix, rendement net ou total)
et les règles de comparaison de performance restent à confirmer.

## Préparer les titres internationaux

La prise en charge internationale devra conserver, pour chaque titre, son
identifiant, sa classe d'action, sa cotation, sa devise et l'unité du cours. Les
symboles Bloomberg devront être rapprochés explicitement des identifiants du
fournisseur de données, sans supposer qu'un nom de société identifie une action.

Le portefeuille reste valorisé en USD. Notre simulation ne bénéficie pas de la
conversion automatique de Bloomberg : elle devra conserver le cours local et un
taux de conversion vers USD, chacun avec date et source, et refuser une opération
si les données nécessaires sont absentes ou trop anciennes. Cette conversion de
valorisation ne constitue pas une position Forex. Tant que ces données et les
conventions ne sont pas disponibles, ne pas présenter une performance simulée
comme identique à celle du challenge.

L'application collecte automatiquement les titres NYSE/Nasdaq suivis en USD.
Les [cotations internationales et taux sourcés](INTERNATIONAL_MARKET.md) peuvent
désormais être fournis explicitement pour valoriser et simuler en USD. Leur
collecte automatique reste à connecter ; aucun titre ni taux fictif n'est ajouté.

## Importer l'univers

### Liste partielle reçue le 10 octobre 2026

L'utilisateur confirme que le classeur transmis par son collègue est sa liste
WLS disponible. Il contient 3 000 identifiants Bloomberg distincts dans
`Feuil1!A1:A3000`, sans en-tête ni doublon. Cette origine est déclarée par
l'utilisateur, sans authentification automatique du fichier. La date de
composition et l'URL de l'export ne sont pas fournies. Les dates techniques du
classeur ne sont pas utilisées comme dates de composition de l'indice.

La préparation locale est conservée dans
`private-data/wls/wls-partial-2026-10-10.json`, hors Git. Elle garde chaque
identifiant original, sa cellule source, les zéros initiaux, le hash SHA-256 du
classeur et la date de lecture. Elle indique explicitement sa couverture
partielle et laisse les correspondances de cotation absentes.

Ce fichier de préparation n'est pas encore un import d'éligibilité dans
`wls_universe`. Un code Bloomberg comme `US` ne désigne pas automatiquement
NYSE ou Nasdaq. Le champ Bloomberg `Equity` est conservé comme secteur Bloomberg,
sans remplacer la validation du type d'instrument exigée par l'import.
Le rapprochement doit conserver le titre et sa cotation exacts ; aucun CIK,
marché, devise ou symbole fournisseur n'est deviné. L'absence d'un titre dans
cette liste partielle ne prouve pas son exclusion du WLS.

L'effectif d'environ 10 400 titres et la couverture de 99 % de la capitalisation
mondiale restent des indications transmises par l'utilisateur sur l'univers
complet, sans mesure déduite de ces 3 000 lignes. Les prochains exports devront
garder leur propre date de composition et leur provenance.

### Import de cotations rapprochées

La préparation est désormais consultable dans `/portfolio`, avec recherche,
pagination et compteur de correspondances. Elle utilise un registre distinct
`wls_candidates` en PostgreSQL et ne remplace jamais `wls_universe`.

```powershell
docker compose cp ./private-data/wls/wls-partial-2026-10-10.json backend:/tmp/wls-partial.json
docker compose exec backend python -m app.cli.import_wls_candidates --file /tmp/wls-partial.json
```

L'import valide le manifeste et conserve le hash, la provenance déclarée et les
cellules sources. Une reprise du même fichier conserve les correspondances déjà
saisies. Un autre hash est refusé pour préserver cet instantané ; le remplacement
par une nouvelle composition et son historique restent à implémenter. L'URN
SHA-256 interne identifie le fichier local, sans prétendre être une URL officielle.

`GET /api/v1/market/wls-candidates` accepte `search`, `offset` et `limit` (maximum
100). `POST /api/v1/market/wls-candidates/mappings` déclare une correspondance avec
un titre suivi : identifiant Bloomberg exact, identifiant du titre, URL sans
paramètres secrets, date de la source, justification et confirmation explicite.
Une suggestion vient uniquement d'un identifiant Bloomberg déjà saisi sur le
titre ; aucun rapprochement par ticker seul ou émetteur n'est effectué. Les
déclarations conservent l'identité exacte du titre et leur date de saisie. Une
déclaration contradictoire ou un remplacement est refusé ; une identité modifiée
est signalée en conflit. La saisie ne certifie pas le contenu des preuves.

Ces correspondances préparent la normalisation. Elles ne modifient ni les
identités suivies, ni les collecteurs, ni l'éligibilité des achats simulés. La date
de la preuve de correspondance ne devient jamais la date de composition WLS.
L'import d'éligibilité ci-dessous exige encore une composition datée et sa source.

Ne pas reconstruire WLS depuis la SEC ni depuis une liste publique approximative.
L'import utilise un export que l'utilisateur est autorisé à exploiter, normalisé
en CSV UTF-8 avec les colonnes suivantes :

```csv
security_id,symbol,exchange,asset_class
```

`security_id` est un identifiant unique de chaque titre/cotation dans cet export,
pas un identifiant d'entreprise. `asset_class=equity` signifie ici une action ;
les ETF, fonds, dérivés et autres instruments doivent être exclus à la normalisation.
Le ticker et le marché doivent correspondre exactement au titre suivi (`NYSE`,
`Nasdaq` ou le MIC fourni pour une cotation internationale). Les tickers numériques
sont acceptés et leurs zéros initiaux conservés. Ne pas inventer de conversion
de symboles Bloomberg vers ceux du fournisseur. La collecte automatique de cours
hors du périmètre américain n'est pas encore prise en charge.

Copier le CSV autorisé dans le conteneur puis importer avec sa date et l'URL de sa
source officielle, qui peut nécessiter un accès privé :

```powershell
docker compose cp ./wls.csv backend:/tmp/wls.csv
docker compose exec backend python -m app.cli.import_wls --file /tmp/wls.csv --as-of AAAA-MM-JJ --source-url URL_OFFICIELLE
```

L'import atomique conserve les lignes, le hash, la source et la date de consultation
dans `entity_registries` sous `wls_universe`. Une liste partielle reste partielle :
le compteur affiche réellement les lignes importées, sans prétendre atteindre
10 426. L'application ne peut pas authentifier automatiquement l'origine du fichier.

Un achat simulé exige une ligne correspondante par **ticker et marché** avec une
classification d'action. Un CIK partagé ne transfère jamais l'éligibilité d'un titre
à un autre. Sans export, les nouveaux achats sont bloqués. Les ventes de titres
déjà détenus restent possibles pour réduire une ancienne position ; elles ne
peuvent créer de position courte. Les reprises d'ordres déjà enregistrés ne créent
pas de nouvelle opération.

Le capital proposé par défaut devient 1 000 000 USD ; les simulations existantes
gardent leur capital et leur historique. Les frais et limites restent configurables
et provisoires. La collecte NYSE/Nasdaq en USD et son budget actuel de 20 requêtes
par jour couvrent une sélection de suivi, pas l'ensemble des 10 426 titres WLS.
