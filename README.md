# 🧩 sheet-to-diagram (Dockerized)

Ce projet exécute un script Python utilisant `pandas` dans un conteneur Docker, afin d’éviter les problèmes d’antivirus (ex. : McAfee) et garantir un environnement cohérent.

---

## 📁 Structure attendue



docker build -t sheet-to-diagram .


# Windows
docker run --rm -v %cd%:/app sheet-to-diagram

# Linux / WSL
docker run --rm -v $(pwd):/app sheet-to-diagram


# Exemple : monter un dossier contenant des fichiers Excel
docker run --rm -v %cd%:/app -v C:\chemin\vers\excels:/data sheet-to-diagram

docker rmi sheet-to-diagram
