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

Le client Ollama envoie le titre et un passage limité à 8 000 caractères du document récupéré avec le JSON Schema Pydantic de sortie. Après un échec définitif de récupération, l'extrait RSS reste utilisable. `semantic-v4` produit un résumé bref en français, un type d'événement, des sociétés, actifs, dates, montants, scores et jusqu'à trois preuves courtes. La température est fixée à zéro. Toute citation qui ne peut pas être retrouvée dans le passage transmis invalide le résultat. Les analyses échouées attendent dix minutes avant une nouvelle tentative ; une analyse en cours reste réservée pendant 31 minutes, couvrant le délai Ollama maximal configurable.

`analysis_runs` journalise les succès et les échecs avec le modèle, la version du prompt, le hash d'entrée, la durée et les tokens. L'analyse est désactivée par défaut afin que la collecte reste disponible sans GPU ni modèle téléchargé.

La clé unique inclut désormais le hash d'entrée. Une récupération de texte permet une nouvelle analyse sans écraser une analyse RSS. `input_text` et `source_url` conservent exactement le passage utilisé et son origine. Les sorties anciennes restent consultables même si le texte de l'article est ensuite enrichi.

Le regroupement précède les cycles d'analyse : même numéro de dépôt SEC, ou texte complet identique avec source et date identiques. L'événement d'origine reste auditable via `merged_into_event_id`. Aucun rapprochement fondé uniquement sur un titre ou un score de similarité n'est effectué.
