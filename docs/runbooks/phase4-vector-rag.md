# Phase 4 — Knowledge → Data Cloud Search Index (Vector Search)

**Goal.** Load Wikipedia narrative text into Salesforce Knowledge (for citations) and build a Data Cloud **Search Index (Vector Search)** over that content.

This runbook is written for a **Salesforce Developer Edition** org with tight storage. It uses **one Knowledge article per Wikipedia entity** (~80 records), then chunks inside the Search Index using **Passage Extraction**.

**Time budget.** ~2 hours.

## Prerequisites

- Phase 3 complete: Data Cloud **Provisioned** (see [phase3-zero-copy-setup.md](phase3-zero-copy-setup.md)).
- Lightning Knowledge enabled: **Setup** → Quick Find **Knowledge** → turn on Lightning Knowledge.
- Deploy custom fields on `Knowledge__kav`:

```powershell
sf project deploy start -o football_agent -d force-app/main/default/objects/Knowledge__kav
```

Custom fields used: `Body__c`, `EntityType__c`, `EntitySlug__c`, `SourceUrl__c`.  
Standard fields used: `Title`, `Summary`, `UrlName`, `Language`, `PublishStatus`.

---

## Step 1 — Chunk Wikipedia locally

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .

python -m etl.embed.chunker --parquet data/wikipedia/documents --out data/chunks/wikipedia.jsonl
```

Expected: `data/chunks/wikipedia.jsonl` exists and is ~4,218 lines.

---

## Step 2 — Upload Knowledge (entity-level) and publish

Upload one Knowledge article per entity:

```powershell
.\.venv\Scripts\python.exe -m etl.embed.upload_to_knowledge `
  --jsonl data/chunks/wikipedia.jsonl `
  --granularity entity `
  --on-duplicate skip
```

Publish drafts:

> **Setup** → Quick Find **Knowledge Settings** → **Publish All Drafts**.

Expected: ~80 published Knowledge articles.

---

## Step 3 — Data Cloud Data Stream for `Knowledge__kav`

Create the data stream:

1. **App Launcher** → **Data Cloud**.
2. **Data Streams** → **New**.
3. Source: **Salesforce CRM** (Salesforce connector).
4. Object: `**Knowledge__kav`**.
5. Set these names:


| UI field                      | Value                          |
| ----------------------------- | ------------------------------ |
| **Data Stream Name**          | `WikipediaKnowledgeStream`     |
| **Data Lake Object Label**    | `Wikipedia Knowledge Articles` |
| **Data Lake Object API Name** | `WikipediaKnowledge__dll`      |
| **Object Category**           | `Knowledge`                    |
| **Primary Key**               | `Knowledge Article Version ID` |


1. Select fields:
  - Standard: **Title**, **Summary**, **UrlName**, **Language**, **PublishStatus**
  - Custom: **Body__c**, **EntityType__c**, **EntitySlug__c**, **SourceUrl__c**
  - Unselect: `MigratedToFromArticleVersion`
2. Deploy and wait for the stream status to be **Active**.

---

## Step 3b — Map the Data Stream to a DMO

1. Open **Data Streams** → `WikipediaKnowledgeStream`.
2. In the **Data Mapping** card, click **Start**.
3. Create a new DMO:
  - **DMO label:** `Wikipedia Knowledge Article Version`
  - **DMO API name:** `WikipediaKnowledgeArticleVersion__dlm`
4. Auto-map fields and verify these key mappings exist:
  - `Id__c` → primary key (Knowledge Article Version Id)
  - `Body__c` → body text field (DMO API name will appear as `Body__c__c`)
  - `EntitySlug__c`, `EntityType__c` → filter fields (DMO API names `EntitySlug__c__c`, `EntityType__c__c`)
  - `SourceUrl__c` → citation URL field (DMO API name `SourceUrl__c__c`)
5. Save/deploy until mapping shows **Complete**.

Expected: the DMO contains rows (~80).

---

## Step 4 — Create the Search Index (Vector Search)

1. **Data Cloud** → **Search Indexes** → **New**.
2. Choose **Advanced Setup**.
3. Search type: **Vector Search**.
4. **Search Index label:** `Fan360 Wiki Knowledge`
5. **Search Index API name:** `Fan360WikiKnowledge` (keep this short)
6. Source DMO: `WikipediaKnowledgeArticleVersion__dlm`.
7. **Fields to chunk:** `Body__c` only.
  - Chunking strategy: **Passage Extraction**
  - Strip HTML: **true**
  - Max tokens: **512**
8. **Fields for filtering:** select the DMO fields whose API names are `EntityType__c__c` and `EntitySlug__c__c` (labels are still *Entity Type* and *Entity Slug*).
9. Vector model: **E5 Large V2 Embedding Model**.
10. Save.

---

## Step 5 — Run the index build

Open the Search Index → **Rebuild**.

Expected: **Process History** has an entry with status **Succeeded** and non-zero records/chunks processed.

---

## Verification (Phase 4 exit gate)

In the Search Index preview/test search, run:

- `Pep Guardiola false nine`
- `Klopp gegenpressing`

Expected:

- Results include relevant passages from `Body__c`.
- Filters reflect `EntityType__c` / `EntitySlug__c`.
- Each result has a usable Wikipedia URL (from `SourceUrl__c`).

Record for Phase 5:

- Search Index API name: `Fan360WikiKnowledge`
- Source DMO: `WikipediaKnowledgeArticleVersion__dlm`

---

## Optional — Supabase pgvector (chunk-level RAG store)

This is a **separate** vector store used by `cloud-run/llm-shim` for `/rag/search`. It stores **one row per chunk** (~4,218 rows) and is not constrained by Salesforce DE data storage.

### Step S1 — Create the table in Supabase

Supabase → your project → **SQL Editor**. Run:

```sql
create extension if not exists vector;

create table if not exists broadcast_knowledge (
  chunk_id     text primary key,
  source_url   text,
  title        text,
  entity_type  text,
  entity_slug  text,
  text         text,
  token_count  int,
  vector       vector(768)
);

create index if not exists broadcast_knowledge_vec_idx
  on broadcast_knowledge using ivfflat (vector vector_cosine_ops);
```

### Step S2 — Get the connection string (Session pooler)

Supabase → **Connect** (top header) → **Connection string** → **Session pooler** → format **URI**.

Copy the URI and replace `[YOUR-PASSWORD]` with your DB password. Use the URI as-is (no manual edits).

### Step S3 — Upload parquet embeddings into pgvector

```powershell
$env:PGVECTOR_DSN = "<paste Session pooler URI here>"

.\.venv\Scripts\python.exe -m etl.embed.upload_to_pgvector `
  --parquet data/embeddings/wikipedia.parquet `
  --batch-size 200 `
  --log-every-batches 5
```

### Step S4 — Verify data in Supabase (SQL)

```sql
select count(*) as rows from broadcast_knowledge;
```

```sql
select count(*) filter (where vector is not null) as with_vector,
       count(*) as total
from broadcast_knowledge;
```

```sql
select chunk_id, entity_slug, left(text, 120) as snippet
from broadcast_knowledge
limit 5;
```

Proceed to [phase5-agent-build.md](phase5-agent-build.md).