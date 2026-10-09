# Blender 5.2.2 Hardening Design

## Status

Approved conversational design for implementation planning.

## Goal

Turn RFingAdam/mcp-blender PR #42 (`ba50391438f45d9a6055fc70366b3781f653c178`) into a hardened local Blender automation fork that can be trusted against a real Blender 5.2.2 LTS scene without known native-crash paths, unsafe semantic fallbacks, unbounded main-thread stalls, or unrestricted script execution by default.

## Supported Runtime

- Guaranteed Blender target: **Blender 5.2.2 LTS only**.
- Python-side MCP server: Python 3.12 on Windows for the primary supported environment.
- Older Blender versions may continue to work incidentally, but they are not compatibility requirements and must not constrain the 5.2.2 design.
- The fork starts from PR #42 rather than release v0.4.0 or current upstream `main` because PR #42 already fixes the known `validate_enum` family and passes the strongest existing 5.2.2 integration suite.

## Design Principles

1. Preserve useful existing tools; replace unsafe infrastructure rather than rewrite the project from zero.
2. Blender API access stays on Blender's main thread.
3. Socket/network work must never execute Blender mutations directly.
4. A tool must either perform the documented operation or fail explicitly; non-equivalent semantic fallbacks are forbidden.
5. Every bug fix begins with a regression test that fails before the production change.
6. Native-crash-prone tools are tested in isolated Blender processes.
7. User-owned files and explicit output paths are never treated as disposable temporary assets.

## Runtime Architecture

The runtime is split into four responsibilities:

```text
MCP stdio server
    -> TCP client
    -> Blender socket transport
    -> request queue
    -> main-thread dispatcher
    -> handler / job stage
    -> response queue
    -> TCP client
    -> MCP result
```

The socket layer only parses framed JSON, validates the request envelope, assigns request IDs, enqueues work, and sends completed responses. It does not invoke handlers directly.

The main-thread dispatcher is driven by a stable `bpy.app.timers` callback reference. Each tick performs bounded bookkeeping and at most a bounded unit of Blender work. A handler is not allowed to spin, sleep, poll remote services, or wait for external I/O inside the timer callback.

External HTTP polling, provider requests, filesystem preparation, and subprocess waiting run outside Blender's main thread. Their Blender-facing stages are returned to the main-thread dispatcher as short jobs.

Operations for which Blender exposes no safe non-blocking interactive path are classified explicitly as `blocking`. They are not disguised as cancellable asynchronous jobs. A blocking command may be disabled in live interactive mode until a safe implementation exists, or moved to an isolated background-Blender workflow when that preserves the requested semantics.

## Job Model

Long-running workflows use explicit job state rather than holding an MCP request open for minutes.

```text
submit -> job_id
status(job_id) -> queued | running | completed | failed | cancelled
cancel(job_id) -> accepted | unsupported | already_finished
```

Cancellation is honest: `cancelled` is reported only when the underlying work has actually stopped or has not started. If Blender has entered an operation that cannot be pre-empted safely, the job reports `cancellable=false` and cancellation does not lie about completion.

MCP request timeouts only bound client waiting. They never imply that a Blender mutation was cancelled. Timed-out request IDs remain tracked until the Blender-side operation reaches a terminal state, so a late mutation cannot become invisible.

## Transaction and Recovery Model

Global `bpy.ops.ed.undo()` is not the primary rollback mechanism.

Three recovery tiers are used:

1. **Context restore** for active object, selection, mode, frame, render settings, camera, shading, and tool settings.
2. **Local data rollback** for bounded mutations whose previous values/data can be copied safely.
3. **Recovery checkpoint** for high-risk destructive operations where a `.blend` checkpoint is materially safer than attempting ad-hoc inverse operations.

Any code path that performs Blender undo, file reload, or other operation capable of invalidating Blender `ID` references must discard cached `bpy.types.ID` objects and reacquire them by stable identifiers before further access.

A native Blender process crash cannot be rolled back in-process. High-risk tools therefore require isolated regression coverage before they are allowed in live mode, and recovery checkpoints are created before destructive live operations when the cost is justified.

## State Guard

A shared state guard surrounds handlers that touch Blender context. It snapshots only state the operation can affect and restores it in `finally` unless the tool contract explicitly says the state change is persistent.

The guard can cover:

- active object and selected objects;
- current mode (`OBJECT`, `EDIT`, `SCULPT`, etc.);
- current frame;
- render engine, filepath, image format, resolution where relevant;
- active scene camera;
- viewport shading when a viewport operation changes it;
- tool settings/select mode where an operator requires them.

Restoration failures are surfaced as part of the tool error rather than silently swallowed.

## Blender Operators and Context

Preferred implementation order is:

1. direct Blender Data API / RNA;
2. `bmesh` for mesh topology operations;
3. `bpy.ops` with a verified explicit context override;
4. ordinary context-sensitive `bpy.ops` only when no safer equivalent exists.

A context-sensitive operator must verify its required area/region/mode before invocation. Missing `VIEW_3D` context produces a structured `unsupported_in_current_context` error rather than an unrelated fallback.

`knife_project` must never fall back to Boolean INTERSECT. Similar fallbacks elsewhere are audited under the same rule: fallback behavior must preserve operation semantics, not merely return some geometry.

## Blender 5.2.2 API Policy

The fork targets the actual Blender 5.2.2 API directly. Compatibility wrappers remain only when they simplify the code and do not preserve obsolete behavior.

Known required migrations include Boolean solver enums, EEVEE engine naming, Geometry Nodes modifier properties, compositor access, annotations/Grease Pencil, Actions/F-curves, sculpt mask APIs, brush falloff properties, mesh loop selection, and transform operator parameter names.

## Geometry Nodes

Geometry Nodes gets a focused Blender-5.2 helper layer instead of scattered version checks.

The helper layer is responsible for:

- enumerating group interface sockets;
- resolving sockets by stable identifier/name rather than fragile numeric position;
- reading and writing modifier inputs through the Blender 5.2 modifier-properties API;
- typed assignment for float, int, bool, vector, object, material, collection, image, and string inputs;
- returning a structured error when a socket cannot be resolved or assigned.

The known `geonode_apply` and `geonode_inspect` failures are regression targets. `scatter_instances` must also cover random-scale and both random-rotation branches, not only the default path.

## Sculpt and Other Context-Heavy Tools

Sculpt is treated as a high-risk subsystem because multiple valid-looking calls produced native `EXCEPTION_ACCESS_VIOLATION` during isolated Blender 5.2.2 testing.

Every sculpt tool must be classified as one of:

- safe with Data API / deterministic operator context;
- GUI-context dependent and covered by an explicit `VIEW_3D` test;
- unsupported for automated live use in 5.2.2.

A tool remains unavailable in live mode until its isolated subprocess test proves it does not crash Blender for its minimum valid fixture. Python exceptions are acceptable test failures; process termination is not.

The same risk policy applies to bake, physics cache, save/load, undo/reload, and other operations capable of blocking or invalidating large portions of scene state.

## Script Execution Security

Typed tools are the primary interface. The current unrestricted `exec(script, {"bpy": bpy, "__builtins__": __builtins__})` path is not permitted in the default production profile.

The default fallback script tool uses AST validation and a deliberately narrow namespace. It rejects at minimum:

- imports and dynamic import mechanisms;
- filesystem, process, shell, registry, and network access;
- dunder traversal and reflection paths that escape the intended namespace;
- save/load/restart and destructive global Blender operations not explicitly allowlisted;
- arbitrary deletion of datablocks/scene data outside the restricted operation contract.

A raw unrestricted Python mode may exist only as an explicitly enabled developer feature, disabled by default and clearly separated from the normal MCP tool surface.

## Transport Hardening

Default binding is loopback only (`127.0.0.1`). During migration the fork defaults to port **9877** so it can coexist with the existing custom bridge on 9876; the port remains configurable. Binding to a non-loopback interface requires an explicit unsafe/developer opt-in.

The transport must provide:

- bounded request size and bounded per-client receive buffers;
- newline framing that cannot grow memory indefinitely on malformed clients;
- queued/partial writes for non-blocking sockets rather than assuming `sendall()` behaves like a blocking socket;
- deterministic failure of all pending requests on disconnect;
- no reader-task self-await during disconnect;
- deferred server restart after the current request/tick completes;
- a stable timer callback object used for register/is_registered/unregister;
- truthful Start/Stop UI results when bind/listen fails.

Loopback-only operation is the security boundary for the normal local profile, so an authentication token is not required for that profile. Non-loopback mode, if retained, must require a separate explicit security design before it is considered supported.

## Temporary Assets and Screenshots

Bridge-owned temporary assets live under a dedicated session root:

```text
%TEMP%\mcp-blender\<session-id>\
```

Every temporary file created without an explicit user output path is registered with ownership metadata and creation time.

Viewport/render preview TTL is **600 seconds (10 minutes)**.

Cleanup runs:

- when the add-on starts;
- after a new temporary asset is registered;
- from a lightweight periodic timer;
- during orderly add-on/server shutdown.

Cleanup operates only inside bridge-owned temp roots and never deletes a path explicitly supplied by the user. The bridge-owned temp root has a **1 GiB hard cap**. Expired assets are reclaimed first; if the root is still above the cap, the oldest non-active bridge-owned temporary assets are evicted. If no safe eviction candidate exists, allocation of a new temporary asset fails explicitly instead of touching user files or active-job files.

Viewport capture must validate that the generated image is decodable and has non-trivial dimensions/size before returning success. A tiny or invalid file is an error, not a successful screenshot.

## Tool Result Contract

All tool handlers converge on one logical result model:

```json
{"ok": true, "result": {}}
```

or

```json
{"ok": false, "error": {"code": "...", "message": "...", "details": {}}}
```

Handlers do not mix `{"error": ...}`, `{"success": false}`, thrown exceptions, and successful MCP envelopes arbitrarily. The MCP layer maps a logical tool failure to `isError=true` while preserving structured error details.

## Schema and Validation Policy

JSON schemas must express the actual Blender 5.2.2 contract rather than merely document it.

Required changes include:

- exact `minItems`/`maxItems` for vectors, colors, dimensions, and resolutions;
- integer schemas for indices/counts where fractional values are invalid;
- conditional requirements (`oneOf`, `if/then`) for mode/preset-dependent arguments;
- rejection of booleans where numeric values are expected;
- rejection of NaN and infinity at the Python validation boundary;
- explicit angle units instead of magnitude-based degree/radian guessing;
- enums containing only values accepted by Blender 5.2.2;
- range validation where Blender has a meaningful bounded domain.

Validation occurs before mutation. A payload rejected by schema/validation must not alter selection, mode, object data, files, or render settings.

## File Operations

Save/export/import operations distinguish user files from temporary files.

- `overwrite=false` is the default for explicit output files.
- Existing user files require an explicit overwrite opt-in before replacement.
- Paths are normalized before use and error messages return the resolved target.
- Parent directory creation is explicit in the tool contract rather than an accidental side effect.
- Temporary intermediate files use the bridge temp manager.
- TTL cleanup never touches explicit user output paths.

Save/load operations are classified as high risk because they may invalidate Blender IDs and global context. They must use the transaction/reacquisition rules and isolated tests.

## State-Preserving Render and Analysis

Temporary renders and multi-angle analysis restore every setting they modify, including render engine, resolution, percentage, filepath, file format, active camera, and viewport shading properties. Temporary cameras, images, node groups, and materials created solely for analysis are removed unless the tool contract says they are outputs.

## Test Architecture

The existing unit suite and PR #42 Blender integration suite remain regression baselines, but they are not sufficient coverage for the complete tool surface.

A generated tool manifest records for every registered MCP tool:

- MCP name and schema;
- Blender handler mapping;
- risk class (`read`, `bounded_mutation`, `context_heavy`, `blocking`, `external`);
- minimum valid fixture/payload;
- expected observable result;
- required cleanup and state-restoration assertions;
- whether external credentials/services are required.

The qualification harness launches Blender 5.2.2 with deterministic fixtures. Risky tools run one per fresh Blender process so a native crash is reported as a failed test rather than terminating the remainder of the suite.

For each production bug fixed during hardening, TDD requires:

1. write the smallest regression test reproducing the failure;
2. run it and confirm the expected RED failure;
3. implement the minimal fix;
4. run the targeted test GREEN;
5. run the relevant subsystem tests;
6. run the full available suite before completing that task.

Native process exit, timeout, leaked process, corrupted output, or missing cleanup is a test failure.

## External Integrations

Cloud/local AI providers are not considered end-to-end verified when credentials or the provider are unavailable. Their status is reported separately:

- local contract/serialization test;
- mocked protocol test only where unavoidable;
- live provider E2E PASS, FAIL, or SKIPPED with an explicit reason.

A skipped provider is never counted as a successful E2E test.

## Mandatory Regression Targets from the Audit

The implementation plan must include explicit tests for the already reproduced failures:

- socket client disconnect self-await;
- non-blocking socket response buffering;
- timer callback registration identity;
- bind failure falsely reported as server started;
- `mesh_loop_cut` native crash path;
- `mesh_select_edge_loops` removed operator;
- `mesh_edge_slide` obsolete `even` argument;
- Boolean `FAST` enum on Blender 5.2.2;
- EEVEE schema/AI hardcoded `BLENDER_EEVEE_NEXT`;
- `geonode_apply` and `geonode_inspect` old modifier IDProperty access;
- Geometry Nodes scatter random-scale socket indexing;
- Geometry Nodes scatter aligned random rotation read-only property;
- annotation add/clear old `Scene.grease_pencil` access;
- Grease Pencil create old layer/stroke API;
- markup fallback old `Scene.node_tree` compositor API;
- sculpt random mask old `vertex_paint_masks` API;
- sculpt face-set obsolete enums;
- sculpt mesh-filter/mask/extract native crash paths;
- MSFS direct legacy `action.fcurves` access;
- MSFS livery `brush.curve_preset` access;
- non-equivalent Knife Project -> Boolean INTERSECT fallback;
- render multi-angle state leaks;
- invalid/trivial viewport screenshot accepted as success;
- unrestricted script execution in the default profile;
- bool/NaN/Inf numeric validation gaps;
- version mismatch between package/add-on/log/release artifact.

These are minimum known regressions, not the complete qualification surface.

## Implementation Phases

The repair is intentionally staged so each layer can be reviewed and verified independently:

1. **Qualification harness** — generated tool manifest, isolated Blender runner, crash/time-out accounting.
2. **Transport/dispatcher** — request queue, bounded timer work, correct socket lifecycle and response buffering.
3. **Transactions/state guard** — context restoration, ID reacquisition rules, local rollback/checkpoint policy.
4. **Validation/security** — normalized result contract, finite-number validation, restricted scripting, loopback policy.
5. **Core Blender 5.2 modeling** — enums, mesh operators, context-safe replacements, semantic fallback removal.
6. **Geometry Nodes 5.2** — modifier-property API and stable socket helpers.
7. **Annotations/Grease Pencil/compositor** — migrate to Blender 5.2 APIs and verify output.
8. **Sculpt/physics/context-heavy tools** — per-tool safety classification and isolated qualification.
9. **Temporary assets/screenshots** — session temp manager, 600-second TTL, image validation and cleanup.
10. **Schemas/error contract/files** — conditional schemas, path/overwrite semantics, uniform MCP failures.
11. **Packaging/versioning** — single version source, matching add-on/package/build artifact and install docs.
12. **Full qualification** — map and exercise the entire registered tool surface with explicit PASS/FAIL/SKIP accounting.

Each phase uses small commits. A phase is not declared complete merely because its targeted tests pass; the full available regression suite must also run before completion of that phase.

## Packaging and Version Source

Package version, Blender `bl_info`/extension metadata, runtime log version, and generated artifact name derive from one canonical version source. Building from a 0.4.x source tree must not produce a misleading `blender_mcp_addon-0.3.0.zip`.

The source-install and packaged-install paths must install matching server/add-on protocol versions. Startup reports both protocol version and Blender target so version mismatches can be diagnosed without inspecting files manually.

## Definition of Done

The hardening fork is complete only when all of the following are true for the supported local Blender 5.2.2 profile:

- every registered MCP tool maps to a known handler or an intentionally unsupported capability;
- schemas validate against their minimum fixtures;
- every locally testable tool has at least one minimum invocation in the qualification manifest;
- no known minimum valid fixture causes an unexpected Blender native crash;
- all known Blender 5.2 API regressions from the audit have regression tests;
- no known stale-ID undo/reload path remains;
- default script execution is restricted;
- loopback transport disconnect/reconnect and pending-request cleanup pass;
- state guard tests show no unintended selection/mode/render/camera leaks;
- temporary screenshot/render cleanup passes the 600-second TTL rules;
- explicit user output files are never removed by temp cleanup;
- package/add-on/runtime versions agree;
- unit suite, existing Blender integration suite, new hardening tests, and tool qualification report have been run freshly with no unreported failures.

External provider tools may be `SKIPPED` only when the report names the missing service/credential and their local contract tests pass.

## Non-Goals

- Guaranteed compatibility with Blender 4.2, 5.0, or future Blender versions.
- Exposing the normal MCP listener to LAN/WAN clients.
- Making every fundamentally blocking Blender operator magically cancellable.
- Replacing Blender's renderer, physics engine, Geometry Nodes, or sculpt systems.
- Rewriting all existing 229+ tools when a proven 5.2-compatible implementation already works.
- Preserving undocumented quirks of the upstream project when they conflict with safe, deterministic Blender 5.2.2 behavior.

## Delivery Boundary

This design produces a hardened local fork and its tests. Upstream PR submission, publication to PyPI, and merging back to RFingAdam/mcp-blender are separate decisions after the local fork is qualified.
