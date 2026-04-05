# BPMN Element Highlighting - Konzeptionelles Design

## 🎯 Ziel

Wenn ein Compliance-Segment im Prozesstext (oben) hervorgehoben wird, soll automatisch das **am besten passende BPMN-Element** im Diagramm (unten) visuell hervorgehoben werden.

---

## 📊 Bestehende Architektur

### Aktueller Text-Highlighting-Flow:

```
User klickt Segment in SegmentTable
    ↓
activeSegmentId wird gesetzt
    ↓
TextViewer erhält activeSegmentId
    ↓
extracted_process_segment wird mit fuzzy matching im Text gefunden
    ↓
Text-Region wird visuell hervorgehoben (gelber Hintergrund)
```

### Datenstruktur:

```typescript
ComplianceSegment {
  id: string
  extracted_process_segment: string[]  // Array von Text-Passagen
  // ... andere Felder
}
```

---

## 🧠 Konzeptionelle Lösung

### Ansatz: **Semantic Matching zwischen Text und BPMN-Elementen**

Da wir:
1. ✅ **Hervorgehobene Text-Segmente** haben (`extracted_process_segment`)
2. ✅ **BPMN-XML mit Element-Namen** haben (Tasks, Gateways, Events)
3. ✅ **Sentence-Transformer-Modell** bereits verwenden (`all-MiniLM-L6-v2`)

Können wir:
- **BPMN-Element-Texte extrahieren** (Task-Namen, Gateway-Labels, etc.)
- **Semantic Similarity** zwischen hervorgehobenem Text und BPMN-Element-Texten berechnen
- **Top-1-Match** im Diagramm highlighten

---

## 🔄 Architektur-Erweiterung

### Phase 1: Backend-Enhancement (Python)

#### 1.1 BPMN-Element-Extraktion

```python
def extract_bpmn_elements(bpmn_xml: str) -> List[BpmnElement]:
    """
    Parse BPMN XML und extrahiere alle relevanten Elemente mit Text.
    
    Returns:
        List[BpmnElement]: Liste von BPMN-Elementen mit ID und Text
    """
    # Parse XML
    root = ET.fromstring(bpmn_xml)
    elements = []
    
    # Extrahiere Tasks
    for task in root.findall('.//bpmn:task', namespaces):
        element_id = task.get('id')
        element_name = task.get('name', '')
        element_type = 'task'
        
        # Prüfe auf Documentation/Annotation
        doc = task.find('.//bpmn:documentation', namespaces)
        doc_text = doc.text if doc is not None else ''
        
        elements.append({
            'id': element_id,
            'type': element_type,
            'name': element_name,
            'documentation': doc_text,
            'text': f"{element_name} {doc_text}".strip()
        })
    
    # Extrahiere User Tasks
    for task in root.findall('.//bpmn:userTask', namespaces):
        # ... analog
    
    # Extrahiere Service Tasks
    for task in root.findall('.//bpmn:serviceTask', namespaces):
        # ... analog
    
    # Extrahiere Gateways
    for gateway in root.findall('.//bpmn:*Gateway', namespaces):
        # ... analog
    
    # Extrahiere Events
    for event in root.findall('.//bpmn:*Event', namespaces):
        # ... analog
    
    return elements
```

#### 1.2 Semantic Matching Funktion

```python
def find_best_matching_bpmn_element(
    highlighted_text: str,
    bpmn_elements: List[Dict],
    model: SentenceTransformer,
    threshold: float = 0.3
) -> Optional[str]:
    """
    Findet das BPMN-Element mit höchster semantischer Ähnlichkeit.
    
    Args:
        highlighted_text: Der hervorgehobene Prozesstext
        bpmn_elements: Liste aller BPMN-Elemente mit Text
        model: Sentence-Transformer-Modell
        threshold: Minimum similarity (0-1)
    
    Returns:
        element_id des best-matching Elements oder None
    """
    if not bpmn_elements or not highlighted_text:
        return None
    
    # Embeddings berechnen
    text_emb = model.encode(highlighted_text)
    element_texts = [elem['text'] for elem in bpmn_elements]
    element_embs = model.encode(element_texts)
    
    # Ähnlichkeiten berechnen
    similarities = util.pytorch_cos_sim(text_emb, element_embs)[0]
    
    # Bestes Element finden
    max_idx = similarities.argmax()
    max_sim = similarities[max_idx].item()
    
    if max_sim >= threshold:
        return bpmn_elements[max_idx]['id']
    
    return None
```

#### 1.3 Pipeline-Integration

In `run_pipeline()` nach Sentence-Matching:

```python
# Bestehend: Step 9 - Sentence Matching
df_final["top_similar_sentences"] = df_final.apply(...)

# NEU: Step 10 - BPMN Element Matching (nur wenn BPMN vorhanden)
if bpmn_xml:
    bpmn_elements = extract_bpmn_elements(bpmn_xml)
    
    df_final["matched_bpmn_element_id"] = df_final.apply(
        lambda row: find_best_matching_bpmn_element(
            row["extracted_process_segment"],
            bpmn_elements,
            st_model
        ),
        axis=1
    )
else:
    df_final["matched_bpmn_element_id"] = None
```

---

### Phase 2: Frontend-Enhancement (TypeScript/React)

#### 2.1 Type-Erweiterung

```typescript
// lib/types.ts
export interface ComplianceSegment {
  id: string
  process_id: number
  category: string
  short_evidence: string
  easy_rule: string
  chunk_id: string
  chunk_text: string
  extracted_process_segment: string[]
  matched_bpmn_element_id?: string | null  // ← NEU
}
```

#### 2.2 BPMN-Viewer mit Highlighting

```typescript
// components/bpmn-viewer.tsx

interface BpmnViewerProps {
  bpmnXml?: string | null
  highlightedElementId?: string | null  // ← NEU
}

export function BpmnViewer({ bpmnXml, highlightedElementId }: BpmnViewerProps) {
  // ...existing viewer setup...
  
  useEffect(() => {
    if (!viewerRef.current || !highlightedElementId) return
    
    const canvas = viewerRef.current.get("canvas")
    const elementRegistry = viewerRef.current.get("elementRegistry")
    const graphicsFactory = viewerRef.current.get("graphicsFactory")
    
    // Clear previous highlights
    canvas.removeMarker(previousHighlight, 'highlight')
    
    // Add highlight to new element
    const element = elementRegistry.get(highlightedElementId)
    if (element) {
      canvas.addMarker(highlightedElementId, 'highlight')
      
      // Optional: Scroll to element
      canvas.scrollToElement(element)
    }
    
    setPreviousHighlight(highlightedElementId)
  }, [highlightedElementId])
  
  // ...rest of component...
}
```

#### 2.3 CSS für BPMN-Highlighting

```css
/* app/globals.css */

/* BPMN Element Highlighting */
.djs-element.highlight .djs-visual > :nth-child(1) {
  stroke: #f59e0b !important;  /* Orange border */
  stroke-width: 3px !important;
  fill: #fef3c7 !important;    /* Light yellow fill */
}

.djs-element.highlight .djs-visual text {
  fill: #92400e !important;    /* Dark text */
  font-weight: bold !important;
}

/* Animation für sanften Übergang */
.djs-element .djs-visual > * {
  transition: stroke 0.3s ease, fill 0.3s ease;
}
```

#### 2.4 Document-Reviewer Integration

```typescript
// components/document-reviewer.tsx

// Im Results-Phase:
const activeSegment = sortedSegments.find(s => s.id === activeSegmentId)
const highlightedBpmnElementId = activeSegment?.matched_bpmn_element_id ?? null

return (
  <ResizablePanel defaultSize={40} minSize={25}>
    <ResizablePanelGroup direction="vertical">
      {/* Oben: TextViewer */}
      <ResizablePanel defaultSize={50}>
        <TextViewer
          process={data.process}
          segments={filteredSegments}
          activeSegmentId={activeSegmentId}
        />
      </ResizablePanel>
      
      <ResizableHandle withHandle />
      
      {/* Unten: BpmnViewer mit Highlighting */}
      <ResizablePanel defaultSize={50}>
        <BpmnViewer 
          bpmnXml={data.bpmnXml}
          highlightedElementId={highlightedBpmnElementId}  // ← NEU
        />
      </ResizablePanel>
    </ResizablePanelGroup>
  </ResizablePanel>
)
```

---

## 🔍 Matching-Strategien

### Option A: **Direkte Semantic Similarity** (Empfohlen)

**Pro:**
- Nutzt bereits vorhandenes Sentence-Transformer-Modell
- Funktioniert auch bei unterschiedlicher Formulierung
- Keine zusätzlichen LLM-Calls nötig

**Con:**
- Matching-Qualität hängt von BPMN-Element-Namen ab
- Kurze Task-Namen ("Approve", "Send") haben wenig Kontext

**Implementierung:**
```python
# Backend
text = "The merchant reviews and signs the standard service agreement"
bpmn_elements = [
    {'id': 'Task_123', 'text': 'Sign service agreement'},
    {'id': 'Task_456', 'text': 'Review contract terms'},
    {'id': 'Task_789', 'text': 'Submit application'}
]
best_match = find_best_matching_bpmn_element(text, bpmn_elements, model)
# → 'Task_123' (höchste Similarity)
```

### Option B: **Keyword-basiertes Matching**

**Pro:**
- Einfach und schnell
- Keine ML-Modelle nötig

**Con:**
- Funktioniert nicht bei Synonymen/Paraphrasen
- Braucht exakte Übereinstimmung

**Implementierung:**
```python
def keyword_match(text: str, bpmn_elements: List[Dict]) -> Optional[str]:
    text_words = set(text.lower().split())
    
    best_match = None
    best_overlap = 0
    
    for elem in bpmn_elements:
        elem_words = set(elem['text'].lower().split())
        overlap = len(text_words & elem_words)
        
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = elem['id']
    
    return best_match if best_overlap > 0 else None
```

### Option C: **Hybrid: Semantic + Keyword**

**Pro:**
- Kombiniert Vorteile beider Ansätze
- Fallback auf Keywords wenn Semantic schwach

**Con:**
- Komplexere Logik

**Implementierung:**
```python
def hybrid_match(text, bpmn_elements, model):
    # Zuerst: Semantic
    semantic_match = find_best_matching_bpmn_element(text, bpmn_elements, model)
    
    if semantic_match and similarity > 0.5:
        return semantic_match
    
    # Fallback: Keyword
    return keyword_match(text, bpmn_elements)
```

---

## 📦 Datenfluss

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User wählt BPMN-Datei & startet Analyse                  │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Backend: convert_bpmn_to_text()                          │
│    - Erstellt Prozesstext für Compliance-Analyse            │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Backend: run_pipeline()                                  │
│    - Standard Compliance-Analyse läuft                      │
│    - Extrahiert "extracted_process_segment" für jedes Rule  │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Backend: extract_bpmn_elements(bpmn_xml)                 │
│    - Parse BPMN XML                                         │
│    - Extrahiert alle Tasks, Gateways, Events mit Text       │
│    - Ergebnis: [{'id': 'Task_1', 'text': 'Review...'}]      │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Backend: find_best_matching_bpmn_element()               │
│    - Für jedes Segment:                                     │
│      * Compute Embedding von extracted_process_segment      │
│      * Compute Embeddings aller BPMN-Element-Texte          │
│      * Finde Element mit höchster Cosine-Similarity         │
│      * Speichere Element-ID in "matched_bpmn_element_id"    │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Backend: Response                                        │
│    {                                                        │
│      process: "...",                                        │
│      segments: [                                            │
│        {                                                    │
│          id: "seg-1",                                       │
│          extracted_process_segment: ["merchant signs..."], │
│          matched_bpmn_element_id: "Task_SignAgreement"  ← │
│        }                                                    │
│      ],                                                     │
│      bpmnXml: "<bpmn:definitions...>"                       │
│    }                                                        │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Frontend: Document-Reviewer                              │
│    - Rendert SegmentTable, TextViewer, BpmnViewer           │
│    - User klickt auf Segment → activeSegmentId = "seg-1"   │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Frontend: TextViewer                                     │
│    - Highlightet Text in "extracted_process_segment"        │
│    - Gelber Hintergrund für "merchant signs..."            │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Frontend: BpmnViewer                                     │
│    - Erhält highlightedElementId="Task_SignAgreement"       │
│    - Verwendet bpmn-js API:                                 │
│      * canvas.addMarker('Task_SignAgreement', 'highlight')  │
│    - CSS applied: Orange Border + Yellow Fill               │
│    - Optional: canvas.scrollToElement()                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎨 Visuelles Ergebnis

```
┌─────────────────────────────────────────────────────────────┐
│ Segments Table                                              │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ [SELECTED] → Service Agreement Rule              ← Click││
│ │              Non-Compliant                              ││
│ └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                     ↓ aktiviert beide:
┌─────────────────────────────────────────────────────────────┐
│ Process Text (oben)                                         │
│ ┌─────────────────────────────────────────────────────────┐│
│ │ The merchant reviews and                                ││
│ │ ╔═══════════════════════════════════════════════╗       ││
│ │ ║ signs the standard service agreement          ║ ← 🟡  ││
│ │ ╚═══════════════════════════════════════════════╝       ││
│ │ which includes data handling terms...                   ││
│ └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ BPMN Model (unten)                                          │
│ ┌─────────────────────────────────────────────────────────┐│
│ │  [Start] → [Review] → ╔═══════════════════╗ → [End]    ││
│ │                        ║ Sign Agreement    ║ ← 🟠      ││
│ │                        ║   (highlighted)   ║            ││
│ │                        ╚═══════════════════╝            ││
│ └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## ⚡ Performance-Überlegungen

### Embedding-Berechnung

**Problem:** Embeddings für alle BPMN-Elemente bei jedem Segment-Match neu berechnen ist teuer.

**Lösung: Pre-compute & Cache**

```python
# In run_pipeline() EINMAL berechnen
if bpmn_xml:
    bpmn_elements = extract_bpmn_elements(bpmn_xml)
    
    # Pre-compute embeddings EINMAL
    element_texts = [elem['text'] for elem in bpmn_elements]
    bpmn_element_embeddings = st_model.encode(element_texts)
    
    # Matching mit pre-computed embeddings
    df_final["matched_bpmn_element_id"] = df_final.apply(
        lambda row: find_best_match_with_precomputed(
            row["extracted_process_segment"],
            bpmn_elements,
            bpmn_element_embeddings,
            st_model
        ),
        axis=1
    )
```

**Zeit-Ersparnis:**
- Ohne Cache: N_segments × N_elements × embedding_time
- Mit Cache: N_segments × similarity_computation_time (viel schneller!)

---

## 🧪 Test-Strategie

### Unit Tests

```python
def test_extract_bpmn_elements():
    bpmn_xml = """
    <bpmn:definitions>
      <bpmn:task id="Task_1" name="Review Application" />
      <bpmn:userTask id="Task_2" name="Sign Contract" />
    </bpmn:definitions>
    """
    elements = extract_bpmn_elements(bpmn_xml)
    assert len(elements) == 2
    assert elements[0]['id'] == 'Task_1'
    assert 'Review Application' in elements[0]['text']

def test_semantic_matching():
    text = "The user signs the contract"
    elements = [
        {'id': 'Task_1', 'text': 'Review document'},
        {'id': 'Task_2', 'text': 'Sign contract'},
        {'id': 'Task_3', 'text': 'Submit form'}
    ]
    match = find_best_matching_bpmn_element(text, elements, model)
    assert match == 'Task_2'
```

### Integration Tests

```python
def test_full_pipeline_with_bpmn_matching():
    process_text = "User signs agreement"
    bpmn_xml = load_test_bpmn()
    regulation = load_test_regulation()
    
    df_result = run_pipeline(process_text, regulation, client, bpmn_xml)
    
    assert 'matched_bpmn_element_id' in df_result.columns
    assert df_result['matched_bpmn_element_id'].notna().any()
```

---

## 🚀 Implementation Roadmap

### Phase 1: Backend (Python) - 4-6 Stunden

1. ✅ Implementiere `extract_bpmn_elements()` mit XML-Parsing
2. ✅ Implementiere `find_best_matching_bpmn_element()` mit Embeddings
3. ✅ Integriere in `run_pipeline()` mit Caching
4. ✅ Unit Tests schreiben
5. ✅ Manuelle Tests mit Beispiel-BPMN

### Phase 2: Frontend (TypeScript/React) - 3-4 Stunden

1. ✅ Erweitere `ComplianceSegment` Type um `matched_bpmn_element_id`
2. ✅ Erweitere `BpmnViewer` um `highlightedElementId` Prop
3. ✅ Implementiere Highlighting-Logik mit `bpmn-js` Markers
4. ✅ CSS für visuelles Highlighting
5. ✅ Integriere in `document-reviewer.tsx`

### Phase 3: Testing & Refinement - 2-3 Stunden

1. ✅ End-to-End Tests
2. ✅ Performance-Optimierung
3. ✅ Edge-Case-Handling (kein Match, mehrere gleich gute Matches)
4. ✅ Dokumentation

**Gesamt: ~10-13 Stunden**

---

## 🤔 Offene Fragen & Entscheidungen

### 1. Similarity-Threshold

**Frage:** Welcher Threshold für "good enough" Match?

**Optionen:**
- **0.3** (niedrig): Fast immer ein Match, aber evtl. falsch
- **0.5** (mittel): Balance zwischen Precision und Recall
- **0.7** (hoch): Nur sehr sichere Matches

**Empfehlung:** Start mit 0.4, dann experimentell anpassen

### 2. Mehrere Matches

**Frage:** Was wenn mehrere Elemente ähnlich gute Scores haben?

**Optionen:**
- **A:** Nur Top-1 highlighten
- **B:** Alle mit Score > Threshold highlighten (unterschiedliche Intensität)
- **C:** Top-3 anzeigen, User kann auswählen

**Empfehlung:** Option A für Simplicity, später Option B für Power-User

### 3. Kein Match

**Frage:** Was wenn kein Element über Threshold?

**Optionen:**
- **A:** Nichts highlighten (silent failure)
- **B:** Bestes Element trotzdem highlighten mit schwacher Opacity
- **C:** Nachricht anzeigen "Kein passendes BPMN-Element gefunden"

**Empfehlung:** Option A (silent), später Option C mit UI-Indikator

### 4. BPMN-Elemente ohne Namen

**Frage:** Was mit Tasks ohne `name` Attribut?

**Optionen:**
- **A:** Überspringen
- **B:** Verwende `id` als Fallback
- **C:** Verwende Documentation-Text

**Empfehlung:** Option C, dann B als Fallback

---

## 💡 Alternative Ansätze

### Alt 1: LLM-basiertes Matching

```python
def llm_based_matching(text: str, bpmn_elements: List[Dict], client) -> str:
    prompt = f"""
    Given this process text segment: "{text}"
    
    And these BPMN elements:
    {json.dumps(bpmn_elements)}
    
    Which BPMN element ID best matches the text segment?
    Return only the element ID.
    """
    response = get_llm_response(prompt, client)
    return response.strip()
```

**Pro:** Sehr intelligent, versteht Kontext
**Con:** Langsam, teuer, nicht deterministisch

### Alt 2: Position-basiertes Matching

Falls BPMN-Elemente sequentiell sind und Prozesstext auch:

```python
def position_based_matching(segment_position: int, bpmn_elements: List[Dict]) -> str:
    # Mappe Segment-Position auf BPMN-Element-Position
    index = int(segment_position / total_segments * len(bpmn_elements))
    return bpmn_elements[index]['id']
```

**Pro:** Einfach, schnell
**Con:** Funktioniert nur bei linearen Prozessen, keine Intelligenz

---

## ✅ Fazit

**JA, es ist möglich!** Die beste Lösung ist:

1. **Backend:** Semantic Matching mit Sentence-Transformers (bereits vorhanden)
2. **Frontend:** `bpmn-js` Marker API für visuelles Highlighting
3. **Performance:** Pre-compute BPMN-Element-Embeddings einmal
4. **UX:** Synchronisiertes Highlighting zwischen Text und Diagramm

**Nächster Schritt:** Möchten Sie, dass ich diese Lösung implementiere? 🚀

