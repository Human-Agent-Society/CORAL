# Criterion ledger -- mechanical fields only

Every criterion published in an adaptive or yoked run. Semantic annotations are in `annotations.json` and are single-researcher.

**Timing correction:** legacy `receipt` keys denote feedback-writing events, not verified reading. These are availability-based sensitivity scenarios, not lower/upper exposure bounds. Earlier rubric access and later feedback reading are possible.

**Failed evaluations are not receipt.** An evaluation that produced no score keeps its list of criteria in force while its text becomes an infrastructure notice, so it is excluded from every count here and recorded in `ledger.json` under `listed_in_force_without_feedback`. A logged context insertion counts as delivery of a criterion only when the inserted payload names it.

**receipt any→own** is the lag in minutes between the first scored attempt by *any* agent under the new version (feedback is public; agents read each other's) and each agent's own first scored attempt under it -- the range across the four agents. **eligible commits** are counted from both scenarios; **(naming)** is how many of those commits name the criterion.

## Worked trace: artifact-derived diagnosis versus a brief-derived criterion

This pair illustrates what trajectory access adds, and what it does not. The adaptive criterion is valuable because it identifies an implementation-level difference that the existing scores flattened. The yoked criterion is also sensible and behaviorally testable, but it can be produced directly from an explicit requirement in the brief. Plausible criterion wording alone is therefore not evidence that artifact access helped.

### Adaptive: Simulated State Durability

1. **Observed defect and evidence.** At the first adaptive publication, the proposer received three staged attempts. In `da574d38`, recommender status was recomputed with `Math.random() > 0.5` inside the render loop, so repeated lookups could disagree. In `835afed9`, the applicant view hard-coded `Pending` while the reviewer view derived status separately from an ID hash. In contrast, `c954f12a` assigned status once and persisted it with a timestamp. The existing Interaction Experience scores were 0.75, 0.70 and 0.70, so they did not express this consequential difference. The admitted quotation came from `835afed9`'s evaluator feedback: “the recommendation status tracking (pending/received indicators using application ID) isn't visible in the UI I explored.”

2. **Published criterion.** `Simulated State Durability` was added in rubric **v2** at checkpoint 8 (processed after 9 scored attempts). It required applicant, recommender, submission and reviewer state to remain stable across repeated reads and views, while allowing a simulated transition only if it was written to durable state.

3. **Availability and delivery.** The first scored v2 feedback was written for captain-nemo eight minutes after publication. All four agents subsequently received their own scored feedback carrying the criterion: captain-nemo at that first event, captain-ahab and jack-sparrow seven minutes later, and davy-jones eight minutes later. A public note then relayed the evolved criteria to the group. This historical run predates the context-insertion recorder, so these are evidence of public availability and own-feedback receipt, **not verified model-context delivery or proof that an agent read the text**.

4. **Subsequent changes.** The commit record contains targeted implementation responses. Captain-ahab replaced render-time randomness with persisted local-storage state and later added deterministic `receivedAt` transitions. Captain-nemo added local-storage persistence for submission state. Davy-jones explicitly replaced `Math.random()` with durable recommendation status. Jack-sparrow made related state-initialization and import fixes, but its commit text does not tie the change as directly to this criterion. Online scores on the new criterion rose from first to last observation for all four agents: ahab 0.30→0.50, nemo 0.25→0.90, davy 0.30→0.60 and jack 0.20→0.75. These sequences establish response consistent with the feedback; they do not by themselves establish causation or successful repair.

5. **Independent behavioral result.** Frozen check P1 tested the terminal artifacts through visible visitor workflows. Davy-jones's terminal artifact was classified `durable`. Ahab, Nemo and Jack were `status-not-revisitable`: the checker could not return through a visible route to the submitted status, so it could not verify stable repeated reads. Thus the trace shows an output-specific diagnosis, propagation, and targeted code response, but independently verifies complete terminal durability for only **one of four** adaptive artifacts.

### Yoked contrast: Draft Continuity and Portability

The yoked proposer had no artifacts, scores, feedback or agent notes. It quoted the brief's explicit requirement to “show an empty state if no draft exists and autosave locally, with an option to export/import a draft file to continue on another device,” expanded that clause into `Draft Continuity and Portability`, and published it in **v2** at the matched first checkpoint. It is a coherent and discriminative criterion, but its provenance is entirely task-level: it diagnoses no observed artifact and substantially overlaps the seed criterion Instruction Following.

All four yoked agents later had scored feedback containing the criterion, between zero and eleven minutes after the first public feedback event; again, this run predates verified context-delivery logging. None of the subsequent commit messages names the criterion. Some later changes concern autosave, import, or persisted drafts, but the record cannot distinguish responses to this criterion from responses to ordinary evaluator feedback or continued implementation.

Frozen check P2 still found meaningful differences in the terminal artifacts: captain-ahab preserved the sampled fields on reload but offered no import path; captain-nemo's application was not reachable; davy-jones truncated one sampled essay from 372 to 300 characters on both reload and round-trip; and jack-sparrow's closed application made the draft workflow not applicable. This shows that a brief-derived criterion can be useful. The sharper adaptive contribution is therefore **additional diagnostic information about actual implementations**, not merely the production of a plausible new requirement. In this pair, that informational advantage produced clearer targeted changes but only partial independently verified repair.

| task | arm | v | criterion | provenance | scored@pub | receipt any→own (min) | eligible commits own/any (naming) | later scored | spread all | distinct |
|---|---|---|---|---|---|---|---|---|---|---|
| fellowship | adaptive | 2 | Simulated State Durability | evaluator_feedback | 9 | 0–8 | 10/10 (1/1) | 12 | 0.8 | 9 |
| fellowship | adaptive | 2 | Simulated Dependency Traversability | evaluator_feedback | 9 | 0–8 | 10/10 (0/0) | 12 | 0.65 | 7 |
| fellowship | adaptive | 3 | Draft Continuity Round-Trip | evaluator_feedback | 13 | 0–10 | 7/7 (0/0) | 8 | 0.95 | 7 |
| fellowship | adaptive | 3 | Validation Signal Fidelity | evaluator_feedback | 13 | 0–10 | 7/7 (1/1) | 8 | 0.7 | 7 |
| fellowship | adaptive | 4 | Reviewer Adjudication Sufficiency | evaluator_feedback | 17 | 0–20 | 3/3 (0/0) | 4 | 0.65 | 4 |
| fellowship | adaptive | 4 | Purpose-Built Design Voice | evaluator_feedback | 17 | 0–20 | 3/3 (2/2) | 4 | 0.2 | 3 |
| fellowship | yoked | 2 | Draft Continuity and Portability | trajectory_blind | 8 | 0–11 | 10/10 (0/0) | 15 | 0.55 | 9 |
| fellowship | yoked | 2 | Recommender Request Lifecycle | trajectory_blind | 8 | 0–11 | 10/10 (0/0) | 15 | 0.6 | 8 |
| fellowship | yoked | 3 | Form Validation and Upload Failure Recovery | trajectory_blind | 12 | 0–12 | 7/7 (0/0) | 11 | 0.8 | 9 |
| fellowship | yoked | 3 | Reviewer Dashboard Filtering and Scoring State | trajectory_blind | 12 | 0–12 | 7/7 (0/0) | 11 | 0.3 | 7 |
| fellowship | yoked | 4 | Submission Confirmation, Receipt ID, and Downloadable Copy | trajectory_blind | 17 | 0–10 | 3/3 (0/0) | 6 | 0.25 | 4 |
| fellowship | yoked | 4 | Deadline-Bounded Draft Access | trajectory_blind | 17 | 0–10 | 3/3 (2/2) | 6 | 0.85 | 3 |
| museum | adaptive | 2 | Identity Specificity | evaluator_feedback | 9 | 0–6 | 10/10 (2/2) | 15 | 0.8 | 9 |
| museum | adaptive | 2 | Affordance Integrity | evaluator_feedback | 9 | 0–6 | 10/10 (3/3) | 15 | 0.35 | 4 |
| museum | adaptive | 3 | Content Legibility Under Viewport Constraint | evaluator_feedback | 13 | 0–7 | 6/6 (0/0) | 11 | 0.6 | 6 |
| museum | adaptive | 3 | Keyboard Operability of the Interaction Model | evaluator_feedback | 13 | 0–7 | 6/6 (0/0) | 11 | 1.0 | 6 |
| museum | adaptive | 4 | Curatorial Presence of the Art | evaluator_feedback | 17 | 0–7 | 2/2 (0/0) | 7 | 0.7 | 6 |
| museum | adaptive | 4 | Coherence of Stated Institutional Facts | evaluator_feedback | 17 | 0–7 | 2/2 (0/0) | 7 | 0.3 | 2 |
| museum | yoked | 2 | Institutional Identity Coherence | trajectory_blind | 8 | 0–4 | 5/5 (0/0) | 16 | 0.4 | 6 |
| museum | yoked | 2 | Dutch Contemporary-Art Institutional Specificity | trajectory_blind | 8 | 0–4 | 5/5 (0/0) | 16 | 0.15 | 4 |
| museum | yoked | 3 | Entry-Point Self-Sufficiency | trajectory_blind | 12 | 0–8 | 3/4 (0/0) | 12 | 0.05 | 2 |
| museum | yoked | 3 | Commitment to a Chosen Form | trajectory_blind | 12 | 0–8 | 3/4 (0/0) | 12 | 0.4 | 6 |

## Checkpoint outcomes

| task | arm | after N attempts | status | proposed | published | not published |
|---|---|---|---|---|---|---|
| fellowship | adaptive | 9 | **published** | Simulated State Durability, Simulated Dependency Traversability | Simulated Dependency Traversability, Simulated State Durability | – |
| fellowship | adaptive | 13 | **published** | Draft Continuity Round-Trip, Validation Signal Fidelity | Draft Continuity Round-Trip, Validation Signal Fidelity | – |
| fellowship | adaptive | 17 | **published** | Reviewer Adjudication Sufficiency, Purpose-Built Design Voice | Purpose-Built Design Voice, Reviewer Adjudication Sufficiency | – |
| fellowship | yoked | 8 | **published** | Draft Continuity and Portability, Recommender Request Lifecycle | Draft Continuity and Portability, Recommender Request Lifecycle | – |
| fellowship | yoked | 12 | **published** | Form Validation and Upload Failure Recovery, Reviewer Dashboard Filtering and Scoring State | Form Validation and Upload Failure Recovery, Reviewer Dashboard Filtering and Scoring State | – |
| fellowship | yoked | 17 | **published** | Submission Confirmation, Receipt ID, and Downloadable Copy, Deadline-Bounded Draft Access | Deadline-Bounded Draft Access, Submission Confirmation, Receipt ID, and Downloadable Copy | – |
| museum | adaptive | 9 | **published** | Identity Specificity, Affordance Integrity | Affordance Integrity, Identity Specificity | – |
| museum | adaptive | 13 | **published** | Content Legibility Under Viewport Constraint, Keyboard Operability of the Interaction Model | Content Legibility Under Viewport Constraint, Keyboard Operability of the Interaction Model | – |
| museum | adaptive | 17 | **published** | Curatorial Presence of the Art, Coherence of Stated Institutional Facts | Coherence of Stated Institutional Facts, Curatorial Presence of the Art | – |
| museum | yoked | 8 | **published** | Institutional Identity Coherence, Dutch Contemporary-Art Institutional Specificity | Dutch Contemporary-Art Institutional Specificity, Institutional Identity Coherence | – |
| museum | yoked | 12 | **published** | Entry-Point Self-Sufficiency, Commitment to a Chosen Form | Commitment to a Chosen Form, Entry-Point Self-Sufficiency | – |
| museum | yoked | 17 | **abstained** | Web-Native Accessible Delivery | – | Web-Native Accessible Delivery |
