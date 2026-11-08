#!/usr/bin/env bash
# Learner simulator runs with real Holo calls (costs tokens). One at a time:
# the H account allows 30 requests per minute.
# Usage: sim.sh <scenario> <persona[,persona…]> [seeds] [h-tutor dir]
# Scenarios: h-tutor/sim/scenarios/*.json. Personas: diligent, novice, distracted, curious.
set -euo pipefail
scenario="${1:?usage: sim.sh <scenario> <personas> [seeds] [h-tutor dir]}"
personas="${2:?personas, e.g. diligent,novice}"
seeds="${3:-1}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="${4:-$(cd "$here/../../../../.." && pwd)}"
cd "$root/src-tauri"
SIM_SCENARIO="$scenario" SIM_PERSONA="$personas" SIM_SEEDS="$seeds" \
  cargo test --locked --lib sim::tests::simulate -- --ignored --nocapture 2>&1 | grep -E "seed [0-9]+:|report:|panicked"
