# Pipeline v8 Updates Summary

## Changes Made

### 1. **Relevance Check (S2) - Simplified Output**
- **Before**: S2 could output "yes", "partially", or "no"
- **After**: S2 now outputs only **"yes"** or **"no"**
  - Chunks with `relevance = "yes"` continue to S3 & S4
  - Chunks with `relevance = "no"` are filtered out and stop processing
- **Location**: `backend/prompts/2_Relevance.txt` (already updated)
- **Code**: `backend/functions_pipeline_v8.py` line 798 already filters correctly: `df_s2_filtered = df_s2[df_s2["s2_relevance"] == "yes"].copy()`

### 2. **Category Naming - NOT ADDRESSED → NO EVIDENCE**
- **Before**: Compliance categories were `COMPLIANT`, `NON-COMPLIANT`, or `NOT ADDRESSED`
- **After**: Now using `COMPLIANT`, `NON-COMPLIANT`, or `NO EVIDENCE`
- **Severity Levels** (for strictness-based resolution):
  - Most Severe: `NON-COMPLIANT` (severity = 3)
  - Medium: `NO EVIDENCE` (severity = 2)
  - Least Severe: `COMPLIANT` (severity = 1)
- **Updated Files**:
  - `lib/mock-data.ts` - Updated mock segment categories
  - `backend/functions_pipeline_v8.py` - Uses `NO EVIDENCE` in severity mapping

### 3. **Right Panel Display - Reasoning Field**
- **What displays**: When you select a segment, the right panel shows:
  - **S3 Reasoning** (from the winning S3 run):
    - If both runs agree: Shows single reasoning with the agreed category
    - If runs differ: Shows reasoning from both Run 1 and Run 2 with their respective categories
  - **S4 Ambiguity Section**:
    - Ambiguous term (if identified)
    - Assumption reasoning (if needed)
    - Compliance category from S4 analysis
- **Variable Used**: `s3_reasoning_1` and/or `s3_reasoning_2` from the S3Output schema
  - These are populated from the `reasoning` field in the S3 compliance analysis prompt output

## Pipeline Flow with Updates

```
[Process + Regulations] 
    ↓
[S1: Classification] → Identify compliance rules
    ↓
[S2: Relevance Check] → yes/no → FILTER OUT "no"
    ↓
[S3: Compliance Analysis (Dual Runs)] → Two independent analyses
    ├─ Run 1: s3_category_1, s3_reasoning_1, s3_rule_aspect_1, s3_short_evidence_1
    ├─ Run 2: s3_category_2, s3_reasoning_2, s3_rule_aspect_2, s3_short_evidence_2
    ├─ Resolution: final_category (conservative = most severe wins)
    └─ Categories: COMPLIANT | NON-COMPLIANT | NO EVIDENCE
    ↓
[S4: Ambiguity Analysis] → Single run
    ├─ Identify ambiguous terms requiring assumptions
    ├─ Output: s4_ambiguous_term, s4_mapped_evidence, s4_assumption, s4_compliance_category
    └─ Flag: ambiguous_field = "yes" if S4 category ≠ final_category
    ↓
[Post-Processing] → BPMN matching, position compute, save to history
    ↓
[Output JSON] → Segments with full pipeline data + winning S3 run's evidence
```

## Key Differences from Earlier Versions

1. **S2 is simpler**: No more partial relevance - either relevant or not
2. **Categories are clearer**: "NO EVIDENCE" replaces "NOT ADDRESSED" throughout
3. **S3 runs identically**: Both runs use the same prompt/rules, no special first vs. second run logic
4. **Strictness applies uniformly**: Conservative/pragmatic affects all disagreements equally
5. **Display logic preserved**: Right panel still shows `s3_reasoning_1` and `s3_reasoning_2` for transparency

## Files Modified

- `backend/prompts/2_Relevance.txt` - S2 prompt (yes/no only)
- `backend/functions_pipeline_v8.py` - Severity mapping uses NO EVIDENCE
- `lib/mock-data.ts` - Mock data updated with NO EVIDENCE categories
- `backend/app.py` - Pipeline integration (already correct)

## Testing

To verify the updates work:
1. Start the backend: `python backend/app.py`
2. Select a process and regulation in the frontend
3. Click "Analyze"
4. Verify that:
   - S2 filtering only passes "yes" chunks to S3
   - Final categories show as COMPLIANT, NON-COMPLIANT, or NO EVIDENCE
   - Right panel displays s3_reasoning_1/s3_reasoning_2 when a segment is selected
