## Heartbeat: Diagnosis

Analyze the causal relationship between your actions and the eval result.

### 1. What did you change?
List the specific edits and tool calls since the last eval. Be exact:
- Which files, which lines, what was the change?
- Which commands did you run?

### 2. What was the result?
- Previous score: check `coral log --agent {agent_id}` for your last two evals
- Current score: from the eval feedback above
- Did it improve, regress, or stay the same?

### 3. Why?
Explain the causal link between your changes and the score change:
- **If improved:** What specifically caused the improvement? Which part of your change mattered most? Could you push this further?
- **If regressed:** What broke? Was it a logic error, a wrong assumption, or a tool misuse? What did the error message or feedback tell you?
- **If unchanged:** Why didn't your change have an effect? Was it targeting the wrong bottleneck?

### 4. What did you learn?
One concrete takeaway that applies to future attempts:
- "Changing X affects Y because Z"
- "The grader measures A, so optimizing B doesn't help"
- "Running `coral eval` instead of testing manually gives different results because..."

### 5. Next action
Based on this diagnosis, what is the single most impactful thing to try next?
