export interface ComplianceSegment {
  id: string
  /** df_compliance_category_table_report['process_id'] — used for sorting rows ascending (not displayed) */
  process_id: number
  /** final_category: "COMPLIANT" | "NON-COMPLIANT" | "NO EVIDENCE" — resolved final category after S3 & S4 */
  category: string
  /** df_compliance_category_table_report['short_evidence'] — summary shown in the table */
  short_evidence: string
  /** df_compliance_category_table_report['easy_rule'] — short rule description shown in Rule column */
  easy_rule: string
  /** df_compliance_category_table_report['chunk_id'] — clickable source ID */
  chunk_id: string
  /** df_compliance_category_table_report['chunk_text'] — full rule text shown on expand */
  chunk_text: string
  /** df_compliance_category_table_report['extracted_process_segment'] — exact text to highlight in the process */
  extracted_process_segment: string
  /** matched BPMN element ID for highlighting in diagram */
  matched_bpmn_element_id?: string | null
  /** optional detailed reasoning report for the selected segment */
  compliance_report?: string

  /* ── New Pipeline v8 Fields ── */
  
  /** S3 Run 1: Category result */
  s3_category_1?: string
  /** S3 Run 1: Reasoning text */
  s3_reasoning_1?: string
  /** S3 Run 1: Rule aspect extracted */
  s3_rule_aspect_1?: string
  /** S3 Run 1: Short evidence */
  s3_short_evidence_1?: string
  /** S3 Run 1: Process segment identified */
  s3_segment_1?: string
  /** S3 Run 1: Confidence score */
  s3_category_confidence_1?: number

  /** S3 Run 2: Category result */
  s3_category_2?: string
  /** S3 Run 2: Reasoning text */
  s3_reasoning_2?: string
  /** S3 Run 2: Rule aspect extracted */
  s3_rule_aspect_2?: string
  /** S3 Run 2: Short evidence */
  s3_short_evidence_2?: string
  /** S3 Run 2: Process segment identified */
  s3_segment_2?: string
  /** S3 Run 2: Confidence score */
  s3_category_confidence_2?: number

  /** S3 Resolution: "agreement" | "strictness" — how the final category was determined */
  s3_resolution?: string

  /** S4 Ambiguity Analysis: Whether assumption is needed */
  s4_assumption_needed?: string
  /** S4: The ambiguous term identified in the rule */
  s4_ambiguous_term?: string
  /** S4: The mapped evidence from the process */
  s4_mapped_evidence?: string
  /** S4: The assumption made to resolve ambiguity */
  s4_assumption?: string
  /** S4: The compliance category opinion from S4 */
  s4_compliance_category?: string

  /** Flag: "yes" | "no" — whether S4 disagrees with final category or if assumption needed */
  ambiguous_field?: string
}

/** A single chunk from the regulation / compliance document */
export interface RegulationChunk {
  chunk_id: string
  chunk_text: string
}

export interface DocumentData {
  /** The full process text displayed on the right side */
  process: string
  segments: ComplianceSegment[]
  /** All regulation chunks that form the full document (ordered) */
  chunks: RegulationChunk[]
  /** BPMN XML content if process was uploaded as BPMN file */
  bpmnXml?: string | null
}

/** An available process the user can select */
export interface ProcessOption {
  id: string
  name: string
  description: string
}

/** An available regulation document the user can select */
export interface RegulationOption {
  id: string
  name: string
  description: string
}

/** Response from the /api/options endpoint */
export interface OptionsData {
  processes: ProcessOption[]
  regulations: RegulationOption[]
}

/** A regulation item returned by /api/regulations */
export interface RegulationItem {
  id: string
  name: string
  description: string
  chunk_count: number
}

/** Response from /api/regulations */
export interface RegulationsListData {
  regulations: RegulationItem[]
}

/** Response from /api/regulations/:id/chunks */
export interface RegulationChunksData {
  name: string
  chunks: RegulationChunk[]
}

/** Mode for process input */
export type ProcessMode = "select" | "type" | "bpmn"

/** A history item representing a past analysis */
export interface HistoryItem {
  id: string
  filename: string
  dataset_id: string | null
  run_id: string | null
  process_name: string
  regulation_name: string
  date: string
}
