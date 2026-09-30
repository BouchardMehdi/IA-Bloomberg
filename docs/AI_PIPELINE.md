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
