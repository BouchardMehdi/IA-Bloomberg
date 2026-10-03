# Règles du challenge communiquées par l'utilisateur

Informations reçues le 3 octobre 2026 ; le règlement et l'export officiel restent
à fournir.

- Capital initial : 1 000 000 USD.
- Actions uniquement, positions longues ; pas de levier, de vente à découvert,
  de trading de devises ou de matières premières.
- Univers : WLS, non public, annoncé comme 10 426 **titres**, couvrant l'essentiel
  des grandes capitalisations. Ce nombre vient de l'utilisateur et n'est pas une
  composition récupérée ou vérifiée par Market AI.
- Une société peut avoir plusieurs titres : une identité d'émetteur ne suffit pas
  à identifier un instrument achetable.

Les frais, dates, plafonds par position, traitement des dividendes/splits et marchés
précis restent à confirmer. La restriction sur les devises ne permet pas de déduire
que toutes les actions autorisées sont cotées en USD.

## Importer l'univers

Ne pas reconstruire WLS depuis la SEC ni depuis une liste publique approximative.
L'import utilise un export que l'utilisateur est autorisé à exploiter, normalisé
en CSV UTF-8 avec les colonnes suivantes :

```csv
security_id,symbol,exchange,asset_class
```

`security_id` est un identifiant unique de chaque titre/cotation dans cet export,
pas un identifiant d'entreprise. `asset_class=equity` signifie ici une action ;
les ETF, fonds, dérivés et autres instruments doivent être exclus à la normalisation.
Le ticker et le marché doivent correspondre exactement au titre suivi (actuellement
`NYSE` ou `Nasdaq`). Ne pas inventer de conversion de symboles Bloomberg vers ceux
du fournisseur. La liste peut contenir d'autres marchés ; leur collecte de cours
n'est pas encore prise en charge.

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
