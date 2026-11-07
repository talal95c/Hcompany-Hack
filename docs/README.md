# Documentation de conception

État : design et socle technique étape 0. Lire [AGENTS](../AGENTS.md), [PRD](../PRD.md), [synthèse architecture](../ARCHITECTURE.md). Les exemples de leçons ne sont pas des preuves obtenues ; les schémas, fixtures et scaffold sont désormais testables, sans moteur pédagogique implémenté.

## architecture
- [accessibilite-native](architecture/accessibilite-native.md) (proposition)
- [addon](architecture/addon.md)
- [desktop-tauri](architecture/desktop-tauri.md)
- [engine](architecture/engine.md)
- [face-agent](architecture/face-agent.md)
- [preparation](architecture/preparation.md)
- [services-ia](architecture/services-ia.md)
- [vue-ensemble](architecture/vue-ensemble.md)

## contrats
- [evenements-addon](contrats/evenements-addon.md)
- [lecon](contrats/lecon.md)
- [ordres](contrats/ordres.md)
- [ws-desktop](contrats/ws-desktop.md)

## decisions
- [0001-tauri-v2](decisions/0001-tauri-v2.md)
- [0002-ia-cloud](decisions/0002-ia-cloud.md)
- [0003-engine-asyncio](decisions/0003-engine-asyncio.md)
- [0004-fais-le](decisions/0004-fais-le.md)
- [0005-chemin-critique](decisions/0005-chemin-critique.md)
- [0006-paliers](decisions/0006-paliers.md)
- [0007-memoire](decisions/0007-memoire.md)
- [0008-skill-mcp](decisions/0008-skill-mcp.md)
- [0009-addon-capteur](decisions/0009-addon-capteur.md)
- [0010-cibles-descriptives](decisions/0010-cibles-descriptives.md)
- [0011-accessibilite-native](decisions/0011-accessibilite-native.md) (proposé)

## workflows
- [01-preparer-un-tuto](workflows/01-preparer-un-tuto.md)
- [02-etape-reussie](workflows/02-etape-reussie.md)
- [03-erreur](workflows/03-erreur.md)
- [04-blocage-paliers](workflows/04-blocage-paliers.md)
- [05-question-vocale](workflows/05-question-vocale.md)
- [06-fais-le](workflows/06-fais-le.md)
- [07-export-agent](workflows/07-export-agent.md)
- [08-mode-degrade](workflows/08-mode-degrade.md)
- [09-premier-lancement-permissions](workflows/09-premier-lancement-permissions.md)

## Transversal
- [Environnement de développement et commandes d'installation](environnement-dev.md)
- [optimisations-v3](optimisations-v3.md)
- [extension-apps-natives](extension-apps-natives.md) (explication, proposition)
- [zones-ombre](zones-ombre.md)
- [tests-et-jalons](tests-et-jalons.md)
- [equipe-et-workflow](equipe-et-workflow.md)
- [glossaire](glossaire.md)

## Plans des dossiers
- [contracts](../contracts/README.md)
- [engine](../engine/README.md)
- [addon](../addon/README.md)
- [desktop](../desktop/README.md)
- [prep](../prep/README.md)
- [agent](../agent/README.md)
- [lessons](../lessons/README.md)
- [bench](../bench/README.md)
- [tests](../tests/README.md)

## Schémas conservés
[Architecture SVG](schemas/architecture.svg) · [Cas d'usage SVG](schemas/cas-usage.svg). Ils ne sont pas régénérés pour cette livraison ; les ADR et les documents détaillés portent les décisions actualisées.
