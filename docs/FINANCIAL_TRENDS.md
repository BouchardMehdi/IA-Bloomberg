# Comparaison des résultats dans le temps

Dans `/analysis`, la rubrique « Évolution du chiffre d’affaires et des bénéfices »
compare les observations SEC US-GAAP de l’émetteur, sans appel IA ni collecte
supplémentaire. Elle ne modifie ni le classement de recherche, ni le portefeuille.

`GET /api/v1/market/instruments/{id}/financial-trends` lit les seules mesures
`revenue` et `net_income` du CIK vérifié. Les autres sociétés, devises, définitions,
BPA et taxonomies ne sont jamais utilisés comme substituts.

## Conditions de calcul

Pour chaque concept et unité, la fin de période conservée la plus récente est
retenue. Les débuts de période distincts restent séparés : trimestre et cumul
ne sont jamais fusionnés. La date de dépôt la plus récente pour ce contexte est
retenue, avec ses sources et valeurs. Les valeurs contradictoires à cette date
bloquent le calcul, sans choisir un identifiant arbitraire.

La période de comparaison doit être présente dans **chaque même dépôt** retenu,
avec même concept, taxonomie, unité et date de dépôt. Cette règle utilise la
présentation comparative de ce dépôt plutôt qu’une valeur historique d’une
autre version. Il n’est pas tenté de revenir à un ancien dépôt quand le nouveau
ne contient pas de période comparable.

Les dates de début et fin doivent toutes deux être décalées du même nombre de
jours, entre 350 et 378 jours : fenêtre explicite d’environ un an, avec durée
strictement identique. Les périodes ne doivent pas se chevaucher. Une durée
différente, une année bissextile changeant la durée ou une année de 53 semaines
peut donc bloquer la comparaison. Aucun trimestre n’est déduit par soustraction
de cumuls, ni à partir de `fy/fp`. Plusieurs périodes ou valeurs précédentes
possibles bloquent le calcul. Les dates futures sont exclues.

## Présentation

Les deux montants, unités, dates exactes et preuves SEC sont affichés. La
variation est `actuel - précédent`, en décimal exact. Le pourcentage est
`variation / précédent × 100`, arrondi à deux décimales, **seulement si la base
est positive**. Pour une base nulle ou négative, seul l’écart en montant reste
disponible ; le passage de perte à bénéfice ou l’inverse est explicité.

Une variation publiée n’est pas une croissance organique : changements de
périmètre, conventions comptables, activités cédées et autres ruptures restent
à examiner dans le document. La correspondance structurelle vérifiée n’établit
ni valorisation attractive, ni rendement, ni recommandation d’achat. Les durées
et motifs de blocage sont visibles et l’absence de comparaison n’est pas un zéro.

La lecture est bornée à 2 000 observations. Si cette borne est dépassée, tous les
calculs sont bloqués : la fiche signale sa couverture incomplète pour éviter
qu’une valeur contradictoire ou comparative soit omise. Aucun instantané
historique ou backtest n’est prétendu. L’historique reste intact.

Tests : `tests/test_financial_trends.py`, et vérification SQL/API sans réseau,
avec toutes les écritures annulées :

```powershell
docker compose run --rm --no-deps backend python -m tests.smoke_financial_trends
```
