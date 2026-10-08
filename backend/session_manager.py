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

    def __init__(self, base_dir: Path | str | None = None):
        if base_dir is None:
            backend_dir = Path(__file__).resolve().parent
            base_dir = backend_dir.parent / "output" / "sessions"

        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.active_pointer_file = self.base_dir / ".active_session"
        self._active_session: SessionMetadata | None = None

        self._migrate_legacy_if_needed()
        self._load_or_create_initial_session()

    def _migrate_legacy_if_needed(self) -> None:
        """Migrate existing legacy output/plans/ and output/captures/ if sessions directory is empty."""
        try:
            existing_sessions = [d for d in self.base_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
            if existing_sessions:
                return  # Sessions already exist, no migration needed

            output_dir = self.base_dir.parent
            legacy_plans_dir = output_dir / "plans"
            legacy_captures_dir = output_dir / "captures"

            # Check if there are legacy plans or captures to migrate
            has_plans = legacy_plans_dir.exists() and any(legacy_plans_dir.iterdir())
            has_captures = legacy_captures_dir.exists() and any(legacy_captures_dir.iterdir())

            if not (has_plans or has_captures):
                return

            logger.info("Migrating legacy plans and captures to sessions/...")
            legacy_session_name = "Legacy_Archive"
            legacy_slug = "legacy_archive"
            legacy_session_dir = self.base_dir / legacy_slug
            legacy_session_dir.mkdir(parents=True, exist_ok=True)
            test_shots_dir = legacy_session_dir / "test_shots"
            test_shots_dir.mkdir(parents=True, exist_ok=True)
            timelapse_dir = legacy_session_dir / "timelapse"
            timelapse_dir.mkdir(parents=True, exist_ok=True)

            migrated_plan: dict[str, Any] = {}
            if has_plans:
                for plan_entry in legacy_plans_dir.iterdir():
                    if plan_entry.is_dir():
                        plan_file = plan_entry / "plan.json"
                        if plan_file.exists():
                            try:
                                with open(plan_file, encoding="utf-8") as pf:
                                    migrated_plan = json.load(pf)
                                break
                            except Exception:
                                pass

            if has_captures:
                # Copy or move root capture files to test_shots/
                for f in list(legacy_captures_dir.iterdir()):
                    if f.is_file() and f.name.startswith("capture_"):
                        try:
                            shutil.copy2(f, test_shots_dir / f.name)
                        except Exception:
                            pass
                    elif f.is_dir() and f.name.startswith("timelapse_"):
                        # Copy contents of latest timelapse dir to timelapse/
                        for tf in f.iterdir():
                            if tf.is_file():
                                try:
                                    shutil.copy2(tf, timelapse_dir / tf.name)
                                except Exception:
                                    pass

            meta = SessionMetadata(
                name=legacy_session_name,
                slug=legacy_slug,
                plan=migrated_plan,
            )
            self._save_session_metadata(meta)
            self._set_active_session_slug(legacy_slug)
            self._active_session = meta
            logger.info(f"Successfully migrated legacy files into session '{legacy_slug}'")
        except Exception as e:
            logger.warning(f"Legacy migration skipped or failed: {e}")

    def _load_or_create_initial_session(self) -> None:
        """Load the active session from disk pointer or create a default session."""
        if self.active_pointer_file.exists():
            try:
                active_slug = self.active_pointer_file.read_text(encoding="utf-8").strip()
                if active_slug:
                    session = self._load_session_by_slug(active_slug)
                    if session:
                        self._active_session = session
                        return
            except Exception as e:
                logger.warning(f"Could not load active session pointer: {e}")

        # If any sessions exist, pick the most recently updated one
        all_sessions = self.list_sessions()
        if all_sessions:
            first_slug = all_sessions[0]["slug"]
            session = self._load_session_by_slug(first_slug)
            if session:
                self._active_session = session
                self._set_active_session_slug(first_slug)
                return

        # Otherwise create a fresh default session for today
        default_name = f"Session_{datetime.now().strftime('%Y-%m-%d')}"
        self._active_session = self.create_session(name=default_name)

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

    def create_session(
        self,
        name: str | None = None,
        plan: dict[str, Any] | None = None,
        activate: bool = True,
    ) -> SessionMetadata:
        """Create a new self-contained session directory and optionally activate it."""
        session_name = (name or "").strip()
        if not session_name:
            session_name = f"Session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}"

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
                tl_files = [f for f in timelapse_dir.iterdir() if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".jpg", ".jpeg")]
                tl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                timelapse_count = len(tl_files)
                if tl_files:
                    latest_tl_shot_name = tl_files[0].name

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
                "thumbnail_url": thumb_url,
                "plan_name": session.plan.get("name") if isinstance(session.plan, dict) else None,
            })

        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results
