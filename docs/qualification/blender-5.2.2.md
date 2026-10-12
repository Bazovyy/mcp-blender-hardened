# Blender 5.2.2 Qualification Report

**Fork version:** 0.5.0  
**Guaranteed target:** Blender 5.2.2 LTS  
**Qualification date:** 2026-10-12  
**Default hardened addon port:** 9877

## Result

| Status | Count |
|---|---:|
| PASS | 205 |
| FAIL | 0 |
| SKIP_EXTERNAL | 27 |
| **Total registered MCP tools** | **232** |

Every registered tool has exactly one qualification entry. The final local run had no native Blender crash, qualification timeout, or local-tool failure. `SKIP_EXTERNAL` is reserved for capabilities that require a provider, network service, optional image dependency, credential, or external converter.

## Risk breakdown

| Risk class | PASS | FAIL | SKIP_EXTERNAL |
|---|---:|---:|---:|
| blocking | 12 | 0 | 0 |
| bounded_mutation | 146 | 0 | 0 |
| context_heavy | 15 | 0 | 0 |
| external | 0 | 0 | 27 |
| read | 32 | 0 | 0 |

## External / optional skips

- `blender_polyhaven_search` - requires Poly Haven network service
- `blender_polyhaven_download` - requires Poly Haven network service
- `blender_ai_generate_model` - requires configured AI generation provider
- `blender_ai_model_status` - requires provider job id
- `blender_ai_generate_model_sync` - requires configured AI generation provider
- `blender_ai_generate_texture` - requires configured image generation provider
- `blender_ai_generate_texture_sync` - requires configured image generation provider
- `blender_ai_generate_reference_image` - requires configured image generation provider
- `blender_ai_inpaint_texture` - requires configured image generation provider
- `blender_ai_texture_from_render` - requires configured image generation provider
- `blender_msfs_livery_sample_color` - requires optional Pillow dependency not bundled with Blender
- `blender_msfs_livery_download_template` - requires external template download source
- `blender_msfs_livery_analyze` - requires optional Pillow/image-analysis dependency
- `blender_msfs_livery_transfer` - requires optional Pillow/image-processing dependency
- `blender_msfs_livery_extract_colors` - requires optional Pillow dependency not bundled with Blender
- `blender_msfs_livery_convert_to_dds` - requires optional external DDS conversion tool
- `blender_analyze_viewport` - requires external Ollama vision service
- `blender_refine_iteration` - requires external Ollama vision service
- `blender_refine_create_session` - refinement workflow requires external vision service
- `blender_refine_get_session` - refinement workflow requires external vision service
- `blender_refine_list_sessions` - refinement workflow requires external vision service
- `blender_ai_evaluate` - requires external Ollama vision service
- `blender_ai_refine` - requires external Ollama vision service
- `blender_ai_probe_backends` - probes optional external/local AI services
- `blender_ai_pipeline_generate` - requires configured AI providers
- `blender_ai_pipeline_status` - requires external pipeline job
- `blender_silhouette_compare` - requires optional Pillow image-analysis dependency not bundled with Blender

## Final release gates

- Full host test suite: **168 passed, 10 skipped**.
- Baseline Blender integration suite: **42/42 passed** on Blender 5.2.2 LTS.
- Complete tool qualification: **205 PASS, 0 FAIL, 27 SKIP_EXTERNAL**.
- Version consistency suite: **3/3 passed**.
- Addon package build: **PASS**, `blender_mcp_addon-0.5.0.zip` (241.6 KB).
- `git diff --check`: **PASS**.

## Qualification semantics

- Context-heavy operations run in isolated Blender processes. A documented safe `context_required` result in headless Blender is accepted only for a case that explicitly declares that error code.
- External-provider tools are not counted as PASS when the provider or optional dependency is unavailable.
- A process exit without the qualification PASS sentinel, a Python traceback, an access violation, or a timeout is a failure.
- Explicit user output paths are not TTL-cleaned and are not overwritten unless `overwrite=true`.
- Restricted script execution remains the default; unrestricted Python is not exposed as the normal tool path.

## Known target boundary

This fork is qualified for **Blender 5.2.2 LTS only**. Compatibility with Blender 4.x, 5.0, or future Blender releases is best-effort and is not part of this release gate. The baseline suite currently emits one Blender 6.0 deprecation warning for `Material.use_nodes`; it is not a Blender 5.2.2 failure.
