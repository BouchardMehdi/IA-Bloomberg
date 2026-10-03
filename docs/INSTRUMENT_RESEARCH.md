# Analyses des titres suivis

La page `/analysis` rapproche les titres ajoutés dans `/portfolio` des publications
et des faits déjà conservés en PostgreSQL. Elle ne consomme aucun appel LLM
supplémentaire et ne crée aucun ordre.

L’API `GET /api/v1/market/instruments/{id}/research?limit=20&offset=0` fournit les
fiches, le cours disponible et l’état d’éligibilité WLS. `next_offset` permet de
parcourir les candidats suivants. Une page peut être vide si les candidats sont
sans source datée ou sans mention exploitable.

Trois rapprochements sont distingués : mention explicite du ticker et du marché
du titre ; mention résolue de son émetteur ; document associé au CIK de l’émetteur.
Les candidats ambigus ou non vérifiés ne suffisent pas. Un lien documentaire ne
prouve pas que la société est le sujet d’un fait, et une mention de l’émetteur
ne prouve pas un impact sur toutes ses classes d’actions. Les rôles issus de
l’extraction restent à contrôler dans les preuves et le document complet.

Les publications restent des publications ; seules les fiches de faits enfants
présentent un résumé extrait et sa preuve. Les fiches conservent URL et date de
publication, ainsi que la couverture disponible. Les sources sans date de
publication sont exclues de cette vue. Les événements fusionnés sont exclus.
Les événements macroéconomiques ne sont pas affectés automatiquement à tous les
titres. L’absence de fiche ne prouve pas l’absence de nouvelles.

L’impact et l’horizon restent à déterminer. Les points à examiner sont une grille
de lecture générale, pas des risques avérés ni un score de rentabilité. Aucun
objectif de prix, signal d’achat ou effet causal sur le cours n’est inventé.
Le cours est une clôture brute datée, indépendante de la date du document.
Les nouveaux achats simulés restent bloqués sans appartenance vérifiée à l’export
WLS fourni par l’utilisateur. Le référentiel SEC ne remplace pas cet export.
