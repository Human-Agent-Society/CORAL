"""``EvolvingTaskGrader``: a criteria-driven grader whose rubric can grow.

One grade, in order:

    load current rubric version  (seed it on the first grade)
    advance the rubric           adaptive: at a checkpoint, propose -> admit -> publish
                                 yoked:    replay the paired run's checkpoint outcomes
                                 static:   never
    evaluate under that version  (inner grader, with retries on infrastructure failure)
    write one event              (scores bound to the version they were scored under)

Everything the mechanism decides is written down: one trigger-decision record
per grade, one immutable snapshot per version, the exact evidence the proposer
was shown, and a changelog. Nothing here reads a held-out split, and nothing
after a publication is allowed to rewrite the version an earlier score cites.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from coral.config import GraderConfig
from coral.grader.evolution import policy as pol
from coral.grader.evolution import proposals as prop
from coral.grader.evolution.failures import (
    FailureCode,
    FailureRecord,
    classify_generic,
    inspect_evaluator_log,
    summarize,
)
from coral.grader.evolution.state import (
    Criterion,
    EvolutionStore,
    Observation,
    RubricSnapshot,
    utcnow,
)
from coral.grader.task_grader import TaskGrader
from coral.types import BUDGET_CLASS_TUNE, ScoreBundle

logger = logging.getLogger(__name__)

#: Shown to the agent verbatim whenever the evaluator could not produce a
#: score at all, in every arm.
#:
#: A raw failure message with no attribution invites the agent to explain a
#: result that does not exist, and the only material it has is its own last
#: change, so it concludes the change broke the grader and retreats to cosmetic
#: edits. The message therefore says what happened and that it is not about the
#: submission, and nothing more.
#:
#: An attempt only reaches this path when every retry failed to yield a score
#: -- never when the evaluator ran and scored the work low. So this message is
#: always true when it appears: it is a statement about the evaluator, not the
#: submission.
INFRA_FAILURE_FEEDBACK = (
    "Evaluation unavailable because of evaluator infrastructure/account limits. "
    "This is not evidence about the quality or complexity of your submission. "
    "Do not modify your artifact in response to this failure."
)


class EvolvingTaskGrader(TaskGrader):
    """Subclass and set ``inner_grader_cls`` to the fixed-criteria grader to wrap."""

    inner_grader_cls: type[TaskGrader] | None = None

    def __init__(self, config: GraderConfig) -> None:
        super().__init__(config)
        if self.inner_grader_cls is None:
            raise TypeError(
                f"{type(self).__name__} must set `inner_grader_cls` to the criteria-driven "
                "TaskGrader it wraps (e.g. `inner_grader_cls = AgenticEvaluator`)."
            )
        self.inner = self.inner_grader_cls(config)

    # ------------------------------------------------------------------ main

    def evaluate(self) -> ScoreBundle:
        evo_cfg = self.args.get("evolution") or {}
        cfg = pol.PolicyConfig.from_args(evo_cfg)
        # Written for every arm, the fixed one included: it is the only record
        # of which arm this run is once the task name is identical across arms.
        self._write_manifest_once(cfg, evo_cfg)
        attempt_id, agent_id = self._attempt_id(), self._agent_id()
        if cfg.mode == "static":
            # Same retry path as the evolving arms. A static arm that got no
            # retry on evaluation failure would lose attempts the other arms
            # kept, and that asymmetry alone could move a comparison.
            result, failures = self._evaluate_with_retries(
                self.args.get("criteria") or [], cfg, attempt_id
            )
            self._mask_infra_failure(result)
            result.metadata = {
                **(result.metadata or {}),
                "rubric_version_scored": 1,
                "eval_version": 1,
                "evaluation_retries": len(failures),
                "evaluation_failures": summarize(failures),
            }
            return result

        store = EvolutionStore(self.private_dir)

        with store.locked():
            snap = store.load_current() or store.publish_snapshot(self._seed_snapshot())
            snap = self._advance_rubric(store, snap, cfg)
            criteria_arg = [c.to_criteria_arg() for c in snap.criteria]
            scored_version = snap.version

        result, failures = self._evaluate_with_retries(criteria_arg, cfg, attempt_id)
        self._mask_infra_failure(result)

        scores = {
            n: float(s.value)
            for n, s in (result.scores or {}).items()
            if getattr(s, "value", None) is not None
        }
        store.write_event(
            {
                "attempt_id": attempt_id,
                "agent_id": agent_id,
                "outcome": "scored" if result.aggregated is not None else "failed",
                "rubric_version_scored": scored_version,
                "aggregated": result.aggregated,
                "scores": scores,
                "criteria_in_force": [c["name"] for c in criteria_arg],
                "evaluator_model": self.args.get("evaluator_model"),
                "failures": [f.to_dict() for f in failures],
                "failure_summary": summarize(failures),
                "evaluator_meta": {"retries": len(failures)},
            },
            # Lets a re-grade replace an event left behind by a grader that
            # died before finalizing. Safe because the daemon holds this
            # attempt's claim for the whole grade, so nothing else can
            # finalize between the check and the write.
            is_finalized=self.is_finalized,
        )
        result.metadata = {
            **(result.metadata or {}),
            "rubric_version_scored": scored_version,
            "eval_version": scored_version,  # legacy alias; same value, never rewritten
            "evaluation_retries": len(failures),
            "evaluation_failures": summarize(failures),
        }
        return result

    @staticmethod
    def _mask_infra_failure(result: ScoreBundle) -> None:
        """Replace raw evaluator-failure text with INFRA_FAILURE_FEEDBACK.

        Applied identically in every arm, on the one code path all three
        share, so no arm can receive a different account of the same failure.
        Only fires when no score was produced -- a scored attempt keeps its
        real feedback, however low the score.
        """
        if result.aggregated is None:
            result.feedback = INFRA_FAILURE_FEEDBACK

    # ------------------------------------------------- rubric advancement

    def _advance_rubric(
        self, store: EvolutionStore, snap: RubricSnapshot, cfg: pol.PolicyConfig
    ) -> RubricSnapshot:
        """One gate evaluation per finalized attempt, one diagnostic record.

        Three arms, one entry point. Static never gets here. Adaptive runs the
        frozen gates and then the triggers. Yoked ignores triggers entirely and
        replays its paired adaptive run's successful publications.
        """
        obs = store.observations(self.is_finalized)
        attempts = self._finalized_attempt_count()
        scored = len(obs)
        if cfg.mode == "yoked":
            return self._advance_yoked(store, snap, obs, cfg, attempts, scored)
        return self._advance_adaptive(store, snap, obs, cfg, attempts, scored)

    def _advance_adaptive(
        self,
        store: EvolutionStore,
        snap: RubricSnapshot,
        obs: list[Observation],
        cfg: pol.PolicyConfig,
        attempts: int,
        scored: int,
    ) -> RubricSnapshot:
        return self._advance_adaptive_checkpointed(store, snap, obs, cfg, attempts, scored)

    def _advance_adaptive_checkpointed(
        self,
        store: EvolutionStore,
        snap: RubricSnapshot,
        obs: list[Observation],
        cfg: pol.PolicyConfig,
        attempts: int,
        scored: int,
    ) -> RubricSnapshot:
        """Fixed opportunities to reconsider the rubric; the trajectory decides
        only whether and what changes, never when.

        Checkpoints are indices on the SCORED-observation clock: the proposer is
        invoked when the run has produced its Nth observation, not its Nth
        submission. An evaluation that failed (evaluator crash, timeout) is not
        an observation and does not advance a checkpoint, so infrastructure
        failures cannot consume a proposer's evidence window. Both counts are
        written on every record; the yoke replays the same scored indices.

        Every checkpoint gets an explicit ``status``: ``published``, ``abstained``
        (the proposer ran and found nothing admissible) or ``blocked`` (it was
        never invoked: the deadline or the rubric cap stopped it). Collapsing
        ``blocked`` into ``abstained`` would let a yoke read "the deadline had
        passed" as "the proposer examined the evidence and found nothing".
        """
        checkpoint_index = store.checkpoints_evaluated("adaptive")
        checkpoint_value, detail = pol.checkpoint_due(scored, cfg.checkpoints, checkpoint_index)
        gate = pol.Gate(True, "checkpoint schedule", pol.free_slots(snap, cfg), [])
        trig = pol.TriggerResult(
            f"checkpoint_{checkpoint_value}" if checkpoint_value is not None else None, detail
        )
        if checkpoint_value is None:
            store.write_trigger_decision(
                {
                    **self._diagnostic(snap, obs, cfg, attempts, scored, gate, trig),
                    "published": False,
                }
            )
            return snap

        blockers: list[str] = []
        if cfg.latest_publication_attempt is not None and attempts > cfg.latest_publication_attempt:
            # A bound on the REAL clock: a criterion published with no attempt
            # budget left to be scored against it inflates the publication count
            # without any exposure.
            blockers.append(
                f"too late to publish: {attempts} real attempts done, last allowed is "
                f"{cfg.latest_publication_attempt}"
            )
        slots = pol.free_slots(snap, cfg)
        if slots < 1:
            blockers.append(f"no free slots at max_criteria={cfg.max_criteria}")
        record = self._diagnostic(snap, obs, cfg, attempts, scored, gate, trig)
        record["checkpoint_index"] = checkpoint_index
        record["checkpoint_value"] = checkpoint_value
        if blockers:
            record["gate_open"] = False
            record["gate_blockers"] = blockers
            store.write_trigger_decision({**record, "published": False, "status": "blocked"})
            return snap

        window_ids = [o.attempt_id for o in obs[-cfg.window :]]
        trig = pol.TriggerResult(f"checkpoint_{checkpoint_value}", detail, window_ids)
        new, outcome = self._evolve(store, snap, obs, cfg, trig, gate)
        published = new.version != snap.version
        fields = self._publication_fields(new, outcome, published)
        fields.update(self._checkpoint_status(published, outcome))
        store.write_trigger_decision({**record, **fields})
        return new

    @staticmethod
    def _checkpoint_status(published: bool, outcome: prop.FilterOutcome) -> dict[str, Any]:
        """published / abstained / blocked, for a checkpoint that got as far
        as calling (or trying to call) the proposer.

        A proposer that never produced an answer (crashed, timed out, rejected by
        an exhausted account) is not the same claim as one that ran and found
        nothing; a record that collapsed them could not tell a quota rejection
        from a content-based abstention.
        """
        if published:
            return {"status": "published"}
        if outcome.proposer_error is not None:
            return {
                "status": "blocked",
                "gate_blockers": [f"proposer invocation failed: {outcome.proposer_error}"],
            }
        return {"status": "abstained"}

    def _publication_fields(
        self, new: RubricSnapshot, outcome: prop.FilterOutcome, published: bool
    ) -> dict[str, Any]:
        """The fields common to every publish-or-not record, adaptive or yoked."""
        return {
            "published": published,
            "accepted_count": len(outcome.accepted) if published else 0,
            "accepted_criteria": [
                {
                    "name": c.name,
                    "description": c.description,
                    "cited_evidence": c.cited_evidence,
                    "cited_source_id": c.cited_source_id,
                    "quote": c.quote,
                }
                for c in new.criteria
                if c.added_in_version == new.version
            ]
            if published
            else [],
            "rejected": [{"name": p.name, "reason": r} for p, r in outcome.rejected],
            "proposer_compute": outcome.proposer_meta,
            "published_version": new.version if published else None,
            "triggering_attempt": new.created_by_attempt_id,
            "triggering_agent": new.created_by_agent_id,
        }

    def _advance_yoked(
        self,
        store: EvolutionStore,
        snap: RubricSnapshot,
        obs: list[Observation],
        cfg: pol.PolicyConfig,
        attempts: int,
        scored: int,
    ) -> RubricSnapshot:
        return self._advance_yoked_checkpointed(
            store, snap, obs, cfg, attempts, scored, self._yoked_schedule()
        )

    def _advance_yoked_checkpointed(
        self,
        store: EvolutionStore,
        snap: RubricSnapshot,
        obs: list[Observation],
        cfg: pol.PolicyConfig,
        attempts: int,
        scored: int,
        schedule: dict[str, Any],
    ) -> RubricSnapshot:
        """Replay the adaptive arm's checkpoints (same scored-observation indices)
        with its realized accepted count and status at each one.

        A checkpoint where the adaptive proposer abstained is replayed as zero
        exposure at the same index, not skipped. A checkpoint the adaptive arm
        never reached (``blocked``) has no well-defined count, so
        ``_yoked_schedule`` refuses such a schedule before this method runs.
        """
        checkpoints = [int(c) for c in schedule["checkpoints"]]
        counts = [int(c) for c in schedule["accepted_counts"]]
        checkpoint_index = store.checkpoints_evaluated("yoked")
        checkpoint_value, detail = pol.checkpoint_due(scored, checkpoints, checkpoint_index)
        base = {
            "mode": "yoked",
            "finalized_attempts": attempts,
            "scored_attempts": scored,
            "rubric_version": snap.version,
            "source_run": schedule.get("source_run"),
            "schedule_sha256": schedule.get("schedule_sha256"),
            "replay_detail": detail,
        }
        if checkpoint_value is None:
            store.write_trigger_decision({**base, "published": False})
            return snap

        base["checkpoint_index"] = checkpoint_index
        base["checkpoint_value"] = checkpoint_value
        # asynchronous grading can skip the intended index; the replay fires at the
        # first grade at or past it, and both numbers stay on the record
        base["intended_scored"] = checkpoint_value
        base["index_slip"] = scored - checkpoint_value
        want = counts[checkpoint_index]
        base["required_count"] = want
        if want == 0:
            # The adaptive proposer abstained here. Recording that without
            # calling the blind proposer keeps exposure exactly matched at
            # zero cost, and avoids asking it to manufacture a criterion that
            # would only have to be filtered back out to preserve the count.
            store.write_trigger_decision(
                {**base, "published": False, "accepted_count": 0, "status": "abstained"}
            )
            return snap

        blockers: list[str] = []
        if cfg.latest_publication_attempt is not None and attempts > cfg.latest_publication_attempt:
            # Adaptive published `want` criteria at this index without being
            # blocked; if this arm passes the real-attempt deadline first, the
            # required count cannot be produced: a replay failure, not a silent zero.
            blockers.append(
                f"too late to publish: {attempts} real attempts done, last allowed is "
                f"{cfg.latest_publication_attempt}"
            )
        if blockers:
            store.write_trigger_decision(
                {**base, "published": False, "gate_blockers": blockers, "status": "blocked"}
            )
            self._record_replay_failure(
                store, checkpoint_index + 1, f"needed {want} criteria; this arm's own {blockers[0]}"
            )
            return snap

        trig = pol.TriggerResult(f"yoked_checkpoint_{checkpoint_value}", detail, [])
        gate = pol.Gate(True, "yoked checkpoint replay", pol.free_slots(snap, cfg), [])
        new, outcome = self._evolve(
            store, snap, obs, cfg, trig, gate, blind=True, require_exactly=want
        )
        published = new.version != snap.version
        fields = self._publication_fields(new, outcome, published)
        fields.update(self._checkpoint_status(published, outcome))
        store.write_trigger_decision({**base, **fields})
        if not published:
            reason = (
                f"proposer invocation failed: {outcome.proposer_error}"
                if outcome.proposer_error is not None
                else f"needed {want} criteria, produced {len(outcome.accepted)}"
            )
            self._record_replay_failure(store, checkpoint_index + 1, reason)
        return new

    def _yoked_schedule(self) -> dict[str, Any]:
        """Load and verify the paired adaptive run's exported checkpoint schedule.

        A ``blocked`` checkpoint means the adaptive proposer was never invoked
        there ("the deadline had passed"), not "it examined the evidence and
        found nothing"; an incomplete schedule is missing checkpoints the
        adaptive run never reached. Either would replay an undefined exposure,
        so both void the pair before a single attempt of this arm is graded.
        """
        import hashlib

        rel = (self.args.get("evolution") or {}).get("yoked_schedule_file")
        if not rel:
            raise ValueError("evolution.mode is yoked but no yoked_schedule_file is configured")
        task_dir = self._task_dir()
        path = (task_dir / rel) if task_dir and not Path(rel).is_absolute() else Path(rel)
        payload = json.loads(path.read_text())
        if payload.get("schedule_kind") != "checkpoint":
            raise ValueError(f"yoked schedule {path} is not a checkpoint schedule")
        hashed = {
            "checkpoints": payload.get("checkpoints"),
            "accepted_counts": payload.get("accepted_counts"),
            "statuses": payload.get("statuses"),
            "complete": payload.get("complete"),
        }
        digest = hashlib.sha256(json.dumps(hashed, sort_keys=True).encode()).hexdigest()
        if digest != payload.get("schedule_sha256"):
            raise ValueError(
                f"yoked schedule {path} fails its own hash; it was edited after export"
            )
        statuses = payload.get("statuses") or []
        blocked = [
            cp
            for cp, st in zip(payload.get("checkpoints") or [], statuses, strict=False)
            if st == "blocked"
        ]
        if blocked:
            raise ValueError(
                f"yoked schedule {path} has blocked checkpoint(s) {blocked} -- the adaptive proposer "
                "was never invoked there (deadline or rubric cap); refusing to replay an undefined exposure"
            )
        if payload.get("complete") is False:
            raise ValueError(
                f"yoked schedule {path} is incomplete -- the adaptive run did not evaluate every "
                "configured checkpoint; refusing to replay a partial schedule"
            )
        return payload

    def _diagnostic(
        self,
        snap: RubricSnapshot,
        obs: list[Observation],
        cfg: pol.PolicyConfig,
        attempts: int,
        scored: int,
        gate: pol.Gate,
        trig: pol.TriggerResult,
    ) -> dict[str, Any]:
        """One explainable record per rubric evaluation: what was looked at, under
        which version, and why publication was or was not attempted."""
        here = [o for o in obs if o.rubric_version == snap.version]
        win = here[-cfg.window :]
        return {
            "mode": cfg.mode,
            "finalized_attempts": attempts,
            "scored_attempts": scored,
            "rubric_version": snap.version,
            "criteria": [c.name for c in snap.criteria],
            "gate_open": gate.allowed,
            "gate_blockers": gate.blockers,
            "window_attempt_ids": [o.attempt_id for o in win],
            "window_scores": {o.attempt_id: o.scores for o in win},
            "aggregate_values": [o.aggregated for o in win],
            "policy": {
                "checkpoints": list(cfg.checkpoints),
                "max_criteria": cfg.max_criteria,
                "window": cfg.window,
                "latest_publication_attempt": cfg.latest_publication_attempt,
            },
            "selected_trigger": trig.fired,
            "selected_detail": trig.detail,
        }

    def _record_replay_failure(self, store: EvolutionStore, index: int, reason: str) -> None:
        """A yoke that cannot reproduce a publication voids the paired block."""
        path = Path(self.private_dir) / "evolving" / "replay_failures.jsonl"
        logger.error("YOKE REPLAY FAILURE (publication %d): %s — this pair is void.", index, reason)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(
                json.dumps(
                    {
                        "at": utcnow(),
                        "publication": index,
                        "reason": reason,
                        "attempt_id": self._attempt_id(),
                    }
                )
                + "\n"
            )

    def _finalized_attempt_count(self) -> int:
        """Every finalized non-tune submission, whatever the evaluation did.

        Not the checkpoint clock (that is the scored-observation count): this is
        the real-attempt count behind ``latest_publication_attempt`` and the
        ``finalized_attempts`` field of every record. Crashed and timed-out
        evaluations count here because the attempt consumed budget.
        """
        n = 0
        for p in self._attempts_dir().glob("*.json"):
            try:
                a = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            meta = a.get("metadata") or {}
            # Only tune sweeps and soft-deleted records are excluded. NOT
            # budget_class "grader_error": the daemon stamps that on every
            # crash and timeout, so filtering it would drop precisely the
            # attempts this clock exists to keep — and an arm with two crashed
            # evaluations would then hit its update points two attempts later
            # than its twin.
            if meta.get("archived") or meta.get("budget_class") == BUDGET_CLASS_TUNE:
                continue
            status = a.get("status")
            if status is not None and status != "pending":
                n += 1
        return n

    def _evolve(
        self,
        store: EvolutionStore,
        snap: RubricSnapshot,
        obs: list[Observation],
        cfg: pol.PolicyConfig,
        trig: pol.TriggerResult,
        gate: pol.Gate,
        *,
        blind: bool = False,
        require_exactly: int | None = None,
    ) -> tuple[RubricSnapshot, prop.FilterOutcome]:
        """Propose, filter, and publish. Returns the snapshot and the outcome.

        ``blind`` is the yoked arm: same proposer, same model, same schema, same
        filters, same weights — but a prompt built from the brief and the rubric
        only, and no read of notes, feedback, artifacts or scores. That single
        switch is the treatment contrast.

        ``require_exactly`` is the yoke's replay obligation. Publishing a
        different number of criteria than the paired adaptive run would break
        the matched exposure the whole control depends on, so nothing is
        published and the caller voids the pair.
        """
        criteria = list(snap.criteria)
        new_version = snap.version + 1
        max_new = min(gate.free_slots, cfg.max_new_criteria_per_round)
        if require_exactly is not None:
            max_new = require_exactly

        # What a proposal is allowed to quote. The adaptive arm may quote the
        # feedback it was shown; the yoked arm may quote the brief. Same rule,
        # different evidence base — so the arms differ in what they can observe,
        # not in how strictly they are held.
        if blind:
            notes = prop.NoteBundle()
            context = self._stage_proposer_context(
                feedback={}, attempt_ids=[], blind=True, version=new_version
            )
            evidence_sources = context.sources
            prompt = prop.build_blind_prompt(
                snap=snap,
                task_text=self._task_text(),
                seed_names=[c["name"] for c in (self.args.get("criteria") or [])],
                max_new=max_new,
                evidence_context=context,
            )
        else:
            notes = prop.read_agent_notes(Path(self.private_dir).parent / "public" / "notes", cfg)
            feedback = self._feedback_across_agents(obs, trig.attempt_ids)
            context = self._stage_proposer_context(
                feedback=feedback,
                attempt_ids=list(feedback),
                blind=False,
                version=new_version,
            )
            evidence_sources = context.sources
            prompt = prop.build_prompt(
                snap=snap,
                trigger=trig.fired or "",
                trigger_detail=trig.detail,
                task_text=self._task_text(),
                feedback_by_attempt=feedback,
                notes=notes,
                max_new=max_new,
                evidence_context=context,
            )
        try:
            (context.root / "prompt.md").write_text(prompt)
            raw = prop.run_evolution_agent(
                model=cfg.proposer_model or self.args.get("evaluator_model", "sonnet"),
                prompt=prompt,
                scratch_cwd=context.root,
                timeout=cfg.proposer_timeout,
                **self._proposer_overrides(cfg),
            )
            (context.root / "response.json").write_text(
                json.dumps(raw, indent=2, sort_keys=True) + "\n"
            )
        except prop.EvolutionAgentError as e:
            (context.root / "error.txt").write_text(str(e) + "\n")
            logger.warning("proposer failed; rubric unchanged: %s", e)
            # proposer_error, not a plain empty outcome: the caller must not
            # record this as an abstention. Whatever the underlying cause
            # (crash, timeout, or a rejected/exhausted account -- see
            # _looks_like_usage_limit), the proposer never produced an answer,
            # so "it examined the evidence and found nothing" would be false.
            return snap, prop.FilterOutcome(proposer_error=str(e))
        finally:
            self._archive_proposer_context(context)
            shutil.rmtree(context.root, ignore_errors=True)

        proposer_meta = raw.get("_coral_proposer_meta") or {}
        outcome = prop.filter_proposals(
            raw.get("new_criteria") or [], snap, store, cfg, max_new, evidence_sources
        )
        outcome.proposer_meta = proposer_meta
        if not outcome.accepted:
            logger.info("no proposal survived filtering: %s", [r for _, r in outcome.rejected])
            return snap, outcome

        if not blind:
            # Derive attempt provenance from the mechanically verified source
            # instead of trusting the proposer to duplicate it correctly in a
            # second field. A source may be either the historical short form
            # (the attempt id itself) or a staged artifact path.
            for proposal in outcome.accepted:
                source = proposal.cited_source_id
                attempt_id = source if source in feedback else None
                if source.startswith("attempts/"):
                    parts = source.split("/", 2)
                    if len(parts) >= 2 and parts[1] in feedback:
                        attempt_id = parts[1]
                if attempt_id is not None and attempt_id not in proposal.source_attempt_ids:
                    proposal.source_attempt_ids.append(attempt_id)

        new_criteria = prop.to_criteria(
            outcome.accepted, new_version, trig.fired or "", cfg.expansion_weight
        )
        if require_exactly is not None and len(new_criteria) != require_exactly:
            logger.error(
                "yoke needs exactly %d criteria, proposer yielded %d; publishing nothing.",
                require_exactly,
                len(new_criteria),
            )
            return snap, outcome
        if blind:
            for c in new_criteria:
                c.provenance = "trajectory_blind"
                # cited_source_id and quote survive: the admission gate has
                # already checked them against the brief verbatim, so they
                # cannot smuggle in a run observation, and keeping them is what
                # makes the yoke's gate auditable after the fact.
                # cited_evidence is free text nobody validated, so a proposer
                # could invent "attempt a3 had no focus ring" there. Cleared, so
                # "the yoke carries no run evidence" holds by construction.
                c.cited_evidence = ""
                c.source_attempt_ids = []
                c.source_note_ids = []
        criteria += new_criteria
        triggering = trig.attempt_ids[-1] if trig.attempt_ids else None
        new = RubricSnapshot(
            version=new_version,
            criteria=criteria,
            trigger=trig.fired or "",
            notes=str(raw.get("notes", ""))[:2000],
            parent_version=snap.version,
            created_by_attempt_id=triggering,
            created_by_agent_id=next((o.agent_id for o in obs if o.attempt_id == triggering), None),
        )
        store.publish_snapshot(new)
        if triggering:
            store.annotate_event(triggering, {"rubric_version_created_after": new_version})
        store.append_changelog(
            self._changelog(
                new, trigger_detail=trig.detail, rejected=outcome.rejected, notes=notes, raw=raw
            )
        )
        return new, outcome

    def _proposer_overrides(self, cfg: pol.PolicyConfig) -> dict[str, Any]:
        """Non-default proposer routing: a scripted command, or a runtime other than
        the default backend. Passed only when set."""
        out: dict[str, Any] = {}
        if cfg.proposer_command:
            out["command"] = self._proposer_command(cfg)
        if cfg.proposer_runtime != "claude_code":
            out["runtime"] = cfg.proposer_runtime
        return out

    def _proposer_command(self, cfg: pol.PolicyConfig) -> list[str]:
        """The scripted proposer command with ``{task_dir}`` resolved, so a task
        file can point at a script it ships without knowing where it is checked out."""
        task_dir = self._task_dir()
        return [
            part.replace("{task_dir}", str(task_dir)) if task_dir is not None else part
            for part in (cfg.proposer_command or [])
        ]

    def _task_dir(self) -> Path | None:
        """The task directory, from the `.coral/config_dir` breadcrumb."""
        try:
            return Path(
                (Path(self.private_dir).parent / "config_dir").read_text(encoding="utf-8").strip()
            )
        except OSError:
            return None

    def _write_manifest_once(self, cfg: pol.PolicyConfig, evo_cfg: dict[str, Any]) -> None:
        """Record what this run actually is, where agents cannot read it.

        Once the three arms share a byte-identical task name (so nothing about
        the arm reaches an agent, including through the results directory
        path), the arm is no longer recoverable from the run's file names. This
        manifest is where it lives instead: written to ``.coral/private/``,
        which is the one path agent runtimes are denied.

        Written once and never rewritten, so a resumed run cannot quietly
        change the conditions it claims to have run under. A conflicting
        rewrite attempt is logged rather than applied.
        """
        path = Path(self.private_dir) / "run_manifest.json"
        arm = cfg.mode
        manifest = {
            "arm": arm,
            "written_at": utcnow(),
            "evaluator_model": self.args.get("evaluator_model"),
            "evaluator_max_turns": self.args.get("evaluator_max_turns"),
            "policy": dataclasses.asdict(cfg),
            "yoked_schedule_file": evo_cfg.get("yoked_schedule_file"),
            "seed_criteria": self.args.get("criteria") or [],
        }
        if path.exists():
            try:
                old = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                return
            # Round-trip before comparing. `policy` comes from dataclasses.asdict,
            # so update_schedule is a tuple in memory and a list once written;
            # comparing the two directly reported drift on every single call and
            # would have trained us to ignore a warning that matters.
            fresh = json.loads(json.dumps(manifest, sort_keys=True))
            drift = {k for k in fresh if k != "written_at" and old.get(k) != fresh[k]}
            if drift:
                logger.error(
                    "run manifest drift on fields %s; keeping the original manifest. "
                    "This run's conditions no longer match what it started under.",
                    sorted(drift),
                )
            return
        # Unique temp per call: concurrent graders all reach here on the first
        # round of evaluations, and a shared temp name means one thread renames
        # the file out from under another.
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".manifest.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(manifest, f, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    @staticmethod
    def _last_evolution_index(snap: RubricSnapshot, obs: list[Observation]) -> int | None:
        if snap.created_by_attempt_id is None:
            return None
        for i, o in enumerate(obs):
            if o.attempt_id == snap.created_by_attempt_id:
                return i + 1
        return None

    # ---------------------------------------------------------- delegation

    def _delegate(self, criteria: list[dict[str, Any]]) -> ScoreBundle:
        self.inner.config = dataclasses.replace(
            self.config, args={**self.config.args, "criteria": criteria}
        )
        self.inner.codebase_path = self.codebase_path
        self.inner.private_dir = self.private_dir
        self.inner.tasks = self.tasks
        self.inner.island_id = getattr(self, "island_id", None)
        result = self.inner.evaluate()
        return self.bundle(float(result)) if isinstance(result, (int, float)) else result

    def _evaluate_with_retries(
        self, criteria: list[dict[str, Any]], cfg: pol.PolicyConfig, attempt_id: str
    ) -> tuple[ScoreBundle, list[FailureRecord]]:
        """Retry against the *same* snapshot; first success wins, never best-of."""
        failures: list[FailureRecord] = []
        result: ScoreBundle | None = None
        for i in range(1 + max(0, cfg.max_evaluation_retries)):
            result = self._delegate(criteria)
            if result.aggregated is not None:
                return result, failures
            log_path_fn = getattr(self.inner, "evaluator_log_path", None)
            log_info = inspect_evaluator_log(log_path_fn(attempt_id) if log_path_fn else None)
            explanation = " ".join(
                [result.feedback or ""]
                + [s.explanation or "" for s in (result.scores or {}).values()]
            )
            code = classify_generic(explanation, log_info)
            hook = getattr(self.inner, "classify_failure", None)
            if code is FailureCode.UNKNOWN and hook:
                code = hook(result, log_info) or FailureCode.UNKNOWN
            failures.append(FailureRecord(code, i + 1, explanation, log_info))
            logger.warning("evaluation %d failed (%s)", i + 1, code.value)
            if code is FailureCode.ACCOUNT_SESSION_LIMIT:
                # An exhausted usage window holds until it resets, hours away; a
                # retry cannot succeed and only burns quota the next attempt needs.
                logger.error(
                    "usage window exhausted; not retrying attempt %s (retrying would only "
                    "consume more quota)",
                    attempt_id,
                )
                break
        return result, failures  # type: ignore[return-value]

    # ------------------------------------------------------------ context

    def _attempt_id(self) -> str:
        meta = (self.tasks[0].metadata or {}) if self.tasks else {}
        return str(meta.get("commit_hash") or "unknown-attempt")

    def _agent_id(self) -> str | None:
        return ((self.tasks[0].metadata or {}) if self.tasks else {}).get("agent_id")

    def _attempts_dir(self) -> Path:
        return Path(self.private_dir).parent / "public" / "attempts"

    def is_finalized(self, attempt_id: str) -> bool:
        """True once CORAL's daemon has written a terminal status for the attempt."""
        try:
            status = json.loads((self._attempts_dir() / f"{attempt_id}.json").read_text()).get(
                "status"
            )
        except (OSError, json.JSONDecodeError):
            return False
        return status is not None and status != "pending"

    def _task_text(self) -> str:
        if self.tasks:
            t = self.tasks[0]
            return f"{getattr(t, 'name', '')}\n\n{getattr(t, 'description', '')}"
        return str(self.args.get("task_description", ""))

    def _feedback_across_agents(
        self, obs: list[Observation], attempt_ids: list[str]
    ) -> dict[str, str]:
        """One attempt per distinct agent from the trigger window, so the
        evolution agent generalizes across solution strategies."""
        chosen, seen = [], set()
        for o in reversed(obs):
            if o.attempt_id in attempt_ids and o.agent_id not in seen:
                chosen.append(o.attempt_id)
                seen.add(o.agent_id)
        chosen += [a for a in attempt_ids if a not in chosen]
        out = {}
        for aid in chosen[:4]:
            try:
                fb = json.loads((self._attempts_dir() / f"{aid}.json").read_text()).get("feedback")
            except (OSError, json.JSONDecodeError):
                fb = None
            if fb:
                out[aid] = str(fb)
        return out

    def _stage_proposer_context(
        self,
        *,
        feedback: dict[str, str],
        attempt_ids: list[str],
        blind: bool,
        version: int,
    ) -> prop.EvidenceContext:
        """Freeze exactly what one proposer call may inspect.

        An inner grader may expose a persistent evidence directory. Old runs
        and other grader types simply fall back to complete attempt feedback.
        A unique, retained directory makes every proposal call auditable.
        """
        evidence_dirs: dict[str, Path] = {}
        hook = getattr(self.inner, "evolution_evidence_dir", None)
        if hook is not None and not blind:
            # The inner grader's framework attributes are normally assigned
            # just before it evaluates. Evolution can run on a daemon worker
            # whose inner has not evaluated anything yet, so private_dir was
            # unset and the hook raised AttributeError -- which crashed the
            # grade, and a burst of those consumed a whole publication window.
            self.inner.private_dir = self.private_dir
            self.inner.codebase_path = self.codebase_path
            for attempt_id in attempt_ids:
                try:
                    path = Path(hook(attempt_id))
                except Exception:
                    # Artifact evidence is an enrichment. Whatever an optional
                    # hook raises, the grade proceeds without it; a proposer
                    # with feedback only is a degraded input, not a failed
                    # attempt.
                    logger.warning("evidence hook failed for %s", attempt_id, exc_info=True)
                    continue
                if path.is_dir():
                    evidence_dirs[attempt_id] = path
        # Run outside the repository and run tree. Claude's restricted mode
        # confines file tools to this working directory; putting it under the
        # run itself would make the yoke's parent directories unnecessarily
        # close to its allowed boundary.
        root = Path(tempfile.mkdtemp(prefix=f"coral-proposer-v{version}-"))
        # stage_evidence_context requires a not-yet-existing leaf so it can
        # detect accidental reuse; mkdtemp reserves the name, then we remove
        # that empty leaf only.
        root.rmdir()
        return prop.stage_evidence_context(
            root=root,
            task_text=self._task_text(),
            feedback_by_attempt=feedback,
            evidence_dirs_by_attempt=evidence_dirs,
            blind=blind,
        )

    def _archive_proposer_context(self, context: prop.EvidenceContext) -> Path:
        """Keep the exact isolated input, prompt, output and usage metadata."""
        parent = Path(self.private_dir) / "evolving" / "proposer_contexts"
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / context.root.name
        shutil.copytree(context.root, target)
        return target

    def _seed_snapshot(self) -> RubricSnapshot:
        return RubricSnapshot(
            version=1,
            criteria=[
                Criterion(
                    name=c["name"],
                    description=c.get("description", ""),
                    weight=float(c.get("weight", 1.0)),
                    anchor=bool(c.get("anchor", False)),
                    provenance="task_specification",
                )
                for c in (self.args.get("criteria") or [])
            ],
            created_at=utcnow(),
        )

    # ---------------------------------------------------------- changelog

    def _changelog(
        self,
        snap: RubricSnapshot,
        *,
        trigger_detail: str = "",
        rejected: list | None = None,
        notes: prop.NoteBundle | None = None,
        raw: dict[str, Any] | None = None,
    ) -> str:
        lines = [
            f"## Version {snap.version}",
            f"- **Trigger:** {snap.trigger}",
            f"- **Parent:** v{snap.parent_version}",
        ]
        if trigger_detail:
            lines.append(f"- **Why:** {trigger_detail}")
        if snap.created_by_attempt_id:
            lines.append(
                f"- **Triggered by attempt:** `{snap.created_by_attempt_id}` (agent {snap.created_by_agent_id})"
            )
        if snap.notes:
            lines.append(f"- **Notes:** {snap.notes}")
        lines += ["", "### Active criteria"]
        for c in snap.criteria:
            tag = " (anchor)" if c.anchor else ""
            lines.append(
                f"- **{c.name}** (weight {c.weight}){tag} [{c.provenance}]: {c.description}"
            )
        if rejected:
            lines += ["", "### Proposals rejected this round"]
            lines += [f"- **{p.name}**: {reason}" for p, reason in rejected]
        if notes is not None:
            lines += ["", "### Agent notes supplied"]
            lines += [f"- {Path(p).name}" for p in notes.included] or ["- (none)"]
            lines += [f"- skipped {Path(p).name}: {why}" for p, why in notes.skipped]
        lines.append("\n---\n")
        return "\n".join(lines)
