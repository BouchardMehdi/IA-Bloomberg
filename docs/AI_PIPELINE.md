# Pipeline IA

L'intégration IA n'est pas encore active. Son contrat prévu est le suivant :

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

Les prompts seront versionnés dans `prompts/`. Les appels enregistreront la version du modèle, la version du prompt, la durée et le statut. Les futurs workers récupéreront leurs tâches via l'API et renverront uniquement des résultats structurés.

Pour réduire la charge locale, les filtres déterministes et la déduplication exacte doivent précéder tout appel à Ollama.

## Première passe déterministe

Avant l'intégration d'un modèle, le scheduler crée un événement minimal pour chaque article primaire non traité. Les publications BCE et Fed deviennent des `central_bank_announcement`; les dépôts SEC deviennent des `regulatory_filing`. Chaque événement conserve une clé de déduplication, la date du document et un lien primaire vers l'article.

Cette passe enregistre le fait vérifiable qu'une annonce ou un dépôt a été publié. L'extraction IA ultérieure pourra produire des événements métier plus précis et relier plusieurs articles au même fait sans supprimer cette provenance.

Pour les dépôts SEC, l'extracteur déterministe récupère déjà le formulaire, le CIK, le nom du déclarant et le numéro d'accession disponible. Il crée ou actualise la société correspondante puis la relie à l'événement avec le rôle `subject`. Chaque résultat porte la version `deterministic-v1` et un extrait justificatif limité provenant du document source.
