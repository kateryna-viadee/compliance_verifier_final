from sklearn.metrics import accuracy_score, precision_score, recall_score, confusion_matrix, classification_report
import pandas as pd
import numpy as np

import re
import json
import pandas as pd
import inspect
import random
from sentence_transformers import SentenceTransformer, util
import time
import json
import inspect
import pandas as pd
from tqdm import tqdm
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

model = SentenceTransformer('all-MiniLM-L6-v2')
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)

def get_llm_response(prompt, client, seed=42):
    nonce = str(int(time.time()))

    response = client.chat.completions.create(
        model= "gpt-5.4-US", #"gpt-4o-mini",#"gpt-4o-mini", #"gpt-4o"
        messages=[
            {"role": "system", "content": f"nonce:{nonce}"},  # busts cache
            {"role": "user", "content": prompt}
        ],
        seed=123,  # keeps results reproducible
    )
    return response.choices[0].message.content


def evaluate_chunk(document, process, llm_client=None, evaluation_prompt_template=None):
    results = []
    parsed_fields = set()

    for i, item in enumerate(tqdm(document, desc="Evaluating chunks", unit="chunk")):
        if isinstance(item, tuple):
            chunk_id, chunk = item
        else:
            chunk_id, chunk = i + 1, item
        evaluation_prompt = evaluation_prompt_template.format(process=process, chunk=chunk)
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            parsed_fields.update(parsed.keys())
        except:
            parsed = {}

        results.append({
            'chunk_id': chunk_id,
            'chunk_text': chunk,
            'process': process,
            **parsed
        })

    return pd.DataFrame(results)


def display_results(df, parsed_fields=None, include_process=True, include_chunk_text=True):
    base_fields = {'chunk_id', 'chunk_text', 'process'}

    if parsed_fields is None:
        parsed_fields = [col for col in df.columns if col not in base_fields]

    for _, row in df.iterrows():
        print(f"{'=' * 60}")
        print(f"Chunk {row['chunk_id']}")
        print(f"{'=' * 60}")
        if include_process:
            print(f"Process: {row['process']}")
        if include_chunk_text:
            print(f"Chunk: {row['chunk_text']}")
        print(f"{'-' * 40}")
        for field in parsed_fields:
            if field in row:
                print(f"{field.capitalize()}: {row[field]}")
        print()


def display_results_general(df, exclude_cols=None):
    if exclude_cols is None:
        exclude_cols = []

    cols = [col for col in df.columns if col not in exclude_cols]

    for _, row in df.iterrows():
        first = True
        for col in cols:
            if first:
                print(f"{'=' * 60}")
                print(f"{col}: {row[col]}")
                print(f"{'=' * 60}")
                first = False
            else:
                print(f"{col}: {row[col]}")
                print(f"{'-' * 40}")
        print()


def evaluate_chunks_against_process_sentences(documents, process_sentences, llm_client, evaluation_prompt_template):
    results = []

    for doc_idx, chunk in enumerate(documents):
        for proc_idx, process_sentence in enumerate(process_sentences):
            evaluation_prompt = evaluation_prompt_template.format(
                process_sentence=process_sentence,
                chunk=chunk
            )
            response = get_llm_response(evaluation_prompt, llm_client)

            try:
                clean = response.strip().removeprefix("```json").removesuffix("```").strip()
                parsed = json.loads(clean)
            except Exception:
                parsed = {}

            results.append({
                'chunk_id': doc_idx + 1,
                'chunk_text': chunk,
                'process_idx': proc_idx + 1,
                'process_sentence': process_sentence,
                **parsed
            })

    return pd.DataFrame(results)


def evaluate_chunks_against_process_sentences(chunk_ids, chunk_texts, process_sentences, llm_client,
                                              evaluation_prompt_template):
    results = []

    for chunk_id, chunk in zip(chunk_ids, chunk_texts):
        for proc_idx, process_sentence in enumerate(process_sentences):
            evaluation_prompt = evaluation_prompt_template.format(
                process_sentence=process_sentence,
                chunk=chunk
            )
            response = get_llm_response(evaluation_prompt, llm_client)

            try:
                clean = response.strip().removeprefix("```json").removesuffix("```").strip()
                parsed = json.loads(clean)
            except Exception:
                parsed = {}

            results.append({
                'chunk_id': chunk_id,
                'chunk_text': chunk,
                'process_idx': proc_idx + 1,
                'process_sentence': process_sentence,
                **parsed
            })

    return pd.DataFrame(results)


def run_step(chunks, process, client, prompt_template, step_name, include_process=0):
    if isinstance(process, list):
        chunk_ids, chunk_texts = zip(*chunks)
        df = evaluate_chunks_against_process_sentences(chunk_ids, chunk_texts, process, client, prompt_template)
    else:
        df = evaluate_chunk(chunks, process, client, prompt_template)

    df.to_excel(f"{step_name}.xlsx", index=False)
    display_results(df, include_process=include_process)
    print(df)
    return df


# TODO: run_step anpassen, damit es mit beiden evaluate Funktionen funktioniert. Am besten wäre es, wenn die Funktion automatisch erkennt, ob es sich um eine Liste von Prozesssätzen oder einen einzelnen Prozess handelt und dann die entsprechende Evaluierungsfunktion

def run_step(chunks, process, client, prompt_template, step_name, include_process=0):
    evaluated = evaluate_chunk(chunks, process, client, prompt_template)
    df = pd.DataFrame(evaluated)

    with pd.ExcelWriter(f"{step_name}.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Results", index=False)
        prompt_df = pd.DataFrame({"prompt_template": [prompt_template]})
        prompt_df.to_excel(writer, sheet_name="Prompt Template", index=False)

    display_results(df, include_process=include_process)
    print(df)
    return df


#### SOLL ICH ALLE SO UMFORMATIEREN UND PARSING VORHER MACHEN?
def evaluate_chunks_against_process_sentences_df(df, llm_client, evaluation_prompt_template, chunk_col='chunk',
                                                 process_sentence_col='process_sentence'):
    def evaluate_row(row):
        evaluation_prompt = evaluation_prompt_template.format(
            process_sentence=row[process_sentence_col],
            chunk=row[chunk_col]
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
        except Exception:
            parsed = {}

        return pd.Series(parsed)

    parsed_df = df.apply(evaluate_row, axis=1)
    return pd.concat([df, parsed_df], axis=1)


def evaluate_chunks_against_process_sentences_df(df, llm_client, evaluation_prompt_template, chunk_col='chunk',
                                                 process_sentence_col='process_sentence', **format_kwargs):
    def evaluate_row(row):
        evaluation_prompt = evaluation_prompt_template.format(
            process_sentence=row[process_sentence_col],
            chunk=row[chunk_col],
            **format_kwargs
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
        except Exception:
            parsed = {}

        return pd.Series(parsed)

    parsed_df = df.apply(evaluate_row, axis=1)
    return pd.concat([df, parsed_df], axis=1)


def evaluate_chunk_df(df, chunk_col, process_col, llm_client=None, evaluation_prompt_template=None):
    results = []
    parsed_fields = set()

    for i, row in df.iterrows():
        chunk = row[chunk_col]
        process = row[process_col]

        evaluation_prompt = evaluation_prompt_template.format(process=process, chunk=chunk)
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            parsed_fields.update(parsed.keys())
        except:
            parsed = {}

        results.append({
            'chunk_id': i + 1,
            'chunk_text': chunk,
            'process': process,
            **parsed
        })

    return pd.DataFrame(results)

def evaluate_chunk_df_no_json(df, chunk_col, chunk_id_col, process_col, llm_client=None, evaluation_prompt_template=None):
    results = []
    parsed_fields = set()

    for i, row in df.iterrows():
        chunk = row[chunk_col]
        process = row[process_col]
        chunk_id = row[chunk_id_col]

        evaluation_prompt = evaluation_prompt_template.format(process=process, chunk=chunk)
        response = get_llm_response(evaluation_prompt, llm_client)

        results.append({
            'chunk_id': chunk_id,
            'chunk_text': chunk,
            'process': process,
            'compliance_report': response
        })

    return pd.DataFrame(results)


# VERIFICATION FUNCTION (FIRST NOT USED)


def evaluate_chunk_df_1(df, chunk_col, process_col, process_idx_col, sentence_list, llm_client=None,
                      evaluation_prompt_template=None):
    results = []
    parsed_fields = set()

    for i, row in df.iterrows():
        chunk = row[chunk_col]
        process_sentece = row[process_col]
        idx = row[process_idx_col]

        # build the list with <TARGET> tags applied to idx-1 and idx elements
        tagged_list = []
        for j, sentence in enumerate(sentence_list):
            if j == idx or j == idx - 1:
                tagged_list.append(f"<TARGET>{sentence}<TARGET>")
            else:
                tagged_list.append(sentence)

        evaluation_prompt = evaluation_prompt_template.format(
            process_sentence=process_sentece,
            chunk=chunk,
            process_sentences=tagged_list
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            parsed_fields.update(parsed.keys())
        except:
            parsed = {}

        results.append({
            'chunk_id': i + 1,
            'chunk_text': chunk,
            'process_sentence': process_sentece,
            **parsed
        })

    return pd.DataFrame(results)


def evaluate_chunk_df_no_json_1(df, chunk_col, process_col, process_idx_col, sentence_list, llm_client=None,
                              evaluation_prompt_template=None):
    results = []

    for i, row in df.iterrows():
        chunk_id = row['chunk_id']
        chunk = row[chunk_col]
        process_sentece = row[process_col]
        idx = row[process_idx_col]

        # build the list with <TARGET> tags applied to idx-1 and idx elements
        tagged_list = []
        for j, sentence in enumerate(sentence_list):
            if j == idx or j == idx - 1:
                tagged_list.append(f"<TARGET>{sentence}<TARGET>")
            else:
                tagged_list.append(sentence)

        evaluation_prompt = evaluation_prompt_template.format(
            process_sentence=process_sentece,
            chunk=chunk,
            process_sentences=tagged_list
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        results.append({
            'chunk_id': chunk_id,
            'process_idx': idx,
            'chunk_text': chunk,
            'process_sentence': process_sentece,
            'compliance_report': response

        })

    return pd.DataFrame(results)


def evaluate_chunk_df_classify_compliance(df, chunk_col, process_col, analysis_col, llm_client=None,
                                          evaluation_prompt_template=None):
    results = []
    parsed_fields = set()

    for i, row in df.iterrows():
        chunk_id = row['chunk_id']
        chunk = row[chunk_col]
        process_sentece = row[process_col]
        analysis = row[analysis_col]

        evaluation_prompt = evaluation_prompt_template.format(

            compliance_analysis=analysis,
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            parsed_fields.update(parsed.keys())
        except:
            parsed = {}

        results.append({
            'chunk_id': chunk_id,
            'chunk_text': chunk,
            'process_sentence': process_sentece,
            'compliance_report': analysis,
            **parsed

        })

    return pd.DataFrame(results)


def evaluate_chunks_against_process_sentences_df_amb(df, chunk_col, process_col, process_idx_col, sentence_list,
                                                     llm_client=None, evaluation_prompt_template=None,
                                                     ambiguous_terms_col='ambiguous_terms'):
    results = []

    for i, row in df.iterrows():
        chunk_id = row['chunk_id']
        chunk = row[chunk_col]
        process_sentece = row[process_col]
        idx = row[process_idx_col]
        ambiguous_terms = row[ambiguous_terms_col]

        # build the list with <TARGET> tags applied to idx-1 and idx elements
        tagged_list = []
        for j, sentence in enumerate(sentence_list):
            if j == idx or j == idx - 1:
                tagged_list.append(f"<TARGET>{sentence}<TARGET>")
            else:
                tagged_list.append(sentence)

        evaluation_prompt = evaluation_prompt_template.format(
            process_sentence=process_sentece,
            chunk=chunk,
            process_sentences=tagged_list,
            ambiguous_terms=ambiguous_terms
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        results.append({
            'chunk_id': chunk_id,
            'process_idx': idx,
            'chunk_text': chunk,
            'process_sentence': process_sentece,
            'ambiguous_terms': ambiguous_terms,
            'compliance_report': response

        })

    return pd.DataFrame(results)


def evaluate_chunk_df_exrtact_assumtions(df, chunk_col, process_col, analysis_col, llm_client=None,
                                         evaluation_prompt_template=None, ambiguous_terms_col='ambiguous_terms'):
    results = []
    parsed_fields = set()

    for i, row in df.iterrows():
        chunk_id = row['chunk_id']
        chunk = row[chunk_col]
        process_sentece = row[process_col]
        analysis = row[analysis_col]
        ambiguous_terms = row[ambiguous_terms_col]

        evaluation_prompt = evaluation_prompt_template.format(

            compliance_analysis=analysis,
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            parsed_fields.update(parsed.keys())
        except:
            parsed = {}

        results.append({
            'chunk_id': chunk_id,
            'chunk_text': chunk,
            'process_sentence': process_sentece,
            'compliance_report': analysis,
            'ambiguous_terms': ambiguous_terms,
            **parsed

        })

    return pd.DataFrame(results)

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)


def evaluate_binary_classification(
    labels,
    dataframe,
    predicted_value_column,
    ground_truth_column,
    pos_label=None,
    df_name=None,
    task = None,
    prompt = None
):
    # Extract values
    y_pred = dataframe[predicted_value_column].values
    y_true = dataframe[ground_truth_column].values

    # Default pos_label to the second label if not specified
    if pos_label is None:
        pos_label = labels[1]

    # Try to get dataframe name from caller if not provided
    if df_name is None:
        try:
            frame = inspect.currentframe().f_back
            df_name = next(
                (name for name, val in frame.f_locals.items() if val is dataframe),
                "unknown"
            )
        except Exception:
            df_name = "unknown"

    # Calculate evaluation metrics
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, labels=labels, average='binary', pos_label=pos_label, zero_division=0)
    recall = recall_score(y_true, y_pred, labels=labels, average='binary', pos_label=pos_label, zero_division=0)
    f1 = f1_score(y_true, y_pred, labels=labels, average='binary', pos_label=pos_label, zero_division=0)
    conf_matrix = confusion_matrix(y_true, y_pred, labels=labels)

    cm = conf_matrix
    tn, fp, fn, tp = cm[0,0], cm[0,1], cm[1,0], cm[1,1]
    n = tn + fp + fn + tp

    results = {
        'task': task,
        'prompt': prompt,
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'tp': tp,
        'tn': tn,
        'fp': fp,
        'fn': fn,
        'n': n,
        'confusion_matrix': conf_matrix,
        'confusion_matrix_labels': labels
    }

    # Print report
    cm = conf_matrix
    print("\n" + "="*60)
    print(f"CLASSIFICATION EVALUATION REPORT OF {df_name}")
    print("="*60)
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print("\nConfusion Matrix:")
    print(f"\n            Predicted {labels[0]:<10}  Predicted {labels[1]:<10}")
    print(f"Actual {labels[0]:<5} {cm[0, 0]:>18d}  {cm[0, 1]:>18d}")
    print(f"Actual {labels[1]:<5} {cm[1, 0]:>18d}  {cm[1, 1]:>18d}")
    print("="*60 + "\n")

    return results

def join_predictions_to_ground_truth(gt_df, pred_df, join_key, how='left'): #TODO: IST ES RICHTIG LEFT JOIN? WAS WENN IN DEN NÄCHSTEN SCHRITTEN UNTERSCHIEDLICHE LÄNGE

    merged_df = gt_df.merge(pred_df, on=join_key, how=how, suffixes=('_gt', '_pred'))

    n_missing = merged_df['prediction'].isna().sum() if 'prediction' in merged_df.columns else None

    if n_missing is not None:
        print(f"Missing predictions: {n_missing}")

    return merged_df

def evaluate_all_chunks(document, process, llm_client=None, evaluation_prompt_template=None):
    # Normalize all chunks to (chunk_id, chunk) pairs
    chunks_with_ids = [
        item if isinstance(item, tuple) else (i + 1, item)
        for i, item in enumerate(document)
    ]

    # Serialize the full document list into one block
    document_block = "\n\n".join(
        f"[Chunk {chunk_id}]:\n{chunk}" for chunk_id, chunk in chunks_with_ids
    )

    evaluation_prompt = evaluation_prompt_template.format(process=process, chunk=document_block)
    response = get_llm_response(evaluation_prompt, llm_client)

    try:
        clean = response.strip().removeprefix("```json").removesuffix("```").strip()
        parsed_list = json.loads(clean)
        if not isinstance(parsed_list, list):
            parsed_list = [parsed_list]
    except:
        parsed_list = []

    # Align results back to original chunks by chunk_id
    llm_by_id = {item.get("chunk_id", i + 1): item for i, item in enumerate(parsed_list)}

    results = [
        {

            **{k: v for k, v in llm_by_id.get(chunk_id, {}).items() if k != 'chunk_id'}
        }
        for chunk_id, chunk in chunks_with_ids
    ]

    return pd.DataFrame(results)


def evaluate_chunk_df_judge_compliance(df, rule, process_sentence, explanation, category, full_process, llm_client=None,
                                       evaluation_prompt_template=None):
    results = []
    parsed_fields = set()

    for i, row in df.iterrows():

        evaluation_prompt = evaluation_prompt_template.format(
            rule=row[rule],
            process_sentence=row[process_sentence],
            full_process=full_process,
            explanation=row[explanation],
            category=row[category]
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            parsed_fields.update(parsed.keys())
        except:
            parsed = {}

        results.append({
            **row.to_dict(),  # all original columns
            **parsed  # appended parsed fields
        })

    return pd.DataFrame(results)


# DIESE FUNKTION WIRDERHOLT SICH; BEIM NÄCHSten refortoren könnte man sie anpassen, sodasss die Abhänfifket zum prompt nicht drin ist, sindern VORGELAGERT
def evaluate_chunk_df_judge_compliance(df, rule, process_sentence, explanation, category, full_process, llm_client=None,
                                       evaluation_prompt_template=None):
    results = []
    parsed_fields = set()

    for i, row in df.iterrows():

        evaluation_prompt = evaluation_prompt_template.format(
            rule=row[rule],
            process_sentence=row[process_sentence],
            full_process=full_process,
            explanation=row[explanation],
            category=row[category]
        )
        response = get_llm_response(evaluation_prompt, llm_client)

        try:
            clean = response.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            parsed_fields.update(parsed.keys())
        except:
            parsed = {}

        results.append({
            **row.to_dict(),  # all original columns
            **parsed  # appended parsed fields
        })

    return pd.DataFrame(results)

def find_top_similar_sentences(query: str, original_text: str, top_k: int = 1) -> list[str]:
    """
    Findet die TOP-K ähnlichsten Sätze (sortiert nach Ähnlichkeit).
    Kein Threshold - immer genau top_k Ergebnisse (oder weniger).
    """
    if pd.isna(original_text) or not isinstance(original_text, str):
        return []

    # Sätze splitten
    sentences = re.split(r'(?<=[.!?;])\s+', original_text.strip())
    sentences = [s.strip() for s in sentences if len(s) > 3]

    if not sentences:
        return []
    # Embeddings
    query_emb = model.encode(query)
    sent_embs = model.encode(sentences)

    # Ähnlichkeiten berechnen & TOP-K holen
    similarities = util.pytorch_cos_sim(query_emb, sent_embs)[0]

    # Top-K Indizes (sortiert absteigend)
    top_indices = similarities.argsort(descending=True)[:top_k]

    # Top-Sätze zurückgeben
    top_sentences = [sentences[i] for i in top_indices]

    return top_sentences

def find_top_similar_sentences(query: str, original_text: str, threshold: float = 0.6) -> list[str]:
    """
    Findet alle Sätze über einem Ähnlichkeits-Threshold (sortiert nach Ähnlichkeit).
    """
    if pd.isna(original_text) or not isinstance(original_text, str):
        return []

    # Sätze splitten
    sentences = re.split(r'(?<=[.!?;])\s+', original_text.strip())
    sentences = [s.strip() for s in sentences if len(s) > 3]

    if not sentences:
        return []

    # Embeddings
    query_emb = model.encode(query)
    sent_embs = model.encode(sentences)

    # Ähnlichkeiten berechnen
    similarities = util.pytorch_cos_sim(query_emb, sent_embs)[0]

    # Nur Sätze über dem Threshold, sortiert absteigend
    filtered = [
        sentences[i]
        for i in similarities.argsort(descending=True)
        if similarities[i] >= threshold
    ][:1]

    return filtered

def convert_bpmn_to_text(bpmn_content, llm_client=None):
    """
    Convert a BPMN XML file to plain text using LLM.

    Args:
        bpmn_content (str): The BPMN XML content as a string
        llm_client: The OpenAI/Azure client for LLM calls

    Returns:
        str: Plain text description of the BPMN process
    """
    prompt_bpmn_to_text = """You are an expert in summarizing BPMN models. Your task is to create a clear, precise, and coherent summary of a BPMN process model based on an XML representation of BPMN that you receive. Describe the entire process in the correct logical sequence and do not simply omit parts. However, do not add any information that does not clearly emerge from the process model. Pay attention to the following points:

1. **Process overview:** Begin with an introductory sentence that describes the main goal of the process as well as the fundamental steps.

2. **Content completeness:** Ensure that all essential elements of the process are covered, in particular:
   * **Lanes:** Describe the roles involved in the process.
   * **Tasks:** Explain the activities and who performs them.
   * **Gateways:** Describe the decision points and which decisions are made by whom.
   * **Annotations:** Incorporate the content from annotations in an appropriate way, since the modeling person considered this information important.
   * **Links:** Mention when links to other content or models are included and where they lead. Also include the links with their URLs in the summary.

3. **Explain control flow:** Explain how the tasks are connected and which events enable the transition from one task to the next. Address sequences and dependencies.

4. **Preservation of specifics:** Preserve proper names in texts and specific characteristics of the model to ensure that the summary clearly identifies the process. Technical IDs, such as alphanumeric IDs from the XML, should not be mentioned because they are not relevant for understanding.

5. **Avoid interpretation:** Strictly adhere to the given information without adding subjective or interpretative elements.

6. **Clear chronological structure:** Describe the model in a coherent text in its correct logical sequence. You may use subheadings to structure your response.

Ensure that the summary is informative and readable without adding another summary of the process at the end.

Input:
{content}"""

    evaluation_prompt = prompt_bpmn_to_text.format(content=bpmn_content)
    bpmn_text = get_llm_response(evaluation_prompt, llm_client)

    return bpmn_text

def extract_bpmn_elements(bpmn_xml: str) -> List[Dict]:
    """
    Parse BPMN XML und extrahiere alle relevanten Elemente mit Text.

    Args:
        bpmn_xml: BPMN XML content as string

    Returns:
        List[Dict]: Liste von BPMN-Elementen mit id, type, name, text
    """
    try:
        root = ET.fromstring(bpmn_xml)
    except ET.ParseError as e:
        print(f"[BPMN] XML Parse Error: {e}")
        return []

    # BPMN Namespace
    namespaces = {
        'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
        'bpmn2': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
        'bpmndi': 'http://www.omg.org/spec/BPMN/20100524/DI',
    }

    elements = []

    # Helper function to extract text from element
    def get_element_text(elem, namespaces):
        name = elem.get('name', '')

        # Try to find documentation
        doc_text = ''
        for ns_prefix in ['bpmn', 'bpmn2']:
            doc = elem.find(f'.//{ns_prefix}:documentation', namespaces)
            if doc is not None and doc.text:
                doc_text = doc.text.strip()
                break

        # Combine name and documentation
        text = f"{name} {doc_text}".strip()
        return name, doc_text, text

    # Extract all task types
    task_types = [
        'task', 'userTask', 'serviceTask', 'scriptTask',
        'businessRuleTask', 'manualTask', 'sendTask', 'receiveTask'
    ]

    for task_type in task_types:
        for ns_prefix in ['bpmn', 'bpmn2', '']:
            xpath = f'.//{ns_prefix}:{task_type}' if ns_prefix else f'.//{task_type}'
            try:
                for task in root.findall(xpath, namespaces if ns_prefix else {}):
                    element_id = task.get('id')
                    if not element_id:
                        continue

                    name, doc, text = get_element_text(task, namespaces)

                    if text:  # Only add if there's actual text
                        elements.append({
                            'id': element_id,
                            'type': task_type,
                            'name': name,
                            'documentation': doc,
                            'text': text
                        })
            except Exception:
                continue

    # Extract Gateways
    gateway_types = [
        'exclusiveGateway', 'parallelGateway', 'inclusiveGateway',
        'eventBasedGateway', 'complexGateway'
    ]

    for gateway_type in gateway_types:
        for ns_prefix in ['bpmn', 'bpmn2', '']:
            xpath = f'.//{ns_prefix}:{gateway_type}' if ns_prefix else f'.//{gateway_type}'
            try:
                for gateway in root.findall(xpath, namespaces if ns_prefix else {}):
                    element_id = gateway.get('id')
                    if not element_id:
                        continue

                    name, doc, text = get_element_text(gateway, namespaces)

                    # Gateways often don't have names, use type as fallback
                    if not text:
                        text = gateway_type.replace('Gateway', ' Gateway')

                    elements.append({
                        'id': element_id,
                        'type': gateway_type,
                        'name': name,
                        'documentation': doc,
                        'text': text
                    })
            except Exception:
                continue

    # Extract Events
    event_types = [
        'startEvent', 'endEvent', 'intermediateThrowEvent',
        'intermediateCatchEvent', 'boundaryEvent'
    ]

    for event_type in event_types:
        for ns_prefix in ['bpmn', 'bpmn2', '']:
            xpath = f'.//{ns_prefix}:{event_type}' if ns_prefix else f'.//{event_type}'
            try:
                for event in root.findall(xpath, namespaces if ns_prefix else {}):
                    element_id = event.get('id')
                    if not element_id:
                        continue

                    name, doc, text = get_element_text(event, namespaces)

                    # Events often don't have names, use type as fallback
                    if not text:
                        text = event_type.replace('Event', ' Event')

                    elements.append({
                        'id': element_id,
                        'type': event_type,
                        'name': name,
                        'documentation': doc,
                        'text': text
                    })
            except Exception:
                continue

    print(f"[BPMN] Extracted {len(elements)} elements from BPMN XML")
    return elements


def find_best_matching_bpmn_element(
    highlighted_text: str,
    bpmn_elements: List[Dict],
    bpmn_element_embeddings: np.ndarray,
    model: SentenceTransformer,
    threshold: float = 0.3
) -> Optional[str]:
    """
    Findet das BPMN-Element mit höchster semantischer Ähnlichkeit.

    Args:
        highlighted_text: Der hervorgehobene Prozesstext (oder Liste)
        bpmn_elements: Liste aller BPMN-Elemente mit Text
        bpmn_element_embeddings: Pre-computed embeddings für BPMN-Elemente
        model: Sentence-Transformer-Modell
        threshold: Minimum similarity (0-1)

    Returns:
        element_id des best-matching Elements oder None
    """
    if not bpmn_elements or not highlighted_text:
        return None

    # Handle list of text segments
    if isinstance(highlighted_text, list):
        highlighted_text = ' '.join(str(x) for x in highlighted_text if x)

    highlighted_text = str(highlighted_text).strip()
    if not highlighted_text:
        return None

    try:
        # Compute embedding for highlighted text
        text_emb = model.encode(highlighted_text)

        # Compute similarities with pre-computed BPMN embeddings
        similarities = util.pytorch_cos_sim(text_emb, bpmn_element_embeddings)[0]

        # Find best match
        max_idx = similarities.argmax().item()
        max_sim = similarities[max_idx].item()

        if max_sim >= threshold:
            matched_id = bpmn_elements[max_idx]['id']
            matched_text = bpmn_elements[max_idx]['text']
            print(f"[BPMN Match] Text: '{highlighted_text[:50]}...' -> Element: '{matched_text}' (similarity: {max_sim:.3f})")
            return matched_id
        else:
            print(f"[BPMN Match] No match above threshold {threshold} (best: {max_sim:.3f})")
            return None

    except Exception as e:
        print(f"[BPMN Match] Error: {e}")
        return None
