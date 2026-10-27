# Local HTTP API

Base URL http://127.0.0.1:8765. No CORS. Writes require application/json and X-CSRF-Token from the initial page meta tag. Origin/Host must match local server. This is a single-user local API, not public authentication.

| Method/path | Body / result |
|---|---|
| GET /api/config | Sanitized provider/model state, no secret |
| GET /api/projects | Project list |
| POST /api/projects | {name, files:{filename:UTF8_text}}; fixed input filenames only |
| POST /api/examples | {name:clean/defective/corrected/ambiguous/blocked/crs_same_unit_wrong} |
| GET /api/projects/{id} | Revision, draft, approval, input hashes, preview, point preview, jobs, audit |
| POST /api/projects/{id}/draft | {revision,key,mode:manual/live,confirm_outbound:true for live}; 202 job |
| POST /api/projects/{id}/approve | {revision,proposal,reviewer}; revision conflict = 409 |
| POST /api/projects/{id}/validate | {revision,key}; requires approved current snapshot; 202 job |
| POST /api/projects/{id}/corrected | {revision,files:{poi.csv/poi.geojson/crs.json:text},name}; new batch inheriting ruler |
| GET /api/jobs/{id} | status, revision, result or error |
| GET /api/jobs/{id}/report.json | Completed job result; JSON export |
| GET /api/jobs/{id}/report.html | Deterministically rendered report; attachment |
| POST /api/compare | {before:completed_validation_job_id,after:completed_validation_job_id} |

Job states QUEUED, RUNNING, COMPLETED, FAILED, INTERRUPTED are distinct from PASS/FAIL/INDETERMINATE. A completed validation job may contain FAIL or INDETERMINATE. Job idempotency keys are scoped to project and operation revision; a repeated key does not rerun the job. Queue limit is eight active jobs, with two worker threads.

All inputs are fixed named files. No browser API accepts a local path to read arbitrary files. Upload limits are 20 MiB/file, 25 MiB combined content and 30 MiB JSON request. Point previews stop at 10,000; full checks operate on the full supplied batch. Malformed GeoJSON is rejected instead of silently omitting records.

Changing a draft requires fresh approval. The approval contains raw input SHA-256; validation refuses if input bytes changed. Correction creates a new batch, preserves original files and reuses the approved ruler. No automatic row modification or deletion.
