import os
import re
import uuid
import logging
from typing import Optional
from pathlib import Path

from fastapi import UploadFile

from ..models.settings import SystemSettings
from ..core.database import SessionLocal

logger = logging.getLogger(__name__)

class StorageService:
    """
    A unified StorageService that dynamically uploads files to the configured Active Storage Provider.
    Supported providers: 'local', 'cloudinary', 'firebase', 's3'
    """
    
    # Extensions we are willing to write to disk. Anything else is stored as
    # .bin so an upload can never become a served script or a source file.
    _ALLOWED_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff",
        ".pdf", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".mp4", ".mov",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".txt",
    }

    # Never trust an extension that a browser would execute or render as markup.
    _DANGEROUS_EXTENSIONS = {
        ".html", ".htm", ".xhtml", ".svg", ".js", ".mjs", ".php", ".phtml",
        ".py", ".sh", ".bash", ".pl", ".rb", ".jsp", ".asp", ".aspx", ".cgi",
        ".exe", ".dll", ".so", ".jar", ".bat", ".cmd", ".ps1",
    }

    @staticmethod
    def _get_settings() -> Optional[SystemSettings]:
        with SessionLocal() as db:
            return db.query(SystemSettings).filter(SystemSettings.id == 1).first()

    @staticmethod
    def safe_filename(filename: Optional[str], content_type: Optional[str] = None) -> str:
        """Turn a client-supplied filename into something safe to write.

        The name arrives from a multipart upload, so it is fully attacker
        controlled. ``os.path.join(dir, name)`` does NOT contain it — a leading
        slash makes the result absolute and ``..`` walks out of the folder — so
        an unsanitised name is an arbitrary file write, not just a messy one.

        Keeps only a basename, drops any extension we would not serve, and falls
        back to a random name when nothing usable is left.
        """
        # Strip directory components for BOTH separators: a Windows-style name
        # reaches a Linux server unchanged and os.path.basename would keep it.
        raw = (filename or "").replace("\\", "/")
        raw = raw.split("/")[-1].strip()

        # Drop control characters and null bytes, then collapse to a safe set.
        raw = re.sub(r"[\x00-\x1f]", "", raw)
        stem, ext = os.path.splitext(raw)
        ext = ext.lower()

        if ext in StorageService._DANGEROUS_EXTENSIONS or ext not in StorageService._ALLOWED_EXTENSIONS:
            guessed = None
            if content_type:
                ct = content_type.lower()
                for candidate, suffix in (
                    ("png", ".png"), ("webp", ".webp"), ("gif", ".gif"),
                    ("bmp", ".bmp"), ("tiff", ".tif"), ("pdf", ".pdf"),
                    ("jpeg", ".jpg"), ("jpg", ".jpg"),
                ):
                    if candidate in ct:
                        guessed = suffix
                        break
            ext = guessed or ".bin"

        stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("._-")
        if not stem:
            stem = uuid.uuid4().hex
        stem = stem[:80]

        return f"{stem}{ext}"

    @staticmethod
    def upload_file(
        file_data: bytes, 
        folder: str, 
        filename: Optional[str] = None, 
        content_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Upload a file based on the dynamic settings configured in the admin panel.
        Returns the URL or relative path (e.g., /uploads/...)
        """
        if not file_data:
            return None
            
        settings = StorageService._get_settings()
        provider = settings.active_storage_provider if settings else "local"
        
        # Default filename if not provided
        if not filename:
            ext = ".jpg" # fallback default
            if content_type:
                if "png" in content_type.lower(): ext = ".png"
                elif "webp" in content_type.lower(): ext = ".webp"
                elif "gif" in content_type.lower(): ext = ".gif"
                elif "bmp" in content_type.lower(): ext = ".bmp"
                elif "tiff" in content_type.lower(): ext = ".tif"
                elif "pdf" in content_type.lower(): ext = ".pdf"
            filename = f"{uuid.uuid4().hex}{ext}"

        # Single choke point: every provider path below receives a sanitised
        # name, so no caller can reintroduce a traversal by forwarding
        # UploadFile.filename straight through.
        original = filename
        filename = StorageService.safe_filename(filename, content_type)
        if filename != original:
            logger.warning("Rejected unsafe upload filename %r -> %r", original, filename)

        # The folder is set by our own code, never by a request, but keep it
        # from escaping too in case that ever changes.
        folder = "/".join(
            part for part in str(folder or "").replace("\\", "/").split("/")
            if part not in ("", ".", "..")
        ) or "misc"

        logger.info(f"Uploading file {filename} to {folder} via {provider} provider...")

        try:
            if provider == "cloudinary":
                return StorageService._upload_to_cloudinary(file_data, folder, filename, settings)
            elif provider == "s3":
                return StorageService._upload_to_s3(file_data, folder, filename, settings)
            elif provider == "firebase":
                return StorageService._upload_to_firebase(file_data, folder, filename, settings)
            else:
                return StorageService._upload_to_local(file_data, folder, filename)
        except Exception as e:
            logger.error(f"Error uploading via {provider}: {e}", exc_info=True)
            return StorageService._upload_to_local(file_data, folder, filename)

    @staticmethod
    def _upload_to_local(file_data: bytes, folder: str, filename: str) -> Optional[str]:
        """Save exactly as before: to the local /uploads folder"""
        base_upload_dir = "uploads"
        target_dir = os.path.join(base_upload_dir, folder)
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.join(target_dir, filename)
        
        try:
            with open(file_path, "wb") as f:
                f.write(file_data)
            return f"/uploads/{folder}/{filename}"
        except Exception as e:
            logger.error(f"Error saving file locally: {e}")
            return None

    @staticmethod
    def _upload_to_cloudinary(file_data: bytes, folder: str, filename: str, settings: SystemSettings) -> Optional[str]:
        """Upload to Cloudinary"""
        import cloudinary
        import cloudinary.uploader
        
        if not settings.cloudinary_cloud_name or not settings.cloudinary_api_key or not settings.cloudinary_api_secret:
            logger.error("Cloudinary credentials missing. Please configure in Settings.")
            raise ValueError("Incomplete Cloudinary credentials")

        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True
        )
        
        # Remove extension for Cloudinary public_id
        public_id = os.path.splitext(filename)[0]
        full_path = f"pama/{folder}/{public_id}"
        
        response = cloudinary.uploader.upload(
            file_data,
            public_id=full_path,
            resource_type="auto"
        )
        return response.get("secure_url")

    @staticmethod
    def _upload_to_s3(file_data: bytes, folder: str, filename: str, settings: SystemSettings) -> Optional[str]:
        """Upload to AWS S3 / DigitalOcean Spaces"""
        import boto3
        
        if not settings.aws_access_key_id or not settings.aws_secret_access_key or not settings.aws_bucket_name:
            logger.error("AWS S3 credentials missing. Please configure in Settings.")
            raise ValueError("Incomplete S3 credentials")

        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region_name
        )
        
        object_name = f"{folder}/{filename}"
        
        # If it's DigitalOcean spaces or similar, an endpoint_url might be needed. 
        # But boto3 usually handles AWS out of the box.
        
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = 'application/octet-stream'

        # We upload from bytes
        s3_client.put_object(
            Bucket=settings.aws_bucket_name,
            Key=object_name,
            Body=file_data,
            ContentType=content_type
        )
        
        # Construct URL
        # Format depends on region: https://{bucket}.s3.{region}.amazonaws.com/{key}
        if settings.aws_region_name:
            return f"https://{settings.aws_bucket_name}.s3.{settings.aws_region_name}.amazonaws.com/{object_name}"
        else:
            return f"https://{settings.aws_bucket_name}.s3.amazonaws.com/{object_name}"

    @staticmethod
    def _upload_to_firebase(file_data: bytes, folder: str, filename: str, settings: SystemSettings) -> Optional[str]:
        """Upload to Firebase Storage"""
        from firebase_admin import storage, credentials
        import firebase_admin

        bucket_name = settings.firebase_storage_bucket
        if not bucket_name:
            logger.error("Firebase Storage bucket missing. Please configure in Settings.")
            raise ValueError("Incomplete Firebase Storage bucket name")

        # Initialize firebase_admin if it hasn't been already
        if not firebase_admin._apps:
            logger.info("Initializing Firebase Admin SDK in StorageService...")
            try:
                if settings.firebase_service_account_json:
                    import json
                    cert_dict = json.loads(settings.firebase_service_account_json)
                    cred = credentials.Certificate(cert_dict)
                    firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})
                    logger.info("Successfully initialized Firebase Admin using provided JSON credentials.")
                else:
                    # Fallback to application default credentials (ADC) if no JSON is provided
                    logger.warning("No Firebase Service Account JSON provided in settings. Trying Application Default Credentials...")
                    cred = credentials.ApplicationDefault()
                    firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})
            except Exception as e:
                logger.error(f"Failed to initialize Firebase Admin: {e}")
                # Ultimate fallback initialize without explicit credentials
                try:
                    firebase_admin.initialize_app(options={'storageBucket': bucket_name})
                except Exception as inner_e:
                    logger.error(f"Ultimate fallback initialization also failed: {inner_e}")
                    raise e
        else:
            # Important: if the app is already initialized, it might not have the storageBucket set
            # We can override the bucket when calling storage.bucket(bucket_name) directly which we do below.
            pass

        bucket = storage.bucket(bucket_name)
        blob = bucket.blob(f"{folder}/{filename}")
        
        # Uploading raw bytes
        blob.upload_from_string(file_data)
        blob.make_public()
        
        return blob.public_url

    @staticmethod
    def delete_file(
        file_url: Optional[str], settings: Optional[SystemSettings] = None
    ) -> bool:
        """
        Delete a file from Local, Firebase, Cloudinary, or AWS S3 based on its URL and the active provider settings.
        """
        if not file_url:
            return False

        if settings is None:
            settings = StorageService._get_settings()

        try:
            # 1. Cloudinary
            if "res.cloudinary.com" in file_url:
                import cloudinary.uploader
                import cloudinary

                if (
                    not settings
                    or not settings.cloudinary_cloud_name
                    or not settings.cloudinary_api_key
                    or not settings.cloudinary_api_secret
                ):
                    logger.warning(
                        "Cloudinary delete skipped (missing settings): %s", file_url
                    )
                    return False

                cloudinary.config(
                    cloud_name=settings.cloudinary_cloud_name,
                    api_key=settings.cloudinary_api_key,
                    api_secret=settings.cloudinary_api_secret,
                )

                # public_id matches upload path, e.g. pama/audio/pickup_audio_5_abc12345
                # URL may be .../video/upload/v123/pama/audio/file.m4a or .../upload/pama/audio/file.m4a
                parts = file_url.split("/upload/")
                if len(parts) < 2:
                    return False
                path_part = parts[1]
                # Strip optional transformation chain (e.g. w_400,c_fill/...)
                while "/" in path_part:
                    head, tail = path_part.split("/", 1)
                    if "," in head or re.match(
                        r"^[a-z0-9_]+_[a-z0-9]+", head, re.I
                    ):
                        path_part = tail
                        continue
                    break
                path_part = re.sub(r"^v\d+/", "", path_part)
                public_id = (
                    path_part.rsplit(".", 1)[0] if "." in path_part else path_part
                )
                if not public_id:
                    return False

                # Audio uploads often use resource_type video or raw, not image
                last_result = None
                for rt in ("video", "raw", "image"):
                    try:
                        resp = cloudinary.uploader.destroy(
                            public_id, resource_type=rt
                        )
                        last_result = (resp or {}).get("result")
                        if last_result == "ok":
                            return True
                    except Exception as inner:
                        logger.debug(
                            "Cloudinary destroy failed (%s, %s): %s",
                            rt,
                            public_id,
                            inner,
                        )
                if last_result == "not found":
                    return True
                logger.warning(
                    "Cloudinary destroy did not succeed for public_id=%s last=%s",
                    public_id,
                    last_result,
                )
                return False

            # 2. AWS S3 / DigitalOcean Spaces (S3-compatible)
            elif ".amazonaws.com" in file_url or "digitaloceanspaces.com" in file_url:
                import boto3
                from urllib.parse import urlparse

                if (
                    not settings
                    or not settings.aws_access_key_id
                    or not settings.aws_secret_access_key
                    or not settings.aws_bucket_name
                ):
                    return False
                    
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    region_name=settings.aws_region_name
                )
                
                # Extract S3 key from URL:
                # https://bucket-name.s3.region.amazonaws.com/voice_messages/file.m4a
                # https://bucket.region.digitaloceanspaces.com/voice_messages/file.m4a
                parsed = urlparse(file_url)
                object_key = parsed.path.lstrip('/')
                s3_client.delete_object(Bucket=settings.aws_bucket_name, Key=object_key)
                return True
                
            # 3. Firebase
            elif "firebasestorage.googleapis.com" in file_url or "storage.googleapis.com" in file_url:
                from firebase_admin import storage, credentials
                import firebase_admin

                if not settings:
                    return False

                bucket_name = settings.firebase_storage_bucket
                if not bucket_name:
                    return False
                    
                if not firebase_admin._apps:
                    if settings.firebase_service_account_json:
                        import json
                        import types
                        creds_dict = json.loads(settings.firebase_service_account_json)
                        
                        # Fix private key escaping issue
                        if "private_key" in creds_dict:
                            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                            
                        cred = credentials.Certificate(creds_dict)
                        # Mock os.environ to prevent GCP credential fetch warnings
                        import os
                        original_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ""
                        try:
                            firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})
                        except Exception:
                            logger.error("Failed to initialize Firebase with settings JSON", exc_info=True)
                        if original_env is not None:
                            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = original_env
                        else:
                            del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
                            
                    else:
                        try:
                            firebase_admin.initialize_app(options={'storageBucket': bucket_name})
                        except Exception:
                            pass
                            
                from urllib.parse import unquote, urlparse
                # Extract path from Firebase URL
                # Format 1: https://firebasestorage.googleapis.com/v0/b/bucket/o/uploads%2Fnews%2Ffilename.jpg?alt=media
                # Format 2: https://storage.googleapis.com/bucket_name/uploads/news/filename.jpg
                
                parsed = urlparse(file_url)
                if "firebasestorage.googleapis.com" in file_url:
                    path_parts = parsed.path.split('/o/')
                    if len(path_parts) > 1:
                        blob_path = unquote(path_parts[1])
                    else:
                        blob_path = None
                else:
                    # storage.googleapis.com
                    # path is /bucket_name/uploads/news/filename.jpg
                    path = unquote(parsed.path)
                    prefix = f"/{bucket_name}/"
                    if path.startswith(prefix):
                        blob_path = path[len(prefix):]
                    else:
                        blob_path = None
                        
                if blob_path:
                    bucket = storage.bucket(bucket_name)
                    blob = bucket.blob(blob_path)
                    blob.delete()
                    return True

            # 4. Absolute URL that maps to local uploads/ (same server or reverse proxy)
            elif file_url.startswith("http://") or file_url.startswith("https://"):
                from urllib.parse import urlparse

                parsed = urlparse(file_url)
                p = parsed.path or ""
                if p.startswith("/uploads/"):
                    return StorageService.delete_local_file(p)

            # 5. Local relative path
            else:
                return StorageService.delete_local_file(file_url)
                
        except Exception as e:
            logger.error(f"Cloud deletion failed for {file_url}: {e}", exc_info=True)
            return False
            
        return False

    @staticmethod
    def delete_local_file(file_path: Optional[str]) -> bool:
        """
        Delete a local file if it exists. 
        Useful for replacing an old local avatar.
        Does not attempt to delete cloud files (Cloudinary/S3) yet to avoid accidental data loss.
        """
        if not file_path:
            return False
            
        # Only delete true local files
        if file_path.startswith("http://") or file_path.startswith("https://"):
            return False
        
        # Handle leading slash in db (e.g. /uploads/...)
        clean_path = file_path.lstrip('/')
        
        base_dir = Path(os.getcwd())
        full_path = base_dir / clean_path
        
        if full_path.exists() and full_path.is_file():
            try:
                os.remove(full_path)
                return True
            except Exception as e:
                logger.error(f"Exception while deleting local file {full_path}: {e}")
        return False
