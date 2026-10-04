# Fiches d’opportunité

Dans `/analysis`, chaque titre suivi dispose d’une fiche préparée à la demande
depuis PostgreSQL, sans collecte réseau, appel LLM, nouvel ordre ou nouveau score.
Le classement existant conserve sa seule fonction de priorité de recherche.

`GET /api/v1/market/instruments/{id}/opportunity` rassemble quatre rubriques :

- **Éléments favorables à examiner** : observations de résultat net positif SEC.
- **Risques documentés** : observations de perte nette SEC. Les autres faits
  extraits sont accompagnés de questions et preuves dans « points et risques à
  vérifier », sans sentiment ni direction financière déduits de leur type.
- **Prochains événements** : dates prévisionnelles de résultats dans les 180
  prochains jours, avec source, date de publication lorsqu’elle existe et
  consultation séparée. Elles ne sont jamais annoncées comme confirmées.
- **Données manquantes et travail restant** : couverture financière/documentaire,
  calendrier, cours, conversion USD, WLS et analyses nécessaires avant décision.

Les arguments comptables conservent la fin de période la plus récente du résultat
net dans les observations examinées, et tous les débuts de période, unités et
dépôts correspondants. Un cumul n’est jamais transformé en trimestre. Les valeurs
republiées et contradictoires restent distinctes. Les périodes terminées depuis
plus de 180 jours sont signalées. Ni un bénéfice, ni une perte ne prouvent un
rendement futur, une croissance ou une valorisation. Les BPA et définitions du
chiffre d’affaires ne servent pas de raccourci pour un signal favorable.

Le calendrier retient la dernière consultation par fournisseur, type d’observation
et fin de période **avant** de filtrer les dates futures : déplacer une date dans
le passé ne réactive pas son ancienne prévision. Les dates contradictoires entre
fournisseurs ou observations simultanées sont visibles. Une observation de résultat
publié retire les prévisions de sa période ; sans résultat conservé, une date
passée ne prouve pas que la publication a eu lieu. La fiche ne déduit aucune date
de résultats depuis les dates de dépôt SEC ou les périodes XBRL.

Une date et une estimation du même fournisseur pour le même événement, même source
et date de publication sont affichées une seule fois ; leurs observations restent
conservées séparément dans le calendrier.

Les mentions ambiguës/non vérifiées ne permettent pas de créer des arguments.
Un document seul reste accessible dans les fiches documentaires, sans devenir un
fait favorable ou un risque avéré. Les faits enfants doivent avoir une preuve,
une mention exploitable et une source datée non future ; leurs rôles et la
couverture du texte restent affichés pour contrôle.

La fiche examine au maximum 100 candidats documentaires, 100 observations
financières et 1 000 observations de calendrier. Elle signale explicitement toute
borne atteinte et n’est jamais présentée comme exhaustive. Les historiques
complets restent consultables dans les rubriques spécialisées. Une rubrique vide
ne signifie ni absence de nouvelles, ni absence de risque, ni montant nul.

« Actualiser la fiche » relit les données conservées ; les collectes utilisent
leurs boutons et quotas propres. Les contraintes WLS et du portefeuille restent
inchangées. Aucun avis d’achat, objectif de cours, rendement ou score d’opportunité
n’est calculé. La fiche n’est pas un instantané historique ni un backtest.

Vérifications : `tests/test_opportunity.py` et `tests/smoke_opportunity.py`.
Le test PostgreSQL/API annule toutes ses écritures et ne consulte aucun fournisseur.

```powershell
docker compose run --rm --no-deps backend python -m tests.smoke_opportunity
```
