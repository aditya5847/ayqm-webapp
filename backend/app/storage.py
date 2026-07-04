import hashlib
import json
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from .config import Settings, get_settings


class ObjectStorage(Protocol):
    def put_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> dict: ...

    def put_file(self, key: str, path: Path, content_type: str | None = None) -> dict: ...

    def put_json(self, key: str, value: object) -> dict: ...

    def read_json(self, key: str) -> dict: ...

    def download_file(self, key: str, destination: Path) -> Path: ...

    def head(self, key: str) -> dict | None: ...

    def presign_get(self, key: str, expires_seconds: int = 3600) -> str | None: ...

    def presign_put(self, key: str, content_type: str, expires_seconds: int = 3600) -> str | None: ...

    def delete_object(self, key: str) -> None: ...

    def delete_prefix(self, prefix: str) -> None: ...


def _safe_local_path(root: Path, key: str) -> Path:
    path = (root / key).resolve()
    root = root.resolve()
    if root not in path.parents and path != root:
        raise ValueError("Object key escapes storage root")
    return path


class LocalObjectStorage:
    def __init__(self, root: Path):
        self.root = root

    def put_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> dict:
        destination = _safe_local_path(self.root, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with destination.open("wb") as output:
            while chunk := stream.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        return {"key": key, "size": size, "sha256": digest.hexdigest(), "content_type": content_type}

    def put_file(self, key: str, path: Path, content_type: str | None = None) -> dict:
        with path.open("rb") as source:
            return self.put_stream(key, source, content_type)

    def put_json(self, key: str, value: object) -> dict:
        destination = _safe_local_path(self.root, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        destination.write_bytes(payload)
        return {
            "key": key,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_type": "application/json",
        }

    def read_json(self, key: str) -> dict:
        return json.loads(_safe_local_path(self.root, key).read_text(encoding="utf-8"))

    def download_file(self, key: str, destination: Path) -> Path:
        source = _safe_local_path(self.root, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        return destination

    def head(self, key: str) -> dict | None:
        path = _safe_local_path(self.root, key)
        if not path.exists():
            return None
        return {"key": key, "size": path.stat().st_size}

    def presign_get(self, key: str, expires_seconds: int = 3600) -> str | None:
        return None

    def presign_put(self, key: str, content_type: str, expires_seconds: int = 3600) -> str | None:
        return None

    def delete_object(self, key: str) -> None:
        path = _safe_local_path(self.root, key)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        path = _safe_local_path(self.root, prefix)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


class R2ObjectStorage:
    def __init__(self, settings: Settings):
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as exc:  # pragma: no cover - production dependency guard
            raise RuntimeError("boto3 is required when AYQM_STORAGE_BACKEND=r2") from exc
        self.bucket = settings.r2_bucket or ""
        self.client_error = ClientError
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )

    def put_stream(self, key: str, stream: BinaryIO, content_type: str | None = None) -> dict:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_fileobj(stream, self.bucket, key, ExtraArgs=extra or {})
        return self.head(key) or {"key": key}

    def put_file(self, key: str, path: Path, content_type: str | None = None) -> dict:
        with path.open("rb") as source:
            return self.put_stream(key, source, content_type)

    def put_json(self, key: str, value: object) -> dict:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.client.put_object(Bucket=self.bucket, Key=key, Body=payload, ContentType="application/json")
        return {
            "key": key,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_type": "application/json",
        }

    def read_json(self, key: str) -> dict:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return json.loads(response["Body"].read())

    def download_file(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(destination))
        return destination

    def head(self, key: str) -> dict | None:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except self.client_error as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return {
            "key": key,
            "size": int(response.get("ContentLength", 0)),
            "content_type": response.get("ContentType"),
            "etag": str(response.get("ETag", "")).strip('"'),
        }

    def presign_get(self, key: str, expires_seconds: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def presign_put(self, key: str, content_type: str, expires_seconds: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_seconds,
        )

    def delete_object(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys = [item["Key"] for item in page.get("Contents", [])]
            for start in range(0, len(keys), 1000):
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": key} for key in keys[start:start + 1000]], "Quiet": True},
                )


def get_object_storage(settings: Settings | None = None) -> ObjectStorage:
    resolved = settings or get_settings()
    if resolved.storage_backend == "r2":
        return R2ObjectStorage(resolved)
    return LocalObjectStorage(resolved.upload_root)
