
# Diagram Builder — Structurizr

🗓️ *Généré le 2025-07-14*

Génère un *diagram‑as‑code* Structurizr à partir d'un inventaire Excel (*Applications* & *Flows*).

## 1. Prérequis

- Python ≥ 3.9  
- `pip`  
- (optionnel) Docker pour Structurizr‑Lite

## 2. Installation

```bash
python -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install pandas openpyxl structurizr-model structurizr-view structurizr-api
```

## 3. Exécution

```bash
python generate_diagram.py flows_applications.xlsx \
    --views system,container \
    --filter-protocol grpc,http \
    --hide-tags Keep \
    --output diagrams
```

Le dossier *diagrams/* contiendra `workspace.dsl` et `workspace.json`.

## 4. Structurizr Cloud (facultatif)

```bash
export STRUCTURIZR_API_KEY="yourKey"
export STRUCTURIZR_API_SECRET="yourSecret"
export STRUCTURIZR_WORKSPACE_ID="12345"
```

Relance le script : le workspace sera poussé automatiquement.

## 5. Visualisation locale

```bash
docker run --rm -it -p 8080:8080 -v $(pwd)/diagrams:/usr/local/structurizr structurizr/lite
# Ouvre http://localhost:8080 puis charge workspace.dsl
```

## 6. Aide

```bash
python generate_diagram.py --help
```
