"""
Flask API backend for Compliance Verifier.

HOW TO USE:
-----------
1. Install dependencies:
       pip install flask flask-cors pandas openai python-dotenv sentence-transformers

2. Set your environment variables (in .env or export):
       OPENAI_API_KEY=your-key-here

3. In this file, replace the EXAMPLE data below with your real data:
       - Fill PROCESSES dict with your actual process texts
       - Fill REGULATIONS dict with your actual regulation chunk lists

4. Run the server:
       python backend/app.py

5. The API will be available at:
       http://localhost:5005

Endpoints:
  GET  /api/options   — returns available processes and regulation documents
  POST /api/analyze   — runs compliance analysis for selected process + regulation
  GET  /api/document  — (legacy) returns pre-computed results from final_2.xlsx
"""

import os
import sys
import re
import time
import ast
import json
import queue
import threading

from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import pandas as pd
from dotenv import load_dotenv
from openai import AzureOpenAI
from werkzeug.utils import secure_filename

# Import v8 pipeline functions
from functions_pipeline_v8 import (
    make_llm,
    run_dataset,
    build_final_table,
    save_outputs,
)
from sentence_transformers import SentenceTransformer
from openai import AzureOpenAI

# Add POC directory to path for BPMN utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "POC"))
try:
    from functions_POC import convert_bpmn_to_text, extract_bpmn_elements, find_best_matching_bpmn_element
    BPMN_UTILS_AVAILABLE = True
except ImportError:
    BPMN_UTILS_AVAILABLE = False
    print("[Warning] BPMN utilities not available - BPMN features disabled")

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── History folder path ──
HISTORY_FOLDER = os.path.join(os.path.dirname(__file__), "history")
os.makedirs(HISTORY_FOLDER, exist_ok=True)

# ── Sentence-transformer model (loaded once at startup) ──
st_model = SentenceTransformer("all-MiniLM-L6-v2")

# ── LLM client (v8 pipeline uses LangChain AzureChatOpenAI) ──
AZURE_ENDPOINT = "https://litellm.ai.viadee.cloud"
AZURE_API_KEY = os.getenv("OPENAI_API_KEY", "")
AZURE_API_VERSION = ""
load_dotenv()
print(f"🔑 API key loaded: {'YES' if os.getenv('OPENAI_API_KEY') else 'NO - KEY MISSING'}")
# Create v8 LLM instance
llm_v8 = make_llm(AZURE_ENDPOINT, AZURE_API_KEY, AZURE_API_VERSION)

# Create OpenAI client for BPMN conversion (still uses direct API)
openai_client = AzureOpenAI(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=AZURE_API_KEY,
    api_version=AZURE_API_VERSION,
)

# ── Load v8 prompts from files ──
def _load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

PROMPTS_V8 = {
    "classification": _load_prompt("1_Classification.txt"),
    "relevance": _load_prompt("2_Relevance.txt"),
    "compliance_p3": _load_prompt("3_Analysis.txt"),
    "ambiguity": _load_prompt("4_Ambiguity.txt"),
}


# =============================================================
# HARDCODED INPUTS — these are the inputs to the pipeline.
# Replace with your real process texts and regulation chunk lists.
# =============================================================

PROCESSES = {
    "merchant-onboarding": {
        "name": "Merchant Onboarding Process",
        "description": "End-to-end merchant onboarding workflow including identity verification, risk assessment, and account activation",
        "text": """
The merchant submits an online application form including business name, registration number, contact information, and requested payment services; An automated system checks the form for completeness and generates a case ID; Incomplete applications are returned to the merchant with specific instructions on missing fields.
A compliance analyst verifies the merchant's legal registration against the national business registry; The analyst also confirms the merchant's principal place of business through address validation services; Beneficial ownership verification is performed only when flagged by the automated risk scoring tool, not for all merchants.
The merchant's legal entity name and all beneficial owners are screened against all government-maintained sanctions and exclusion lists; Any match results in automatic rejection of the application; Screening results are logged and attached to the case file.
The merchant is assigned a risk category (low, medium, or high) based on its business type, geography, and transaction volume projections; High-risk merchants receive a general advisory notice but no additional due diligence procedures are applied beyond the standard verification; The risk category is recorded in the merchant profile.
Technical staff configure the merchant's payment processing environment with encryption, access controls, and tokenization of sensitive authentication data; All consumer data stored in the system is protected using AES-256 encryption at rest and TLS 1.3 in transit; A data protection impact assessment is completed and filed.
The merchant's point-of-sale or e-commerce system is integrated with the payment gateway; Technical staff run a series of test transactions to validate connectivity, latency, and error handling; Test results are documented and approved by a QA lead.
The merchant's account is enrolled in the batch-processed transaction monitoring system, which runs nightly scans to detect patterns indicative of fraud; Alerts are reviewed by the fraud operations team on the following business day; The system does not operate in real time.
The merchant reviews and signs the standard service agreement, which includes data handling terms, fee schedules, and dispute resolution clauses; The agreement includes a clause authorizing the provider to share anonymized transaction data with analytics partners for market research; The executed agreement is stored in the contract management system.
New team members supporting the merchant account attend a training session covering operational procedures, escalation paths, and compliance awareness; The training is delivered quarterly and covers general regulatory topics; Attendance records are maintained by HR.
Following successful completion of all prior steps, the merchant account is activated in the production environment; The merchant receives onboarding confirmation with login credentials and support contact details; A 30-day post-activation review is scheduled.
""",
    },
}


REGULATIONS = {
    "digital-payment-directive": {
        "name": "Digital Payment Services Directive",
        "description": "Federal Commerce Authority directive on digital payment services and consumer data safeguarding",
        "chunks": [
            {"chunk_id": "DPD-1", "chunk_text": "This Directive establishes a unified framework for the regulation of digital payment services and the safeguarding of consumer data within the jurisdiction of the Federal Commerce Authority."},
            {"chunk_id": "DPD-2", "chunk_text": "The provisions herein apply to all licensed payment service providers, payment facilitators, and affiliated merchants operating within the regulated marketplace."},
            {"chunk_id": "DPD-3", "chunk_text": "The Federal Commerce Authority recognizes the growing importance of digital commerce and the need to balance innovation with consumer protection."},
            {"chunk_id": "DPD-4", "chunk_text": "For the purposes of this Directive, 'payment service provider' refers to any entity authorized to initiate, process, or settle electronic payment transactions on behalf of consumers or merchants."},
            {"chunk_id": "DPD-5", "chunk_text": "'Consumer data' shall mean any personally identifiable information, financial account details, transaction histories, or behavioral data collected during the provision of payment services."},
            {"chunk_id": "DPD-6", "chunk_text": "'Sensitive authentication data' includes, but is not limited to, full card numbers, security codes, PINs, and biometric identifiers used for transaction authorization."},
            {"chunk_id": "DPD-7", "chunk_text": "All payment service providers shall conduct a comprehensive identity verification of each merchant prior to granting access to payment processing services."},
            {"chunk_id": "DPD-8", "chunk_text": "The identity verification process must include validation of the merchant's legal registration, beneficial ownership structure, and principal place of business."},
            {"chunk_id": "DPD-9", "chunk_text": "Payment service providers are prohibited from onboarding any merchant that appears on a government-maintained sanctions or exclusion list."},
            {"chunk_id": "DPD-10", "chunk_text": "Where a merchant operates in a high-risk category as defined in Annex II, the payment service provider shall apply enhanced due diligence measures appropriate to the level of risk."},
            {"chunk_id": "DPD-11", "chunk_text": "Verification records shall be retained for a minimum period of seven years from the date of merchant account closure."},
            {"chunk_id": "DPD-12", "chunk_text": "This chapter outlines the obligations of payment service providers with respect to consumer data collected during payment processing."},
            {"chunk_id": "DPD-13", "chunk_text": "Payment service providers shall implement adequate technical and organizational safeguards to protect consumer data against unauthorized access, disclosure, or destruction."},
            {"chunk_id": "DPD-14", "chunk_text": "Consumer data must not be shared with third parties for marketing purposes without the explicit, documented consent of the consumer."},
            {"chunk_id": "DPD-15", "chunk_text": "All consumer data transfers across jurisdictional boundaries require prior authorization from the Data Oversight Board and must employ end-to-end encryption."},
            {"chunk_id": "DPD-16", "chunk_text": "In the event of a data breach affecting consumer records, the payment service provider must notify the Federal Commerce Authority within 72 hours of becoming aware of the breach."},
            {"chunk_id": "DPD-17", "chunk_text": "Payment service providers shall establish and maintain a real-time transaction monitoring system capable of detecting anomalous or potentially fraudulent activity."},
            {"chunk_id": "DPD-18", "chunk_text": "Transactions exceeding the threshold amount specified in Annex III must be flagged for manual review and reported to the Financial Intelligence Unit within five business days."},
            {"chunk_id": "DPD-19", "chunk_text": "The Federal Commerce Authority may issue supplementary guidance on monitoring methodologies from time to time."},
            {"chunk_id": "DPD-20", "chunk_text": "Every payment service provider must establish a formal consumer complaint resolution procedure that is easily accessible and clearly communicated to all users."},
            {"chunk_id": "DPD-21", "chunk_text": "Consumer complaints must be acknowledged within two business days and resolved within 30 calendar days of receipt."},
            {"chunk_id": "DPD-22", "chunk_text": "If a complaint cannot be resolved within the prescribed timeframe, the provider shall escalate the matter to the Consumer Mediation Office and inform the consumer in writing of the escalation."},
            {"chunk_id": "DPD-23", "chunk_text": "This chapter addresses the requirements for maintaining operational resilience in the delivery of payment services."},
            {"chunk_id": "DPD-24", "chunk_text": "Payment service providers operating critical payment infrastructure shall conduct annual business continuity testing and submit results to the Federal Commerce Authority."},
            {"chunk_id": "DPD-25", "chunk_text": "Non-compliance with the provisions of this Directive may result in administrative penalties, license suspension, or revocation, as determined by the Federal Commerce Authority."},
            {"chunk_id": "DPD-26", "chunk_text": "The penalty framework established under this Directive does not preclude additional civil or criminal liability under applicable law."},
            {"chunk_id": "DPD-27", "chunk_text": "Beneficial ownership verification should be conducted in a manner that is proportionate to the overall risk profile of the merchant, taking into account factors that the compliance team considers relevant at the time of assessment."},
            {"chunk_id": "DPD-28", "chunk_text": "Transaction monitoring alerts must be reviewed and actioned within a timeframe that is reasonable given the nature and severity of the alert, and in accordance with generally accepted industry practices."},
            {"chunk_id": "DPD-29", "chunk_text": "Staff supporting merchant accounts must receive adequate and up-to-date compliance training that is sufficient to enable them to perform their duties competently."},
        ],
    },
}

# ── Load regulation chunks from Excel ──
_df_reg = pd.read_excel("backend/POC/regulation_chunks.xlsx")

REGULATIONS = {}
for doc_name in _df_reg["document_name"].unique():
    doc_df = _df_reg[_df_reg["document_name"] == doc_name]
    doc_id = doc_name.lower().replace(" ", "-")
    REGULATIONS[doc_id] = {
        "name": doc_name,
        "description": f"Regulation document: {doc_name}",
        "chunks": [
            {"chunk_id": str(row["chunk_id"]), "chunk_text": str(row["chunk_text"])}
            for _, row in doc_df.iterrows()
        ],
    }

# =============================================================
# PIPELINE V8 — runs the full compliance analysis pipeline
# =============================================================


def run_pipeline_v8(
    process_text: str,
    document: list[dict],
    dataset_id: str = "api_request",
    strictness: str = "conservative",
    bpmn_xml: str = None,
    on_progress=None,
) -> pd.DataFrame:
    """
    Runs the full v8 compliance analysis pipeline.

    Pipeline stages:
      S1: Chunk classification (single run per chunk)
      S2: Relevance check (tiebreaker: 2 runs, optional 3rd)
      S3: Compliance analysis (always 2 runs, strictness-based resolution)
      S4: Ambiguity analysis (single run, ambiguous_field flag)

    Args:
        process_text: The full process string.
        document: List of {"chunk_id": ..., "chunk_text": ...} dicts.
        dataset_id: Identifier for this analysis run.
        strictness: "conservative" (most severe wins) or "pragmatic" (least severe wins).does it make sense to add 
        S4 Ambiguity Analysis
        bpmn_xml: Optional BPMN XML content for element matching.

    Returns:
        Final DataFrame with v8 pipeline output columns.
    """
    def _emit(msg: str):
        if on_progress:
            on_progress(msg)

    # Convert document to list of chunk texts
    chunk_texts = [c["chunk_text"] for c in document]

    # Run the v8 pipeline
    step_dfs = run_dataset(
        dataset_id=dataset_id,
        document=chunk_texts,
        process=process_text,
        llm=llm_v8,
        prompts=PROMPTS_V8,
        strictness=strictness,
        on_progress=on_progress,
    )

    # Build final table from accumulated results
    _emit("Building results table...")
    accumulated = {k: [v] for k, v in step_dfs.items()}
    df_final = build_final_table(accumulated)
    print("✓")

    if df_final.empty:
        print("[Pipeline v8] ✗ No results produced.")
        return pd.DataFrame()

    print(f"  Total segments: {len(df_final)}")

    # Add process_text column for reference
    df_final["process_text"] = process_text

    # ── BPMN Element Matching (if BPMN XML provided) ──
    if bpmn_xml and "s3_segment_1" in df_final.columns:
        _emit("Matching BPMN elements...")
        try:
            from functions_POC import extract_bpmn_elements, find_best_matching_bpmn_element
            bpmn_elements = extract_bpmn_elements(bpmn_xml)

            if bpmn_elements:
                element_texts = [elem['text'] for elem in bpmn_elements]
                bpmn_element_embeddings = st_model.encode(element_texts)

                def match_bpmn(row):
                    # Use winning S3 segment for matching
                    s3_cat_1 = row.get("s3_category_1", "")
                    s3_cat_2 = row.get("s3_category_2", "")
                    final_cat = row.get("final_category", "")
                    
                    if str(s3_cat_1).strip() == str(final_cat).strip():
                        segment = row.get("s3_segment_1", "")
                    else:
                        segment = row.get("s3_segment_2", "")
                    
                    return find_best_matching_bpmn_element(
                        segment, bpmn_elements, bpmn_element_embeddings,
                        st_model, threshold=0.5
                    )

                df_final["matched_bpmn_element_id"] = df_final.apply(match_bpmn, axis=1)
                matches_found = df_final["matched_bpmn_element_id"].notna().sum()
                print(f"✓ ({matches_found}/{len(df_final)} matched)")
            else:
                print("✗ (no BPMN elements found)")
                df_final["matched_bpmn_element_id"] = None
        except ImportError:
            print("✗ (BPMN utils unavailable)")
            df_final["matched_bpmn_element_id"] = None
    else:
        df_final["matched_bpmn_element_id"] = None

    # ── Compute process_id (position in process text for ordering) ──
    _emit("Computing process positions...")
    process_str = str(process_text)
    
    def compute_process_id(row):
        # Use winning S3 segment
        s3_cat_1 = str(row.get("s3_category_1", "")).strip()
        final_cat = str(row.get("final_category", "")).strip()
        segment_str = row.get("s3_segment_1", "") if s3_cat_1 == final_cat else row.get("s3_segment_2", "")
        
        if isinstance(segment_str, str) and segment_str:
            try:
                segments = ast.literal_eval(segment_str) if segment_str.startswith("[") else [segment_str]
                positions = [process_str.find(s) for s in segments if isinstance(s, str) and process_str.find(s) != -1]
                return min(positions) if positions else -1
            except:
                return process_str.find(segment_str) if segment_str in process_str else -1
        return -1

    df_final["process_id"] = df_final.apply(compute_process_id, axis=1)
    print("✓")

    # Map winning S3 reasoning to compliance_report for the frontend
    def _get_winning_reasoning(row):
        cat1 = str(row.get("s3_category_1", "")).strip()
        final = str(row.get("final_category", "")).strip()
        if cat1 == final:
            return str(row.get("s3_reasoning_1", ""))
        return str(row.get("s3_reasoning_2", ""))

    df_final["compliance_report"] = df_final.apply(_get_winning_reasoning, axis=1)

    # Save output Excel for history (after compliance_report is computed)
    output_path = os.path.join(HISTORY_FOLDER, f"{dataset_id}_{int(time.time())}.xlsx")
    df_final.to_excel(output_path, index=False)

    return df_final


# =============================================================
# LEGACY — pre-computed results loaded at startup
# =============================================================

try:
    _legacy_excel_path = os.path.join(os.path.dirname(__file__), "POC", "final_2.xlsx")
    df_compliance_category_table_report = pd.read_excel(_legacy_excel_path)
    legacy_process = str(df_compliance_category_table_report["process_sentence"].iloc[1])
except Exception:
    df_compliance_category_table_report = pd.DataFrame()
    legacy_process = ""


# =============================================================
# HELPER FUNCTIONS
# =============================================================


def parse_list_field(raw):
    """Safely parse a field that should be a list but may be stored as a string."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return parsed
            return [str(parsed)]
        except (ValueError, SyntaxError):
            return [raw]
    return [str(raw)]


def build_segments(df):
    """Convert DataFrame rows into segment dicts for the frontend.
    
    Logic:
    - If s3_category_1 = s3_category_2: use run 1 data
    - If different: use the run whose category matches final_category (winning run)
    """
    segments = []
    for i, row in df.iterrows():
        # Determine which S3 run "won"
        s3_cat_1 = row.get("s3_category_1")
        s3_cat_2 = row.get("s3_category_2")
        final_cat = row.get("final_category")
        
        # Use run 1 by default
        use_run_1 = True
        
        # If both runs exist and differ, pick the one matching final_category
        if (pd.notna(s3_cat_1) and pd.notna(s3_cat_2) and 
            str(s3_cat_1).strip() != str(s3_cat_2).strip()):
            # Categories differ - use the run matching final_category
            if str(s3_cat_2).strip() == str(final_cat).strip():
                use_run_1 = False
        
        # Select evidence and rule aspect from winning run
        def _str(val):
            return str(val) if pd.notna(val) else ""

        if use_run_1:
            short_evidence = _str(row.get("s3_short_evidence_1"))
            easy_rule = _str(row.get("s3_rule_aspect_1"))
            extracted_segment = _str(row.get("s3_segment_1"))
        else:
            short_evidence = _str(row.get("s3_short_evidence_2"))
            easy_rule = _str(row.get("s3_rule_aspect_2"))
            extracted_segment = _str(row.get("s3_segment_2"))

        segment = {
            "id": f"seg-{i}",
            "process_id": int(row["process_id"]) if pd.notna(row.get("process_id")) else i,
            "category": _str(final_cat),  # Use final_category from v8 pipeline
            "short_evidence": short_evidence,
            "easy_rule": easy_rule,
            "chunk_id": str(row.get("chunk_id", "")),
            "chunk_text": str(row.get("chunk_text", "")),
            "extracted_process_segment": parse_list_field(extracted_segment if extracted_segment else row.get("extracted_process_segment", [])),
            "compliance_report": str(row.get("compliance_report", "")),
            
            # S3 Run 1
            "s3_category_1": str(s3_cat_1) if pd.notna(s3_cat_1) else None,
            "s3_reasoning_1": str(row.get("s3_reasoning_1", "")) if pd.notna(row.get("s3_reasoning_1")) else None,
            "s3_rule_aspect_1": str(row.get("s3_rule_aspect_1", "")) if pd.notna(row.get("s3_rule_aspect_1")) else None,
            "s3_short_evidence_1": str(row.get("s3_short_evidence_1", "")) if pd.notna(row.get("s3_short_evidence_1")) else None,
            "s3_segment_1": str(row.get("s3_segment_1", "")) if pd.notna(row.get("s3_segment_1")) else None,
            "s3_category_confidence_1": float(row["s3_category_confidence_1"]) if pd.notna(row.get("s3_category_confidence_1")) else None,
            
            # S3 Run 2
            "s3_category_2": str(s3_cat_2) if pd.notna(s3_cat_2) else None,
            "s3_reasoning_2": str(row.get("s3_reasoning_2", "")) if pd.notna(row.get("s3_reasoning_2")) else None,
            "s3_rule_aspect_2": str(row.get("s3_rule_aspect_2", "")) if pd.notna(row.get("s3_rule_aspect_2")) else None,
            "s3_short_evidence_2": str(row.get("s3_short_evidence_2", "")) if pd.notna(row.get("s3_short_evidence_2")) else None,
            "s3_segment_2": str(row.get("s3_segment_2", "")) if pd.notna(row.get("s3_segment_2")) else None,
            "s3_category_confidence_2": float(row["s3_category_confidence_2"]) if pd.notna(row.get("s3_category_confidence_2")) else None,
            
            # S3 Resolution
            "s3_resolution": str(row.get("s3_resolution", "")) if pd.notna(row.get("s3_resolution")) else None,
            
            # S4 Ambiguity Analysis
            "s4_assumption_needed": str(row.get("s4_assumption_needed", "")) if pd.notna(row.get("s4_assumption_needed")) else None,
            "s4_ambiguous_term": str(row.get("s4_ambiguous_term", "")) if pd.notna(row.get("s4_ambiguous_term")) else None,
            "s4_mapped_evidence": str(row.get("s4_mapped_evidence", "")) if pd.notna(row.get("s4_mapped_evidence")) else None,
            "s4_assumption": str(row.get("s4_assumption", "")) if pd.notna(row.get("s4_assumption")) else None,
            "s4_compliance_category": str(row.get("s4_compliance_category", "")) if pd.notna(row.get("s4_compliance_category")) else None,
            
            # Ambiguous Field Flag
            "ambiguous_field": str(row.get("ambiguous_field", "")) if pd.notna(row.get("ambiguous_field")) else None,
        }

        # Add BPMN element ID if present
        if "matched_bpmn_element_id" in row and pd.notna(row["matched_bpmn_element_id"]):
            segment["matched_bpmn_element_id"] = str(row["matched_bpmn_element_id"])
        else:
            segment["matched_bpmn_element_id"] = None

        segments.append(segment)
    return segments


def build_chunks(chunk_list):
    """Convert a list of chunk dicts for the frontend."""
    if isinstance(chunk_list, pd.DataFrame):
        return [
            {"chunk_id": str(row["chunk_id"]), "chunk_text": str(row["chunk_text"])}
            for _, row in chunk_list.iterrows()
        ]
    return [{"chunk_id": c["chunk_id"], "chunk_text": c["chunk_text"]} for c in chunk_list]


# ── API ENDPOINTS ──────────────────────────────────────────────


@app.route("/api/options", methods=["GET"])
def get_options():
    """Returns the available processes and regulation documents."""
    processes = [
        {"id": pid, "name": p["name"], "description": p["description"]}
        for pid, p in PROCESSES.items()
    ]
    regulations = [
        {"id": rid, "name": r["name"], "description": r["description"]}
        for rid, r in REGULATIONS.items()
    ]
    return jsonify({"processes": processes, "regulations": regulations})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    # ── Parse request synchronously before streaming ──
    process_id = None
    process_text = None
    process_name = None
    save_process = False
    regulation_id = None
    bpmn_xml = None
    selected_process = None

    if request.files.get('bpmn_file'):
        bpmn_file = request.files['bpmn_file']
        process_name = request.form.get("process_name", "")
        save_process = request.form.get("save_process", "false").lower() == "true"
        regulation_id = request.form.get("regulation_id")

        if not bpmn_file or not bpmn_file.filename.endswith('.bpmn'):
            return jsonify({"error": "BPMN file with .bpmn extension is required"}), 400
        if not regulation_id:
            return jsonify({"error": "regulation_id is required"}), 400

        try:
            bpmn_xml = bpmn_file.read().decode('utf-8')
            process_text = convert_bpmn_to_text(bpmn_xml, openai_client)
        except Exception as e:
            return jsonify({"error": f"Failed to convert BPMN file: {str(e)}"}), 500
    else:
        body = request.get_json(silent=True) or {}
        process_id = body.get("process_id")
        process_text = body.get("process_text")
        process_name = body.get("process_name")
        save_process = body.get("save_process", False)
        regulation_id = body.get("regulation_id")

        if not regulation_id:
            return jsonify({"error": "regulation_id is required"}), 400
        if not process_id and not process_text:
            return jsonify({"error": "Either process_id, process_text, or BPMN file is required"}), 400

        if process_id:
            selected_process = PROCESSES.get(process_id)
            if not selected_process:
                return jsonify({"error": f"Unknown process: {process_id}"}), 404
            process_text = selected_process["text"]

    if save_process and process_name and not process_id:
        new_id = process_name.lower().replace(" ", "-")
        if new_id not in PROCESSES:
            PROCESSES[new_id] = {"name": process_name, "description": f"User-added: {process_name}", "text": process_text}

    selected_regulation = REGULATIONS.get(regulation_id)
    if not selected_regulation:
        return jsonify({"error": f"Unknown regulation: {regulation_id}"}), 404

    document = selected_regulation["chunks"]

    process_name_for_id = process_name or (selected_process["name"] if selected_process else "custom")
    clean_process = process_name_for_id.replace(" ", "_").replace("/", "-")
    clean_regulation = selected_regulation.get("name", regulation_id).replace(" ", "_").replace("/", "-")
    dataset_id = f"{clean_process}_{clean_regulation}"

    # ── Stream SSE ──
    def generate():
        progress_q = queue.Queue()
        result_box = [None]
        error_box = [None]

        def worker():
            try:
                result_box[0] = run_pipeline_v8(
                    process_text=process_text,
                    document=document,
                    dataset_id=dataset_id,
                    strictness="conservative",
                    bpmn_xml=bpmn_xml,
                    on_progress=lambda msg: progress_q.put(msg),
                )
            except Exception as e:
                import traceback; traceback.print_exc()
                error_box[0] = e
            finally:
                progress_q.put(None)  # sentinel

        threading.Thread(target=worker, daemon=True).start()

        while True:
            msg = progress_q.get()
            if msg is None:
                break
            yield f"data: {json.dumps({'type': 'log', 'message': msg})}\n\n"

        if error_box[0]:
            yield f"data: {json.dumps({'type': 'error', 'message': str(error_box[0])})}\n\n"
            return

        df_result = result_box[0]
        segments = [] if df_result is None or df_result.empty else build_segments(df_result)
        payload = {"process": process_text, "segments": segments, "chunks": build_chunks(document), "bpmnXml": bpmn_xml}
        yield f"data: {json.dumps({'type': 'result', 'data': payload})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/document", methods=["GET"])
def get_document():
    """Legacy endpoint — returns pre-computed results from final_2.xlsx."""
    if df_compliance_category_table_report.empty:
        return jsonify({"error": "No pre-computed results available"}), 404

    return jsonify({
        "process": legacy_process,
        "segments": build_segments(df_compliance_category_table_report),
        "chunks": build_chunks(
            [{"chunk_id": "legacy", "chunk_text": "Pre-computed results"}]
        ),
    })


@app.route("/api/history", methods=["GET"])
def get_history():
    """Returns list of available analyses from history Excel files.
    
    Each Excel file can contain multiple analyses, differentiated by dataset_id and run_id.
    """
    history_items = []
    
    if not os.path.exists(HISTORY_FOLDER):
        return jsonify({"items": []})
    
    for filename in os.listdir(HISTORY_FOLDER):
        if not filename.endswith(".xlsx") or filename.startswith("~$"):
            continue
        
        filepath = os.path.join(HISTORY_FOLDER, filename)
        try:
            # Get file modification time as date
            mtime = os.path.getmtime(filepath)
            file_date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            
            # Read full Excel to find unique dataset_id + run_id combinations
            df = pd.read_excel(filepath)
            
            # Determine grouping columns
            has_dataset_id = "dataset_id" in df.columns
            has_run_id = "run_id" in df.columns
            
            if has_dataset_id:
                # Group by dataset_id (and run_id if available)
                group_cols = ["dataset_id"]
                if has_run_id:
                    group_cols.append("run_id")
                
                # Get unique combinations
                unique_groups = df[group_cols].drop_duplicates()
                
                for _, group_row in unique_groups.iterrows():
                    dataset_id = str(group_row["dataset_id"]) if pd.notna(group_row["dataset_id"]) else "unknown"
                    run_id = str(group_row["run_id"]) if has_run_id and pd.notna(group_row.get("run_id")) else None
                    
                    # Filter rows for this group to get metadata
                    if has_run_id and run_id:
                        group_df = df[(df["dataset_id"] == group_row["dataset_id"]) & (df["run_id"] == group_row["run_id"])]
                    else:
                        group_df = df[df["dataset_id"] == group_row["dataset_id"]]
                    
                    first_row = group_df.iloc[0] if len(group_df) > 0 else None
                    
                    # Extract process_name and regulation_name
                    process_name = None
                    regulation_name = None
                    analysis_date = file_date_str
                    
                    if first_row is not None:
                        if "process_name" in df.columns and pd.notna(first_row.get("process_name")):
                            process_name = str(first_row["process_name"])
                        if "regulation_name" in df.columns and pd.notna(first_row.get("regulation_name")):
                            regulation_name = str(first_row["regulation_name"])
                        if "analysis_date" in df.columns and pd.notna(first_row.get("analysis_date")):
                            analysis_date = str(first_row["analysis_date"])
                    
                    # Fallback to dataset_id if names not found
                    if not process_name:
                        process_name = dataset_id
                    if not regulation_name:
                        regulation_name = dataset_id
                    
                    # Create unique ID combining filename, dataset_id, and run_id
                    unique_id = f"{filename}|{dataset_id}"
                    if run_id:
                        unique_id += f"|{run_id}"
                    
                    history_items.append({
                        "id": unique_id,
                        "filename": filename,
                        "dataset_id": dataset_id,
                        "run_id": run_id,
                        "process_name": process_name,
                        "regulation_name": regulation_name,
                        "date": analysis_date,
                    })
            else:
                # No dataset_id column — treat entire file as one analysis
                process_name = filename.replace(".xlsx", "")
                regulation_name = "Unknown Regulation"
                
                if "process_name" in df.columns and len(df) > 0 and pd.notna(df["process_name"].iloc[0]):
                    process_name = str(df["process_name"].iloc[0])
                if "regulation_name" in df.columns and len(df) > 0 and pd.notna(df["regulation_name"].iloc[0]):
                    regulation_name = str(df["regulation_name"].iloc[0])
                
                history_items.append({
                    "id": filename,
                    "filename": filename,
                    "dataset_id": None,
                    "run_id": None,
                    "process_name": process_name,
                    "regulation_name": regulation_name,
                    "date": file_date_str,
                })
                
        except Exception as e:
            print(f"[History] Error reading {filename}: {e}")
            import traceback
            traceback.print_exc()
            # Still add with basic info
            history_items.append({
                "id": filename,
                "filename": filename,
                "dataset_id": None,
                "run_id": None,
                "process_name": filename.replace(".xlsx", ""),
                "regulation_name": "Unknown",
                "date": time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(filepath))),
            })
    
    # Sort by date descending (newest first)
    history_items.sort(key=lambda x: x["date"], reverse=True)
    
    return jsonify({"items": history_items})


@app.route("/api/history/<path:item_id>", methods=["GET"])
def get_history_item(item_id):
    """Loads a specific analysis from a history Excel file.
    
    item_id format: "filename.xlsx|dataset_id|run_id" or "filename.xlsx|dataset_id" or "filename.xlsx"
    """
    # Parse the item_id to extract filename, dataset_id, and run_id
    parts = item_id.split("|")
    filename = parts[0]
    dataset_id = parts[1] if len(parts) > 1 else None
    run_id = parts[2] if len(parts) > 2 else None
    
    # Secure the filename to prevent directory traversal
    safe_filename = secure_filename(filename)
    filepath = os.path.join(HISTORY_FOLDER, safe_filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": f"History file not found: {filename}"}), 404
    
    try:
        df = pd.read_excel(filepath)
        
        # Filter by dataset_id and run_id if provided
        if dataset_id and "dataset_id" in df.columns:
            df = df[df["dataset_id"].astype(str) == dataset_id]
        if run_id and "run_id" in df.columns:
            df = df[df["run_id"].astype(str) == run_id]
        
        if df.empty:
            return jsonify({"error": f"No data found for dataset_id={dataset_id}, run_id={run_id}"}), 404
        
        # Extract process text if available
        process_text = ""
        if "process_text" in df.columns and pd.notna(df["process_text"].iloc[0]):
            process_text = str(df["process_text"].iloc[0])
        
        # Build chunks from regulation data if available
        chunks = []
        if "chunk_id" in df.columns and "chunk_text" in df.columns:
            chunk_df = df[["chunk_id", "chunk_text"]].drop_duplicates()
            chunks = [
                {"chunk_id": str(row["chunk_id"]), "chunk_text": str(row["chunk_text"])}
                for _, row in chunk_df.iterrows()
                if pd.notna(row["chunk_id"]) and pd.notna(row["chunk_text"])
            ]
        
        return jsonify({
            "process": process_text,
            "segments": build_segments(df),
            "chunks": chunks if chunks else [{"chunk_id": "history", "chunk_text": "Historical results"}],
            "bpmnXml": None,
        })
    except Exception as e:
        print(f"[History] Error loading {item_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to load history file: {str(e)}"}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("Compliance Verifier API running at:")
    print("  GET  http://localhost:5005/api/options")
    print("  POST http://localhost:5005/api/analyze")
    print("  GET  http://localhost:5005/api/document")
    print("  GET  http://localhost:5005/api/history")
    print("  GET  http://localhost:5005/api/history/<filename>")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5005, debug=False)
