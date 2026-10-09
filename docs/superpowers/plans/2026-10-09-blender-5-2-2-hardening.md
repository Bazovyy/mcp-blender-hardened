# Blender 5.2.2 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden RFingAdam/mcp-blender PR #42 into a safe, testable Blender 5.2.2-only fork suitable for continuous local automation.

**Architecture:** Preserve the existing 229+ tool surface, but replace unsafe transport/runtime behavior with queued dispatch, explicit state guards, safer transactions, deterministic job handling, strict validation, and Blender-5.2-native APIs. Context-heavy and crash-prone tools are qualified in isolated Blender processes.

**Tech Stack:** Python 3.12, Blender 5.2.2 LTS Python API, asyncio, TCP JSON-RPC, pytest, Blender background subprocess tests.

**Spec:** `docs/superpowers/specs/2026-10-09-blender-5-2-2-hardening-design.md`

## Global Constraints

- Guaranteed Blender target is **Blender 5.2.2 LTS only**.
- Start from PR #42 base plus design commit on branch `hardening/blender-5.2.2`.
- Port 9877 remains the hardened fork default during migration; existing custom bridge may keep 9876.
- Every production fix follows RED -> GREEN -> subsystem suite -> full available suite.
- Blender API mutations remain on Blender main thread.
- No non-equivalent semantic fallback may report success.
- Unrestricted Python execution is disabled by default.
- Temporary screenshot/render TTL is 600 seconds; explicit user output paths are never TTL-cleaned.
- Existing user files are not overwritten without explicit opt-in.
- Native Blender crashes count as test failures and must be isolated per risky tool.

## Review Focus

1. Disconnect while requests are pending must fail every waiter exactly once without self-await or leaked tasks.
2. A timed-out client request must not later produce an unreported mutation without a job/operation identity.
3. State restoration must survive handler exceptions and restore selection/mode/render settings.
4. Context-heavy operators must fail safely when no valid VIEW_3D context exists rather than crash or substitute another operation.
5. Temp cleanup must never delete explicit user paths and must enforce 600-second TTL only inside bridge-owned roots.

---

### Task 1: Qualification Harness and Tool Manifest

**Files:**
- Create: `tests/qualification/test_tool_manifest.py`
- Create: `tests/qualification/tool_manifest.py`
- Create: `tests/qualification/run_blender_case.py`
- Modify: `tests/blender_integration_test.py`

**Interfaces:**
- Produces `ToolCase(name, risk, payload_factory, fixture_factory, assert_result, cleanup)` records.
- Produces `run_blender_case(case_name: str) -> subprocess.CompletedProcess` for one-tool-per-process execution.

- [ ] Write failing tests proving every MCP tool maps to exactly one manifest entry or an explicit external-service skip.
- [ ] Run `pytest tests/qualification/test_tool_manifest.py -v`; expect RED for missing manifest coverage.
- [ ] Implement manifest generation from `src/mcp_blender/server.py` plus explicit fixture overrides for nontrivial tools.
- [ ] Add isolated Blender runner that treats nonzero/native-crash exit as failed qualification.
- [ ] Run targeted qualification tests GREEN, then `pytest tests -q` and commit `test: add per-tool qualification harness`.

### Task 2: Async Client Disconnect and Timeout Correctness

**Files:**
- Modify: `src/mcp_blender/blender_client.py`
- Modify: `tests/test_client.py`

**Interfaces:**
- `BlenderClient.disconnect(*, from_reader: bool = False) -> None` or equivalent internal split that never awaits the current reader task.
- Pending futures terminate exactly once with `BlenderConnectionError`.

- [ ] Add regression tests for remote EOF inside `_read_loop`, explicit disconnect, pending requests, and reconnect after EOF.
- [ ] Verify RED reproduces `Task cannot await on itself` or leaked pending futures.
- [ ] Split reader-shutdown from public disconnect so the reader never cancels/awaits itself.
- [ ] Ensure timeout removes only its own request and late responses are logged/ignored deterministically.
- [ ] Run `pytest tests/test_client.py -v`, then full `pytest tests -q`; commit `fix: harden Blender client disconnect lifecycle`.

### Task 3: Socket Transport, Request Queue, and Main-Thread Dispatcher

**Files:**
- Create: `addon/blender_mcp_addon/runtime.py`
- Modify: `addon/blender_mcp_addon/socket_server.py`
- Modify: `addon/blender_mcp_addon/__init__.py`
- Create: `tests/test_socket_runtime.py`

**Interfaces:**
- `RequestEnvelope(id, method, params, client)` stores parsed work without executing handlers in socket receive code.
- `MainThreadDispatcher.enqueue(envelope)` and `tick(max_items: int, time_budget_ms: float)` execute bounded work on Blender's main thread.
- Per-client output buffers support partial nonblocking writes.

- [ ] Add RED tests proving `_process_clients` only parses/enqueues, request buffers reject oversized frames, and nonblocking writes survive short sends.
- [ ] Add RED test that `start()` failure propagates to the Blender operator instead of reporting success.
- [ ] Implement queue/dispatcher split, bounded receive/request buffers and partial nonblocking writes; default bind stays 127.0.0.1 and non-loopback requires explicit unsafe/developer opt-in.
- [ ] Store the exact timer callback reference used for register/unregister; add deferred restart after current dispatch cycle.
- [ ] Run socket/runtime tests, Blender start-stop smoke test on port 9877, full unit suite; commit `refactor: queue Blender requests through dispatcher`.

### Task 4: State Guard and Transaction Boundary

**Files:**
- Create: `addon/blender_mcp_addon/state_guard.py`
- Create: `addon/blender_mcp_addon/transactions.py`
- Modify: `addon/blender_mcp_addon/handlers/__init__.py`
- Create: `tests/test_state_guard.py`
- Create: `tests/blender_state_guard_test.py`

**Interfaces:**
- `BlenderStateSnapshot.capture()` records active object, selection, mode, frame, camera, render settings and touched tool settings.
- `BlenderStateGuard(restore=True)` restores state in `__exit__`, including handler exceptions.
- `OperationTransaction` records operation id, risk class, checkpoint strategy, result state and reacquisition boundary.

- [ ] Write RED pure tests for snapshot/restore orchestration and exception paths.
- [ ] Write RED Blender subprocess test mutating selection, mode, render filepath/format and camera before raising.
- [ ] Implement state guard with data API first and guarded operators only where mode restoration requires them.
- [ ] Add transaction metadata and forbid implicit global undo as generic rollback.
- [ ] Verify Blender test restores state byte-for-byte for covered settings; run regression suites and commit `feat: add Blender state guards and transactions`.

### Task 5: Validation, Error Contract, and Safe Script Fallback

**Files:**
- Modify: `addon/blender_mcp_addon/validation.py`
- Create: `addon/blender_mcp_addon/result.py`
- Create: `addon/blender_mcp_addon/restricted_exec.py`
- Modify: `addon/blender_mcp_addon/handlers/ai.py`
- Modify: `addon/blender_mcp_addon/handlers/__init__.py`
- Modify: `src/mcp_blender/server.py`
- Create: `tests/test_validation_hardening.py`
- Create: `tests/test_restricted_exec.py`

**Interfaces:**
- Numeric validators reject bool, NaN and Inf.
- `ok(result)` / `fail(code, message, details=None)` define the Blender-side envelope.
- `execute_restricted(script: str, bpy_api) -> dict` accepts only the approved AST subset.

- [ ] Add RED tests for bool-as-int, NaN/Inf vectors/colors, malformed lengths and invalid conditional payloads.
- [ ] Add RED security tests rejecting imports, filesystem/process/network access, dunder traversal and dangerous save/load/restart calls.
- [ ] Implement strict validators and normalized result/error envelope without changing documented successful payload data unnecessarily.
- [ ] Replace unrestricted default `exec`; keep any raw mode behind an explicit disabled-by-default developer preference.
- [ ] Update MCP wrapper to mark failed envelopes as MCP `isError=True`; run targeted and full suites; commit `security: harden validation and script execution`.

### Task 6: Blender 5.2 Core Modeling Compatibility

**Files:**
- Modify: `addon/blender_mcp_addon/handlers/mesh_editing.py`
- Modify: `addon/blender_mcp_addon/handlers/text_objects.py`
- Modify: `src/mcp_blender/server.py`
- Add cases to: `tests/qualification/tool_manifest.py`
- Create: `tests/blender_mesh_52_test.py`

**Interfaces:**
- Boolean solver schema and handlers accept `FLOAT`, `EXACT`, `MANIFOLD`; obsolete `FAST` is rejected.
- Edge loop/slide implementations use Blender 5.2-supported APIs.
- Knife Project has no Boolean INTERSECT fallback; lack of valid context returns explicit failure.

- [ ] Write RED isolated Blender cases for Boolean `FLOAT`, edge loop selection, edge slide `use_even`, loop cut and knife-project-without-context.
- [ ] Confirm existing loop-cut case can crash/fail only in its isolated process, never the whole qualification run.
- [ ] Replace removed/renamed APIs; prefer bmesh traversal for loop operations and explicit context override when an operator is unavoidable.
- [ ] Remove semantic Boolean fallback from knife project and return a stable context-required error.
- [ ] Run all mesh qualification cases one-per-process, existing 42 integration tests, full unit suite; commit `fix: migrate modeling tools to Blender 5.2`.

### Task 7: Geometry Nodes 5.2 Migration

**Files:**
- Create: `addon/blender_mcp_addon/geonodes_52.py`
- Modify: `addon/blender_mcp_addon/handlers/_helpers.py`
- Modify: `addon/blender_mcp_addon/handlers/geonodes.py`
- Create: `tests/blender_geonodes_52_test.py`

**Interfaces:**
- `iter_interface_sockets(group, in_out)` resolves group interface sockets by identifier/name.
- `get_modifier_input(modifier, identifier)` and `set_modifier_input(modifier, identifier, value)` use Blender 5.2 modifier-properties API.
- Node socket lookup is name/identifier/type based, not fragile numeric indexing.

- [ ] Add RED Blender tests for `geonode_apply`, `geonode_inspect`, scatter random scale, aligned random rotation, all array modes, deform and extrude profile.
- [ ] Implement typed 5.2 GN helpers and migrate apply/inspect first.
- [ ] Replace Random Value numeric socket assumptions and read-only Rotate Euler mutation.
- [ ] Assert evaluated geometry/node warnings where meaningful, not merely handler `success`.
- [ ] Run GN subprocess suite plus full regressions; commit `fix: migrate Geometry Nodes tools to Blender 5.2`.

### Task 8: Annotation, Grease Pencil, Compositor, and Render 5.2

**Files:**
- Modify: `addon/blender_mcp_addon/handlers/annotations.py`
- Modify: `addon/blender_mcp_addon/handlers/_helpers.py`
- Modify: `addon/blender_mcp_addon/handlers/render.py`
- Modify: `addon/blender_mcp_addon/handlers/ai.py`
- Modify: `src/mcp_blender/server.py`
- Create: `tests/blender_annotations_52_test.py`
- Create: `tests/blender_render_state_test.py`

**Interfaces:**
- Annotation tools use Blender 5.2 `Scene.annotation`/current Grease Pencil data APIs.
- Compositor fallback uses Blender 5.x compositor node-group API; no `scene.node_tree` dependency.
- All EEVEE paths normalize to `BLENDER_EEVEE`.

- [ ] Add RED tests for annotation add/clear, GP create, markup fallback without Pillow, direct invalid `BLENDER_EEVEE_NEXT`, and AI control render.
- [ ] Migrate annotation/GP/compositor code to 5.2-native APIs and remove stale enum from schemas.
- [ ] Add render-state restoration test for filepath, format, engine, camera and viewport shading after success and exception.
- [ ] Implement state restoration through Task 4 guard rather than per-handler ad hoc cleanup.
- [ ] Run annotation/render/AI-local tests and full regressions; commit `fix: migrate annotation and render paths to Blender 5.2`.

### Task 9: Sculpt, Physics, and Context-Heavy Safety

**Files:**
- Modify: `addon/blender_mcp_addon/handlers/sculpt.py`
- Modify: `addon/blender_mcp_addon/handlers/physics.py`
- Create: `addon/blender_mcp_addon/context.py`
- Create: `tests/blender_context_heavy_test.py`

**Interfaces:**
- `find_view3d_context()` returns a complete window/area/region override or `None`.
- Context-heavy tools return a stable unsupported/context-required error instead of invoking unsafe operators.

- [ ] Add isolated RED cases for sculpt mesh filter, mask ALL/RANDOM, extract mask, face-set LINKED, voxel remesh and physics bake cancellation boundaries.
- [ ] Confirm native crashes are captured as subprocess failures before modifying production code.
- [ ] Migrate removed sculpt data/enums (`vertex_paint_mask`, face-set modes) and gate operators requiring unavailable GUI context.
- [ ] Convert long synchronous physics bake into submitted job/staged polling where cancellation is possible; otherwise expose explicit blocking-risk classification.
- [ ] Run each context-heavy case in a fresh Blender process and full regressions; commit `fix: isolate context-heavy Blender operations`.

### Task 10: Generic Job Model and Long-Running Operations

**Files:**
- Create: `addon/blender_mcp_addon/jobs.py`
- Modify: `addon/blender_mcp_addon/external/job_queue.py`
- Modify: `addon/blender_mcp_addon/handlers/ai.py`
- Modify: `addon/blender_mcp_addon/handlers/baking.py`
- Modify: `addon/blender_mcp_addon/handlers/physics.py`
- Modify: `src/mcp_blender/server.py`
- Create: `tests/test_jobs.py`

**Interfaces:**
- `submit_job(kind, stepper, metadata) -> job_id`, `get_job(job_id)`, `cancel_job(job_id)`.
- Job steppers perform bounded work per dispatcher tick and never sleep in Blender main-thread callbacks.
- Terminal states: `completed`, `failed`, `cancelled`, `timeout`.

- [ ] Add RED tests proving no job step calls `time.sleep`, a single tick obeys the work budget, cancellation reaches a terminal state, and status survives client timeout.
- [ ] Generalize existing AI GenerationJob persistence only where useful; keep Blender runtime job state separate from provider history when responsibilities differ.
- [ ] Replace synchronous AI polling loops with staged job polling and migrate eligible bake/physics operations.
- [ ] Add MCP job submit/status/cancel schemas and deterministic error propagation.
- [ ] Run job tests plus local AI contract tests/full suite; commit `feat: add nonblocking Blender job runtime`.

### Task 11: Temporary Asset Manager and Screenshot Lifecycle

**Files:**
- Create: `addon/blender_mcp_addon/temp_assets.py`
- Modify: `addon/blender_mcp_addon/handlers/render.py`
- Modify: `addon/blender_mcp_addon/handlers/ai.py`
- Modify: `addon/blender_mcp_addon/__init__.py`
- Create: `tests/test_temp_assets.py`
- Create: `tests/blender_screenshot_test.py`

**Interfaces:**
- `TempAssetManager(root, ttl_seconds=600, max_bytes=1_073_741_824)` owns only bridge-created paths.
- `register(path, *, user_owned=False)`, `cleanup_expired(now=None)`, `enforce_cap()` never delete `user_owned=True` paths.

- [ ] Add RED clock-controlled tests for 599/600/601 second boundaries, 1 GiB cap eviction and explicit-output protection.
- [ ] Add Blender screenshot RED test asserting a valid nontrivial image and cleanup registration.
- [ ] Implement bridge-owned session roots, startup cleanup, post-create cleanup and periodic lightweight cleanup timer.
- [ ] Route temporary render/AI artifacts through the manager while preserving explicit output paths.
- [ ] Run temp/screenshot tests and regressions; commit `feat: manage temporary Blender assets safely`.

### Task 12: File Operations and State-Preserving Export/Render

**Files:**
- Modify: `addon/blender_mcp_addon/handlers/export_import.py`
- Modify: `addon/blender_mcp_addon/handlers/scene.py`
- Modify: `addon/blender_mcp_addon/handlers/render.py`
- Modify: `src/mcp_blender/server.py`
- Create: `tests/blender_file_policy_test.py`

**Interfaces:**
- Explicit output operations accept `overwrite: bool = False`.
- Existing destination with overwrite disabled returns `file_exists` without mutation.

- [ ] Add RED tests for existing-file refusal, overwrite opt-in, normalized resolved path reporting and render/export state restoration.
- [ ] Implement shared output-path validation and use Task 4 state guard around temporary render/export changes.
- [ ] Re-run GLB/FBX/OBJ/STL/USD roundtrips under the new policy.
- [ ] Verify no bridge-owned cleanup touches explicit outputs.
- [ ] Run I/O suite plus regressions; commit `fix: make Blender file outputs explicit and state-safe`.

### Task 13: Schema Contract, Rotation Units, and Remaining 5.2 API Sweep

**Files:**
- Modify: `src/mcp_blender/server.py`
- Modify: `src/mcp_blender/types.py`
- Modify: `addon/blender_mcp_addon/compat.py`
- Modify: `addon/blender_mcp_addon/msfs/animation.py`
- Modify: `addon/blender_mcp_addon/msfs/livery/painting.py`
- Modify affected handlers discovered by sweep.
- Modify: `tests/test_tools.py`
- Modify: `tests/test_handler_signatures.py`

**Interfaces:**
- Schemas use exact `minItems/maxItems`, integer types, supported enums and conditional requirements.
- Rotation-bearing tools expose explicit units; no magnitude heuristic guesses degrees vs radians.

- [ ] Add RED schema tests for vector lengths, conditional mode/preset requirements, obsolete 5.x enums and explicit rotation units.
- [ ] Add RED Blender cases for MSFS Action access and livery brush falloff property.
- [ ] Sweep source for audited stale APIs (`BLENDER_EEVEE_NEXT`, `scene.grease_pencil`, `scene.node_tree`, `action.fcurves`, `curve_preset`, `FAST`, removed operators) and make each remaining occurrence intentional/tested or remove it.
- [ ] Update schemas and handlers together so advertised values are executable on Blender 5.2.2.
- [ ] Run schema/signature/unit and targeted Blender tests; commit `fix: align MCP schemas with Blender 5.2.2`.

### Task 14: Packaging, Versioning, and Release Identity

**Files:**
- Modify: `pyproject.toml`
- Modify: `addon/blender_mcp_addon/__init__.py`
- Modify: `scripts/package_addon.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create or modify: `tests/test_version_consistency.py`

**Interfaces:**
- A single version source drives Python package metadata, addon metadata, logs and ZIP filename.
- README installation instructions use the hardened source/package path and port 9877 migration default.

- [ ] Add RED test that detects the current 0.2.0/0.3.0/0.4.0 mismatch.
- [ ] Introduce one version source and consume it from packaging/addon metadata without circular imports.
- [ ] Build addon ZIP and assert its version/name matches Python package identity.
- [ ] Update docs with Blender 5.2.2-only support and security/job behavior.
- [ ] Run package build plus unit suite; commit `build: unify hardened fork versioning`.

### Task 15: Full Tool Qualification and Release Gate

**Files:**
- Complete: `tests/qualification/tool_manifest.py`
- Modify: `tests/qualification/test_tool_manifest.py`
- Modify: `tests/blender_integration_test.py`
- Create: `docs/qualification/blender-5.2.2.md`

**Interfaces:**
- Every registered MCP tool has one qualification status: `PASS`, `FAIL`, or `SKIP_EXTERNAL(reason)`.
- No native crash, timeout, leaked Blender process or missing cleanup can be recorded as PASS.

- [ ] Fill minimum valid fixtures for the complete registered tool set and assert zero unclassified tools.
- [ ] Run safe/read tools in grouped deterministic scenes and every context-heavy/high-risk tool in an isolated Blender 5.2.2 process.
- [ ] Run negative validation/error-contract cases for destructive/file/context-heavy families.
- [ ] Record external provider tests separately; missing credentials/services are explicit skips, never PASS.
- [ ] Run fresh final verification: full pytest, 42+ baseline Blender integration, complete qualification harness, package build, and `git diff --check`.
- [ ] Generate qualification report with exact counts and known external skips; commit `test: qualify hardened tool surface on Blender 5.2.2`.

## Execution Order and Stop Rules

Tasks execute in order because Tasks 3-5 provide infrastructure consumed by later compatibility fixes. Within a task, do not batch unrelated fixes: each audited bug gets a RED reproduction before its production change.

If three attempted fixes for one failure expose new shared-state failures, stop that task and re-evaluate the responsible architecture instead of adding a fourth patch. Never test a known native-crash reproduction inside the user's live Blender scene; use a fresh subprocess fixture.

After each commit, require a clean targeted suite. At phase boundaries (Tasks 5, 10, 14, 15), run the complete available unit suite plus the baseline Blender integration suite. Do not claim the fork ready until Task 15 reports the entire local tool surface and all Definition-of-Done conditions from the spec are met.
