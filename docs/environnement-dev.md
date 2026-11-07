# Environnement du socle — étape 0

## Python 3.11
Commandes exécutées sur la VM (uv était déjà installé) :

```sh
uv python install 3.11
uv venv --python 3.11 /home/ubuntu/.venvs/hcompany-hack
```

Depuis la racine du dépôt :

```sh
uv pip install --python /home/ubuntu/.venvs/hcompany-hack/bin/python -e .
source /home/ubuntu/.venvs/hcompany-hack/bin/activate
ruff check .
pytest -q
```

L'installation editable rend engine, prep, agent et addon importables. Le Python global de la VM est 3.12 ; les vérifications du socle utilisent le venv 3.11. Les extras holo/jev/gladia/linkup/devin/desktop ajoutent les SDK de service sans implémenter encore de client. Les tests des contrats ne font aucun appel cloud.

## Rust et dépendances Tauri Linux
Rust était déjà installé : aucune installation Rust n'a été nécessaire. Commandes de diagnostic exécutées :

```sh
rustc --version
cargo --version
rustup show active-toolchain
```

Versions observées : rustc 1.97.1, cargo 1.97.1, toolchain stable-x86_64-unknown-linux-gnu. Le dépôt conserve Cargo.lock ; CI utilise stable et cargo check --locked sur Ubuntu et macOS. Aucun CLI Tauri ni Node n'est requis pour ce scaffold statique.

Commandes d'installation réellement exécutées sur Ubuntu 22.04 :

```sh
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf libxkbcommon0 libxrender1 libxi6 libxxf86vm1 libxfixes3 libgl1 libegl1 libsm6 xz-utils
```

CI Ubuntu utilise libayatana-appindicator3-dev, le paquet adapté à ubuntu-latest, à la place de libappindicator3-dev sur cette VM 22.04. Les bibliothèques graphiques sont nécessaires même pour cargo check : leurs build scripts utilisent pkg-config.

Depuis desktop/src-tauri :

```sh
cargo check
```

Le premier passage a révélé l'icône requise par generate_context ; une icône RGBA neutre est désormais incluse. Le scaffold ne valide pas les permissions, le rendu ou la capture macOS ; ces tests natifs restent à faire.

## Blender portable 4.5.9 LTS
Commandes exécutées (aucun Blender système préexistant) :

```sh
mkdir -p /home/ubuntu/downloads
curl -fL --retry 3 -o /home/ubuntu/downloads/blender-4.5.9-linux-x64.tar.xz https://download.blender.org/release/Blender4.5/blender-4.5.9-linux-x64.tar.xz
curl -fL -o /home/ubuntu/downloads/blender-4.5.9.sha256 https://download.blender.org/release/Blender4.5/blender-4.5.9.sha256
```

Depuis /home/ubuntu/downloads :

```sh
sha256sum --check --ignore-missing blender-4.5.9.sha256
sudo mkdir -p /opt/blender
sudo tar -xJf /home/ubuntu/downloads/blender-4.5.9-linux-x64.tar.xz --strip-components=1 -C /opt/blender
sudo ln -s /opt/blender/blender /usr/local/bin/blender
blender -b --python-expr "import bpy;print(bpy.app.version)"
```

Sortie observée :

```text
blender-4.5.9-linux-x64.tar.xz: OK
(4, 5, 9)
Blender 4.5.9 LTS (hash 8bf95cbd38d1 built 2026-04-21 01:31:15)

Blender quit
```

L'extraction vise une installation initiale, pas une mise à jour atomique d'une version existante. Le lien ln -s est lui aussi destiné à la première installation. Cette version de la VM ne fixe pas celle du Mac de démo ; toute preuve destinée à ce Mac devra utiliser sa version exacte.
