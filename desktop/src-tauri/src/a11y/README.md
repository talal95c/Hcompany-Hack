# Capteur d'accessibilité

Le trait `AccessibilitySensor` garde les opérations natives hors du WebView. Linux utilise
une connexion AT-SPI paresseuse ; macOS utilise AX et Windows UI Automation.
Les autres plateformes renvoient `PERMISSION_DENIED`.
Le backend Linux est destiné à X11 : les extents écran AT-SPI sont des pixels physiques.
`Monitor::ax_rect` convertit les points AX avec les origines et le facteur du moniteur.

## Backends AX et UI Automation

La résolution commune accepte l'identifiant d'application, le nom localisé, le nom
d'exécutable, le PID et `focused`. Sur macOS, l'identifiant est le bundle ID (ou
l'exécutable sans bundle). AX exige `AXIsProcessTrusted` ; les refus sont typés, sans
reprendre les diagnostics du système. Les appels s'exécutent sur un worker bloquant,
avec un timeout AX par appel plafonné à 150 ms et le budget global de requête.
Au-delà de 512 enfants, seuls `AXVisibleRows` ou `AXVisibleChildren` sont utilisés ;
leur absence marque `LargeContainerSkipped`. Les valeurs AX sont uniquement des
chaînes ou nombres finis. `AXSecureTextField` ne renvoie pas de valeur et ne permet
pas `set_value`. Les actions utilisent AXPress, AXValue, AXFocused, AXSelected,
AXExpanded et les actions natives d'expansion, menu ou défilement disponibles.

Windows utilise `uiautomation` avec ses features par défaut, nécessaires à ses
imports internes. Un worker dédié initialise COM en MTA et garde les éléments COM
sur ce même thread jusqu'à leur destruction. Le parcours ControlView utilise des
propriétés mises en cache pour chaque lecture fraîche. La valeur est demandée dans
un second cache uniquement après le contrôle IsPassword, puis ce contrôle est relu
avant restitution. Les timeouts UIA de connexion et transaction sont plafonnés à
200 ms, avec vérification du budget entre lectures. Les actions utilisent Invoke,
Toggle, Value, SetFocus, SelectionItem, ExpandCollapse et ScrollItem.

Les deux workers ont une file bornée à 16 travaux et un registre natif borné à
10 000 handles, avec une durée logique de 35 s ; le store commun reste limité à
quatre snapshots et 30 s. Les requêtes annulées ne peuvent pas déclencher ensuite
une nouvelle action : l'autorisation est revérifiée au point d'appel natif et le
verrou exclusif reste détenu jusqu'à la fin du travail natif, même après annulation.
Toutes ces durées sont des limites configurées, pas des mesures.

Les tables de rôles AX/UIA et les règles de confidentialité sont dans `platform.rs`
et sont testées sur Linux : AXButton/UIA Button deviennent `button`, les boutons
à bascule `toggle_button`, AXCell/UIA DataItem `table_cell`, AXWindow/UIA Window
`frame`. Les types inconnus restent `unknown`. Les conversions, refs, recherches,
consentements et contrôles après action restent communs.

## Identifiants et limites

Les refs opaques sont `<snapshot_uuid>:n<index>`, y compris `root` et `parent_ref`.
Elles désignent un objet natif dans une application précise, jamais une position dans
le dernier arbre. Quatre snapshots sont gardés pendant 30 s au maximum ; une coupure
invalide toutes les refs. Une lecture `get` conserve l'identifiant du snapshot mais
relit l'objet sans cache de propriétés. Les erreurs natives ne sont jamais retransmises
avec leurs données : seuls des codes et messages fixes sont exposés.

Une observation est limitée à 2 000 nœuds et à une profondeur de 32 par défaut (64 au
maximum), avec un budget de requête de 3 s. Les limites sont configurées, pas des mesures.
Un arbre tronqué porte `complete=false`. Un timeout global porte `TIMEOUT`.
Les nœuds non affichés sont exclus ; les conteneurs sans géométrie propre héritent du
rectangle du parent. Une racine application sans composant est omise, ses fenêtres
deviennent les racines du résultat.

Sous Linux, au-delà de 4 096 enfants déclarés, un conteneur n'est jamais énuméré linéairement.
Une table est parcourue par son interface Table, entre les cellules obtenues par
hit-test des deux coins intérieurs de son rectangle visible. `complete=true` décrit
donc la couverture de la zone visible, pas celle des cellules virtuelles hors écran.
Un hit-test indisponible, une autre sorte de gros conteneur ou une limite de nœuds
rend l'observation incomplète. Les cellules fusionnées sont dédupliquées par handle.
Le parcours est en largeur, niveau par niveau, avec au plus 64 lectures de nœuds
concurrentes. Les métadonnées d'un nœud sont lues simultanément ; les enfants d'un
nœud non affiché ne sont pas lus. Les raisons de troncature sont comptées en interne
par rôle normalisé (`DepthLimit`, `NodeCap`, `Deadline`, `ChildReadError`,
`LargeContainerSkipped`). Les exclusions `InvisibleSkipped` et `DefunctSkipped`
ne rendent pas l'arbre incomplet. Les logs debug contiennent seulement ces comptes
et rôles, jamais les noms ou valeurs.

## Normalisation et recherche

Les rôles anglais AT-SPI sont passés en minuscules, espaces/tirets remplacés par `_` :
`push_button` → `button`, `tool_bar` → `toolbar`, `entry`/`password_text` → `text`,
`checkbox`/`checkbutton` → `check_box`. Les autres rôles sont conservés ainsi normalisés
(`toggle_button`, `table_cell`, `table`, `frame`, `menu_item`, etc.).
Les états exposés sont focused, selected, checked, enabled, expanded, editable,
pressed et busy ; visible exige simultanément Showing et Visible.

La recherche s'applique à un arbre neuf : rôle normalisé exact, valeur exacte, inclusion
des états et sous-séquence ordonnée des noms/rôles d'ancêtres. Pour le nom, une égalité
insensible à la casse est prioritaire ; la recherche par inclusion ne s'applique qu'en
l'absence d'égalité. Plusieurs résultats donnent `AMBIGUOUS_TARGET` et au plus dix
candidats, sans exécution implicite. Aucune cible donne un tableau vide ; une observation
incomplète ne prouve jamais l'absence.

## Actions et confidentialité

Les actions partagent avec l'injection le verrou exclusif et le contrôle du consentement,
de sa durée, de la connexion et de l'arrêt. Le contrôle est refait juste avant l'appel
natif. Les actions utilisent Action, EditableText, Value, Component ou Selection ; une
opération indisponible est refusée par `PERMISSION_DENIED` (le contrat n'a pas de code
distinct pour une action non supportée). Une action réussie est suivie d'une lecture
fraîche ; elle ne prouve pas à elle seule la réussite d'une procédure.

Les valeurs sont transmises seulement au moteur, jamais au WebView, aux logs ou aux
messages d'erreur. `Debug` masque la valeur des nœuds. Les champs de mot de passe ne
renvoient aucune valeur et refusent `set_value`.

## Vérification

Depuis `desktop/src-tauri` : `cargo check --locked`,
`cargo clippy --all-targets -- -D warnings`, `cargo test --locked`.
Le test ignoré `a11y::tests::live_accessibility` nécessite une session X11 et un bus
AT-SPI avec une feuille de données factices ouverte. `HCOMPANY_A11Y_APP` choisit l'app
(défaut `soffice`). Il observe cinq fois, mesure les latences, résout A1 et le bouton
Bold, relit la cellule et contrôle leurs rectangles dans la fenêtre. Il capture aussi
la fenêtre et actionne Bold sous consentement, vérifie le changement d'état puis
restaure l'état initial ; l'absence de consentement et l'arrêt sont testés. Il affiche
les raisons internes, les cinq latences, leur médiane et le
p95 (rang supérieur, donc maximum sur cinq mesures). La profondeur par défaut de 32
permet d'observer les conteneurs imbriqués du panneau latéral de l'application de recette.

## Fenêtres et contrôle ciblé

Le module `discovery` associe les fenêtres natives aux PID et noms AT-SPI. Sous X11,
la fenêtre active est lue via EWMH (focus X11 en secours sans gestionnaire de fenêtres),
les fenêtres visibles sont classées du premier plan vers l'arrière-plan. Les titres
ne sont jamais journalisés. Un sondage lié à chaque connexion publie `app.focus`
seulement lors d'un changement et conserve la dernière application externe lorsque
le panneau du guide prend le focus. Le consentement mémorise cette identité ; chaque
action vérifie le PID cible et le focus natif frais, y compris avant l'appel sémantique.

`capture.request` avec `scope=window` résout la fenêtre de `app`, réutilise le chemin
PNG et renseigne `capture.result.app` avec l'identifiant exécutable. Les régions
ordinaires restent limitées à 1 Mpx ; les fenêtres entières à 16 Mpx et à un seul
moniteur. Sans scope et avec `crop=null`, la sélection historique est conservée.

`highlight.rect` accepte le message WS et le destinataire de commande desktop. Un
couple ref/snapshot encore retenu est relu ; sinon le rectangle fourni sert de secours.
L'overlay convertit les pixels physiques en CSS selon le moniteur et son facteur
d'échelle, puis affiche un contour arrondi et un libellé texte jusqu'à expiration.
