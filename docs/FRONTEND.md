# Navigation et interface

Toutes les pages partagent une navigation latérale sur ordinateur (à partir de
1 024 pixels) et un bouton **Menu** sur tablette et téléphone. La page active est
indiquée visuellement et par `aria-current`. Le menu se ferme après navigation ;
Échap le ferme et remet le focus sur son bouton. Un lien « Aller au contenu »
est disponible au clavier.

| Page | Usage |
| --- | --- |
| `/` — Veille | Publications officielles, faits extraits et état des collectes |
| `/analysis` — Analyser | Priorité de recherche, synthèse, résultats, valorisation, documents et faits |
| `/calendar` — Calendrier | Dates prévisionnelles, estimations et résultats sourcés |
| `/portfolio` — Portefeuille | Simulation, titres suivis, univers WLS et création d’une simulation |
| `/coverage` — Qualité des données | Filtres sur les données manquantes et préparation de preuves |
| `/international` — International | Cotations internationales, ajout d’identité, cours et taux |
| `/alerts` — Alertes | Nouvelles observations et échecs de collecte |
| `/settings` — Mon espace | Imports sourcés, propositions et comptes |
| `/collections` — Suivi des collectes | Historique technique et reprises au plus tôt |
| `/briefing` — Briefing quotidien | Nouveautés, échéances et dossiers à revoir |
| `/journal` — Journal des décisions | Hypothèses et révisions sourcées |

Les sections d’une page sont sélectionnées avec des boutons. Les explications
longues et les formulaires avancés sont repliables. Les limites essentielles
(simulation, WLS provisoire, score de recherche, données manquantes, dates
prévisionnelles) restent visibles dans leur contexte. Les liens vers les sources
et les preuves sont conservés. Une date de consultation n’est pas présentée comme
une date de publication.

## Tutoriels pour les nouveaux utilisateurs

Sous le titre de chacune des onze pages, un encart **Mode d’emploi** présente
le rôle de la page, trois étapes pour commencer et les limites à retenir. Son
contenu dépend de la page ouverte et utilise les noms des sections et boutons
de l’interface, sans demander de connaître l’architecture technique.

Les tutoriels sont affichés par défaut. **Masquer le tutoriel** replie le contenu ;
**Afficher le tutoriel** reste accessible dans l’encart pour le réactiver.
Ce choix est commun à toutes les pages et conservé dans le `localStorage` du
navigateur sous `market-ai:tutorials:v1`. Il se synchronise entre les onglets
du même site et navigateur. Si le stockage est indisponible, le bouton fonctionne
quand même, mais le choix ne peut pas être conservé après rechargement.

Le bouton est utilisable au clavier et expose son état par `aria-expanded` et
`aria-controls`. Masquer un tutoriel ne masque aucun avertissement, blocage ou
preuve affichés dans le reste de la page. Cette aide ne déclenche aucun appel
API, aucune collecte ni opération.

## Listes et mobile

- Veille : six publications et six événements par page, pagination par l’API.
- Classement de recherche : cinq titres par page, pagination par l’API.
- Documents/faits d’un titre, observations financières, calendrier et WLS : dix
  éléments par page, pagination par l’API.
- Titres suivis, qualité des données, cotations internationales, positions,
  dernières opérations, preuves quotidiennes et opérations sur titres : dix
  éléments par page dans les données déjà chargées. Taux : huit par page.
- Les recherches et filtres remettent la liste à la première page. La pagination
  indique la plage et le total si celui-ci est connu, sinon le numéro de page.
  Les boutons inutiles sur une liste d’une seule page sont masqués.

Les limites de couverture de l’API restent applicables : notamment les cinquante
dernières opérations, l’historique quotidien borné et les observations de
valorisation conservées dans leur rubrique. La pagination locale ne prétend pas
charger un historique exhaustif.

Sous 640 pixels, les tableaux de titres, de positions, de correspondances WLS et
de chiffres financiers deviennent des cartes avec les libellés de chaque valeur.
Les formulaires passent sur une colonne, les champs ont une hauteur minimale de
44 pixels et une police de 16 pixels. Les contrôles de navigation et de pagination
ont des zones tactiles adaptées. Les animations respectent la préférence système
de réduction des mouvements.

## Vérification dans le navigateur

Depuis `frontend`, avec le front lancé sur `http://localhost:3000` :

```powershell
npm ci
npm run lint
npm run build
npm run check:ui
```

Le script utilise Chrome ou Edge installé aux emplacements Windows habituels.
On peut préciser `UI_BROWSER_PATH` pour un autre exécutable. Sinon, installer le
navigateur Playwright avec `npx playwright install chromium`.
Pour une autre URL : `$env:UI_BASE_URL='http://localhost:3001'`.

Les contrôles utilisent exclusivement des réponses API simulées dans le navigateur,
sans modifier la base, passer d’ordre ni consommer de quota fournisseur. Ils
vérifient les onze routes à 320, 390, 768 et 1 440 pixels, la navigation au clavier,
les changements de section, les filtres, les paginations et les états vides/erreur.
Ils contrôlent aussi le contenu des tutoriels sur chaque page, leur activation
au clavier, la persistance après rechargement, la synchronisation entre onglets
et le fonctionnement lorsque le stockage du navigateur est bloqué.
Les captures sont enregistrées dans `frontend/.ui-check/`, hors Git et hors image
Docker. Le script échoue en cas de débordement horizontal, d’erreur JavaScript
non interceptée ou de requête d’écriture.

Cette refonte ne modifie aucun calcul financier, règle d’éligibilité, quota ou
contrôle d’opération du backend. Aucune donnée de démonstration n’est insérée en base.

Les pages Alertes et Mon espace ont le même tutoriel et la navigation commune.
Le compteur d’alertes et la connexion utilisent le client API partagé avec cookies
et reconnexion après expiration. Les imports et comptes restent soumis aux droits
serveur. Les répartitions du portefeuille affichent leurs sources et inconnues.
Voir [l’espace partagé](WORKSPACE.md).

`node scripts/check-workspace.mjs` vérifie aussi la connexion, l’expiration de
session, les rôles, les imports et la confirmation des propositions avec des
réponses entièrement simulées, sans écriture réelle.

`node scripts/check-daily-workspace.mjs` vérifie la création du journal,
la confirmation, la conservation des versions et l’accès en lecture seule,
avec toutes les écritures simulées.
