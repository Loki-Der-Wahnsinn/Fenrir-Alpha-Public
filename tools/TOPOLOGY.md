# Read-only Python dependency topology

Run `python tools\topology_features.py .` from the repository root. The tool
parses Python source without executing it or modifying files, and prints JSON.
Parsing errors stop the analysis rather than producing incomplete results.
Symbolic links and Windows reparse points (including junctions) are skipped,
so linked directories and files are not included in the results.
Use `--exclude <relative-directory>` (repeatable) to omit a known non-source
subtree such as a quarantine archive; the JSON output lists these exclusions.
The directory must exist and stay within the analysis root without links.
Python callers may explicitly supply `on_parse_error(path, error)` to
`dependency_graph` to report and exclude unparseable files. Such results are
partial; edges to excluded files are omitted. Directory traversal errors still
stop the analysis.

Vertices are modules. Directed edges are statically resolvable local imports;
dynamic imports and external dependencies are not resolved. Package imports
can introduce edges to both the package and an imported submodule. Results
depend on the selected source directory and may overstate imports in conditional
or unused code.

For topology, direction is discarded. Reciprocal imports enter the filtration at
scale 1 and one-way imports at scale 2; vertices enter at scale 0. `h0_deaths`
lists the finite death scales of connected components; `h0_essential` counts
those that persist. `h1_births_essential` lists graph-cycle birth scales.
This is a graph complex without filled triangles, so cycles never die; these
scales describe a chosen coupling convention, not a physical distance.

`circular_import_groups` lists strongly connected groups of modules in the
directed import graph. Unlike graph cycles, these are possible circular imports.
Because module names are included in the output, review it before sharing.

These features describe structure; by themselves they do not establish improved
recognition or learning from real-world outcomes.
No data is submitted to an LLM or network service.

## Entry-point module inventory

`python tools\module_preflight.py --root <repository> --entry <relative-file>`
lists static imports without importing or executing them. Add
`--reference <local-tree>` to compare with a second source tree.
This tool needs Python 3.10 or newer. Conditional and optional imports are
included; dynamic imports, relative imports and transitive dependencies are
not resolved. Standard-library classification uses the top-level name only;
presence means a file or namespace directory candidate, not an import test.
An unresolved import can be a third-party package rather than a missing file.
Presence in a reference tree is **not** evidence of safety, provenance,
license, functional correctness, or permission to publish it. Links and
Windows reparse points are not followed.

## Bounded neuro-symbolic simulation

`python tools\topology_optimizer.py <source-directory>` combines a single
logistic unit with symbolic circular-import rules to rank simulated removal of
directed import edges. Every suggested removal is independently verified to
preserve the number of connected components and strictly reduce the
lexicographic objective: first the number of modules in directed circular
groups, then the number of undirected graph cycles. The tool **never edits or
executes source files**. Removing an import in real code may break it even if
the graph improves; each suggestion requires human review.

The unit learns online from the measured outcomes of candidate simulations,
not from fabricated labels or actual production results. `--steps` bounds the
rounds (1–10); `--budget` bounds candidates per round (1–500). A
`candidate_budget` stop does not prove a local optimum. Each trial recomputes
graph features, so larger budgets and graphs can be expensive.
For each selected candidate, output includes the circular-group rule, the
unit's probability before the round, and the number of earlier observations.
An untrained unit starts at 0.5; its output is not calibrated confidence.

Learning is in memory by default. To continue it across runs, pass a previous
model with `--model-in <file>` and explicitly create a **new** file with
`--model-out <new-file>`; existing files are never overwritten. The model
stores weights and bounded hashes of observed graph/candidate pairs to avoid
counting identical recent feedback twice. Hashes can still be correlated with
known graphs and should be treated as private. This heuristic does not establish
improved pattern recognition or continuous learning from real-world outcomes.

## Lua graph API

`tools/topology_graph.lua` provides the same graph features to Lua. It has been
tested with Lua 5.4 and 5.5 via Lupa.
It takes dense arrays of module-name strings and directed two-element edges;
duplicate vertices and edges are collapsed. It does not scan files or execute
source code. For example, from the repository root:

```lua
local topology = require("tools.topology_graph")
local result = topology.analyze({"a", "b"}, {{"a", "b"}, {"b", "a"}})
print(result.h0_essential)
```

The Lua API is independent of the Python command and is not integrated into
Fenrir's runtime. To run the optional Python/Lua comparison tests, install
`pytest` and `lupa`, then run `python -m pytest -q tests\test_topology_graph_lua.py`.
