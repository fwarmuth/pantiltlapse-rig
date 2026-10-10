import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger("CameraCommander.Session")


def slugify_name(name: str) -> str:
    """Convert a human-readable session name into a filesystem-safe directory slug."""
    cleaned = re.sub(r"[^\w\-_]+", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "session"


class SessionMetadata(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    plan: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="")


class SessionManager:
    """
    Manages self-contained shoot sessions on disk.
    Each session is isolated under output/sessions/<slug>/ with its own:
      - session.json: Sequence plan, waypoints, camera settings, metadata
      - test_shots/: Snapshots, star snaps, loupe calibration photos
      - timelapse/: Final sequence frames (0001.jpg...)
    """

    def __init__(
        self,
        base_dir: Path | str | None = None,
        time_provider: Any = None,
    ):
        self.time_provider = time_provider
        if base_dir is None:
            backend_dir = Path(__file__).resolve().parent
            base_dir = backend_dir.parent / "output" / "sessions"

        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.active_pointer_file = self.base_dir / ".active_session"
        self._active_session: SessionMetadata | None = None

        self._load_or_create_initial_session()

    def _get_now(self) -> datetime:
        if callable(self.time_provider):
            return self.time_provider()
        return datetime.now()

    def _load_or_create_initial_session(self) -> None:
        """Create a fresh timestamped session on startup to guarantee zero session reuse across shoots."""
        default_name = f"Session_{self._get_now().strftime('%Y-%m-%d_%H%M%S')}"
        self._active_session = self.create_session(name=default_name, activate=True)

    def _set_active_session_slug(self, slug: str) -> None:
        """Write the active session slug pointer atomically."""
        tmp = self.base_dir / f".active_session.tmp.{uuid4().hex[:6]}"
        tmp.write_text(slug, encoding="utf-8")
        tmp.replace(self.active_pointer_file)

    def _get_unique_slug(self, name: str, exclude_slug: str | None = None) -> str:
        """Generate a unique filesystem directory slug for a given session name."""
        base_slug = slugify_name(name)
        slug = base_slug
        counter = 1
        while (self.base_dir / slug).exists():
            if exclude_slug and slug == exclude_slug:
                break
            counter += 1
            slug = f"{base_slug}_{counter:02d}"
        return slug

    def _save_session_metadata(self, session: SessionMetadata) -> None:
        """Atomically persist session.json to disk."""
        session_dir = self.base_dir / session.slug
        session_dir.mkdir(parents=True, exist_ok=True)
        dest_file = session_dir / "session.json"
        temp_file = session_dir / f"session.json.tmp.{uuid4().hex[:6]}"

        session.updated_at = datetime.now(timezone.utc)
        payload = session.model_dump_json(indent=2)
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(dest_file)

    def _load_session_by_slug(self, slug: str) -> SessionMetadata | None:
        """Load session metadata from disk for a given directory slug."""
        manifest = self.base_dir / slug / "session.json"
        if not manifest.exists():
            return None
        try:
            with open(manifest, encoding="utf-8") as f:
                return SessionMetadata.model_validate_json(f.read())
        except Exception as e:
            logger.error(f"Failed to load session manifest at '{manifest}': {e}")
            return None

    def get_active_session(self) -> SessionMetadata:
        """Return the current active session metadata, initializing one if needed."""
        if not self._active_session:
            self._load_or_create_initial_session()
        assert self._active_session is not None
        return self._active_session

    def get_active_session_dir(self) -> Path:
        """Return Path to active session root folder."""
        session = self.get_active_session()
        session_dir = self.base_dir / session.slug
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def get_active_test_shots_dir(self) -> Path:
        """Return Path to active session test_shots/ folder."""
        d = self.get_active_session_dir() / "test_shots"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_active_timelapse_dir(self) -> Path:
        """Return Path to active session timelapse/ folder."""
        d = self.get_active_session_dir() / "timelapse"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_takes(self, slug: str | None = None) -> list[str]:
        """List all take subdirectory names (e.g. ['take_01', 'take_02']) sorted ascending."""
        session_slug = slug or self.get_active_session().slug
        tl_dir = self.base_dir / session_slug / "timelapse"
        if not tl_dir.exists():
            return []
        takes = []
        for entry in tl_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                takes.append(entry.name)
        takes.sort()
        return takes

    def get_latest_timelapse_take_dir(self, slug: str | None = None) -> Path:
        """
        Return the directory of the most recent take, or take_01 if none exists.
        If legacy flat timelapse files exist directly in timelapse/, returns timelapse/ itself.
        """
        session_slug = slug or self.get_active_session().slug
        tl_dir = self.base_dir / session_slug / "timelapse"
        tl_dir.mkdir(parents=True, exist_ok=True)

        takes = self.list_takes(session_slug)
        if takes:
            latest = tl_dir / takes[-1]
            latest.mkdir(parents=True, exist_ok=True)
            return latest

        # Check if legacy flat images exist
        flat_images = [f for f in tl_dir.iterdir() if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".jpg", ".jpeg", ".cr2")]
        if flat_images:
            return tl_dir

        # Otherwise allocate take_01
        take1 = tl_dir / "take_01"
        take1.mkdir(parents=True, exist_ok=True)
        return take1

    def get_next_timelapse_take_dir(self, slug: str | None = None) -> Path:
        """
        Allocate and return a fresh, empty take directory (e.g. take_01, take_02) for a new sequence.
        Reuses an existing take ONLY if it contains 0 images. Never overwrites existing captures.
        """
        session_slug = slug or self.get_active_session().slug
        tl_dir = self.base_dir / session_slug / "timelapse"
        tl_dir.mkdir(parents=True, exist_ok=True)

        takes = self.list_takes(session_slug)
        flat_images = [f for f in tl_dir.iterdir() if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".jpg", ".jpeg", ".cr2")]

        max_idx = 0
        for t in takes:
            m = re.match(r"^take_(\d+)$", t, re.IGNORECASE)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
            else:
                max_idx = max(max_idx, len(takes))

        if flat_images and max_idx == 0:
            max_idx = 1

        if takes and max_idx > 0:
            current_take_dir = tl_dir / f"take_{max_idx:02d}"
            if current_take_dir.exists():
                take_files = [f for f in current_take_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
                if len(take_files) == 0:
                    return current_take_dir

        next_idx = max_idx + 1
        new_take_dir = tl_dir / f"take_{next_idx:02d}"
        new_take_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Allocated new timelapse take: {new_take_dir}")
        return new_take_dir

    def create_session(
        self,
        name: str | None = None,
        plan: dict[str, Any] | None = None,
        activate: bool = True,
    ) -> SessionMetadata:
        """Create a new self-contained session directory and optionally activate it."""
        session_name = (name or "").strip()
        if not session_name:
            session_name = f"Session_{self._get_now().strftime('%Y-%m-%d_%H%M%S')}"

        slug = self._get_unique_slug(session_name)
        session_dir = self.base_dir / slug
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "test_shots").mkdir(parents=True, exist_ok=True)
        (session_dir / "timelapse").mkdir(parents=True, exist_ok=True)

        session = SessionMetadata(
            name=session_name,
            slug=slug,
            plan=plan or {},
        )
        self._save_session_metadata(session)

        if activate:
            self._set_active_session_slug(slug)
            self._active_session = session

        logger.info(f"Created session '{session_name}' ({slug})")
        return session

    def switch_session(self, session_id_or_slug: str) -> SessionMetadata:
        """Switch the active session by ID or slug."""
        target_slug = str(session_id_or_slug).strip()
        session = self._load_session_by_slug(target_slug)

        if not session:
            # Search by UUID
            for entry in self.base_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    s = self._load_session_by_slug(entry.name)
                    if s and str(s.id) == target_slug:
                        session = s
                        break

        if not session:
            raise ValueError(f"Session '{session_id_or_slug}' not found")

        self._set_active_session_slug(session.slug)
        self._active_session = session
        logger.info(f"Switched active session to '{session.name}' ({session.slug})")
        return session

    def rename_session(self, session_id_or_slug: str, new_name: str) -> SessionMetadata:
        """Rename a session and safely update its display name and manifest."""
        session = self.switch_session(session_id_or_slug) if str(session_id_or_slug) != self.get_active_session().slug else self.get_active_session()
        cleaned_name = new_name.strip()
        if not cleaned_name:
            raise ValueError("Session name cannot be empty")

        session.name = cleaned_name
        self._save_session_metadata(session)
        logger.info(f"Renamed session {session.slug} to '{cleaned_name}'")
        return session

    def save_active_plan(self, plan_data: dict[str, Any]) -> SessionMetadata:
        """Update and persist the active session's motion plan."""
        session = self.get_active_session()
        session.plan = plan_data
        if isinstance(plan_data, dict) and plan_data.get("name"):
            # If the plan has a user-entered name, sync session name
            session.name = plan_data["name"]
        self._save_session_metadata(session)
        return session

    def delete_session(self, session_id_or_slug: str) -> bool:
        """Delete a session directory and its media. Automatically switches active if deleting active session."""
        target = self.switch_session(session_id_or_slug) if False else None
        # Locate target
        target_slug = str(session_id_or_slug).strip()
        target_session = self._load_session_by_slug(target_slug)
        if not target_session:
            for entry in self.base_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    s = self._load_session_by_slug(entry.name)
                    if s and str(s.id) == target_slug:
                        target_session = s
                        break

        if not target_session:
            return False

        target_dir = self.base_dir / target_session.slug
        if not target_dir.exists():
            return False

        was_active = (self._active_session and self._active_session.slug == target_session.slug)
        shutil.rmtree(target_dir)
        logger.info(f"Deleted session directory: {target_dir}")

        if was_active:
            self._active_session = None
            self._load_or_create_initial_session()

        return True

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all available shoot sessions sorted by last modified date descending.
        Includes shot counts and thumbnail URLs for quick browsing in the UI.
        """
        results: list[dict[str, Any]] = []
        active_slug = self.get_active_session().slug if self._active_session else ""

        for entry in self.base_dir.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            session = self._load_session_by_slug(entry.name)
            if not session:
                continue

            test_shots_dir = entry / "test_shots"
            timelapse_dir = entry / "timelapse"

            test_shots_count = 0
            latest_test_shot_name = None
            if test_shots_dir.exists():
                test_files = [f for f in test_shots_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
                # Filter to non-raw or companion previews
                displayables = [f for f in test_files if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".svg")]
                displayables.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                test_shots_count = len(displayables)
                if displayables:
                    latest_test_shot_name = displayables[0].name

            timelapse_count = 0
            latest_tl_shot_name = None
            if timelapse_dir.exists():
                all_tl_files = []
                for entry in timelapse_dir.iterdir():
                    if entry.is_dir() and not entry.name.startswith("."):
                        all_tl_files.extend([
                            f for f in entry.iterdir()
                            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".jpg", ".jpeg")
                        ])
                    elif entry.is_file() and not entry.name.startswith(".") and entry.suffix.lower() in (".jpg", ".jpeg"):
                        all_tl_files.append(entry)

                all_tl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                timelapse_count = len(all_tl_files)
                if all_tl_files:
                    latest_tl_shot_name = all_tl_files[0].relative_to(timelapse_dir).as_posix()

            # Determine thumbnail url
            thumb_url = None
            if latest_test_shot_name:
                thumb_url = f"/api/sessions/{session.slug}/test-shots/{latest_test_shot_name}?quality=low"
            elif latest_tl_shot_name:
                thumb_url = f"/api/sessions/{session.slug}/timelapse/{latest_tl_shot_name}?quality=low"

            results.append({
                "id": str(session.id),
                "name": session.name,
                "slug": session.slug,
                "is_active": (session.slug == active_slug),
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "test_shots_count": test_shots_count,
                "timelapse_shots_count": timelapse_count,
                "takes_count": len(self.list_takes(session.slug)),
                "thumbnail_url": thumb_url,
                "plan_name": session.plan.get("name") if isinstance(session.plan, dict) else None,
            })

        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results
