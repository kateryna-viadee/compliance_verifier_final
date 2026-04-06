"""
Compliance Pipeline – Helper Functions (v8)
===========================================
Key changes vs v7
-----------------
* S3 always runs exactly 2 times (no tiebreaker 3rd run).
  Both runs' full outputs are stored with _1 / _2 suffixes in the winner row and
  in the final table.

* final_category is derived from s3_category_1 and s3_category_2:
    same category  → final_category = that category  (resolution = "agreement")
    different      → resolved by `strictness` parameter (resolution = "strictness"):
        conservative → most severe:  NON-COMPLIANT > NO EVIDENCE > COMPLIANT
        pragmatic    → least severe: COMPLIANT > NO EVIDENCE > NON-COMPLIANT

  SEVERITY = {"NON-COMPLIANT": 3, "NO EVIDENCE": 2, "COMPLIANT": 1}

* `strictness` is a new top-level input variable ("conservative" | "pragmatic").

* S4 runs exactly once per chunk (no conditional 2nd run).
  After the single run:
    s4_compliance_category == final_category → ambiguous_field = "no"
    s4_compliance_category != final_category → ambiguous_field = "yes"

* Two Excel outputs:
    intermediate  – one row per sub-run per step, both prompt inputs and outputs.
    final         – one row per (dataset_id, chunk_text), all pipeline stages in
                    wide format; both S3 run outputs appear with _1 / _2 suffixes;
                    ambiguous_field column present.

* 2 parallel workers and nonce-busting retained.
* Join key: (dataset_id, chunk_text).
* All categories normalised to UPPERCASE.
"""

import json
import re
import time
import concurrent.futures
from typing import Any, Dict, List, Literal, Optional, Tuple, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator
from tqdm import tqdm

from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

MAX_WORKERS = 4

# ─────────────────────────────────────────────────────────────────────────────
# SEVERITY / STRICTNESS
# ─────────────────────────────────────────────────────────────────────────────

SEVERITY = {
    "NON-COMPLIANT": 3,
    "NO EVIDENCE"  : 2,
    "COMPLIANT"    : 1,
}


def _resolve_category(cat1: str, cat2: str, strictness: str) -> str:
    """
    Resolve two different S3 categories to a single final_category.
    If they are the same, return that category directly.
    If different:
        conservative → pick the most severe (highest SEVERITY score)
        pragmatic    → pick the least severe (lowest SEVERITY score)
    Unknown/empty categories get score 0.
    """
    if cat1 == cat2:
        return cat1
    sev1 = SEVERITY.get(cat1, 0)
    sev2 = SEVERITY.get(cat2, 0)
    if strictness == "conservative":
        return cat1 if sev1 >= sev2 else cat2
    else:  # pragmatic
        return cat1 if sev1 <= sev2 else cat2


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _norm_cat(v: str) -> str:
    """Normalise a compliance category to UPPERCASE, stripped."""
    return str(v).strip().upper()


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class S1Output(BaseModel):
    reasoning: str
    rule_type: Literal["obligation", "prohibition", "timeframe", "procedure", "conditional", "none"]
    contains_compliance_rule: Literal["yes", "no"]


class S2Output(BaseModel):
    relevance_reasoning: str
    relevance: Literal["yes", "no"]
    requirement: str
    process_link: str

    @field_validator("relevance", mode="before")
    @classmethod
    def norm_relevance(cls, v):
        return str(v).strip().lower()


class S3Output(BaseModel):
    """Decision-tree compliance analysis (Prompt 3 only)."""
    rule_aspect: str
    extracted_process_segment: List[str]
    reasoning: str
    short_evidence: str
    category: str

    @field_validator("extracted_process_segment", mode="before")
    @classmethod
    def coerce_list(cls, v):
        return [v] if isinstance(v, str) else v

    @field_validator("category", mode="before")
    @classmethod
    def norm_cat(cls, v):
        return _norm_cat(v)


class S4AmbiguityOutput(BaseModel):
    ambiguous_term: str
    mapped_evidence: str
    assumption_needed: Literal["Yes", "No"]
    assumption: str
    compliance_category: str

    @field_validator("compliance_category", mode="before")
    @classmethod
    def norm_cat(cls, v):
        return _norm_cat(v)


# ─────────────────────────────────────────────────────────────────────────────
# LLM FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def make_llm(azure_endpoint: str, api_key: str, api_version: str = "") -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=azure_endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment="gpt-5.4-US",
        seed=123,
    )


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_json_parse(text: str) -> dict:
    clean = re.sub(r"```json|```", "", str(text)).strip()
    try:
        return json.loads(clean)
    except Exception:
        return {}


def _extract_tokens(ai_message) -> dict:
    tok = {"tok_input": None, "tok_output": None, "tok_total": None}
    meta = getattr(ai_message, "usage_metadata", None) or {}
    tok["tok_input"]  = meta.get("input_tokens")
    tok["tok_output"] = meta.get("output_tokens")
    tok["tok_total"]  = meta.get("total_tokens")
    raw = (getattr(ai_message, "response_metadata", {}) or {}).get("usage") or {}
    if tok["tok_input"]  is None: tok["tok_input"]  = raw.get("prompt_tokens")
    if tok["tok_output"] is None: tok["tok_output"] = raw.get("completion_tokens")
    if tok["tok_total"]  is None: tok["tok_total"]  = raw.get("total_tokens")
    return tok


def _extract_category_logprob(ai_message, field_name: str = "category") -> Optional[float]:
    """
    Locate the tokens that generate the value of `field_name` inside the JSON
    response and return exp(sum_of_their_logprobs) — i.e. the joint probability
    of that specific value.  Returns None when logprobs are not available.
    """
    meta = getattr(ai_message, "response_metadata", {}) or {}
    lp_content = (meta.get("logprobs") or {}).get("content") or []
    if not lp_content:
        return None

    tokens    = [item.get("token", "")    for item in lp_content]
    lps       = [item.get("logprob", 0.0) for item in lp_content]
    full_text = "".join(tokens)

    # Locate the field value: "category": "VALUE"
    pattern = re.compile(r'"' + re.escape(field_name) + r'"\s*:\s*"([^"]*)"')
    match   = pattern.search(full_text)
    if not match:
        return None

    val_start_char = match.start(1)
    val_end_char   = match.end(1)

    char_pos = 0
    lp_sum   = 0.0
    found    = False
    for tok, lp in zip(tokens, lps):
        tok_end      = char_pos + len(tok)
        overlap_s    = max(char_pos, val_start_char)
        overlap_e    = min(tok_end,  val_end_char)
        if overlap_s < overlap_e:
            weight  = (overlap_e - overlap_s) / max(len(tok), 1)
            lp_sum += lp * weight
            found   = True
        if char_pos >= val_end_char:
            break
        char_pos = tok_end

    return float(np.exp(lp_sum)) if found else None


def _llm_call(
    llm,
    template: str,
    variables: dict,
    output_schema: Optional[Type[BaseModel]] = None,
    bust_cache: bool = True,
    static_system: str = "You are a helpful compliance analysis assistant.",
    nonce: Optional[str] = None,
    timeout_seconds: int = 60,
    max_retries: int = 2,
    return_logprobs: bool = False,
) -> Tuple[Any, bool, dict, Optional[float]]:
    """
    Unified LLM call.
    Returns (parsed_dict_or_str, parse_ok, tokens, logprob_score).
    logprob_score is None unless return_logprobs=True and logprobs are present.
    """
    if bust_cache:
        _n = nonce if nonce is not None else str(int(time.time() * 1000))
        variables = {**variables, "nonce": _n}
        prompt = ChatPromptTemplate.from_messages([
            ("system", static_system),
            ("human", "nonce:{nonce}\n\n" + template),
        ])
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", static_system),
            ("human", template),
        ])

    active_llm = llm.bind(logprobs=True) if return_logprobs else llm

    if output_schema is not None:
        chain = prompt | active_llm.with_structured_output(output_schema, include_raw=True)
    else:
        chain = prompt | active_llm

    last_exc = None
    for attempt in range(1, max_retries + 2):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(chain.invoke, variables)
                raw = fut.result(timeout=timeout_seconds)
        except Exception as e:
            last_exc = e
            if attempt <= max_retries:
                time.sleep(5 * attempt)
            continue

        if output_schema is not None:
            ai_msg    = raw.get("raw")
            parsed    = raw.get("parsed")
            parse_err = raw.get("parsing_error")
            tokens    = _extract_tokens(ai_msg) if ai_msg else {}
            lp_score  = _extract_category_logprob(ai_msg) if (return_logprobs and ai_msg) else None

            if parsed is not None and parse_err is None:
                return parsed.model_dump(), True, tokens, lp_score

            content     = getattr(ai_msg, "content", "") if ai_msg else ""
            parsed_dict = _safe_json_parse(content)
            if parsed_dict:
                return parsed_dict, False, tokens, lp_score

            if attempt <= max_retries:
                time.sleep(5 * attempt)
            continue
        else:
            tokens   = _extract_tokens(raw)
            lp_score = _extract_category_logprob(raw) if return_logprobs else None
            return raw.content, True, tokens, lp_score

    return {}, False, {}, None


def _tok_cols(prefix: str, tokens: dict) -> dict:
    return {f"{prefix}_{k}": v for k, v in tokens.items()}


# ─────────────────────────────────────────────────────────────────────────────
# TIEBREAKER LOGIC  (used by S2 only in v8)
# ─────────────────────────────────────────────────────────────────────────────

def _run_tiebreaker(
    llm,
    template: str,
    variables: dict,
    output_schema: Type[BaseModel],
    category_col: str,
    step_name: str = "step",
    base_nonce: Optional[str] = None,
    return_logprobs: bool = False,
) -> Tuple[dict, List[dict], str, Optional[float]]:
    """
    Two-run tiebreaker (used by S2):
      Run 1 + Run 2 → same category  → resolution = "agreement", return run-1 result
                   → different       → Run 3        → resolution = "tiebreaker", return run-3 result

    Returns:
        winner          – parsed result dict of the winning run
        subrun_records  – list of raw sub-run data dicts (2 or 3 entries)
        resolution      – "agreement" | "tiebreaker"
        logprob_score   – confidence of the winning run's category (None if unavailable)
    """
    _base = base_nonce or str(int(time.time() * 1000))
    subrun_records = []

    def _single(run_idx: int, want_lp: bool = False) -> Tuple[dict, dict, float, Optional[float]]:
        nonce = f"{_base}_{step_name}_r{run_idx}"
        t0    = time.time()
        result, ok, tok, lp = _llm_call(
            llm, template, variables,
            output_schema=output_schema,
            bust_cache=True,
            nonce=nonce,
            return_logprobs=want_lp,
        )
        lat = round(time.time() - t0, 3)
        return (result if (ok and result) else {}), tok, lat, lp

    r1, tok1, lat1, lp1 = _single(1)
    r2, tok2, lat2, _   = _single(2)

    cat1 = _norm_cat(r1.get(category_col, ""))
    cat2 = _norm_cat(r2.get(category_col, ""))

    subrun_records.append({"run_idx": 1, "result": r1, "tok": tok1, "lat": lat1, "lp": lp1})
    subrun_records.append({"run_idx": 2, "result": r2, "tok": tok2, "lat": lat2, "lp": None})

    if cat1 == cat2 and cat1 != "":
        winner      = r1
        winner_lp   = lp1
        resolution  = "agreement"
    else:
        r3, tok3, lat3, lp3 = _single(3, want_lp=return_logprobs)
        subrun_records.append({"run_idx": 3, "result": r3, "tok": tok3, "lat": lat3, "lp": lp3})
        winner     = r3
        winner_lp  = lp3
        resolution = "tiebreaker"

    return winner, subrun_records, resolution, winner_lp


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: CHUNK CLASSIFICATION  (once per dataset, single run)
# ─────────────────────────────────────────────────────────────────────────────

def step_classify_chunks(
    chunks: List[Tuple[int, str]],
    llm,
    prompt_template: str,
    dataset_id: str = "",
    nonce: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Classify each chunk with a single deterministic run.
    Parallel with MAX_WORKERS=2.

    Returns:
        winner_df   – one row per chunk (used downstream)
        subruns_df  – same rows with input columns added (for intermediate table)
    """
    records = []
    _n = nonce or str(int(time.time() * 1000))

    def _process(chunk_tuple):
        cid, ctext = chunk_tuple
        t0 = time.time()
        parsed, ok, tok, _ = _llm_call(
            llm, prompt_template, {"chunk": ctext},
            output_schema=S1Output, bust_cache=True,
            nonce=f"{_n}_s1_{cid}",
        )
        lat = round(time.time() - t0, 3)
        return {
            "dataset_id":               dataset_id,
            "chunk_id":                 cid,
            "chunk_text":               ctext,
            # ── inputs ──
            "in_chunk":                 ctext,
            # ── outputs ──
            "s1_reasoning":             parsed.get("reasoning", ""),
            "s1_rule_type":             parsed.get("rule_type", ""),
            "contains_compliance_rule": parsed.get("contains_compliance_rule", ""),
            "s1_parse_ok":              ok,
            "s1_latency_s":             lat,
            **_tok_cols("s1", tok),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_process, c): c for c in chunks}
        for fut in tqdm(concurrent.futures.as_completed(futures),
                        total=len(chunks), desc="S1 classify", leave=False):
            records.append(fut.result())

    df = (pd.DataFrame(records)
          .sort_values("chunk_id")
          .reset_index(drop=True))

    winner_df  = df.drop(columns=["in_chunk"], errors="ignore")
    subruns_df = df.copy()
    subruns_df["subrun_id"] = 1
    return winner_df, subruns_df


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: RELEVANCE  (once per dataset, tiebreaker logic — unchanged from v7)
# ─────────────────────────────────────────────────────────────────────────────

def step_relevance_tiebreaker(
    df_chunks: pd.DataFrame,
    process: str,
    llm,
    prompt_template: str,
    dataset_id: str = "",
    nonce: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run relevance prompt with tiebreaker (2 runs; optional 3rd if disagreement).
    Parallel with MAX_WORKERS=2.

    Returns:
        winner_df   – one row per chunk
        subruns_df  – one row per sub-run (2 or 3) with inputs + outputs
    """
    winner_records  = []
    subrun_records  = []
    _n = nonce or str(int(time.time() * 1000))

    def _process(row):
        ctext     = row["chunk_text"]
        variables = {"chunk": ctext, "process": process}

        winner, subs, resolution, _ = _run_tiebreaker(
            llm, prompt_template, variables, S2Output,
            category_col="relevance",
            step_name="s2",
            base_nonce=f"{_n}_{row.get('chunk_id', ctext[:12])}",
            return_logprobs=False,
        )

        sub_rows = []
        for sr in subs:
            r   = sr["result"]
            tok = sr["tok"]
            sub_rows.append({
                "dataset_id":      dataset_id,
                "chunk_text":      ctext,
                "subrun_id":       sr["run_idx"],
                "in_chunk":        ctext,
                "s2_relevance":    str(r.get("relevance", "")).lower(),
                "s2_requirement":  r.get("requirement", ""),
                "s2_process_link": r.get("process_link", ""),
                "s2_reasoning":    r.get("relevance_reasoning", ""),
                "s2_parse_ok":     bool(r),
                "s2_latency_s":    sr["lat"],
                **_tok_cols("s2", tok),
            })

        winner_row = {
            "dataset_id":      dataset_id,
            "chunk_text":      ctext,
            "s2_relevance":    str(winner.get("relevance", "no")).lower(),
            "s2_requirement":  winner.get("requirement", ""),
            "s2_process_link": winner.get("process_link", ""),
            "s2_reasoning":    winner.get("relevance_reasoning", ""),
            "s2_resolution":   resolution,
            "s2_runs_used":    len(subs),
        }
        return winner_row, sub_rows

    col_names  = list(df_chunks.columns)
    rows_dicts = [dict(zip(col_names, r)) for r in df_chunks.itertuples(index=False)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_process, row): row for row in rows_dicts}
        for fut in tqdm(concurrent.futures.as_completed(futures),
                        total=len(rows_dicts), desc="S2 relevance", leave=False):
            w, subs = fut.result()
            winner_records.append(w)
            subrun_records.extend(subs)

    return pd.DataFrame(winner_records), pd.DataFrame(subrun_records)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: COMPLIANCE ANALYSIS  (always 2 runs, strictness-based resolution)
# ─────────────────────────────────────────────────────────────────────────────

def step_compliance_dual(
    df_relevant: pd.DataFrame,
    llm,
    prompt_template: str,
    strictness: str = "conservative",
    dataset_id: str = "",
    nonce: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run compliance analysis (P3 prompt) exactly 2 times per chunk.

    Resolution logic:
        s3_category_1 == s3_category_2  → final_category = that category
                                           resolution = "agreement"
        s3_category_1 != s3_category_2  → final_category resolved by `strictness`
                                           resolution = "strictness"

    Both runs' full outputs are stored with _1 / _2 suffixes in the winner row.
    Category log-probability is extracted for both runs.
    Parallel with MAX_WORKERS=2.

    Returns:
        winner_df   – one row per chunk (both run outputs + final_category)
        subruns_df  – two rows per chunk with inputs + outputs
    """
    winner_records = []
    subrun_records = []
    _n = nonce or str(int(time.time() * 1000))

    def _single_run(variables: dict, run_idx: int, base: str) -> Tuple[dict, dict, float, Optional[float]]:
        nonce_val = f"{base}_s3_r{run_idx}"
        t0 = time.time()
        result, ok, tok, lp = _llm_call(
            llm, prompt_template, variables,
            output_schema=S3Output,
            bust_cache=True,
            nonce=nonce_val,
            return_logprobs=True,
        )
        lat = round(time.time() - t0, 3)
        return (result if (ok and result) else {}), tok, lat, lp

    def _process(row):
        ctext        = row["chunk_text"]
        requirement  = row["s2_requirement"]
        process_link = row["s2_process_link"]
        variables    = {"requirement": requirement, "process_link": process_link}
        base         = f"{_n}_{ctext[:20]}"

        r1, tok1, lat1, lp1 = _single_run(variables, 1, base)
        r2, tok2, lat2, lp2 = _single_run(variables, 2, base)

        cat1 = _norm_cat(r1.get("category", ""))
        cat2 = _norm_cat(r2.get("category", ""))

        if cat1 == cat2 and cat1 != "":
            resolution    = "agreement"
            final_cat     = cat1
            winning_reasoning = r1.get("reasoning", "")
        else:
            resolution    = "strictness"
            final_cat     = _resolve_category(cat1, cat2, strictness)
            # Use the reasoning from whichever run produced final_cat
            winning_reasoning = r1.get("reasoning", "") if final_cat == cat1 else r2.get("reasoning", "")

        # ── sub-run rows ─────────────────────────────────────────────────────
        sub_rows = []
        for run_idx, r, tok, lat, lp in [
            (1, r1, tok1, lat1, lp1),
            (2, r2, tok2, lat2, lp2),
        ]:
            sub_rows.append({
                "dataset_id":               dataset_id,
                "chunk_text":               ctext,
                "subrun_id":                run_idx,
                "in_requirement":           requirement,
                "in_process_link":          process_link,
                "s3_category":              _norm_cat(r.get("category", "")),
                "s3_reasoning":             r.get("reasoning", ""),
                "s3_rule_aspect":           r.get("rule_aspect", ""),
                "s3_short_evidence":        r.get("short_evidence", ""),
                "s3_segment":               str(r.get("extracted_process_segment", [])),
                "s3_parse_ok":              bool(r),
                "s3_category_confidence":   lp,
                "s3_latency_s":             lat,
                **_tok_cols("s3", tok),
            })

        # ── winner row (both runs exposed with _1 / _2 suffixes) ────────────
        winner_row = {
            "dataset_id":                 dataset_id,
            "chunk_text":                 ctext,
            "s2_requirement":             requirement,
            "s2_process_link":            process_link,
            # Run 1
            "s3_category_1":              cat1,
            "s3_reasoning_1":             r1.get("reasoning", ""),
            "s3_rule_aspect_1":           r1.get("rule_aspect", ""),
            "s3_short_evidence_1":        r1.get("short_evidence", ""),
            "s3_segment_1":               str(r1.get("extracted_process_segment", [])),
            "s3_category_confidence_1":   lp1,
            # Run 2
            "s3_category_2":              cat2,
            "s3_reasoning_2":             r2.get("reasoning", ""),
            "s3_rule_aspect_2":           r2.get("rule_aspect", ""),
            "s3_short_evidence_2":        r2.get("short_evidence", ""),
            "s3_segment_2":               str(r2.get("extracted_process_segment", [])),
            "s3_category_confidence_2":   lp2,
            # Resolution
            "s3_resolution":              resolution,
            # Winning reasoning forwarded to S4 as corrected_reasoning
            "s3_reasoning":               winning_reasoning,
            # Final category (used by S4 for ambiguous_field comparison)
            "final_category":             final_cat,
        }
        return winner_row, sub_rows

    rows_dicts = df_relevant.to_dict(orient="records")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_process, row): row for row in rows_dicts}
        for fut in tqdm(concurrent.futures.as_completed(futures),
                        total=len(rows_dicts), desc="S3 compliance (dual)", leave=False):
            w, subs = fut.result()
            winner_records.append(w)
            subrun_records.extend(subs)

    return pd.DataFrame(winner_records), pd.DataFrame(subrun_records)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: AMBIGUITY  (single run, ambiguous_field flag)
# ─────────────────────────────────────────────────────────────────────────────

def step_ambiguity_single(
    df_s3: pd.DataFrame,
    llm,
    prompt_template: str,
    dataset_id: str = "",
    nonce: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run ambiguity check for ALL chunks from S3 (regardless of category).
    Always exactly ONE run per chunk.

    After the single run:
        s4_compliance_category == final_category → ambiguous_field = "no"
        s4_compliance_category != final_category → ambiguous_field = "yes"

    Parallel with MAX_WORKERS=2.

    Returns:
        winner_df   – one row per chunk (includes ambiguous_field)
        subruns_df  – one row per chunk with inputs + outputs
    """
    winner_records = []
    subrun_records = []
    _n = nonce or str(int(time.time() * 1000))

    def _process(row):
        ctext               = row["chunk_text"]
        requirement         = row["s2_requirement"]
        process_link        = row["s2_process_link"]
        final_category      = _norm_cat(row.get("final_category", ""))
        s3_reasoning        = row.get("s3_reasoning", "")   # winning reasoning from S3

        variables = {
            "rule":                requirement,
            "process_sentence":    process_link,
            "corrected_reasoning": s3_reasoning,
            "corrected_category":  final_category,
        }

        nonce_val = f"{_n}_s4_{ctext[:20]}_r1"
        t0 = time.time()
        result, ok, tok, _ = _llm_call(
            llm, prompt_template, variables,
            output_schema=S4AmbiguityOutput,
            bust_cache=True,
            nonce=nonce_val,
        )
        lat = round(time.time() - t0, 3)
        r = result if (ok and result) else {}

        s4_cat = _norm_cat(r.get("compliance_category", ""))
        ambiguous_field = "yes" if (s4_cat != "" and s4_cat != final_category) else "no"

        sub_row = {
            "dataset_id":               dataset_id,
            "chunk_text":               ctext,
            "subrun_id":                1,
            "in_rule":                  requirement,
            "in_process_sentence":      process_link,
            "in_corrected_reasoning":   s3_reasoning,
            "in_corrected_category":    final_category,
            "s4_ambiguous_term":        r.get("ambiguous_term", ""),
            "s4_mapped_evidence":       r.get("mapped_evidence", ""),
            "s4_assumption_needed":     r.get("assumption_needed", ""),
            "s4_assumption":            r.get("assumption", ""),
            "s4_compliance_category":   s4_cat,
            "s4_parse_ok":              bool(r),
            "s4_latency_s":             lat,
            **_tok_cols("s4", tok),
        }

        winner_row = {
            "dataset_id":               dataset_id,
            "chunk_text":               ctext,
            "s4_ambiguous_term":        r.get("ambiguous_term", ""),
            "s4_mapped_evidence":       r.get("mapped_evidence", ""),
            "s4_assumption_needed":     r.get("assumption_needed", ""),
            "s4_assumption":            r.get("assumption", ""),
            "s4_compliance_category":   s4_cat,
            "ambiguous_field":          ambiguous_field,
        }
        return winner_row, sub_row

    rows_dicts = df_s3.to_dict(orient="records")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_process, row): row for row in rows_dicts}
        for fut in tqdm(concurrent.futures.as_completed(futures),
                        total=len(rows_dicts), desc="S4 ambiguity (single)", leave=False):
            w, sub = fut.result()
            winner_records.append(w)
            subrun_records.append(sub)

    return pd.DataFrame(winner_records), pd.DataFrame(subrun_records)


# ─────────────────────────────────────────────────────────────────────────────
# ONE PASS  (S1 → S2 → S3 → S4 for a single dataset)
# ─────────────────────────────────────────────────────────────────────────────

def run_dataset(
    dataset_id: str,
    document: List,
    process: str,
    llm,
    prompts: Dict[str, str],
    strictness: str = "conservative",
    on_progress=None,
) -> Dict[str, pd.DataFrame]:
    """
    Run the full pipeline (S1 → S4) for one dataset.
    `strictness` controls final_category resolution when S3 runs disagree:
        "conservative" → most severe  (NON-COMPLIANT > NO EVIDENCE > COMPLIANT)
        "pragmatic"    → least severe (COMPLIANT > NO EVIDENCE > NON-COMPLIANT)
    `on_progress` optional callback(str) for streaming progress to the frontend.
    Returns a dict of DataFrames keyed by step name.
    """
    def _emit(msg: str):
        print(f"  {msg}")
        if on_progress:
            on_progress(msg)

    _n = str(int(time.time() * 1000))
    # Accept either (id, text) tuples or plain strings
    if document and isinstance(document[0], (list, tuple)):
        chunks = [(cid, ctext) for cid, ctext in document]
    else:
        chunks = [(i + 1, chunk) for i, chunk in enumerate(document)]

    print(f"\n{'='*60}")
    print(f"  Dataset   : {dataset_id}  |  chunks: {len(chunks)}")
    print(f"  Strictness: {strictness}")
    print('='*60)

    # ── S1 ───────────────────────────────────────────────────────────────────
    _emit(f"[S1/4] Classification: processing {len(chunks)} chunks...")
    df_s1, df_s1_subs = step_classify_chunks(
        chunks, llm, prompts["classification"],
        dataset_id=dataset_id,
        nonce=f"{_n}_s1",
    )
    df_s1_filtered = df_s1[df_s1["contains_compliance_rule"] != "no"][
        ["dataset_id", "chunk_id", "chunk_text"]
    ].copy()
    _emit(f"[S1/4] Classification: {len(df_s1_filtered)}/{len(df_s1)} contain compliance rules")

    if df_s1_filtered.empty:
        _emit("[S1/4] No compliance rules found — skipping S2-S4")
        return {
            "s1_winner": df_s1, "s1_subruns": df_s1_subs,
            "s2_winner": pd.DataFrame(), "s2_subruns": pd.DataFrame(),
            "s3_winner": pd.DataFrame(), "s3_subruns": pd.DataFrame(),
            "s4_winner": pd.DataFrame(), "s4_subruns": pd.DataFrame(),
        }

    # ── S2 ───────────────────────────────────────────────────────────────────
    _emit(f"[S2/4] Relevance: checking {len(df_s1_filtered)} chunks...")
    df_s2, df_s2_subs = step_relevance_tiebreaker(
        df_s1_filtered, process, llm, prompts["relevance"],
        dataset_id=dataset_id,
        nonce=f"{_n}_s2",
    )
    df_s2_filtered = df_s2[df_s2["s2_relevance"] == "yes"].copy()
    _emit(f"[S2/4] Relevance: {len(df_s2_filtered)}/{len(df_s2)} relevant to process")

    if df_s2_filtered.empty:
        _emit("[S2/4] No relevant chunks — skipping S3-S4")
        return {
            "s1_winner": df_s1, "s1_subruns": df_s1_subs,
            "s2_winner": df_s2, "s2_subruns": df_s2_subs,
            "s3_winner": pd.DataFrame(), "s3_subruns": pd.DataFrame(),
            "s4_winner": pd.DataFrame(), "s4_subruns": pd.DataFrame(),
        }

    # ── S3 ───────────────────────────────────────────────────────────────────
    _emit(f"[S3/4] Compliance Analysis: analyzing {len(df_s2_filtered)} chunks (dual runs, {strictness})...")
    df_s3, df_s3_subs = step_compliance_dual(
        df_s2_filtered, llm, prompts["compliance_p3"],
        strictness=strictness,
        dataset_id=dataset_id,
        nonce=f"{_n}_s3",
    )
    _emit(f"[S3/4] Compliance Analysis: done")

    # ── S4 ───────────────────────────────────────────────────────────────────
    _emit(f"[S4/4] Ambiguity Analysis: checking {len(df_s3)} chunks...")
    df_s4, df_s4_subs = step_ambiguity_single(
        df_s3, llm, prompts["ambiguity"],
        dataset_id=dataset_id,
        nonce=f"{_n}_s4",
    )
    _emit(f"[S4/4] Ambiguity Analysis: done")

    return {
        "s1_winner":  df_s1,      "s1_subruns":  df_s1_subs,
        "s2_winner":  df_s2,      "s2_subruns":  df_s2_subs,
        "s3_winner":  df_s3,      "s3_subruns":  df_s3_subs,
        "s4_winner":  df_s4,      "s4_subruns":  df_s4_subs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXPERIMENT RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_experiment(
    dataset: List[Dict],
    llm,
    prompts: Dict[str, str],
    strictness: str = "conservative",
) -> Dict[str, List[pd.DataFrame]]:
    """
    Run the pipeline for every dataset entry.
    `strictness` ("conservative" | "pragmatic") is applied uniformly to all datasets.
    Returns a dict mapping step names → list of per-dataset DataFrames.
    """
    accumulated: Dict[str, List[pd.DataFrame]] = {
        "s1_winner":  [], "s1_subruns":  [],
        "s2_winner":  [], "s2_subruns":  [],
        "s3_winner":  [], "s3_subruns":  [],
        "s4_winner":  [], "s4_subruns":  [],
    }

    for entry in dataset:
        step_dfs = run_dataset(
            dataset_id=entry["dataset_id"],
            document=entry["document"],
            process=entry["process"],
            llm=llm,
            prompts=prompts,
            strictness=strictness,
        )
        for key, df in step_dfs.items():
            accumulated[key].append(df)

    return accumulated


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def build_intermediate_excel(
    accumulated: Dict[str, List[pd.DataFrame]],
    path: str,
) -> None:
    """
    Write one Excel file with separate sheets for each step's sub-run records.
    Each sheet contains both prompt inputs (in_*) and outputs for every sub-run.
    """
    sheet_map = {
        "S1_subruns":  "s1_subruns",
        "S2_subruns":  "s2_subruns",
        "S3_subruns":  "s3_subruns",
        "S4_subruns":  "s4_subruns",
        "S1_winners":  "s1_winner",
        "S2_winners":  "s2_winner",
        "S3_winners":  "s3_winner",
        "S4_winners":  "s4_winner",
    }

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, key in sheet_map.items():
            dfs = [df for df in accumulated.get(key, []) if not df.empty]
            if dfs:
                pd.concat(dfs, ignore_index=True).to_excel(
                    writer, sheet_name=sheet_name, index=False
                )

    print(f"  ✓ Intermediate table saved → {path}")


def build_final_table(
    accumulated: Dict[str, List[pd.DataFrame]],
) -> pd.DataFrame:
    """
    Build a wide final table with one row per (dataset_id, chunk_text).

    S3 columns appear with _1 / _2 suffixes for both run outputs.
    final_category comes from the S3 winner (strictness-resolved).
    ambiguous_field comes from S4 (yes/no comparison vs final_category).

    Chunks filtered at S1 appear with empty S2-S4 columns.
    Chunks filtered at S2 appear with empty S3-S4 columns.
    """
    def _concat(key: str) -> pd.DataFrame:
        dfs = [df for df in accumulated.get(key, []) if not df.empty]
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    df_s1 = _concat("s1_winner")
    df_s2 = _concat("s2_winner")
    df_s3 = _concat("s3_winner")
    df_s4 = _concat("s4_winner")

    if df_s1.empty:
        return pd.DataFrame()

    master = df_s1.copy()
    master["passed_s1"] = master["contains_compliance_rule"] != "no"

    if not df_s2.empty:
        s2_cols = [c for c in df_s2.columns if c not in ("dataset_id",)]
        master = master.merge(
            df_s2[["dataset_id", "chunk_text"] + [c for c in s2_cols if c != "chunk_text"]],
            on=["dataset_id", "chunk_text"],
            how="left",
        )
        master["passed_s2"] = master["s2_relevance"] == "yes"
    else:
        master["passed_s2"] = False

    if not df_s3.empty:
        # Exclude internal columns that should not be duplicated
        s3_exclude = {"dataset_id", "chunk_text", "s2_requirement", "s2_process_link",
                      "s3_reasoning"}   # s3_reasoning is internal (winning reasoning for S4)
        s3_keep = [c for c in df_s3.columns if c not in s3_exclude]
        master = master.merge(
            df_s3[["dataset_id", "chunk_text"] + s3_keep],
            on=["dataset_id", "chunk_text"],
            how="left",
        )

    if not df_s4.empty:
        s4_keep = [c for c in df_s4.columns if c not in ("dataset_id", "chunk_text")]
        master = master.merge(
            df_s4[["dataset_id", "chunk_text"] + s4_keep],
            on=["dataset_id", "chunk_text"],
            how="left",
        )

    # ── Column ordering ───────────────────────────────────────────────────────
    id_cols     = ["dataset_id", "chunk_id", "chunk_text"]
    s1_cols     = [c for c in master.columns if c.startswith("s1_") or c == "contains_compliance_rule"]
    filter_cols = ["passed_s1", "passed_s2"]
    s2_cols     = [c for c in master.columns if c.startswith("s2_")]
    # S3: group by run (_1 then _2), then resolution + final_category
    s3_run1_cols = [c for c in master.columns if c.endswith("_1") and c.startswith("s3_")]
    s3_run2_cols = [c for c in master.columns if c.endswith("_2") and c.startswith("s3_")]
    s3_meta_cols = [c for c in master.columns
                    if c.startswith("s3_") and not c.endswith("_1") and not c.endswith("_2")]
    s3_cols     = s3_run1_cols + s3_run2_cols + s3_meta_cols
    final_cat_col = ["final_category"] if "final_category" in master.columns else []
    s4_cols     = [c for c in master.columns if c.startswith("s4_")]
    ambig_col   = ["ambiguous_field"] if "ambiguous_field" in master.columns else []

    ordered = (
        id_cols + s1_cols + filter_cols + s2_cols
        + s3_cols + final_cat_col + s4_cols + ambig_col
    )
    ordered = [c for c in ordered if c in master.columns]
    rest    = [c for c in master.columns if c not in ordered]
    master  = master[ordered + rest]

    return master.reset_index(drop=True)


def save_outputs(
    accumulated: Dict[str, List[pd.DataFrame]],
    intermediate_path: str,
    final_path: str,
) -> pd.DataFrame:
    """
    Convenience wrapper: build and save both Excel outputs.
    Returns the final table DataFrame.
    """
    build_intermediate_excel(accumulated, intermediate_path)

    final = build_final_table(accumulated)
    with pd.ExcelWriter(final_path, engine="openpyxl") as writer:
        final.to_excel(writer, sheet_name="final", index=False)
    print(f"  ✓ Final table saved      → {final_path}  ({final.shape[0]} rows × {final.shape[1]} cols)")

    return final


# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT  (unchanged API)
# ─────────────────────────────────────────────────────────────────────────────

def save_checkpoint(accumulated: Dict[str, List[pd.DataFrame]], path: str) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for key, df_list in accumulated.items():
            dfs = [df for df in df_list if not df.empty]
            if dfs:
                pd.concat(dfs, ignore_index=True).to_excel(
                    writer, sheet_name=key[:31], index=False
                )
    print(f"  ✓ Checkpoint saved → {path}")


def load_checkpoint(path: str) -> Dict[str, pd.DataFrame]:
    xf = pd.ExcelFile(path)
    return {sheet: pd.read_excel(xf, sheet_name=sheet) for sheet in xf.sheet_names}
