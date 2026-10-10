# Instructions pour les agents

La valorisation `/analysis` exige un BPA annuel GAAP dilué par titre explicitement
documenté pour la séance, sans attribution automatique d’un BPA SEC d’émetteur.
Les preuves manuelles restent déclarées, pas certifiées par leur saisie. Ne pas
annualiser un trimestre, inventer un ratio d’ADR ou qualifier un prix sans référence
comparable sourcée. Le rendement bénéficiaire n’est pas un rendement futur.
Voir docs/VALUATION.md.

Les comparaisons temporelles SEC exigent même concept, unité, durée exacte et
présentation dans le même dépôt. Ne pas revenir à un ancien dépôt pour contourner
une comparaison manquante ou ambiguë. Base nulle/négative : aucun pourcentage.
Ne pas présenter une variation publiée comme croissance organique ou signal
d'achat. Voir docs/FINANCIAL_TRENDS.md.

Les fiches d’opportunité `/analysis` sont des dossiers de recherche sourcés,
sans score d’achat ou de rendement. Ne pas déduire le sentiment d’un type de fait,
confondre bénéfice comptable et valorisation attractive, ou réactiver une ancienne
date prévisionnelle après son déplacement. Voir docs/OPPORTUNITY_DOSSIERS.md.

Les observations `/analysis` SEC XBRL gardent concepts, unités, début/fin de période
et dépôts distincts. `fy/fp` ne prouvent pas une durée trimestrielle. Ne pas fusionner
les définitions de chiffre d'affaires ni attribuer un BPA d'émetteur à une cotation
sans preuve. Ne pas comparer aux estimations sans conventions et antériorité vérifiées.
Voir docs/FINANCIAL_RESULTS.md.

Les soldes SEC de trésorerie/dette sont instantanés (`start=null`), les flux
exigent un début de période. Ne pas additionner dette courante/non courante,
crédit-bail ou fonds restreints sans correspondances exactes. Aucun total de dette,
ratio ou flux libre n'est calculé par cette couverture. Les flux d'investissement
ou financement négatifs ne prouvent pas une perte.

La collecte SEC ciblée des titres suivis utilise les CIK vérifiés, sans deviner
de cotations ni d'éligibilité WLS. Les dépôts restent des documents, datés par
l'acceptation SEC ; le contexte de l'émetteur ne prouve pas un impact sur le titre.
Voir docs/COMPANY_PUBLICATIONS.md.

Le calendrier `/calendar` conserve les observations sans écraser leur historique.
Les appels Alpha Vantage de calendrier et de cours partagent le quota persistant.
Les dates fournisseur sont prévisionnelles ; une consultation n'est pas une date
de publication. Ne jamais calculer d'écart de BPA avec une période, devise ou
convention inconnue, ni avec une estimation conservée après le résultat.
Voir docs/EARNINGS_CALENDAR.md.

## But du projet

Market AI collecte des informations financières, les normalise puis crée des événements structurés et traçables. La priorité est : pipeline fiable, qualité des sources, puis complexité IA.

## Invariants

- Un `Article` est une source documentaire ; un `Event` est un fait structuré. Plusieurs articles peuvent être liés au même événement.
- PostgreSQL est la mémoire principale. Un LLM ne sert jamais de base de données.
- Toute affirmation présentée à l'utilisateur doit pouvoir être reliée à une URL et à une date de publication.
- Les workers externes accèdent aux tâches via une API dédiée. Ils ne reçoivent pas les identifiants PostgreSQL ou Redis.
- Ne jamais committer `.env`, mot de passe, token ou clé API.
- Ne pas contourner les paywalls ni stocker du contenu non autorisé.

## Architecture

- `backend/app/api` : routes HTTP ;
- `backend/app/core` : configuration ;
- `backend/app/db` : session et base SQLAlchemy ;
- `backend/app/models` : modèles persistants ;
- `backend/migrations` : migrations Alembic ;
- `frontend/app` : application Next.js ;
- `docs` : décisions et procédures.

Les routes ne contiennent pas de logique métier complexe. Les futurs collectors partagent une interface commune. Les sorties IA sont contraintes par JSON Schema, validées par Pydantic puis contrôlées avec des règles déterministes.

## Commandes

```bash
docker compose up --build
docker compose config
docker compose run --rm backend pytest
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run build
```

## Méthode de travail

Avant une modification, lire ce fichier et la documentation concernée. Limiter chaque changement à une fonctionnalité cohérente, ajouter les tests utiles, exécuter les vérifications adaptées et mettre à jour la documentation si le comportement change.

La phase actuelle comprend la fondation, les collectors RSS de la BCE, de la Fed et des dépôts SEC 8-K, la récupération bornée des documents HTML officiels, leur scheduler, l'historique des collectes, l'extraction déterministe d'événements sourcés, l'identification des sociétés SEC par CIK, le regroupement exact avec conservation des sources et une analyse sémantique Ollama optionnelle. Les tests des collectors et de l'analyse utilisent des fixtures ou transports simulés et ne dépendent pas du réseau. Ne pas ajouter de fonction de trading sans demande explicite.

L'analyse sémantique découpe et sélectionne les passages dans un budget explicite, conserve la couverture et reprend les passages réussis. Les faits extraits sont des événements enfants ; le regroupement des publications ne doit jamais fusionner des faits différents issus du même document.

Les identités sont résolues sans appels LLM supplémentaires à partir des noms SEC,
CIK et tickers explicites. Conserver les candidats ambigus et les mentions non
vérifiées. Les liens `source_subject` du document ne prouvent pas le rôle d'une
société dans chaque fait. Le référentiel SEC est daté par sa consultation, pas par
une date de publication inventée ; ses cotations ne sont pas historiques.

Le portefeuille simulé et la collecte de clôtures Alpha Vantage sont autorisés dans
la phase actuelle. Ne pas transmettre d'ordres réels. Les paramètres du challenge
restent provisoires. Les simulations doivent conserver prix/date/source, contrôler
capital et positions, et rester idempotentes. Ne jamais compléter un cours manquant
avec une valeur inventée ; les clés fournisseur restent côté serveur.

Règles connues du challenge : 1 000 000 USD, actions en positions longues uniquement,
sans levier, Forex ou matières premières. WLS est un univers privé annoncé de
10 426 titres ; ne pas le reconstruire approximativement. L'éligibilité vient d'un
export autorisé par titre et cotation, jamais du CIK d'une entreprise. Les frais,
dates et limites restent à confirmer. Voir docs/CHALLENGE.md.

Les actions hors États-Unis et les cotations dans d'autres devises sont autorisées
selon la clarification de l'utilisateur. Bloomberg effectue la conversion dans le
challenge ; notre simulation devra disposer de cours locaux et de taux datés et
sourcés pour valoriser ces titres en USD. L'interdiction du Forex ne signifie pas
une restriction aux actions cotées en USD. NYSE/Nasdaq en USD reste une limite
technique du collecteur automatique, pas une règle du challenge. Les identités
internationales, clôtures locales et taux peuvent être fournis dans `/international`.
Conserver les unités, convertir avec un taux au plus tard à la date du cours et
préserver la conversion initiale de chaque opération. Ne pas inventer de taux,
CIK, MIC ou mapping Bloomberg ; l'ISIN ne prouve pas la cotation ou le WLS.
Voir docs/INTERNATIONAL_MARKET.md.

L'utilisateur demande le 10 octobre 2026 de poursuivre avec sa liste WLS partielle
sans les informations manquantes. OpenFIGI peut enrichir les identités, sans
certifier le WLS ni fournir de cours. Les nouvelles simulations peuvent choisir
`declared_partial` après preuve technique du titre et de sa cotation ; les anciens
portefeuilles restent stricts. Ne jamais convertir ce mode en éligibilité WLS
vérifiée, dater artificiellement le fichier ou créer d'ordre automatiquement.
Conserver les preuves de chaque achat et l'historique des exports. Voir
docs/WLS_AUTOMATION.md.

Les taux de référence BCE sont collectés automatiquement depuis le XML officiel.
Conserver la date de référence, les valeurs EUR utilisées et le calcul vers USD.
Ne pas les présenter comme des taux d'exécution Bloomberg. Les saisies manuelles
gardent priorité pour leur devise/date ; une collecte échouée n'efface aucun taux.
Voir docs/FX_COLLECTION.md.

La collecte des clôtures utilise le contrat commun `PriceProvider`, avec lots
revalidés avant écriture et quotas/reprises persistants par fournisseur. Alpha
Vantage reste le seul adaptateur connecté, NYSE/Nasdaq en USD et unité 1.
Les cotations internationales restent manuelles jusqu'au raccordement d'une
source autorisée et de correspondances exactes ; ne pas inventer de suffixes.
Conserver fournisseur et conventions de chaque cours. Voir docs/PRICE_PROVIDERS.md.

Le raccordement international Alpha Vantage utilise désormais uniquement des
correspondances explicitement documentées dans `price_listing_mappings`, avec
MIC, devise, unité et symbole fournisseur exacts. La saisie reste déclarée ; les
métadonnées de réponse certifient seulement le symbole, pas ces conventions.
Conserver les preuves dans le contexte de cours et respecter le quota partagé.
Aucune correspondance internationale réelle n'est devinée ou préchargée.

L'historique du portefeuille conserve des instantanés réellement observés, sans
écrasement ni reconstitution des jours passés. Les cours/FX absents ou anciens
restent signalés, sans interpolation de performance. Dividendes nets et splits
sont déclarés par cotation et simulation, atomiques et idempotents ; ne pas
inventer d'impôts, fractions compensées, réinvestissement ou règles Bloomberg.
Les splits rétroactifs incompatibles avec le registre sont refusés et les
preuves des ordres passés restent immuables. Voir docs/PORTFOLIO_TRACKING.md.

Les fiches `/analysis` rapprochent les titres suivis des documents et faits sans
appel LLM supplémentaire. Distinguer la mention du titre et de sa cotation du
contexte de l’émetteur. Ne pas transformer ce rapprochement en impact financier
avéré. Voir docs/INSTRUMENT_RESEARCH.md.

Le classement `/analysis` calcule une priorité de recherche déterministe sur les
faits sourcés des 30 derniers jours. Ne pas confondre ce score avec rendement,
signal d'achat ou éligibilité. Une seule contribution par publication parente,
sources non futures, bornes de couverture visibles et données de marché séparées.
Il reste sans appel LLM supplémentaire. Voir docs/RESEARCH_RANKING.md.

Les alertes `/alerts` sont historiques et idempotentes, sans signal d’achat ni
publication inventée. Les marqueurs de lecture sont propres au compte, partagés
en mode local sans comptes. Les flux Airbus/AMF conservent seulement les extraits
RSS officiels bornés. Les imports autorisés ne certifient pas leurs preuves ;
les dividendes/splits importés restent des propositions avant validation explicite.
Les répartitions ne devinent ni secteur ni pays. Une comparaison de benchmark
exige les mêmes dates et une série USD aux conventions immuables, sans reconstruire
le WLS. Les comptes partagent l’espace ; les rôles sont imposés côté serveur.
L’authentification reste désactivée par défaut en local. Les sauvegardes sont
chiffrées avec une clé publique utilisateur et les restaurations de vérification
exigent une nouvelle base dédiée. Voir docs/WORKSPACE.md et docs/DEPLOYMENT.md.
