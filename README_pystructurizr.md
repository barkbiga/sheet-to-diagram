
# Diagram Builder with **pystructurizr**

Génère un fichier **Structurizr DSL** à partir d’un inventaire Excel (*Applications* & *Flows*) en s’appuyant sur la librairie **[pystructurizr](https://github.com/nielsvanspauwen/pystructurizr)**.

--> Objectif : noyer la complexité DSL derrière une API Python élégante, tout en restant compatible Structurizr‑Lite/Cloud.

---

## 1. Installation

Python ≥ 3.9 :

```bash
python3 -m venv .venvdiag
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install pystructurizr pandas openpyxl
```

*(ou, si tu préfères la toute dernière version GitHub)* :

```bash
pip install git+https://github.com/nielsvanspauwen/pystructurizr.git
```

## 2. Lancer la génération

```bash
python3 generate_pystructurizr.py flows_applications.xlsx \
       --views system,container \
       --output diagrams
```

**Résultat :** `diagrams/workspace.dsl`

## 3. Visualiser

### Structurizr‑Lite (Docker)

```bash
docker run -it --rm -p 8080:8080 -v $(pwd)/diagrams:/usr/local/structurizr structurizr/lite
# Ouvrir http://localhost:8080 et choisir workspace.dsl
```

### Structurizr‑CLI

```bash
structurizr-cli export -workspace diagrams/workspace.dsl -format png
```

### Structurizr Cloud

```bash
structurizr-cli push -workspace diagrams/workspace.dsl \
    -id 12345 -key YOUR_KEY -secret YOUR_SECRET
```

---

## 4. Paramètres disponibles

| Option | Par défaut | Description |
|--------|------------|-------------|
| `--views` | `system,container` | Liste des vues à générer |
| `--output` | `build` | Dossier de sortie |

---

_Généré le 2025-07-14_
