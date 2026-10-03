# Pipeline IA

L'analyse IA locale est disponible en option. Le pipeline cible est le suivant :

```text
Article normalisé
  → déduplication exacte
  → extraction Ollama contrainte par JSON Schema
  → validation Pydantic et règles déterministes
  → recherche d'événements candidats
  → création ou rattachement
  → score déterministe
```

La sortie doit pouvoir contenir zéro, un ou plusieurs événements. Chaque date, montant ou déclaration importante conserve un extrait justificatif de la source. Une valeur absente reste inconnue ; le modèle ne doit pas la compléter par supposition.

Le prompt actuel est versionné dans `backend/app/semantic/prompt.py`. Les appels enregistrent le nom du modèle, la version du prompt, la durée et le statut. Les futurs workers récupéreront leurs tâches via l'API et renverront uniquement des résultats structurés.

Pour réduire la charge locale, les filtres déterministes et la déduplication exacte doivent précéder tout appel à Ollama.

## Première passe déterministe

Avant l'intégration d'un modèle, le scheduler crée un événement minimal pour chaque article primaire non traité. Les publications BCE et Fed deviennent des `central_bank_announcement`; les dépôts SEC deviennent des `regulatory_filing`. Chaque événement conserve une clé de déduplication, la date du document et un lien primaire vers l'article.

Cette passe enregistre le fait vérifiable qu'une annonce ou un dépôt a été publié. L'extraction IA ultérieure pourra produire des événements métier plus précis et relier plusieurs articles au même fait sans supprimer cette provenance.

Pour les dépôts SEC, l'extracteur déterministe récupère déjà le formulaire, le CIK, le nom du déclarant et le numéro d'accession disponible. Il crée ou actualise la société correspondante puis la relie à l'événement avec le rôle `subject`. Chaque résultat porte la version `deterministic-v1` et un extrait justificatif limité provenant du document source.

## Analyse sémantique locale

Le prompt actuel est `semantic-v6-entities`. Il ajoute des `entity_mentions` avec nom
copié, type, rôle (`subject`, `counterparty`, `mention`) et citation. La résolution
des identités est déterministe et ne lance aucun appel supplémentaire au modèle.
Les succès `semantic-v5-passages` pour le même document, modèle et plan restent en
cache ; leurs entités sont traitées comme mentions. Les anciennes analyses partielles
peuvent être reprises avec le nouveau prompt. Voir le README pour les limites des
identifiants de titres et des rôles.

`semantic-v5-passages` analyse un plan déterministe établi sur l'ensemble du texte conservé. Les passages respectent autant que possible les limites de phrase et de section ; leurs positions sont conservées. Les indices financiers priorisent les passages utiles et les mentions légales diminuent leur priorité. Le budget par défaut est de trois passages de 3 000 caractères, 9 000 caractères au total, hors titre et prompt. Après un échec définitif de récupération, l'extrait RSS reste utilisable.

Chaque appel utilise un JSON Schema `PassageExtraction` contenant zéro à trois faits. Un passage sans fait peut produire une liste vide. Chaque fait conserve un résumé bref en français, son type, ses entités, dates, montants, scores et une citation. Une citation doit se retrouver dans le titre ou le passage effectivement transmis. Un passage invalide est rejeté intégralement. La température est nulle et la génération est limitée à 1 536 tokens par appel.

Les tentatives échouées ou partielles attendent dix minutes. La réservation d'une analyse en cours couvre le nombre maximal de passages multiplié par le délai du client, plus deux minutes. Une réservation atomique évite de lancer deux traitements concurrents pour la même entrée. Les passages réussis sont réutilisés lors d'une reprise ; ils ne consomment pas de nouveaux appels au modèle.

`analysis_runs` journalise les succès et les échecs avec le modèle, la version du prompt, le hash d'entrée, la durée et les tokens. L'analyse est désactivée par défaut afin que la collecte reste disponible sans GPU ni modèle téléchargé.

La clé unique inclut le hash du titre, du texte complet conservé et de la signature du plan. Une modification dans la fin du document invalide donc le cache. `analysis_runs.input_text` conserve le document d'entrée ; `analysis_passages.input_text` conserve chaque passage transmis. `coverage` distingue les passages non retenus, en attente, réussis et échoués et mesure les caractères analysés sur le texte conservé. Une réussite signifie que tous les passages sélectionnés ont été analysés, sans garantir une couverture intégrale du document.

Les événements de publication gardent leur identité. Les faits deviennent des événements enfants avec `parent_event_id` et `fact_analysis_run_id`. Leur identité déterministe combine la publication, le type et la citation normalisée : des résumés différents avec la même preuve ne recréent pas un événement. Les preuves différentes d'un même fait restent une limite du rapprochement actuel. Les sociétés héritées du document ont le rôle `source_subject`, et les sociétés extraites restent dans les données structurées du fait.

Le regroupement précède les cycles d'analyse : même numéro de dépôt SEC, ou texte complet identique avec source et date identiques. L'événement d'origine reste auditable via `merged_into_event_id`. Aucun rapprochement fondé uniquement sur un titre ou un score de similarité n'est effectué.
