#!/usr/bin/env python3
"""
Test script to run v8 pipeline with sample process and document data.
"""
import sys
import os

print(f"[v0] Current working directory: {os.getcwd()}")

# List current directory
print(f"[v0] Listing /home/user:")
for item in os.listdir("/home/user"):
    print(f"  - {item}")

# Look for the project
possible_paths = [
    "/home/user/v0-project",
    "/root/v0-project",
    "/vercel/share/v0-project",
]

project_root = None
for path in possible_paths:
    if os.path.exists(path):
        print(f"[v0] Found project at: {path}")
        project_root = path
        break

if not project_root:
    print(f"[v0] Project not found! Trying to find it...")
    for root, dirs, files in os.walk("/home"):
        if "backend" in dirs and "functions_pipeline_v8.py" in os.listdir(os.path.join(root, "backend")):
            project_root = root
            print(f"[v0] Found project at: {root}")
            break

if project_root:
    backend_path = os.path.join(project_root, "backend")
    print(f"[v0] Using backend: {backend_path}")
    sys.path.insert(0, backend_path)
    
    try:
        from functions_pipeline_v8 import make_llm, run_dataset, build_final_table
        print("[v0] Successfully imported functions_pipeline_v8")
    except ImportError as e:
        print(f"[v0] Import failed: {e}")
        sys.exit(1)
else:
    print("[v0] Could not find project!")
    sys.exit(1)

from dotenv import load_dotenv
import pandas as pd

load_dotenv()

# Process text
PROCESS = """Step 1: The merchant submits an online application form including business name, registration number, contact information, and requested payment services; An automated system checks the form for completeness and generates a case ID; Incomplete applications are returned to the merchant with specific instructions on missing fields.

Step 2: A compliance analyst verifies the merchant's legal registration against the national business registry; The analyst also confirms the merchant's principal place of business through address validation services; Beneficial ownership verification is performed only when flagged by the automated risk scoring tool, not for all merchants.

Step 3: The merchant's legal entity name and all beneficial owners are screened against all government-maintained sanctions and exclusion lists; Any match results in automatic rejection of the application; Screening results are logged and attached to the case file.

Step 4: The merchant is assigned a risk category (low, medium, or high) based on its business type, geography, and transaction volume projections; High-risk merchants receive a general advisory notice but no additional due diligence procedures are applied beyond the standard verification; The risk category is recorded in the merchant profile.

Step 5: Technical staff configure the merchant's payment processing environment with encryption, access controls, and tokenization of sensitive authentication data; All consumer data stored in the system is protected using AES-256 encryption at rest and TLS 1.3 in transit; A data protection impact assessment is completed and filed.

Step 6: The merchant's point-of-sale or e-commerce system is integrated with the payment gateway; Technical staff run a series of test transactions to validate connectivity, latency, and error handling; Test results are documented and approved by a QA lead.

Step 7: The merchant's account is enrolled in the batch-processed transaction monitoring system, which runs nightly scans to detect patterns indicative of fraud; Alerts are reviewed by the fraud operations team on the following business day; The system does not operate in real time.

Step 8: The merchant reviews and signs the standard service agreement, which includes data handling terms, fee schedules, and dispute resolution clauses; The agreement includes a clause authorizing the provider to share anonymized transaction data with analytics partners for market research; The executed agreement is stored in the contract management system.

Step 9: New team members supporting the merchant account attend a training session covering operational procedures, escalation paths, and compliance awareness; The training is delivered quarterly and covers general regulatory topics; Attendance records are maintained by HR.

Step 10: Following successful completion of all prior steps, the merchant account is activated in the production environment; The merchant receives onboarding confirmation with login credentials and support contact details; A 30-day post-activation review is scheduled."""

# Regulation chunks
DOCUMENT = [
    "7All payment service providers shall conduct a comprehensive identity verification of each merchant prior to granting access to payment processing services.",
    "8The identity verification process must include validation of the merchant's legal registration, beneficial ownership structure, and principal place of business.",
    "17Payment service providers shall establish and maintain a real-time transaction monitoring system capable of detecting anomalous or potentially fraudulent activity.",
    "10Where a merchant operates in a high-risk category as defined in Annex II, the payment service provider shall apply enhanced due diligence measures appropriate to the level of risk.",
    "9Payment service providers are prohibited from onboarding any merchant that appears on a government-maintained sanctions or exclusion list.",
    "13Payment service providers shall implement adequate technical and organizational safeguards to protect consumer data against unauthorized access, disclosure, or destruction.",
    "11Verification records shall be retained for a minimum period of seven years from the date of merchant account closure.",
    "22If a complaint cannot be resolved within the prescribed timeframe, the provider shall escalate the matter to the Consumer Mediation Office and inform the consumer in writing of the escalation.",
    "18Transactions exceeding the threshold amount specified in Annex III must be flagged for manual review and reported to the Financial Intelligence Unit within five business days.",
    "20Every payment service provider must establish a formal consumer complaint resolution procedure that is easily accessible and clearly communicated to all users.",
    "21Consumer complaints must be acknowledged within two business days and resolved within 30 calendar days of receipt.",
]

# Load prompts
def load_prompt(filename: str) -> str:
    path = os.path.join("backend", "prompts", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

PROMPTS = {
    "classification": load_prompt("1_Classification.txt"),
    "relevance": load_prompt("2_Relevance.txt"),
    "compliance_p3": load_prompt("3_Analysis.txt"),
    "ambiguity": load_prompt("4_Ambiguity.txt"),
}

# Create LLM
AZURE_ENDPOINT = "https://litellm.ai.viadee.cloud"
AZURE_API_KEY = os.getenv("OPENAI_API_KEY", "")
AZURE_API_VERSION = ""

llm = make_llm(AZURE_ENDPOINT, AZURE_API_KEY, AZURE_API_VERSION)

# Run pipeline
print("\n" + "=" * 70)
print("RUNNING V8 PIPELINE TEST")
print("=" * 70)
print(f"Process: Merchant Onboarding")
print(f"Regulations: Payment Service Provider Compliance (11 rules)")
print(f"Strictness: conservative")
print("=" * 70 + "\n")

try:
    step_dfs = run_dataset(
        dataset_id="test_merchant_payment",
        document=DOCUMENT,
        process=PROCESS,
        llm=llm,
        prompts=PROMPTS,
        strictness="conservative",
    )
    
    print("\n[Test] Building final results table...")
    accumulated = {k: [v] for k, v in step_dfs.items()}
    df_final = build_final_table(accumulated)
    
    print(f"✓ Pipeline complete: {len(df_final)} compliance findings\n")
    
    # Display results
    if not df_final.empty:
        print("=" * 70)
        print("COMPLIANCE ANALYSIS RESULTS")
        print("=" * 70)
        
        for idx, row in df_final.iterrows():
            print(f"\n[Finding {idx+1}]")
            print(f"  Compliance Category: {row.get('final_category', 'N/A')}")
            print(f"  Regulation: {row.get('chunk_text', 'N/A')[:100]}...")
            print(f"  Rule Aspect: {row.get('s3_rule_aspect_1', 'N/A')}")
            print(f"  Evidence: {row.get('s3_short_evidence_1', 'N/A')[:80]}...")
            if row.get('ambiguous_field') == 'yes':
                print(f"  [AMBIGUOUS] {row.get('s4_ambiguous_term', 'N/A')}")
        
        # Save to Excel
        output_path = os.path.join("backend", "history", "test_merchant_payment.xlsx")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df_final.to_excel(output_path, index=False)
        print(f"\n✓ Results saved to: {output_path}")
    else:
        print("No findings produced by pipeline.")
        
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
