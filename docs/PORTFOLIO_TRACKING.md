# Historique, opérations sur titres et couverture

## Historique observé

`/portfolio` affiche la performance par rapport au capital initial et les preuves
de chaque journée observée. Le scheduler enregistre un instantané toutes les
heures ; la création, un ordre ou une opération sur titres enregistrent également
leur état dans la même transaction. Le bouton permet une observation immédiate.
Aucun appel LLM ou fournisseur supplémentaire n'est nécessaire.

`portfolio_observations` conserve les révisions sans écrasement. Deux captures
consécutives identiques le même jour sont idempotentes ; un retour à un état
précédent produit une nouvelle révision. La vue quotidienne sélectionne la dernière
observation réelle du jour UTC (365 jours par défaut, maximum 1 000). Elle conserve
capital, liquidités, coût des positions, prix et conversions, dates/sources de
cours et taux, gains/pertes, dividendes et identifiants des écritures concernées.
Les corrections futures de cours ou taux ne changent pas les observations passées.

Il s'agit d'une série d'observations, **pas de clôtures synchronisées ni d'un
backtest**. Les jours avant l'activation ou pendant un arrêt ne sont pas inventés.
Les données manquantes rendent la valeur totale indisponible ; les données
anciennes restent identifiées et sont exclues de la courbe. Une interruption
de données coupe la courbe. Un portefeuille vide reste composé de liquidités.
La simulation ne reçoit aucun apport/retrait après création ; la performance est
`(valeur totale / capital initial - 1) × 100`, frais simulés compris. Aucun
benchmark WLS, rendement annualisé ou rendement total certifié n'est reconstruit.

## Dividendes et splits déclarés

Le formulaire `/portfolio` applique exclusivement une opération sourcée à une
simulation choisie. URL documentaire sans secret, date de publication avec fuseau,
note sur le titre et confirmation sont obligatoires. Les preuves sont déclarées,
pas certifiées par la saisie. Il n'y a pas de collecte automatique de ces événements.

- Dividende : date de détachement, date de paiement déjà passée, montant **net**
  par titre en devise principale de la cotation. La quantité provient des achats
  et ventes exécutés **avant le jour UTC du détachement**, avec les splits
  antérieurs enregistrés. Le prix historique de l'ordre n'est pas la date de
  détention. Le cash est crédité sans réinvestissement. Aucun impôt, montant brut
  ou convention Bloomberg n'est déduit. Hors USD, dernier taux au plus tard au
  paiement, dans la limite d'âge FX configurée à cette date ; preuve figée.
- Split : ratio nouveaux/anciens, date effective passée et clôture brute au moins
  à cette date. Le nombre de titres change ; le coût total reste identique.
  Aucun prix historique, ordre ou taux initial n'est réécrit. Une fraction ou une
  quantité hors capacité est refusée, sans compensation fictive. Un split après
  des opérations déjà enregistrées à partir de sa date effective est refusé :
  les rejouer changerait les quantités, frais et règles de simulation. Enregistrer
  le split avant de simuler les opérations suivantes.

Un même portefeuille/titre/type/date effective ne peut recevoir qu'une opération.
Une reprise identique ne crédite rien deux fois ; une contradiction est refusée.
Deux distributions distinctes le même jour nécessitent une convention documentée
regroupant leur montant net avant saisie. Split et détachement le même jour sont
refusés faute de convention d'ordre fiable. Toutes les écritures et la capture
du portefeuille sont atomiques et utilisent le verrou du portefeuille.

Les dividendes nets enregistrés entrent dans le cash et le gain/perte total.
Le gain réalisé des transactions reste séparé des revenus de dividendes.
Une opération omise ou saisie tardivement peut affecter la performance observée ;
l'application ne présente pas cette série comme équivalente au challenge.

## Vue de couverture et préparation de valorisation

`/coverage` regroupe, pour les seuls titres suivis, cours ou FX manquants/anciens,
correspondances à résoudre, WLS non vérifié, collectes en erreur, valorisations
bloquées et références comparables manquantes. Les compteurs peuvent se recouper.
Les reprises et le quota Alpha Vantage restent visibles, sans contournement.

Le bouton de préparation affiche jusqu'à dix candidats SEC de BPA dilué avec
durée annuelle explicite de 350 à 378 jours, parmi les cent derniers faits de
ce concept consultés. Ce sont des documents de l'émetteur, jamais une attribution
automatique au titre. Ils peuvent inclure plusieurs dépôts/périodes. Aucune preuve
de classe, ADR, split ou séance n'est déduite de cette liste.

L'import JSON facilite la saisie de preuves complètes (100 lignes maximum) :

```json
{"items": [{"instrument_id": "UUID du titre", "observation": {"...": "tous les champs ValuationInput"}}]}
```

Voir les schémas `ValuationBatch` et `ValuationInput` dans `/docs` de l'API et
[les règles de valorisation](VALUATION.md). Le fichier entier doit respecter le
schéma ; chaque ligne valide est ensuite contrôlée contre sa cotation. Les
acceptations sont persistées séparément, les refus métier sont retournés par
ligne. Un doublon exact ne recrée pas l'observation. Cela ne remplace aucune
exigence de preuve et ne remplit pas automatiquement un BPA manquant.

## API et vérifications

Routes préfixées `/api/v1/market` :

| Route | Usage |
| --- | --- |
| GET /coverage | Couverture et blocages des titres suivis |
| GET /instruments/{id}/valuation-preparation | Documents candidats et preuves nécessaires |
| POST /valuations/batch | Import de preuves complètes, résultats par ligne |
| GET /portfolios/{id}/history | Dernière observation de chaque journée UTC |
| POST /portfolios/{id}/history | Capture immédiate, sans reconstruction passée |
| GET /portfolios/{id}/actions | Opérations sur titres, maximum 200 affichées |
| POST /portfolios/{id}/actions/{instrument_id} | Application atomique d'un dividende/split déclaré |

Migration `20261010_0019`. Tests sans réseau, fixtures PostgreSQL annulées :

```powershell
docker compose exec backend python -m tests.smoke_portfolio_tracking
```

Le contrôle couvre doublons/conflits, dividendes EUR avec taux figé, split/coût
de revient, vente après split, preuves historiques conservées après correction,
FX manquant, correspondance internationale et quota existant, import de BPA et
réponses de couverture. Aucun portefeuille de test ni ordre de test n'est conservé.
