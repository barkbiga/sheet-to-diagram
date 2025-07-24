
# DUKPT (Derived Unique Key Per Transaction) – 5‑Minute Overview
*Reference: ANSI X9.24‑3 / ISO 11568 (2023)*

---

## 1 · Pourquoi ?

* **Clé unique par transaction** : si une clé est compromise, l’impact se limite à une seule opération.  
* **BDK jamais exportée** : la Base Derivation Key reste confinée dans le HSM.  
* **Logistique simplifiée** : un seul secret maître à injecter en usine.

---

## 2 · Hiérarchie des clés

```
           +-------------+
           |   BDK (HSM) |
           +------+------+        (1) derive IK
                  |
                  v
           +-------------+
           |  IK (TIK)   |        Initial Key  — unique par terminal
           +------+------+        (2) derive WK
                  |
                  v
           +-------------+
           |  WK (Tx)    |        Working Key — dépend du compteur
           +------+------+        (3) derive keys by usage
                  |
        +---------+---------+
        |    |    |    |    |
        v    v    v    v    v
      PIN DATA MAC_R MAC_S …   cinq clés d’usage
```

---

## 3 · Format du **KSN** (12 octets)

| Octets | Champ                       | Commentaire                           |
|--------|----------------------------|---------------------------------------|
| 0‑4    | Derivation ID              | Identifiant  fabricant / acquéreur    |
| 5‑7    | Initial Key ID (partiel)   | —                                     |
| 8‑11   | Compteur (21 bits)         | max = 0x1FFFFF                        |

---

## 4 · Dérivation AES‑256 (ECB)

| Étape | Préfixe | Constante  | Données                    | Algorithme                         |
|-------|---------|-----------|----------------------------|------------------------------------|
| **IK** | `0101 8001` | `0004 0100` | *IK ID* (8 o)              | `IK = AES_ECB(BDK, …)`             |
| **WK** | `0101 8000` | `0004 0100` | UniqueID ‖ Counter        | `WK = AES_ECB(IK, …)`              |
| **Usage** PIN | `0101 1000` | `0004 0100` | UniqueID ‖ Counter        | `PIN_KEY = AES_ECB(WK, …)`         |

> Les préfixes/constantes proviennent du tableau ISO 11568 / X9.24‑3.

---

## 5 · Avantages

* **Compartimentation** : fuite d’une clé n’expose qu’une transaction.  
* **Interopérable** : mêmes clés dérivées côté terminal et côté hôte.  
* **Scalable** : pas de nouvelle clé maître lors de l’ajout d’un terminal.

---

## 6 · Références rapides

* ANSI X9.24‑3‑2017 – *Test Vectors* (gratuit)  
* ISO 11568 :2023 – *Key Management (Retail)*  
* PCI PIN v3.0 – Annexe B (comparaison DUKPT 2009 / AES‑DUKPT)

---




Spécification fonctionnelle – Besoin HSM pour la mise en place du schéma DUKPT
(version 0.9 – à valider)

1. Contexte et objectifs
Élément	Description
Contexte métier	Moderniser la chaîne de paiement pour supporter le schéma DUKPT AES-256 sur l’ensemble des terminaux (POI) et des services back-office.
Enjeu principal	Garantir qu’une clé unique est utilisée pour chaque transaction, sans jamais exposer la BDK en clair, tout en simplifiant la logistique de clés.
Rôle du HSM	Héberger :
• la Base Derivation Key (BDK) par environnement (prod, pré-prod, test)
• les fonctions de dérivation Initial Key et Working Key
• le chiffrement/déchiffrement AES-ECB sous clé dérivée, le cas échéant (PIN block format 4, MAC, etc.).

2. Périmètre
Canaux couverts : terminaux de paiement, e-commerce (opérations server-side), TMS.

Algorithme cible : AES-DUKPT 256 bits (ISO 11568:2023 / ANSI X9.24-3).

Éléments hors périmètre : dérivation TDEA, gestion des clés P2PE, clés de test internes aux équipes QA.

3. Exigences fonctionnelles
Ref	Exigence	Détail / Remarque
F-01	Import sécurisé de la BDK	• Double contrôle (split knowledge, dual control)
• Format TR-31 ou ISO 20038
F-02	Fonction DeriveInitialKey	Entrées : BDK, InitialKeyID (8 oct.)
Sortie : IK (32 oct.)
F-03	Fonction DeriveWorkingKey	Entrées : IK, compteur (21 bits), UniqueID
Sortie : WK (32 oct.)
F-04	Fonction DeriveUsageKey	Types : PIN_ENC, DATA_REQ, DATA_RESP, MAC_REQ, MAC_RESP
Préfixes et constantes conformes tableau ISO/X9
F-05	Limitation compteur	Rejeter > 2 097 151 (0x1FFFFF) ou déclencher rotation IK
F-06	Audit log	Traçabilité : ID opération, KSN, type de clé dérivée, statut
F-07	Performance	≥ 250 dérivations / s (peak) avec latence ≤ 20 ms 95ᵖᵉ centile
F-08	Interfaces	• API C/S (PKCS#11 v2.40)
• REST over TLS 1.3 (optionnel)
F-09	Haute disponibilité	Cluster actif/actif ; RTO < 1 min ; réplication BDK HSM-to-HSM

4. Exigences de sécurité
Ref	Règle
S-01	HSM certifié PCI HSM v3 ou FIPS 140-3 level 3 minimum
S-02	BDK et IK stockées exclusivement en mémoire sécurisée du HSM
S-03	Aucune clé dérivée ne doit être exportable en clair
S-04	Authentification opérateur : MFA + rôles (Crypto-Officer, Auditor…)
S-05	Chiffrement de session : TLS 1.3 + mutual auth (certificats X.509)

*(c) 2025 – document pédagogique, aucune partie normative reproduite in extenso.*

