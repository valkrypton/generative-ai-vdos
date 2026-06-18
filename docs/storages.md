# Storage layer (django-storages + S3)

How generated media (scene images, TTS audio, video clips, final video) is persisted.
The requirements ticket is `docs/webapp-specs/persist-media-to-s3.md`; this doc is the
*implementation* reference. Code lives in `backend/apps/storage/`.

## TL;DR

- One backend is active per environment, chosen by the `STORAGES` setting — **no
  local-vs-S3 branching in application code**.
  - dev: `FileSystemStorage` (writes under `MEDIA_ROOT`, served at `/media/` when `DEBUG`)
  - test: `InMemoryStorage` (offline, no disk, no AWS creds)
  - production: `S3Boto3Storage` (private objects, presigned URLs)
- The DB stores only the file **reference** (`Scene.media_path` is a `FileField`), never bytes.
- All file I/O goes through one facade: `from apps.storage import storage_provider`.

## The facade — `apps/storage/__init__.py`

A single `StorageProvider` class. It does **not** detect the backend at runtime; it looks
the backend up by name from Django's `STORAGES` dict (this mirrors how edX selects storage
via `STORAGES['default']['BACKEND']`).

```python
from apps.storage import storage_provider

storage_provider.upload(scene.media_path, disk_path)   # write a local file into storage
storage_provider.upload(scene.media_path, disk_path, save=False)  # batch, save row later
url = storage_provider.url(scene.media_path)            # access URL, or None if empty
```

- `upload()` calls `field_file.save(...)`, which applies the field's `upload_to` key and
  (by default) saves the model row.
- `url()` returns `self.storage.url(name)` — on S3 this is a **presigned** URL
  automatically (because `querystring_auth=True`); locally it's a plain `/media/…` path.
  There is no S3-specific code path.

To target a second bucket later, add an entry to `STORAGES` and instantiate
`StorageProvider(backend="that_name")`. No code change to the class is needed.

## Settings (`backend/config/settings/`)

`base.py` (shared / dev default):

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"allow_overwrite": True}},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
```

`test.py` → `default` = `InMemoryStorage` (offline).

`production.py`:

```python
AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME,
            "default_acl": None,          # see "Decisions" — ACL-disabled buckets
            "file_overwrite": False,
            "querystring_auth": True,     # private objects served via presigned URLs
            "querystring_expire": 3600,   # signed-URL lifetime (seconds)
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
```

Credentials (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) come from the environment, or
are omitted entirely on AWS infra so boto3 uses the attached IAM role. Never hardcode them;
only `.env` (gitignored) holds real values, and `.env.example` documents the keys.

## Key layout — `Scene.media_path`

`upload_to=scene_media_upload_path` produces user-scoped keys so objects never collide
across users/projects:

```
{owner_id}/{project_id}/images/{filename}   # stills
{owner_id}/{project_id}/clip/{filename}     # animated scenes (scene.animate=True)
```

The key is built from `project.owner_id` (the FK column) rather than `project.owner.id`,
so it doesn't trigger a `UserProfile` query — pair with `select_related("project")` in the
Celery task (`apps/projects/tasks.py`).

## Signed URLs

With `querystring_auth=True`, `storage.url(name)` returns a presigned GET URL valid for
`querystring_expire` seconds — no manual boto3 call. The API exposes this via
`GET /api/projects/<project_pk>/scenes/<pk>/media-urls/` (`SceneViewSet.media_urls`).

Per-call expiry is intentionally **not** supported yet (one global `querystring_expire`).
If a second lifetime is ever needed (e.g. a long-lived "download" link vs a short inline
preview), add `expire=None` to `StorageProvider.url()` and pass it to `storage.url(...)`;
`S3Boto3Storage.url()` already accepts it. There's a breadcrumb comment at that spot.

## Testing

Tests run offline against `InMemoryStorage` (set in `test.py`) — no AWS creds, no disk.
Storage tests live in `backend/apps/projects/tests/`:
`test_storage_utils.py`, `test_storage_paths.py`, `test_signed_urls.py`. S3-specific
behaviour is checked by patching `StorageProvider.storage` with a mock rather than hitting
AWS. To exercise S3 in an isolated test, `@override_settings(STORAGES=...)` or `moto[s3]`.

## IAM policy (minimum, production)

The app needs read/write/delete on objects plus list on the bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow",
     "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
     "Resource": "arn:aws:s3:::your-bucket-name/*"},
    {"Effect": "Allow",
     "Action": ["s3:ListBucket"],
     "Resource": "arn:aws:s3:::your-bucket-name"}
  ]
}
```

## Decisions / gotchas

- **`default_acl = None`, not `"private"`.** Buckets created since Apr 2023 have ACLs
  disabled by default; passing any ACL makes `PutObject` fail with
  `AccessControlListNotSupported`. Privacy is enforced by Block Public Access + bucket
  policy, while `querystring_auth=True` serves objects via presigned URLs. Do not set a
  `custom_domain` on this backend — it conflicts with presigned URLs.
- **One class, settings-driven backend.** An earlier version had
  `Base/Local/S3` provider subclasses + a runtime `_get_provider()` factory. They differed
  only in `url()`, and that difference is unnecessary once `querystring_auth` makes signed
  URLs automatic. Collapsed to one class selected by `STORAGES` name. Don't reintroduce the
  hierarchy unless backends genuinely diverge in behaviour (custom key schemes,
  pre/post-processing, a dedicated bucket class à la edX's `ImportExportS3Storage`).
- **`file_overwrite=False` in prod** means regenerating a scene writes a new hashed key;
  the old S3 object is not auto-deleted. If regeneration churn matters, delete the prior
  key (needs `s3:DeleteObject`, already in the policy above) or add a lifecycle rule.
  Dev uses `allow_overwrite=True` for convenience, so dev and prod differ here.
- **`storage_provider` is a `SimpleLazyObject`** so importing `apps.storage` never touches
  settings/the app registry before Django is ready (mirrors `default_storage`).

## Related

- Skill: `.claude/skills/django-storages-s3/SKILL.md` (general django-storages reference).
- Requirements: `docs/webapp-specs/persist-media-to-s3.md`.
