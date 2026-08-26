# LARS - Laboratory Analytics & Risk System

> 🔒 **Security Notice**: This system implements **Schema-Only Prompting** for AI queries. No sensitive laboratory data (client names, test results, sample IDs) is sent to external APIs. Only metadata (column names, types, structure) is transmitted. See [Security Documentation](docs/SECURITY_SCHEMA_ONLY_PROMPTING.md) for details.

## Features
- 📊 **Pesticide Data Analysis** - AI-powered analytics for laboratory test results
- 🔬 **ISO 17025 Compliance** - Built for accredited laboratories
- 🤖 **Smart AI Assistant** - Natural language queries in Arabic and English
- 🔒 **Privacy-First Design** - Schema-only prompting ensures data never leaves your server
- 📈 **Predictive Analytics** - Trend analysis and risk assessment
- 🗺️ **Interactive Maps** - Geographic visualization of compliance data
- 🧬 **Dietary Exposure Assessment (NEW)** - PRIMo 4 methodology implementation:
  - ADI-based risk calculations (EDI, HQc, HIc)
  - 9 population classes with PRIMo 4 body weights
  - Chemical group classification (Pyrethroids, Organophosphates, Carbamates, etc.)
  - EU MRL API integration for current limits
  - Risk visualization by chemical group

This is a minimal implementation of the RAG model for Excel files retrieval.
## Requirements ›
- Python 3.8 or later
#### Install Python using MiniConda
1) Download and install MiniConda from [here] (https://docs. anaconda.com/free/miniconda/#quick-command-line-install)
2) Create a new environment using the following command:
```bash
$ conda create -n mini-rag python=3.8
```
3) Activate the environment:
```bash
$ conda activate mini-rag-app
```
## Installation
### Install the required packages
```bash
$ pip install -r requirements.txt , pip install -r src/requirements.txt
```
### Setup the environment variables
```bash
$ cp .env.example .env
```
Set your environment variables in the `.env` file. Like `OPENAI_API_KEY` value.
## Run Docker Compose Services

```bash
$ cd docker
$ cp .env.example. env
update '.env with your

## Run the FastAPI server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001

uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
``` 
## POSTMAN Collection
origin  git@github.com:yourusername/repo.git(fetch)

## Difference between branches
git diff --name-only LARS_predict pre_final
git diff LARS_predict pre_final -- path/to/suspected_file.py
git diff LARS_predict..pre_final


 
Download the POSTMAN collection from [/assets/mini-rag-app.postman_collection.json](/ assets/mini-rag-app.postman_collection.json)
# fastapi boilerplate github --> use template from others

*** for devlopmenet only not used in production {
# Show all containers
docker ps -a
# If there are containers, remove them
docker rm $(docker ps -aq)
ولو عايز تحذف حتى الـ running containers كمان، لازم توقفهم الأول:
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)}

# push to github
git push -u origin <your-branch-name>
git push -u origin Dashboard
# ollama serve from cli
/usr/local/bin/ollama serve
# run serve in colab background
!nohup ollama serve & 
!sleep 5 && tail /content/nohup.out
# to run colab server on local machine
ngrok

# Make pg_config available
brew install libpq
brew link --force libpq

# to create database
alembic revision --autogenerate -m "Initial Commit" # from minirag folder
# Apply the migration to the database
alembic upgrade head

# gemini-1.5-flash-latest API
"AIzaSyAND7ureFwWN614Fd6APcNyaBVOm3zkN3c"

# to browse data from docker
docker compose exec fastapi ls -la /app/data/2024/Feb/
# ______________________________________________________

##### instal claude agent 
specify init . --ai claude --ignore-agent-tools

docker compose down 

docker compose up --build

# Cloud Run
streamlit run src/LARS/app_new.py

# local run
LARS_API_BASE_URL=http://localhost:8090 streamlit run src/LARS/app_new.py
# lars-engine local
cd /Users/a12/lars-base
PYTHONPATH=/Users/a12/lars-base/src/LARS:/Users/a12/lars-base/src/LARS/modules \
LARS_DUCKDB_PATH=/Users/a12/lars-base/src/LARS/data/lars_data_test_copy.duckdb \
uvicorn lars_service:app --host 0.0.0.0 --port 8090

# to run questions_bank with LARS API

python3 -m py_compile /Users/a12/lars-base/src/LARS/modules/advanced_handlers.py
python3 -m py_compile /Users/a12/lars-base/src/LARS/modules/core_query_engine.py
python run_question_bank.py questions_bank.csv baseline.csv
python check_progress.py baseline.csv





find bifenazate in tomato

find bifenthrin in all samples 

Find 'Buprofezin' more than 2 times the limit in tomato samples

find non compliant samples with bifenthrin in cucumber samples 
what tomato samples is non compliant with bifenthrin?
                        ـــــــــــــــــــــــــــــــــــــــ        

 ما عدد عينات الطماطم و الخيار و الكوسة كل علي حده
ما هو عدد العينات التي تحتوي علي عدد ٦ مبيد
ابحث عن الايميداكلوبرايد داخل الفستق

ما هو عدد العينات التي تحتوي علي عدد مبيد واحد و عدد ٢ مبيد كل علي حده
ماهي عينات القرنفل التي تحتوي علي مبيد واحد

ابحث عن الفيبرونيل داخل الفاصوليا
ابحث عن imidacloprid في الفستق
ما عدد عينات الطماطم التي تكون فيها القراءة اكبر من الحدود
ما هي الخضروات التي يشملها مبيد البايفنثرن
ما هي عينات الكوسه و الباذنجان التي تحتوي علي مبيد bifenthrin 
ما هي انواع التوابل الموجودة في حي الاسكان 

 ما عدد عينات الطماطم الراسبة اخر ٣ شهور
 كم عدد حالات التسمم؟ 
اعطني تقرير للعينات الغير مطابقة لشهر مارس من حيث المنتج و المبيد و التركيز و المنطقة و تاريخ الاستلام
اعطني تقرير مفصل لاعلى 5 مبيدات من حيث عدد المخالفات و اعرضها مع عدد المخالفات


ما هي عينات الطماطم التي تحتوي علي مبيد البابروفيزن  

عينات تحتوي على الكلوربيريفوس فوق الحد

ما هي عينات الطماطم التي تحتوي علي مبيد البابروفيزن الغير مطابقة

ماهي المبيدات الموجوده في عينة الطماطم  و ما عدد تكرار المبيدات

                        ـــــــــــــــــــــــــــــــــــــــ        

ماهي المبيدات الموجوده في حي الريان و الإسكان كل علي حده
ماهي العينات الغير مطابقة الموجوده في حي الريان و الإسكان كل علي حده
ما هي العينات غير المطابقة  في جمعية البطين الزراعية
ماهي عينات القهوة الراسبة اخر شهر

كم عدد عينات الخيار الفريدة بناءً على كود العينة؟
هل ظهر الأزوكسي ستروبين في الخيار؟


######
اعرض الاحياء في ترتيب تنازلي من الاكثر الي الاقل مخالفه

اعطني المبيدات و السموم الفطريه  فوق الحد المسموح و تحت الحد المسموح للتوابل

كم عدد العينات التي تحتوي علي مبيد الايثيون

ماهو اعلي تركيز و اقل تركيز لمبيد الايميداكلوبرايد

ماهو المدي لتركيزات الايميداكلوبرايد في الطماطم

ماهو المتوسط و الوسيط لمبيد  الايميداكلوبرايد في الطماطم

اعرض المخالفات في كل حي 

   ما هو مؤشر الخطر الصحي لعينات الخيار بناءً على متوسط استهلاك الفرد في السعودية؟
  
  احسب مؤشر الجودة لعينات الفلفل او عدد المبيدات الموجودة بالفلفل



أعطني ملخص المجموعات الكيميائية لكل عينة تحتوي على أكثر من ٣ مبيدات


ماهي المبيدات التي ظهرت في الهيل
مع التكرار و عدد المخالفات

 

 ما عينات الفلفل الراسبة

 ماعدد العينات الفريدة المخالفة في الهيل و ما عدد تكرار المبيدات

 كم عدد المبيدات التي ظهرت في كل عينات الطماطم وكم عدد المبيدات المتسببة في الرسوب


 كم تكرارية الايميداكلوبرايد في الطماطم ، وكم عينة طماطم رسبت خلال التكرار

 ما متوسط تركيز الايميداكلوبريد في العينات فوق الحدود

اوجد عدد العينات الخالية من المبيدات والتي تحتوي على 1 مبيد والتي تحتوي على 3 مبيدات كل على حده



ماهي  المبيدات الموجودة في كل عينه من حيث العدد و تركيز كل مبيد، مثلا هذه العينه تحتوي علي ١٠ مبيدات ٣ مبيدات متسببه في الرسوب او ٢ مبيد متسببين في الرسوب


  """ صنف المبيدات في كل عينه علي سبيل المثال عينه كود ١٧٥٠ تحتوي علي ١٠ مبيدات هذه ال ١٠ عبارة عن ٣ بيرثرويد، ٤ اورجانو فوسفورس، ٣ اورجانوكلورين ثم اوجد , risk من جهة المبيد للعينة


  ماعدد المبيدات في كل صنف ، مثلا الطماطم عددها كلها ١٠٠ عينة ، ٥٠ عينة عدد ٢ مبيد ، ٥٠ عينه عدد ١ مبيد



# LARS — Inspection Priority & Advanced Reports

Two decision-support modules in the LARS Streamlit app (`app_new.py`), both
reading from the shared `chemistry_tidy` / `risk_scores` DuckDB tables.

| Page | Registry key | Entry point |
|---|---|---|
| 🎯 أولوية التفتيش | `"🎯 أولوية التفتيش"` | `modules.inspection_priority_page:show_inspection_priority_page` |
| 📑 التقارير المتقدمة | `"📑 التقارير المتقدمة"` | `modules.advanced_reports:show_advanced_reports_page` |

---

## 📑 Advanced Reports (التقارير المتقدمة)

### Purpose

Seasonal pesticide-residue reports previously took chemists **weeks** to
produce by hand, one commodity at a time, transcribed from printed tables.
This page generates the full report **in one click for any commodity, or
all commodities at once**, directly from live lab data.

### Report tables

| # | Sheet | Contents |
|---|---|---|
| 1 | Seasonal summary | Total / pesticide-free / with residues / violated / ≤MRL, per season |
| 2 | Residue distribution | Histogram of pesticides-per-sample, per season |
| 3 | Pesticide detail | Per-compound frequency, exceed rate, min–max, mean concentration, MRL |
| 4 | IqR quality index | Σ(conc ÷ MRL) per sample, binned into quality categories |
| 5 | Category breakdown | Insecticide / fungicide / acaricide / herbicide / nematicide |
| 6 | Facility risk scorecard | Healthy / Watch / Risky classification per facility |
| 7 | Pesticide watchlist | Compounds whose exceed rate is rising season-over-season |

All seven render as tabs in the UI and export as a single Excel workbook.

### ⚠️ Compliance verdict — read this before modifying

**`sample_result` is the single source of truth for compliance.** Never
re-derive violations from `concentration > limit_value`.

An earlier version did exactly that and reported **35 violated** cucumber
samples in Winter; the correct lab-adjudicated figure is **2**. The raw
`limit_value` field carries data-entry noise (typos, superseded standards),
while `sample_result` holds the chemists' actual sign-off.

Raw MRL comparison is still used, but **only** for:
- Table 3 exceed-rate statistics (diagnostic)
- Table 4 IqR severity scoring
- The verdict-reconciliation audit (flags where the two disagree)

### MRL canonicalization rule

Applied per `(commodity, pesticide)` group in `canonicalize_mrl()`:

| Condition | Treatment |
|---|---|
| Most frequent value | **Dominant** — the reference |
| Minority, ≤2 samples, clean 10×/100×/0.1×/0.01× shift | **Typo** → corrected to dominant |
| Minority, >2 samples | **Legitimate superseded standard** → kept as recorded |
| Anything else | **Ambiguous** → kept as recorded, flagged for review |

Worked example — dinotefuran in cucumber: `5.0` (n=2) is corrected to the
dominant `0.5`; `0.01` (n=8) is kept, being the pre-update EU MRL.

Nothing is ever silently changed — every correction is logged.

### IqR quality index

`IqR = Σ(conc_i ÷ MRL_i)` across every residue in a single sample.

| Range | Category |
|---|---|
| 0 | Excellent |
| 0 – 0.6 | Good |
| 0.6 – 1.0 | Adequate |
| > 1.0 | Inadequate |

**Why it matters:** a sample can be fully compliant (no single residue over
its own MRL) yet carry a heavy cumulative load. IqR captures that; the
binary pass/fail verdict cannot. A rising Inadequate rate is a leading
indicator of future violations.

### Facility risk scorecard

Facilities with **≥5 samples** are classified by combining violation
history *with* cumulative residue burden:

| Class | Meaning |
|---|---|
| **Healthy** | No violations, low inadequate-IqR rate |
| **Watch** | No violations *yet*, but elevated inadequate-IqR rate |
| **Risky** | Has violations, or a high inadequate-IqR rate regardless |

**Watch is the point of this table.** A facility with a clean record but a
rising residue load is invisible to violation-rate reporting — this is the
insight the scorecard exists to surface.

Tuning knobs (keyword args on `t_facility_scorecard`):
`inadequate_watch_threshold=0.20`, `inadequate_risky_threshold=0.35`,
`violation_risky_threshold_pct=10.0`, `min_samples=5`. These are starting
values, not calibrated — tune against your real facility distribution.

### Excluded entities

`EXCLUDED_FACILITY_PATTERNS` filters `جمعية البطين الزراعية` and `الجامعة`
out at the SQL layer (matched with `NOT LIKE '%pattern%'`). These are
referral/institutional entries, not inspectable commercial establishments.

**Note:** the exclusion applies to *all* statistics on the page, including
total sample counts and compliance-rate denominators — not just the
facility scorecard.

---

## 🎯 Inspection Priority (أولوية التفتيش)

### Purpose

A precomputed decision layer ranking municipalities, neighborhoods, and
establishments by inspection priority, using Bayesian shrinkage, commodity
risk, coverage gap, and trend — surfaced as a hierarchical
municipality → neighborhood → establishment recommendation.

Scores live in `risk_scores`, built by `scripts/build_risk_scores.py`.
`modules/inspection_priority.py` is a **read layer only** — it computes
nothing, so the text engine, voice pipeline, and Streamlit UI all share
one source of truth.

### The staleness problem, and the fix

The recommendation used to be **frozen for 1–2 months**, changing only when
new lab data arrived.

Root cause: **no feedback loop.** When an inspector actually visited a
flagged establishment, nothing recorded it. `days_since_last_sample` kept
climbing, so the same name stayed top-ranked indefinitely — still flagged
as "neglected" the day after being inspected.

#### Fix #1 — Inspection feedback loop

- New `inspections_log` table (self-creating on first write).
- **"✅ تم التفتيش"** button per recommended establishment.
- `effective_days_since()` takes the more recent of the last lab sample and
  any logged visit — so a visit counts **immediately**, without waiting for
  a `build_risk_scores.py` rebuild.
- **Undo list** reads the last 10 logged visits from the database.
  Deliberately *not* from `st.session_state`, which only survives the
  current browser session and forgets everything but the last click.

#### Fix #2 — Cooldown

`_filter_cooldown()` suppresses any establishment logged within
`COOLDOWN_DAYS` (default 7) from the recommendation pool, applied **before**
CRP scoring. The cascade then recalculates and promotes the next-highest
cluster.

Expect the whole path to change, not just the establishment — logging one
visit can shift the recommended neighborhood entirely, because CRP
recomputes across the remaining pool.

#### Fix #3 — Genuine motion, honestly scoped

- **`municipality_trend()`** — 30-day window vs. the preceding 30 days,
  requiring ≥5 samples in **both** windows.
- **Days-since-last-inspection counter** per entity, ticking up daily.

**Entity-level trend remains deliberately deferred.** Five months of sparse
per-establishment data cannot support a reliable trend; a facility with 3
samples would produce noise, not signal. This matches the existing
reasoning behind computing `c_trend` at municipality level.

### The map

`modules/inspection_map.py` renders Buraydah neighborhoods with **colour
intensity by risk score**, plus numbered markers tracing the visit route in
nearest-neighbour order (adequate for 3–5 stops; no TSP solver needed).

The map **complements** the hierarchy infographic, it does not replace it:

| Component | Answers |
|---|---|
| Infographic | **Why** — the reasoning chain that makes the recommendation defensible |
| Map | **How do I execute this today** — clustering, travel order |

**No blinking.** Continuous blink animation was considered and rejected: it
reads as unprofessional in a government context, conveys no priority
ordering (everything blinks identically), and is an accessibility problem.
Instead: colour intensity for priority, a **single 0.6s pulse** (not
`infinite`) on "🆕 محدّث" badges for neighborhoods newly entering the top
10 since the page was last opened.

Coordinates live in `modules/buraydah_coords.py`
(`BURAYDAH_NEIGHBORHOODS_COORDS`, ~34 neighborhoods). Neighborhoods absent
from that dict are silently skipped — extend the dict to add coverage.

### Safeguards retained

- **Low-confidence alerts** — high-scoring establishments with too few
  samples are excluded from the main recommendation but shown in a separate
  expander rather than hidden entirely.
- **CRP safety valve** — if a higher-CRP neighborhood exists outside the
  chosen municipality, an explicit warning is shown.
- **Manual overrides** — `risk_overrides` table (via
  `set_manual_override.py`) survives `risk_scores` rebuilds; any boosted row
  is marked and its reason appended, so no number changes without a visible
  cause.

---

## Setup notes

### DuckDB connection — important

`get_duckdb_read()` and `get_duckdb_write()` **must return the same shared
connection.** DuckDB refuses a second connection to the same file with a
different config (`read_only=True` vs `False`) while the first is open —
which is exactly what happens when a page holds a read-only connection
across a render and then logs an inspection.

The fix is a single `@st.cache_resource` read-write connection serving both
functions. A read-write connection reads identically, so no existing call
site changes.

Consequence: **`log_inspection()` and `undo_inspection()` must not close the
connection** — closing the shared object breaks DB access for every page for
the rest of the session.

This assumes single-process `streamlit run`. Multiple worker processes
against one DuckDB file would hit DuckDB's single-writer limit — out of
scope for the current deployment.

### Page registration

Both pages are called by the router as `page_func(api_client)`, so every
entry point must accept that argument even when unused —
`show_advanced_reports_page(api_client=None)`.

### Season definition

Winter = Dec/Jan/Feb, Spring = Mar/Apr/May, Summer = Jun/Jul/Aug,
Autumn = Sep/Oct/Nov. Dates parse as **DD/MM/YYYY**.

Reports only cover seasons present in the data — a partial season (e.g.
data starting 5 Jan gives a Winter of Jan–Feb only) is reported as-is, so be
careful comparing sample volumes against a full prior-year season.

### Performance note

`_render_level_table()` calls `effective_days_since()` per row via
`.apply()`, each doing its own DB round-trip. Fine up to the current
`top_n` ceiling of 50; batch into a single query if that ceiling is raised.