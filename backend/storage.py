import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from domain.models import SequencePlan

logger = logging.getLogger("CameraCommander.Storage")


class PlanStore:
    """
    Atomic disk persistence for sequence plans.
    Stores plans at output/plans/<plan_id>/plan.json using atomic temp-file replace operations.
    Isolated against path traversal and corrupt manifests.
    """

    def __init__(self, base_dir: str | Path | None = None):
        if base_dir is None:
            # Default to output/plans under project root
            backend_dir = Path(__file__).resolve().parent
            base_dir = backend_dir.parent / "output" / "plans"

        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_plan_dir(self, plan_id: UUID | str) -> Path:
        """Validate UUID to prevent path traversal and return target directory."""
        if isinstance(plan_id, str):
            try:
                valid_uuid = UUID(plan_id)
            except ValueError:
                raise ValueError(f"Invalid plan ID format (must be valid UUID): '{plan_id}'") from None
            plan_id = valid_uuid

        plan_dir = self.base_dir / str(plan_id)
        # Ensure target dir remains strictly within base_dir
        if not plan_dir.resolve().is_relative_to(self.base_dir):
            raise ValueError(f"Path traversal detected for plan ID: '{plan_id}'")
        return plan_dir

    def save_plan(self, plan: SequencePlan) -> SequencePlan:
        """
        Save or update a SequencePlan.
        If plan already exists, increments revision counter and updates updated_at timestamp.
        Writes atomically via temporary sibling file and os.replace.
        """
        plan_dir = self._get_plan_dir(plan.id)
        plan_dir.mkdir(parents=True, exist_ok=True)
        dest_file = plan_dir / "plan.json"

        if dest_file.exists():
            plan.revision += 1
            plan.updated_at = datetime.now(timezone.utc)

        # Serialize model to formatted JSON
        payload_json = plan.model_dump_json(indent=2)

        # Write to sibling temp file and atomic replace
        temp_file = plan_dir / f"plan.json.tmp.{uuid4().hex}"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(payload_json)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, dest_file)
            logger.info(f"Saved plan '{plan.name}' ({plan.id}) rev {plan.revision} to {dest_file}")
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

        return plan

    def get_plan(self, plan_id: UUID | str) -> SequencePlan | None:
        """
        Load a SequencePlan by ID.
        Returns None if plan does not exist or manifest is missing.
        """
        try:
            plan_dir = self._get_plan_dir(plan_id)
        except ValueError as e:
            logger.warning(f"Failed plan ID validation: {e}")
            return None

        dest_file = plan_dir / "plan.json"
        if not dest_file.exists():
            return None

        try:
            with open(dest_file, encoding="utf-8") as f:
                data_str = f.read()
            return SequencePlan.model_validate_json(data_str)
        except Exception as e:
            logger.error(f"Failed to load or parse plan from '{dest_file}': {e}")
            return None

    def list_plans(self) -> list[SequencePlan]:
        """
        List all saved plans sorted by updated_at descending.
        Isolates and skips malformed or corrupt plan entries without failing.
        """
        plans: list[SequencePlan] = []
        if not self.base_dir.exists():
            return plans

        for entry in self.base_dir.iterdir():
            if not entry.is_dir():
                continue

            manifest = entry / "plan.json"
            if not manifest.exists():
                continue

            try:
                with open(manifest, encoding="utf-8") as f:
                    data_str = f.read()
                plan = SequencePlan.model_validate_json(data_str)
                plans.append(plan)
            except Exception as e:
                logger.warning(f"Skipping corrupt or invalid plan manifest at '{manifest}': {e}")

        # Sort by updated_at descending
        plans.sort(key=lambda p: p.updated_at, reverse=True)
        return plans

    def delete_plan(self, plan_id: UUID | str) -> bool:
        """
        Delete a plan directory and manifest.
        Returns True if deleted, False if plan did not exist.
        """
        try:
            plan_dir = self._get_plan_dir(plan_id)
        except ValueError:
            return False

        if not plan_dir.exists():
            return False

        try:
            shutil.rmtree(plan_dir)
            logger.info(f"Deleted plan directory: '{plan_dir}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting plan directory '{plan_dir}': {e}")
            return False


class JsonlWriter:
    """
    Append-only newline-delimited JSON writer for run event streams.
    """

    @staticmethod
    def append_event(file_path: str | Path, event_dict: dict):
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        line = json.dumps(event_dict, default=str) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
