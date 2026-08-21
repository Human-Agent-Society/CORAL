"""Structured validation for CORAL task directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from coral.config import CoralConfig


@dataclass(frozen=True)
class ValidationDiagnostic:
    """A machine-readable problem found in a task directory."""

    code: str
    message: str
    path: str | None = None
    severity: Literal["error", "warning"] = "error"

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.path is not None:
            data["path"] = self.path
        return data


@dataclass(frozen=True)
class ValidationReport:
    """Structured result of validating one task directory."""

    task_dir: Path
    diagnostics: tuple[ValidationDiagnostic, ...]

    @property
    def valid(self) -> bool:
        return all(diagnostic.severity != "error" for diagnostic in self.diagnostics)

    @property
    def error_messages(self) -> list[str]:
        """Return the legacy error representation used by the CLI."""
        return [
            diagnostic.message for diagnostic in self.diagnostics if diagnostic.severity == "error"
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_dir": str(self.task_dir),
            "valid": self.valid,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def validate_task(task_dir: Path) -> ValidationReport:
    """Validate a task directory and return structured diagnostics."""
    diagnostics: list[ValidationDiagnostic] = []

    task_yaml = task_dir / "task.yaml"
    if not task_yaml.exists():
        diagnostics.append(
            ValidationDiagnostic(
                code="task.config.missing",
                message=f"task.yaml not found in {task_dir}",
                path="task.yaml",
            )
        )
        return ValidationReport(task_dir, tuple(diagnostics))

    try:
        config = CoralConfig.from_yaml(task_yaml)
    except Exception as exc:
        diagnostics.append(
            ValidationDiagnostic(
                code="task.config.invalid",
                message=f"task.yaml parse error: {exc}",
                path="task.yaml",
            )
        )
        return ValidationReport(task_dir, tuple(diagnostics))

    if not config.grader.entrypoint:
        diagnostics.append(
            ValidationDiagnostic(
                code="grader.entrypoint.missing",
                message=(
                    "No grader configured. Set grader.entrypoint = "
                    "'your_pkg.module:Grader' in task.yaml and grader.setup to "
                    "install the package."
                ),
                path="task.yaml",
            )
        )
    elif ":" not in config.grader.entrypoint:
        diagnostics.append(
            ValidationDiagnostic(
                code="grader.entrypoint.invalid",
                message=(
                    "grader.entrypoint must be 'module.path:ClassName', "
                    f"got {config.grader.entrypoint!r}"
                ),
                path="task.yaml",
            )
        )

    if config.grader.direction not in ("maximize", "minimize"):
        diagnostics.append(
            ValidationDiagnostic(
                code="grader.direction.invalid",
                message=(
                    "grader.direction must be 'maximize' or 'minimize', "
                    f"got '{config.grader.direction}'"
                ),
                path="task.yaml",
            )
        )

    # The grader package is surfaced read-only to agents at <shared_dir>/grader/.
    # Private paths inside it would therefore be copied into .coral/private/ and
    # exposed through the surfaced source at the same time.
    grader_dir = (task_dir / "grader").resolve()
    for private_path in config.grader.private:
        path = Path(private_path)
        if not path.is_absolute():
            path = task_dir / path
        if not path.exists():
            diagnostics.append(
                ValidationDiagnostic(
                    code="grader.private.missing",
                    message=f"Private file not found: {private_path}",
                    path=str(private_path),
                )
            )
            continue
        try:
            path.resolve().relative_to(grader_dir)
        except ValueError:
            pass
        else:
            diagnostics.append(
                ValidationDiagnostic(
                    code="grader.private.exposed",
                    message=(
                        f"grader.private path '{private_path}' is inside the grader package "
                        "(grader/), which is surfaced read-only to agents at "
                        "<shared_dir>/grader/ — this would leak it. Move it outside grader/ "
                        "(e.g. a sibling 'taskdata/')."
                    ),
                    path=str(private_path),
                )
            )

    return ValidationReport(task_dir, tuple(diagnostics))
