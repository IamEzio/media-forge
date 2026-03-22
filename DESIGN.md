# DESIGN: media-forge Distributed Media Processing Engine

This document explains the architecture and design decisions behind **media-forge**, a small but production-inspired media processing engine built on **FastAPI**, **Celery**, **Redis**, **FFmpeg**, and **Docker Compose**.

---

## 1. System Architecture

### Components

1. **API Gateway (FastAPI)**
   - Receives client requests to process media.
   - Accepts file uploads (video + optional subtitles) and job type.
   - Persists inputs to shared storage.
   - Enqueues async jobs into Celery via Redis.
   - Exposes job status and download endpoints.

2. **Task Queue (Celery + Redis)**
   - Redis acts as **broker** (tasks queued here) and **result backend** (states stored here).
   - Celery workers pull tasks from Redis (pull-based model) and push results/states back.

3. **Worker Pool (Celery Workers)**
   - Generic workers that can execute any supported job type: `overlay`, `transcode`, `extract`.
   - Execute FFmpeg commands inside containerized environment.
   - Read inputs and write outputs to shared volume mounted at `/data`.
   - Designed for horizontal scaling via `docker compose up --scale worker=N`.

4. **Shared Storage (Docker Volume)**
   - Named volume `media_data` mounted at `/data` in API and worker containers.
   - Directory layout:

     ```text
     /data/input   # raw uploads from clients
     /data/output  # processed media artifacts
     /data/temp    # scratch space for future extensions
     ```

5. **Frontend**
   - Static HTML/CSS/JS served by FastAPI.
   - Helps validate end-to-end flows (upload, poll, download) without external tools.

### High-Level Flow

```text
Client → FastAPI → Redis (broker) → Celery Workers → /data volume
                                      ↓
                             Redis (result backend)
```

---

## 2. Worker Orchestration & Queue Model

### Pull-Based Worker Model

Workers **pull** jobs from Redis via Celery instead of the API pushing work to specific workers. This has several benefits:

- Workers can join/leave dynamically.
- Load balancing is handled by the queue.
- API remains stateless with respect to worker topology.

### Single Generic Task Type

There is a single Celery task function:

- `process_media_task(job_type, input_path, subtitles_path=None)`

The `job_type` parameter determines which FFmpeg operation to perform. This keeps workers generic and allows the same pool to handle all job categories.

### Redis as Broker & Result Backend

- **Broker**: Celery publishes tasks into Redis (e.g., DB 0).
- **Result backend**: Celery stores task states and return values (e.g., DB 1).
- The API interacts with Celery using the shared `celery_app` instance and **AsyncResult** to query job state.

### Job ID Strategy

- The system uses the **Celery task ID** as the external `job_id`.
- This avoids managing a separate ID space and storage for job metadata.
- Output filenames use this `job_id` to achieve idempotent processing.

---

## 3. Storage Model

### Volume Design

The `media_data` volume is mounted at `/data` in both the API and workers. Within it:

- `/data/input`: uploaded source videos and optional subtitle files.
- `/data/output`: final processed outputs.
- `/data/temp`: reserved for transient data (not extensively used in this demo but included for realistic layout).

### Deterministic Filenames

Workers use deterministic filenames derived from the job ID and job type:

```text
/data/output/{job_id}_{job_type}.mp4
/data/output/{job_id}_{job_type}.mp3  # for extract
```

This design makes tasks **idempotent**:

- On retries, the worker reuses the same output path.
- Before executing FFmpeg, the worker checks if the output file already exists and is non-empty; if so, it short-circuits and returns success.

### Storage Abstraction

- `StorageService` encapsulates all filesystem logic:
  - Saving uploads (`save_upload`)
  - Resolving deterministic output paths (`get_output_path_for_job`)
  - Existence checks and binary opening

This keeps API routes and tasks focused on business logic and makes it easier to evolve storage (e.g., move to S3) by changing a single service.

---

## 4. Job Lifecycle

### 1. Submission (API)

Endpoint: `POST /jobs`

Steps:

1. Validate inputs:
   - `video` must be present.
   - When `job_type=overlay`, `subtitles` must be present.
2. Save uploaded `video` and optional `subtitles` to `/data/input`.
3. Enqueue `process_media_task` with:
   - `job_type`
   - `input_path` (full path under `/data/input`)
   - `subtitles_path` (if any)
4. Return response with:
   - `job_id` (Celery task ID)
   - `status = pending`

### 2. Queueing (Celery + Redis)

- Celery serializes task metadata to JSON and pushes to Redis broker.
- Workers subscribed to the default queue pull tasks as they become available.

### 3. Processing (Worker)

Within `process_media_task`:

1. **Input validation**:
   - Ensure `input_path` exists.
   - For overlay, ensure `subtitles_path` exists.
2. **Determine output path** using `StorageService.get_output_path_for_job(job_id, job_type)`.
3. **Idempotency check**:
   - If output file exists and is non-empty, return success immediately.
4. **FFmpeg command selection**:
   - `overlay`: subtitles filter.
   - `transcode`: scale to 854x480.
   - `extract`: audio-only MP3.
5. **FFmpeg execution**:
   - Use `subprocess.run` to execute FFmpeg.
   - Capture stdout and stderr for logging.
   - Use `-y` to overwrite output files on retries.
6. **Result**:
   - On success, return `{"output_path": ...}`.
   - On FFmpeg failure, raise `FFmpegError` (triggers retries).

### 4. Status Tracking (API)

Endpoint: `GET /jobs/{job_id}`

- The API uses `AsyncResult(job_id)` from Celery to query state.
- Raw Celery states (e.g., `PENDING`, `STARTED`, `SUCCESS`, `FAILURE`) are mapped to simplified domain states using `map_celery_state`:
  - `pending`
  - `processing`
  - `completed`
  - `failed`
- When completed, `output_url` is set to `/jobs/{job_id}/download`.

### 5. Download (API)

Endpoint: `GET /jobs/{job_id}/download?job_type=...`

- The API recomputes the output file path using the `job_id` and `job_type` and returns a `FileResponse` if present.
- If the file is missing, it returns HTTP 404 (either still processing or failed).

---

## 5. Failure Recovery & Resiliency

### Celery Retries with Exponential Backoff

`BaseMediaTask` configures Celery’s retry mechanics:

- `autoretry_for = (FFmpegError,)`
- `max_retries = 5`
- `retry_backoff = True` (exponential backoff)
- `retry_backoff_max = 600` seconds
- `retry_jitter = True` (avoid thundering herd)

Only **FFmpegError** triggers retries. Non-retriable conditions like missing input files result in immediate failure.

### Worker Failures

- If a worker crashes mid-task, Celery will eventually re-dispatch the task (depending on acknowledgment semantics).
- With `task_acks_late=True` in configuration, tasks are only acknowledged after completion, ensuring at-least-once execution.

### Idempotency

- Deterministic output paths per job ensure that retries (or duplicate deliveries) write to the same file.
- FFmpeg is invoked with `-y` to overwrite partially written files from previous failed attempts.
- Before running FFmpeg, the worker checks if the output file exists and is non-empty; if so, it returns success without re-running FFmpeg.

This makes tasks effectively idempotent under typical failure scenarios.

---

## 6. Scalability Design

### Horizontal Scaling of Workers

- Docker Compose scaling:

  ```bash
  docker compose up --build --scale worker=4
  ```

- Each worker container runs the same code and connects to the same Redis broker and `/data` volume.
- Load balancing is handled by Celery using round-robin + prefetch control.

### Task Routing by Type (Extensible)

Although this implementation uses a single default queue, it is structured to support future queue routing:

- Different queues per job type (`overlay`, `transcode`, `extract`).
- Priority queues to isolate latency-sensitive work.
- Dedicated worker pools for heavyweight tasks (e.g., 4K transcodes) vs. light tasks.

### Scaling Beyond A Single Node

To move from tens to tens of thousands of jobs per hour, consider:

1. Deploying API and workers on Kubernetes with autoscaling.
2. Moving storage to object stores (S3, GCS, MinIO) for horizontal scaling.
3. Sharding queues and/or using higher-throughput brokers.
4. Adding observability (metrics + tracing) to drive automatic scaling policies.

---

## 7. Code Structure

The system is organized for separation of concerns and testability:

- **Configuration**: `backend/app/core/config.py`
  - Pydantic `Settings` for environment-driven config.
- **Celery App**: `backend/app/core/celery_app.py`
  - Shared Celery instance imported by API and workers.
- **Domain Models**: `backend/app/models/job_models.py`
  - Job types, status enums, and response models.
- **Services**:
  - `storage_service.py`: filesystem operations and path construction.
  - `job_service.py`: job submission and status lookup abstraction.
- **Workers**:
  - `ffmpeg_service.py`: FFmpeg command composition and subprocess execution.
  - `tasks.py`: Celery task definitions with retry policies.
- **API Layer**:
  - `api/routes_jobs.py`: FastAPI routes, thin HTTP layer.
  - `main.py`: FastAPI app wiring, CORS, and static file serving.

This layout aligns with clean architecture principles:

- Domain logic (job lifecycle, FFmpeg orchestration) is separated from transport (HTTP, Celery).
- Configuration & infrastructure concerns are isolated from business rules.

---

## 8. Trade-Offs 

- **No database (only Redis + filesystem)**  
  Chosen because the current needs are simple: we just need to enqueue jobs and store outputs. A relational DB would add operational and modeling overhead we don’t yet need.

- **Local volume instead of object storage**  
  A Docker volume at `/data` is enough for a single-node, low-scale deployment. Introducing S3/GCS and a more complex storage abstraction is postponed until we actually outgrow one host.

- **Logging-based observability first**  
  Plain logs are sufficient for a small system and easy to reason about. Metrics, tracing, and dashboards are intentionally left as a later evolutionary step, once there’s real load and SLOs to support.

- **Minimal frontend and no auth**  
  For an internal tool/small team, a simple HTML/JS UI without authentication reduces code and cognitive load. As usage grows or becomes multi-tenant, we can introduce a richer client and proper authN/Z.
  
---

## 9. Summary

media-forge is intentionally compact but demonstrates several important distributed system patterns:

- Stateless HTTP API fronting an asynchronous job queue.
- Generic, horizontally scalable worker pool pulling jobs from Redis.
- Distributed, shared storage for large media assets.
- Idempotent, retryable tasks with exponential backoff.
- Clean separation between API, services, and worker logic.

The stack runs end-to-end with a single command:

```bash
docker compose up --build
```

and provides a foundation from which to evolve into a production-grade, cloud-native media processing platform.
