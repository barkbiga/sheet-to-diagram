
# Diagram Builder — Structurizr

🗓️ *Généré le 2025-07-14*

Génère un *diagram‑as‑code* Structurizr à partir d'un inventaire Excel (*Applications* & *Flows*).

## 1. Prérequis

- Python ≥ 3.9  
- `pip`  
- (optionnel) Docker pour Structurizr‑Lite

## 2. Installation

```bash
python3 -m venv .venvdiag
source .venvdiag/bin/activate   # Windows : .venv\Scripts\activate
pip install pandas openpyxl structurizr-model structurizr-view structurizr-api
pip install structurizr-python pandas openpyxl

```

## 3. Exécution

```bash
python3 generate_diagram.py flows_applications.xlsx \
    --views system,container \
    --filter-protocol grpc,http \
    --hide-tags Keep \
    --output diagrams

python3 generate_pystructurizr.py flows_applications.xlsx \
    --views system,container \
    --output diagrams --filter-tag SIRH,

python3 generate_pystructurizr_id_v_3.py flows_applications.xlsx \ 
    --views system,container \
    --output diagrams


    python generate_pystructurizr_id_v4.py flows.xlsx --filter-tag beta,critical

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

docker run --rm -it -p 8080:8080 \
  -v $(pwd)/diagrams:/usr/local/structurizr \
  structurizr/lite

```

## 6. Aide

```bash
python generate_diagram.py --help
```
