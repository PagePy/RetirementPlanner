# À faire

## Fiscalité et simulation

- [x] **Indexer la fiscalité** : les paliers d'impôt, les crédits, le seuil de récupération de la SV et le plafond REER sont indexés via `price_factor` (`TaxCalculator.compute`, `OAS.clawback`, `estate_timeline`).
- [ ] **Règle québécoise du fractionnement** : au Québec, le cédant doit avoir 65 ans ou plus, même pour une rente PD (à valider). Le moteur applique la règle fédérale aux deux paliers.
- [ ] **Afficher le fractionnement** : colonne « Fractionnement » dans les résultats (montant et sens, `pension_split_received`).
- [ ] **Interrupteur de fractionnement** pour mesurer l'économie avec et sans.
- [ ] **Partage de la rente RRQ** entre conjoints (option).
- [ ] **REER de conjoint** (non modélisé).
- [ ] **Dépenses ponctuelles payées par le CELI d'abord** (ex. remplacement de l'auto), en option, avant les retraits REER.
- [ ] **Année de début pour les dettes**, pour simuler un prêt futur (ex. prêt auto en 2040).
- [x] Renommer la colonne « Retenues/Impôts » en « Impôts + récup. SV » (aucune retenue salariale n'y est incluse).

## Distribution avec licences d'essai (Windows + Mac)

Décisions : application de bureau (NiceGUI natif), codes hors ligne signés Ed25519, limitation par date d'expiration, module de licence partagé avec l'application de budget.

### Préparer l'application
- [ ] Déplacer les profils dans le dossier de données utilisateur (`platformdirs`) au lieu de `profiles/` (`PROFILES_DIR` dans `gui/state.py`).
- [ ] Ne jamais distribuer `profiles/` (données personnelles) ; l'ajouter à `.gitignore` et le retirer du suivi git.
- [ ] Compléter `pyproject.toml` (nicegui, plotly, pandas, cryptography, platformdirs) et afficher la version dans l'en-tête.

### Module de licence partagé (dépôt séparé)
- [ ] Format : contenu (produit, nom, numéro, type essai/complet, émission, expiration) + signature Ed25519.
- [ ] Vérification avec clé publique embarquée : valide, expiré, mauvais produit, modifié.
- [ ] Refuser si l'horloge recule de plus d'un jour par rapport à la dernière date vue.
- [ ] Outil personnel de génération de codes ; clé privée hors de tout dépôt.
- [ ] Tests : valide, expiré, mauvais produit, contenu modifié, horloge reculée.

### Intégration au planificateur
- [ ] Vérifier la licence dans `build_app()` (`gui/main.py`) ; écran d'activation sinon.
- [ ] Bandeau « Essai — expire le … (N jours) ».
- [ ] Après expiration : écran d'activation, avec export des profils possible.

### Fabrication des installateurs
- [ ] `nicegui-pack` en mode natif, avec les données `planner/data`.
- [ ] Construction sur chaque système (GitHub Actions : windows-latest et macos-latest).
- [ ] Test sur un Windows et un Mac sans Python ; vérifier qu'aucun profil personnel n'est inclus.

### Application de budget
- [ ] Réutiliser le module de licence (produit « budget ») ; écran d'activation adapté à l'interface (Streamlit ou Tkinter).

### Avant la vente
- [ ] Protection du code (Nuitka ou PyArmor).
- [ ] Signature de code (Apple Developer, certificat Windows).
- [ ] Licence d'utilisation et mention « ceci n'est pas un conseil financier ».
- [ ] TPS/TVQ au-delà de 30 000 $ de ventes, ou plateforme de vente (Lemon Squeezy, Paddle) qui gère les taxes et les codes.

### À préciser
- [ ] Comportement exact après l'expiration.
- [ ] Accès à un Mac pour construire et tester.
- [ ] Interface exacte de l'application de budget.
