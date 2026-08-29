import asyncio
import hashlib
from dataclasses import dataclass
from io import BytesIO

from minio import Minio

from app.core.config import get_settings


@dataclass(frozen=True)
class StoredArtifact:
    object_key: str
    sha256: str
    size_bytes: int


class ArtifactStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_artifact_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    async def put_png(self, object_key: str, content: bytes) -> StoredArtifact:
        await asyncio.to_thread(self._put_png, object_key, content)
        return StoredArtifact(
            object_key=object_key,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

    def _put_png(self, object_key: str, content: bytes) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        self.client.put_object(
            self.bucket,
            object_key,
            BytesIO(content),
            length=len(content),
            content_type="image/png",
        )
