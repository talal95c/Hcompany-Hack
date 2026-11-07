# Profils applicatifs

Pourquoi : isoler le vocabulaire, les sources documentaires et le contexte de chaque
application des clients cloud génériques. Chaque dossier porte un identifiant stable
égal au champ `id` de son `profile.json`, validé par `profile.schema.json`.

Le profil `generic` sert de repli sans restriction documentaire. `HCOMPANY_APPS_DIR`
permet de charger un autre catalogue ; `HCOMPANY_APP` choisit le profil des clients.
