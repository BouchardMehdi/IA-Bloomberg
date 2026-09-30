# Développement

## Backend

Le backend cible Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 et Alembic. Les paramètres viennent de variables d'environnement et sont validés au démarrage.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
ruff check .
```

## Frontend

```bash
cd frontend
npm install
npm run lint
npm run build
```

## Conventions

- Ajouter la logique métier dans des services plutôt que dans les routes.
- Garder les schémas d'entrée/sortie distincts des modèles SQLAlchemy.
- Utiliser UTC pour le stockage et convertir uniquement à l'affichage.
- Ne jamais journaliser de secret ni le contenu intégral d'un article par défaut.
- Ajouter un test lorsqu'il protège une règle métier ou un contrat d'API.
