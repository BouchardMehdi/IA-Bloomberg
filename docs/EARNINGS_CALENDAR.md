# Calendrier et résultats sourcés

La page `/calendar` conserve des observations pour chaque titre suivi. Elle sépare
dates prévues, estimations de bénéfice par action (BPA) et chiffres publiés fournis.
Ces données ne sont ni des ordres, ni des recommandations, ni une preuve WLS.
Les données concernent l'émetteur et ne démontrent pas un effet sur une cotation.

## Collecte

L'adaptateur utilise l'endpoint officiel Alpha Vantage `EARNINGS_CALENDAR`, par
symbole explicite et horizon `3month`, selon la
[documentation du fournisseur](https://www.alphavantage.co/documentation/).
Il concerne les titres suivis via Alpha Vantage, NYSE/Nasdaq, USD, unité 1.
La devise du BPA vient de la réponse, jamais de la devise du cours.
La date de publication et la convention du BPA ne sont pas fournies : elles
restent inconnues. La première consultation n'est pas une date d'annonce.
Un calendrier passé ne signifie pas que des résultats ont été publiés.

Configurer `ALPHA_VANTAGE_API_KEY` côté serveur. Sans clé, aucun appel, aucune
donnée fictive. `EARNINGS_CALENDAR_ENABLED=true` active le passage du scheduler
avant les cours, chaque heure, au maximum deux requêtes par passage.
L'API permet aussi une consultation explicite depuis la page.

Les cours et calendriers partagent les réservations persistantes Alpha Vantage,
le verrou PostgreSQL, le budget quotidien UTC et les délais après quota.
Les calendriers sont en plus limités à `max(1, budget // 4)` requêtes par jour,
soit cinq pour le budget par défaut de vingt. Les erreurs comptent dans ce budget.
Un titre consulté avec succès n'est pas rappelé le même jour ; les interruptions
et autres erreurs attendent au moins une heure. Les cours restent indépendants
des dates de collecte de calendrier. La couverture dépend des titres suivis et
du quota ; elle ne représente pas tout le WLS.

CSV borné à 1 Mo et 1 000 lignes ; symbole, dates, devise, nombres finis et
provenance publique sans clé sont validés avant écriture de toute la réponse.
Les six colonnes requises sont reconnues par leur nom, indépendamment de l'ordre.
La colonne optionnelle `timeOfTheDay` est conservée et affichée telle que fournie,
sans inventer de fuseau horaire ni d'heure exacte. Les colonnes manquantes,
dupliquées ou non prises en charge restent refusées.
Une réponse vide est un succès sans observation ; elle n'efface pas l'historique.
Les erreurs persistées sont des codes fermés, sans corps fournisseur ni clé.

## Saisies et comparaisons

Les cotations internationales peuvent recevoir des observations manuelles avec
URL documentaire autorisée et date réelle de publication avec fuseau. Le
formulaire ne télécharge aucune URL. Les saisies sont déclaratives, à vérifier
dans le document complet. Les nouvelles dates et estimations sont ajoutées sans
écraser l'historique ; renvoyer exactement la même observation est idempotent.

Un écart de BPA demande le même titre, fin de période, périodicité explicite,
devise et convention GAAP de base ou diluée. Les conventions ajustées ou inconnues
sont exclues. L'estimation doit être publiée **et déjà conservée** avant la date
de publication du résultat. Une estimation saisie après coup ne démontre pas
les attentes historiques. À date identique, plusieurs estimations sont ambiguës.
Le calcul utilise la dernière estimation compatible de la page visible, au plus
50 observations par défaut (100 maximum par API). L'absence sur une page ne prouve
pas l'absence dans tout l'historique. Le delta est résultat moins estimation ;
le pourcentage utilise la valeur absolue de l'estimation et reste absent si elle
vaut zéro. Les pertes et BPA nuls restent valides. Aucun consensus n'est inventé.

Les publications officielles déjà collectées sont consultables dans `/analysis`.
Elles restent des documents ou faits sourcés : aucun chiffre n'est attribué
automatiquement à une période fiscale depuis un simple dépôt 8-K.

## API

- `GET /api/v1/market/instruments/{id}/earnings?limit=50&offset=0`
- `POST /api/v1/market/instruments/{id}/earnings` : observation manuelle.
- `POST /api/v1/market/instruments/{id}/earnings/collect` : consultation fournisseur.

Une saisie contient `kind` (`schedule`, `estimate`, `reported`),
`fiscal_period_end`, `report_date`, `period_type` (`quarterly`, `annual`, `unknown`),
`source_url` et `published_at`. Pour les chiffres, fournir aussi `eps`, `currency`
et `basis` (`unknown`, `gaap_basic`, `gaap_diluted`, `adjusted_basic`, `adjusted_diluted`).

## Sources proposées par le collègue

La page affiche les liens Arkéa, Investing, Reuters, Bloomberg, Boursorama,
Trading Economics et BCE pour consultation. Seuls les collecteurs déjà documentés
et Alpha Vantage sont connectés. Aucun scraping de paywall ou de calendrier
Investing n'est ajouté. Les API et flux sous licence demandent un accès autorisé.
Une reprise Reuters dans Boursorama ne constitue pas une confirmation indépendante.
La récupération automatique des résultats chiffrés et des publications des sociétés
hors SEC reste à raccorder à une source autorisée avec des identités exactes.
