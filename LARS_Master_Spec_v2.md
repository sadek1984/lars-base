# LARS — Master Specification & Exhaustive Question Bank
### Laboratory Assistant & Report System · Municipal Food Safety Laboratory, Al-Qassim
**Version:** 2.0 (supersedes v1.0)
**Source dataset:** `6_months.xlsx` — sheet `Pesticide Analysis`
**Profiled:** 6,811 rows · 1,859 unique sample codes · 05 Jan 2026 → 17 May 2026
**Canonical DuckDB table:** `residues` (configurable via `LARS_TABLE_NAME`, default `residues`)
**Question bank size:** 220 distinct queries

---

# SECTION 0 — DATA REALITY CHECK

All values below are measured directly from the source file. Every handler, prompt, and answer template in this document is constrained by them.

## 0.1 Verified findings (carried forward from v1.0, re-confirmed)

| # | Finding | Measured value | Consequence |
|---|---|---|---|
| **0.1** | **Residue count censored at 10** | `Attribute` slots run `ملوث 1` → `ملوث 10`; 100 samples sit exactly at 10 | Any residue-count answer is a **lower bound** at n=10. Handlers must emit a censoring flag. |
| **0.2** | **Compliance label contradicts computed result** | 392 samples labelled `compliant (مطابقة)` contain ≥1 row where `reading > mrl`; 1 labelled `non-compliant` contains none | Every compliance answer must declare basis: **label-based** or **computed**. |
| **0.3** | **Analyte names heavily misspelled** | 272 distinct strings for ~150 real compounds | Exact-match `WHERE` silently undercounts. Alias resolution is mandatory pre-SQL. |
| **0.4** | **Corrupt numerics stored as text** | 747 non-numeric `Reading` (`0.0090.9`, `1.0100.1`); 766 non-numeric `Limit` (`0.05-metalaxyl`, `2..0`) | Cast with error capture; excluded rows must be **counted and reported**. |
| **0.5** | **MRL missing on ~11% of residue rows** | 766 rows null/unparseable `Limit` | HRI, %MRL, exceedance answers must state `n_evaluable / n_total`. |
| **0.6** | **Test-type column unreliable** | Rows tagged `سموم فطرية` carry pesticide analytes (carbendazim, azoxystrobin, chlorpyrifos…) | Never filter mycotoxin questions on `نوع الاختبار` alone. |
| **0.7** | **Commodity names not normalized** | 279 raw → 243 after trim | Per-commodity counts split across whitespace duplicates. |
| **0.8** | **Neighborhood 12.9% missing** | 880 null `الحى` across 54 neighborhoods | All neighborhood rankings must append the unassigned bucket. |
| **0.9** | **Coverage is 4.4 months, not 6** | 05 Jan 2026 → 17 May 2026; 11 unparseable dates | Filename says `6_months`; **it is not**. Anchor all periods to `MAX(sample_date)`. |
| **0.10** | **No QA/QC metadata in schema** | No uncertainty, instrument, calibration, analyst, batch, QC columns | GUM / Westgard / calibration questions are unanswerable → Section 5. |
| **0.11** | **No toxicological reference data** | No ADI, ARfD, body weight, ingestion rate columns | HRI requires external reference tables (present in app UI, absent from dataset). |

## 0.2 NEW findings added in v2.0

| # | Finding | Measured value | Consequence |
|---|---|---|---|
| **0.12** | **Zero organochlorines in the entire dataset** | No `endosulfan`, `DDT`, `lindane`, `dicofol`, `heptachlor`, or any OC compound among 272 analyte strings | Any query naming `أورجانوكلورين` must return an **explicit domain message**, not `0`. See §3.4. |
| **0.13** | **Zero mycotoxin analytes despite 2,518 mycotoxin-tagged rows** | No `aflatoxin`, `ochratoxin`, `zearalenone`, `fumonisin`. The string `aflab` (32 rows) is truncated/unresolved | `سموم فطرية` questions cannot be answered from analyte names. Requires source-system verification. |
| **0.14** | **Analyte–reading concatenation corruption** | `chlorpyrifos1.057` — compound name and concentration merged into the name field | Not a spelling variant; the reading must be **reconstructed**, not dropped. |
| **0.15** | **Spirotetramat has 3 spellings; acetamiprid has 3** | `spirotetramat` / `spirotetramate` / `spirotrtramate`; `acetamiprid` / `acetamipeid` / `acetamaiprid` | Extends the alias table beyond the v1.0 list. |
| **0.16** | **`ctpermethrin` — leading-character corruption** | 1 variant of `cypermethrin` | Fuzzy matching must tolerate leading-char noise, not only trailing. |
| **0.17** | **Municipality 7.4% missing** | 503 null `اسم البلدية` across 9 municipalities; 3 municipalities have <15 rows (`بلدية الرس`=12, `الجامعة`=7, `مواطنين`=1) | Per-municipality rates on the small three are statistically meaningless — suppress or flag. |
| **0.18** | **Residue-count distribution is bimodal** | 1→288, 2→273, 3→210, 4→143, 5→124, 6→75, 7→46, 8→39, 9→44, **10→100** | The spike at 10 is the censoring artefact (0.1), not a real population feature. Never present it as a finding. |

## 0.3 Canonical schema (post-ETL, long format)

```sql
CREATE TABLE residues (
  sample_code          INTEGER,
  sample_date          DATE,
  commodity_raw        TEXT,
  commodity            TEXT,        -- trimmed + normalized
  commodity_group      TEXT,        -- توابل / خضراوات / فواكهة / حبوب / مكسرات / ورقيات / تمور
  test_type            TEXT,
  facility             TEXT,
  municipality         TEXT,
  neighborhood         TEXT,
  sample_state         TEXT,        -- Dry / Fresh
  sample_result_label  TEXT,        -- as-received label (see 0.2)
  slot_no              INTEGER,     -- 1..10, censoring indicator
  pesticide_raw        TEXT,
  pesticide_canonical  TEXT,        -- resolved via alias table §4.1
  pesticide_class      TEXT,        -- §4.3
  cmg_group            TEXT,        -- common mechanism group, §4.4
  reading              DOUBLE,      -- NULL if unparseable
  mrl                  DOUBLE,      -- NULL if unparseable/absent
  parse_error_reading  BOOLEAN,
  parse_error_mrl      BOOLEAN,
  is_detected          BOOLEAN,     -- pesticide_canonical <> 'NO CBD'
  is_exceedance        BOOLEAN      -- reading > mrl; NULL if either missing
);
```

---

# SECTION 1 — UPDATED INTENT CLUSTERING & PARETO ANALYSIS

## 1.1 Cluster identification

| ID | Cluster | Core analytical intent | Representative logged query |
|---|---|---|---|
| **C1** | Analyte Lookup / Presence | Find a named compound in a named commodity or across all | `ابحث عن الايميداكلوبرايد داخل الفستق` |
| **C2** | Compliance Filter | Return samples failing MRL, scoped by commodity/analyte | `ما هي عينات الطماطم غير المطابقة بالبايفنثرين` |
| **C3** | Multi-Residue Count | Count samples holding exactly / at least N residues | `ما هو عدد العينات التي تحتوي علي عدد ٦ مبيد` |
| **C4** | Simple Aggregation | Count samples per commodity / neighborhood / municipality | `ما عدد عينات الطماطم و الخيار و الكوسة كل علي حده` |
| **C5** | Descriptive Statistics | min / max / mean / median / range of concentrations | `ماهو المتوسط و الوسيط لمبيد الايميداكلوبرايد في الطماطم` |
| **C6** | Ranking / Top-N | Order entities descending by violation count or rate | `اعرض الاحياء في ترتيب تنازلي من الاكثر الي الاقل مخالفه` |
| **C7** | Geospatial Slice | Filter/split by neighborhood, municipality, facility | `ماهي المبيدات الموجوده في حي الريان و الإسكان كل علي حده` |
| **C8** | Temporal Trend | Scope to a period; compare periods | `ما عدد عينات الطماطم الراسبة اخر ٣ شهور` |
| **C9** | Chemical-Class Profiling | Group residues by chemical family / CMG | `أعطني ملخص المجموعات الكيميائية لكل عينة تحتوي على أكثر من ٣ مبيدات` |
| **C10** | Risk Index (HRI / QI) | Health risk or quality index per commodity/group | `ما هو مؤشر الخطر الصحي لعينات الخيار…` |
| **C11** | Composite Report | Multi-column tabular export for a period | `اعطني تقرير للعينات الغير مطابقة لشهر مارس…` |
| **C12** | Poisoning Incidents | Query the incident module | `كم عدد حالات التسمم؟` |
| **C13** | Multiplier Threshold | Exceedance by a factor of the limit | `Buprofezin more than 2 times the limit in tomato` |
| **C14** | Uniqueness / Dedup | Distinct sample count by code | `كم عدد عينات الخيار الفريدة بناءً على كود العينة؟` |
| **C15** | Data-Quality Introspection | Coverage, censoring, missing-MRL, unassigned buckets | *(new — synthesized, no logged precedent)* |

## 1.2 Frequency ranking — corrected Pareto math

**Measured log distribution (45 logged queries):**

| Band | Clusters | Logged count | **Measured share** | Anticipated production share |
|---|---|---|---|---|
| **High Frequency** | C1, C2, C3, C4, C14 | **24 / 45** | **53.3%** | **~70%** |
| **Medium Frequency** | C5, C6, C7, C8, C11 | 14 / 45 | 31.1% | ~20% |
| **Low Frequency / Long Tail** | C9, C10, C12, C13, C15 | 7 / 45 | 15.6% | ~10% |

> **Explicit statement for the record:** The High-Frequency tier (C1, C2, C3, C4, C14) *currently covers 53.3% of logged queries, anticipated to reach ~70% under daily production load.*
>
> **Rationale for the projected shift:** the logged sample is a Technical-Director-authored exploration set, not an operational trace. It over-represents novel analytical probing (C5, C9, C10) and under-represents the repetitive lookup-and-verify behaviour that dominates daily bench work. As routine users onboard, C1/C2/C4 volume rises while C9/C10 stays approximately flat in absolute terms — pushing the deterministic tier toward 70% share without any change in absolute long-tail volume.
>
> **Engineering implication:** do not size the Tier-0 handler set against 53.3%. Size it against 70%, because the marginal cost of an unused deterministic handler is near-zero, while the marginal cost of an LLM fallback on a high-volume query is recurring.

## 1.3 Parameter extraction per cluster

| Cluster | Dynamic entities |
|---|---|
| C1 | `[analyte]`, `[commodity]`, `[scope: all\|one]` |
| C2 | `[commodity]`, `[analyte?]`, `[compliance_basis: label\|computed]` |
| C3 | `[N_residues]`, `[operator: exactly\|at_least\|at_most]`, `[commodity?]` |
| C4 | `[entity_list]`, `[split_flag]`, `[dedup: unique_sample_code]` |
| C5 | `[analyte]`, `[commodity?]`, `[stat_set]`, `[filter: >MRL?]` |
| C6 | `[group_by]`, `[metric: count\|rate]`, `[top_n]` |
| C7 | `[neighborhood_list]`, `[municipality?]`, `[facility?]`, `[split_flag]` |
| C8 | `[period]`, `[anchor: MAX(date)]`, `[comparison_period?]` |
| C9 | `[min_residue_count]`, `[taxonomy: class\|cmg]`, `[grain: sample\|commodity]` |
| C10 | `[commodity]`, `[pesticide_group]`, `[population_class]`, `[mrl_source]` |
| C11 | `[period]`, `[column_set]`, `[export_format]` |
| C13 | `[analyte]`, `[multiplier]`, `[commodity]` |
| C15 | `[dimension: coverage\|censoring\|mrl_gap\|unassigned]` |

## 1.4 Highest-value linguistic parameter

The split token `كل على حده` / `كل علي حده` appears in 4 logged queries and is the single most common cause of wrong-shape answers. It means **separate GROUP BY rows, never a merged total.** Equivalent surface forms to detect: `كل على حدة`, `مفصلة حسب`, `لكل … على حده`, `منفصلة`, `كل واحد لوحده`.

---

# SECTION 2 — EXHAUSTIVE QUESTION BANK (220 QUERIES)

**Legend for the Tags column:**
`AN`=analyte · `CM`=commodity · `CG`=commodity_group · `NB`=neighborhood · `MU`=municipality · `FC`=facility · `PD`=period · `N`=residue count · `MULT`=multiplier · `SPLIT`=separate grouping required · `DUAL`=Arabic dual form · `MIX`=mixed Arabic/Latin script · `TRANS`=Arabic transliteration of analyte · `CENS`=censoring caveat required · `BASIS`=compliance basis must be declared · `EMPTY`=expected empty result, needs domain message · `DQ`=data-quality introspection

---

## GROUP A — Analyte & Commodity Lookup (A001–A060)
*Persona A dominant · Clusters C1, C4, C7, C14*

| # | Arabic | English | Tags |
|---|---|---|---|
| A001 | ابحث عن الإيميداكلوبرايد في الفستق | Find imidacloprid in pistachio | AN, CM, TRANS |
| A002 | ابحث عن bifenthrin في كل العينات | Find bifenthrin across all samples | AN, MIX |
| A003 | ابحث عن الفيبرونيل داخل الفاصوليا | Find fipronil in green beans | AN, CM, TRANS |
| A004 | ابحث عن الكلوربيريفوس في الطماطم | Find chlorpyrifos in tomato | AN, CM, TRANS |
| A005 | هل ظهر الأزوكسي ستروبين في الخيار؟ | Did azoxystrobin appear in cucumber? | AN, CM |
| A006 | ما هي عينات الكوسة التي تحتوي على bifenthrin؟ | Which zucchini samples contain bifenthrin? | AN, CM, MIX |
| A007 | ما هي عينات الكوسة والباذنجان التي تحتوي على bifenthrin؟ | Which zucchini and eggplant samples contain bifenthrin? | AN, CM×2, MIX |
| A008 | ابحث عن الكاربندازيم في الكمون بكل أنواعه | Find carbendazim across all cumin varieties | AN, CM-variants |
| A009 | ما هي عينات الهيل التي تحتوي على التيبوكونازول؟ | Which cardamom samples contain tebuconazole? | AN, CM |
| A010 | ابحث عن الأسيتاميبريد في الفلفل البارد الأخضر | Find acetamiprid in green bell pepper | AN, CM |
| A011 | هل يوجد ميتالاكسيل في القهوة؟ | Is metalaxyl present in coffee? | AN, CM |
| A012 | ابحث عن البروفينوفوس في الفراولة | Find profenofos in strawberry | AN, CM |
| A013 | ما هي عينات العنب التي تحتوي على البوسكاليد؟ | Which grape samples contain boscalid? | AN, CM |
| A014 | ابحث عن الثياميثوكسام في البرتقال | Find thiamethoxam in orange | AN, CM |
| A015 | هل ظهر الإيثيون في التفاح؟ | Did ethion appear in apple? | AN, CM |
| A016 | ابحث عن الديفينوكونازول في اليانسون | Find difenoconazole in anise | AN, CM |
| A017 | ما هي عينات اللوز التي تحتوي على الكاربوفيوران؟ | Which almond samples contain carbofuran? | AN, CM |
| A018 | ابحث عن السيهالوثرين في الليمون الأسود | Find cyhalothrin in dried lime | AN, CM |
| A019 | هل يوجد إيمامكتين في الشمر؟ | Is emamectin present in fennel? | AN, CM |
| A020 | ابحث عن الأبامكتين في طحينة السمسم | Find abamectin in sesame tahini | AN, CM |
| A021 | ما هي الخضروات التي ظهر فيها مبيد البايفنثرين؟ | Which vegetables did bifenthrin appear in? | AN → CM list |
| A022 | في أي منتجات ظهر الكلوربيريفوس؟ | In which commodities did chlorpyrifos appear? | AN → CM list |
| A023 | في أي التوابل ظهر الكاربندازيم؟ | In which spices did carbendazim appear? | AN, CG |
| A024 | ما هي المنتجات التي ظهر فيها الفيبرونيل؟ | Which commodities contained fipronil? | AN → CM list |
| A025 | في أي المكسرات ظهرت المبيدات؟ | Which nuts showed pesticide detections? | CG |
| A026 | كم عدد العينات التي تحتوي على مبيد الإيثيون؟ | How many samples contain ethion? | AN, count |
| A027 | كم عدد العينات التي ظهر فيها الإيميداكلوبرايد؟ | How many samples showed imidacloprid? | AN, count |
| A028 | كم مرة تكرر الأزوكسي ستروبين في كامل البيانات؟ | How many times did azoxystrobin recur overall? | AN, freq |
| A029 | ماهي المبيدات التي ظهرت في الهيل مع التكرار وعدد المخالفات | Pesticides in cardamom with frequency and violation count | CM, 3-col |
| A030 | ماهي المبيدات الموجودة في عينة الطماطم وما عدد تكرار كل مبيد؟ | Which pesticides are in tomato samples and how often does each recur? | CM, freq |
| A031 | ما هي المبيدات الموجودة في الخيار مرتبة حسب التكرار؟ | Pesticides in cucumber ranked by frequency | CM, rank |
| A032 | ما هي المبيدات التي ظهرت في القهوة؟ | Which pesticides appeared in coffee? | CM |
| A033 | ما هي المبيدات التي ظهرت في الفاصوليا؟ | Which pesticides appeared in green beans? | CM |
| A034 | ما هي المبيدات التي ظهرت في الفستق والكاجو كل على حده؟ | Pesticides in pistachio and cashew, separately | CM×2, SPLIT |
| A035 | ما هي المبيدات المشتركة بين الطماطم والخيار؟ | Which pesticides are common to both tomato and cucumber? | CM×2, intersect |
| A036 | ما هي المبيدات الموجودة في الطماطم وغير موجودة في الخيار؟ | Pesticides in tomato but absent from cucumber | CM×2, diff |
| A037 | ما هي المبيدات التي ظهرت مرة واحدة فقط في كامل الفترة؟ | Which pesticides appeared exactly once overall? | rare |
| A038 | ما هي أكثر ١٠ مبيدات تكراراً في التوابل؟ | Top 10 most frequent pesticides in spices | CG, top_n |
| A039 | ما هي أكثر ٥ مبيدات تكراراً في الخضراوات؟ | Top 5 most frequent pesticides in vegetables | CG, top_n |
| A040 | ما هي المبيدات التي لم تظهر إطلاقاً في الفواكه؟ | Which pesticides never appeared in fruit? | CG, negative |
| A041 | ما عدد عينات الطماطم والخيار والكوسة كل على حده؟ | Sample counts for tomato, cucumber, zucchini — separately | CM×3, SPLIT |
| A042 | كم عدد عينات الخيار الفريدة بناءً على كود العينة؟ | Unique cucumber samples by sample code | CM, dedup |
| A043 | كم عدد العينات الفريدة في الهيل وما عدد تكرار المبيدات فيها؟ | Unique cardamom samples and residue recurrence count | CM, dedup |
| A044 | ما إجمالي عدد العينات لكل نوع منتج؟ | Total sample count per commodity group | CG |
| A045 | كم عينة من التوابل مقابل الخضراوات؟ | Spices vs vegetables sample count | CG×2 |
| A046 | ما هي أنواع التوابل الموجودة في حي الإسكان؟ | Which spice types exist in Al-Iskan neighborhood? | CG, NB |
| A047 | ماهي المبيدات الموجودة في حي الريان والإسكان كل على حده | Pesticides in Al-Rayyan and Al-Iskan, separately | NB×2, SPLIT |
| A048 | ما هي المبيدات الموجودة في حي الجردة؟ | Which pesticides are in Al-Jardah? | NB |
| A049 | ما هي المبيدات الموجودة في حي النهضة وحي الأفق كل على حده؟ | Pesticides in Al-Nahda and Al-Ufuq, separately | NB×2, SPLIT, DUAL |
| A050 | في أي الأحياء ظهر الكاربوفيوران؟ | In which neighborhoods did carbofuran appear? | AN → NB |
| A051 | في أي بلديات ظهر الكلوربيريفوس؟ | In which municipalities did chlorpyrifos appear? | AN → MU |
| A052 | ما هي العينات المأخوذة من جمعية البطين الزراعية؟ | Which samples came from Al-Batin Agricultural Association? | FC |
| A053 | ما هي المبيدات الموجودة في عينات بلدية شرق بريدة؟ | Pesticides in East Buraidah municipality samples | MU |
| A054 | قارن المبيدات المكتشفة بين بلدية غرب بريدة وبلدية شمال بريدة | Compare detected pesticides: West vs North Buraidah | MU×2 |
| A055 | ما عدد العينات في كل بلدية مفصلة حسب نوع المنتج؟ | Sample count per municipality, split by commodity group | MU, CG, SPLIT |
| A056 | كم عينة ليس لها حي مسجّل؟ | How many samples have no recorded neighborhood? | DQ |
| A057 | كم عينة ليس لها بلدية مسجّلة؟ | How many samples have no recorded municipality? | DQ |
| A058 | ما هي العينات الخالية تماماً من المبيدات؟ | Which samples had zero detections? | zero-detect |
| A059 | ما هي المنتجات التي لم تسجل فيها أي اكتشافات؟ | Which commodities recorded no detections at all? | CM, negative |
| A060 | ما الفرق بين عينات Dry وعينات Fresh من حيث المبيدات المكتشفة؟ | Dry vs Fresh samples: detected-pesticide comparison | state, MIX |

---

## GROUP B — Compliance, MRL & Threshold Queries (B001–B050)
*Persona A dominant · Clusters C2, C13 · **every item requires `BASIS`***

| # | Arabic | English | Tags |
|---|---|---|---|
| B001 | ما هي عينات الطماطم غير المطابقة بسبب البايفنثرين؟ | Tomato samples non-compliant due to bifenthrin | AN, CM, BASIS |
| B002 | ما هي عينات الخيار غير المطابقة بسبب البايفنثرين؟ | Cucumber samples non-compliant due to bifenthrin | AN, CM, BASIS |
| B003 | عينات تحتوي على الكلوربيريفوس فوق الحد | Samples containing chlorpyrifos above the limit | AN, BASIS |
| B004 | ما هي عينات الطماطم التي تحتوي على البابروفيزن غير المطابقة؟ | Non-compliant tomato samples containing buprofezin | AN, CM, TRANS, BASIS |
| B005 | ما عدد عينات الطماطم التي تكون فيها القراءة أكبر من الحدود؟ | Tomato samples where reading exceeds the limit | CM, computed |
| B006 | ما عدد عينات الخيار التي تجاوزت الحد المسموح؟ | Cucumber samples exceeding the permitted limit | CM, computed |
| B007 | ما هي عينات الكمون المخالفة؟ | Which cumin samples are in violation? | CM, BASIS |
| B008 | ما هي عينات الهيل المخالفة وبأي مبيد؟ | Which cardamom samples violate, and by which pesticide? | CM, BASIS |
| B009 | ما هي عينات الفلفل الراسبة؟ | Which pepper samples failed? | CM, BASIS |
| B010 | ما هي عينات القهوة الراسبة؟ | Which coffee samples failed? | CM, BASIS |
| B011 | ما هي عينات الفراولة المخالفة؟ | Which strawberry samples are in violation? | CM, BASIS |
| B012 | ما هي عينات العنب المخالفة وبأي تركيز؟ | Which grape samples violate, and at what concentration? | CM, BASIS |
| B013 | ما هي عينات البرتقال التي تجاوزت الحد؟ | Which orange samples exceeded the limit? | CM, computed |
| B014 | ما هي عينات الفستق المخالفة؟ | Which pistachio samples are in violation? | CM, BASIS |
| B015 | ما هي عينات اللوز والكاجو المخالفة كل على حده؟ | Almond and cashew violations, separately | CM×2, SPLIT |
| B016 | أوجد Buprofezin بأكثر من ضعفي الحد في الطماطم | Find buprofezin above 2× the limit in tomato | AN, CM, MULT=2, MIX |
| B017 | أوجد الإيميداكلوبرايد بأكثر من ٣ أضعاف الحد في الخيار | Find imidacloprid above 3× the limit in cucumber | AN, CM, MULT=3 |
| B018 | ما هي العينات التي تجاوز فيها التركيز ١٠ أضعاف الحد؟ | Samples where concentration exceeded 10× the limit | MULT=10 |
| B019 | ما هي العينات التي تجاوز فيها التركيز ضعف الحد في التوابل؟ | Spice samples exceeding 2× the limit | CG, MULT=2 |
| B020 | ما هي العينات التي تقع تحت الحد المسموح لكن فوق ٨٠٪ منه؟ | Samples below the limit but above 80% of it | borderline |
| B021 | ما هي العينات القريبة من الحد (بين ٩٠٪ و١٠٠٪)؟ | Samples in the 90–100% of MRL band | borderline |
| B022 | أعطني المبيدات والسموم الفطرية فوق الحد وتحت الحد للتوابل | Spices: pesticides and mycotoxins above and below the limit | CG, split |
| B023 | ما عدد المخالفات في الخضراوات مقابل الفواكه؟ | Violations in vegetables vs fruit | CG×2 |
| B024 | ما هي العينات التي تجاوزت الحد بمبيدين على الأقل؟ | Samples exceeding the limit for at least two pesticides | DUAL, N≥2 |
| B025 | ما هي العينات التي تجاوزت الحد بثلاثة مبيدات أو أكثر؟ | Samples exceeding the limit for 3+ pesticides | N≥3 |
| B026 | كم عدد المبيدات التي ظهرت في عينات الطماطم وكم منها تسبب في الرسوب؟ | Pesticides detected in tomato and how many caused failure | CM, dual-metric |
| B027 | كم تكرارية الإيميداكلوبرايد في الطماطم، وكم عينة طماطم رسبت خلال التكرار؟ | Imidacloprid frequency in tomato and how many of those failed | AN, CM |
| B028 | ما نسبة المخالفة لكل مبيد على حده؟ | Violation rate per pesticide, separately | SPLIT, rate |
| B029 | ما نسبة المخالفة لكل منتج على حده؟ | Violation rate per commodity, separately | SPLIT, rate |
| B030 | ما هي المبيدات التي نسبة مخالفتها أعلى من ٥٠٪؟ | Pesticides with a violation rate above 50% | rate, threshold |
| B031 | ما هي المبيدات التي ظهرت ولم تسبب أي مخالفة؟ | Pesticides detected that never caused a violation | negative |
| B032 | ما هي العينات المخالفة التي لا يوجد لها حد مسجل؟ | Flagged samples with no recorded MRL | DQ |
| B033 | كم عدد المتبقيات التي تعذّر تقييمها لعدم وجود حد؟ | Residues not evaluable due to missing MRL | DQ |
| B034 | كم عدد القراءات التي تعذّر تحويلها لرقم؟ | How many readings could not be parsed as numeric? | DQ |
| B035 | ما هي العينات المصنّفة مطابقة رغم وجود قراءة فوق الحد؟ | Samples labelled compliant yet containing a reading above the limit | DQ, BASIS |
| B036 | ما الفرق بين عدد المخالفات حسب التصنيف وحسب الحساب؟ | Label-based vs computed violation count difference | DQ, BASIS |
| B037 | ما هي عينات الطماطم غير المطابقة في حي الريان؟ | Non-compliant tomato samples in Al-Rayyan | CM, NB |
| B038 | ماهي العينات غير المطابقة في حي الريان والإسكان كل على حده | Non-compliant samples in Al-Rayyan and Al-Iskan, separately | NB×2, SPLIT |
| B039 | ما هي العينات غير المطابقة في جمعية البطين الزراعية؟ | Non-compliant samples at Al-Batin Agricultural Association | FC |
| B040 | ما هي العينات غير المطابقة في بلدية الصفراء الفرعية؟ | Non-compliant samples in Al-Safra sub-municipality | MU |
| B041 | كم عدد المخالفات في كل حي مفصلة؟ | Violation count per neighborhood, itemized | NB, SPLIT |
| B042 | ما عدد عينات الطماطم الراسبة آخر ٣ شهور؟ | Failed tomato samples in the last 3 months | CM, PD |
| B043 | ما هي عينات القهوة الراسبة آخر شهر؟ | Failed coffee samples last month | CM, PD |
| B044 | ما هي العينات غير المطابقة في شهر مارس؟ | Non-compliant samples in March | PD |
| B045 | كم عدد المخالفات في شهرين الأخيرين؟ | Violations in the last two months | PD, DUAL |
| B046 | ما هي المخالفات في عينات Dry مقابل Fresh؟ | Violations in Dry vs Fresh samples | state, MIX |
| B047 | ما هي المنشآت التي تكررت مخالفاتها أكثر من ٣ مرات؟ | Facilities with more than 3 repeat violations | FC, threshold |
| B048 | ما هي العينات التي رسبت بسبب مبيد واحد فقط؟ | Samples that failed due to a single pesticide only | N=1 |
| B049 | ما نسبة الرسوب في التوابل مقارنة بالمعدل العام؟ | Spice failure rate vs the overall average | CG, rate |
| B050 | ما هي أعلى ١٠ قراءات تجاوزاً للحد بالنسبة المئوية؟ | Top 10 readings by percentage exceedance of the limit | top_n, %MRL |

---

## GROUP C — Multi-Residue Counts & Chemical-Class Profiling (C001–C030)
*Persona A dominant · Clusters C3, C9 · **items touching n=10 require `CENS`***

| # | Arabic | English | Tags |
|---|---|---|---|
| C001 | ما هو عدد العينات التي تحتوي على ٦ مبيدات؟ | How many samples contain exactly 6 pesticides? | N=6 |
| C002 | ما عدد العينات التي تحتوي على مبيد واحد و٢ مبيد كل على حده؟ | Samples with 1 pesticide and with 2 pesticides, separately | N=[1,2], SPLIT |
| C003 | أوجد عدد العينات الخالية من المبيدات والتي تحتوي على ١ مبيد والتي تحتوي على ٣ مبيدات كل على حده | Samples with zero, one, and three pesticides, separately | N=[0,1,3], SPLIT |
| C004 | ما هي عينات القرنفل التي تحتوي على مبيد واحد؟ | Clove samples containing exactly one pesticide | CM, N=1 |
| C005 | ما هي العينات التي تحتوي على مبيدين بالضبط؟ | Samples containing exactly two pesticides | N=2, DUAL |
| C006 | ما هي العينات التي تحتوي على أكثر من ٥ مبيدات؟ | Samples containing more than 5 pesticides | N>5 |
| C007 | ما هي العينات التي تحتوي على ٣ مبيدات على الأقل؟ | Samples containing at least 3 pesticides | N≥3 |
| C008 | ما هي العينات التي وصلت للحد الأقصى ١٠ متبقيات؟ | Samples that hit the 10-residue ceiling | N=10, **CENS** |
| C009 | ما هو توزيع عدد المبيدات لكل عينة؟ | Distribution of residue count per sample | dist, **CENS** |
| C010 | ما عدد المبيدات في كل صنف — مثلاً الطماطم ١٠٠ عينة، ٥٠ بمبيدين و٥٠ بمبيد واحد | Residue-count distribution per commodity | CM, dist |
| C011 | ما هو توزيع عدد المبيدات في الخيار؟ | Residue-count distribution in cucumber | CM, dist |
| C012 | ما هو توزيع عدد المبيدات في الكمون؟ | Residue-count distribution in cumin | CM, dist |
| C013 | ما هو متوسط عدد المبيدات لكل عينة طماطم؟ | Mean residue count per tomato sample | CM, **CENS** |
| C014 | ما هو متوسط عدد المبيدات في التوابل مقابل الخضراوات؟ | Mean residue count: spices vs vegetables | CG×2, **CENS** |
| C015 | ما هي المنتجات التي متوسط عدد مبيداتها أعلى من ٤؟ | Commodities with mean residue count above 4 | CM, threshold |
| C016 | ما هي المبيدات الموجودة في كل عينة من حيث العدد وتركيز كل مبيد، وكم منها متسبب في الرسوب؟ | Per sample: residue list, count, concentrations, and failure contributors | composite |
| C017 | صنّف المبيدات في العينة ١٧٥٠ حسب المجموعة الكيميائية | Classify pesticides in sample 1750 by chemical class | sample_code, class |
| C018 | أعطني ملخص المجموعات الكيميائية لكل عينة تحتوي على أكثر من ٣ مبيدات | Chemical-class summary for every sample with >3 pesticides | N>3, class |
| C019 | ما هي المجموعات الكيميائية الموجودة في عينات الطماطم؟ | Which chemical classes occur in tomato samples? | CM, class |
| C020 | ما هي المجموعة الكيميائية الأكثر تسبباً في المخالفات؟ | Which chemical class causes the most violations? | class, rank |
| C021 | ما عدد الاكتشافات لكل مجموعة كيميائية؟ | Detection count per chemical class | class |
| C022 | ما نسبة المخالفة لكل مجموعة كيميائية على حده؟ | Violation rate per chemical class, separately | class, SPLIT, rate |
| C023 | ما هي عينات الخيار التي تحتوي على مبيدات من البيرثرويد؟ | Cucumber samples containing pyrethroids | CM, class |
| C024 | ما هي عينات الطماطم التي تحتوي على أورجانوفوسفورس؟ | Tomato samples containing organophosphates | CM, class |
| C025 | ما هي عينات الطماطم التي تحتوي على أورجانوكلورين؟ | Tomato samples containing organochlorines | CM, class, **EMPTY** |
| C026 | ما هو مؤشر الخطر لمجموعة الأورجانوكلورين في الخيار؟ | Organochlorine risk index in cucumber | class, **EMPTY** |
| C027 | كم عينة تحتوي على أكثر من مجموعة كيميائية واحدة؟ | Samples containing more than one chemical class | class, N>1 |
| C028 | كم عينة تحتوي على مبيدين أو أكثر يشتركون في نفس آلية السمّية؟ | Samples with ≥2 pesticides sharing a common toxicity mechanism | CMG, DUAL |
| C029 | ما هي العينات التي تحتوي على نيونيكوتينويد وكارباميت معاً؟ | Samples containing both neonicotinoids and carbamates | class×2 |
| C030 | ما هو توزيع المجموعات الكيميائية عبر الأحياء؟ | Chemical-class distribution across neighborhoods | class, NB |

---

## GROUP D — Executive & Dashboard Metrics (D001–D045)
*Persona B dominant · Clusters C4, C6, C8, C11, C12, C15*

| # | Arabic | English | Tags |
|---|---|---|---|
| D001 | ما هي نسبة المطابقة العامة خلال الفترة؟ | Overall compliance rate for the period | KPI, BASIS |
| D002 | كم إجمالي العينات المستلمة وكم عينة فريدة؟ | Total samples received and unique sample count | throughput |
| D003 | ما هو ملخص تنفيذي لأداء المختبر هذا الشهر؟ | Executive summary of lab performance this month | PD, composite |
| D004 | ما هو ملخص تنفيذي للربع الأول؟ | Executive summary for Q1 | PD, composite |
| D005 | ما هي أعلى ٥ مبيدات من حيث عدد المخالفات؟ | Top 5 pesticides by violation count | top_n |
| D006 | ما هي أعلى ١٠ مبيدات من حيث نسبة المخالفة؟ | Top 10 pesticides by violation rate | top_n, rate |
| D007 | ما هي أعلى ٥ منتجات من حيث نسبة الرسوب؟ | Top 5 commodities by failure rate | top_n, rate |
| D008 | ما هي أعلى ٥ منتجات من حيث عدد المخالفات؟ | Top 5 commodities by violation count | top_n |
| D009 | اعرض الأحياء في ترتيب تنازلي من الأكثر إلى الأقل مخالفة | Rank neighborhoods descending by violations | NB, rank |
| D010 | ما هي أخطر ٥ أحياء من حيث نسبة المخالفة؟ | Top 5 riskiest neighborhoods by violation rate | NB, top_n, rate |
| D011 | ما هو أداء كل بلدية من حيث نسبة المطابقة؟ | Compliance rate per municipality | MU, KPI |
| D012 | قارن بين بلدية شرق بريدة وبلدية غرب بريدة في نسبة المخالفة | Compare violation rates: East vs West Buraidah | MU×2 |
| D013 | ما هي المنشآت الأكثر تكراراً في المخالفات؟ | Which facilities repeat-offend most? | FC, rank |
| D014 | ما هي أعلى ١٠ منشآت من حيث عدد العينات المفحوصة؟ | Top 10 facilities by samples tested | FC, top_n |
| D015 | ما عدد العينات المفحوصة شهرياً؟ | Monthly tested-sample throughput | PD, trend |
| D016 | كيف تغيرت نسبة المخالفة بين الربع الأول والربع الثاني؟ | Q1 vs Q2 violation-rate change | PD×2 |
| D017 | قارن مخالفات الطماطم بين شهرين متتاليين | Compare tomato violations across two consecutive months | CM, PD, DUAL |
| D018 | هل هناك ارتفاع موسمي في المخالفات؟ | Is there a seasonal spike in violations? | trend |
| D019 | ما هو اتجاه نسبة المطابقة على مدى الأشهر؟ | Compliance-rate trend across months | trend |
| D020 | في أي شهر كانت أعلى نسبة مخالفة؟ | Which month had the highest violation rate? | PD, rank |
| D021 | ما هي الفئات الغذائية الأعلى خطورة؟ | Which food categories carry the highest risk? | CG, rank |
| D022 | ما نسبة كل نوع منتج من إجمالي العينات؟ | Share of each commodity group in total samples | CG, share |
| D023 | ما نسبة عينات التوابل من إجمالي المخالفات؟ | Spices' share of total violations | CG, share |
| D024 | ما هو توزيع العينات بين Dry و Fresh؟ | Dry vs Fresh sample distribution | state, MIX |
| D025 | كم عدد حالات التسمم الغذائي المسجلة؟ | Number of recorded food-poisoning incidents | poisoning |
| D026 | ما هو اتجاه حالات التسمم خلال الفترة؟ | Food-poisoning incident trend over the period | poisoning, trend |
| D027 | هل هناك علاقة بين الأحياء الأعلى مخالفة والأحياء الأعلى تسمماً؟ | Correlation between high-violation and high-poisoning neighborhoods | poisoning, NB |
| D028 | أعطني تقرير العينات غير المطابقة لشهر مارس (المنتج، المبيد، التركيز، المنطقة، تاريخ الاستلام) | March non-compliance report with those five columns | PD, composite |
| D029 | أعطني تقرير مفصل لأعلى ٥ مبيدات من حيث عدد المخالفات مع الأعداد | Detailed report of top 5 pesticides by violation count | top_n, composite |
| D030 | أعطني تقرير المخالفات لكل حي مع عدد العينات ونسبة المخالفة | Per-neighborhood violation report with counts and rates | NB, composite |
| D031 | أعطني تقرير شهري بعدد العينات والمخالفات ونسبة المطابقة | Monthly report: samples, violations, compliance rate | PD, composite |
| D032 | ما هي المنتجات التي لم تسجل أي مخالفة إطلاقاً؟ | Which commodities recorded zero violations? | CM, negative |
| D033 | ما هي الأحياء الخالية من المخالفات؟ | Which neighborhoods are violation-free? | NB, negative |
| D034 | ما هي الفترة الزمنية التي تغطيها البيانات فعلياً؟ | What period does the data actually cover? | **DQ** |
| D035 | ما نسبة العينات التي تعذّر تقييمها لعدم وجود حد مسجّل؟ | % of samples not evaluable due to missing MRL | **DQ** |
| D036 | ما نسبة السجلات الناقصة في حقل الحي؟ | % of records missing the neighborhood field | **DQ** |
| D037 | ما نسبة السجلات الناقصة في حقل البلدية؟ | % of records missing the municipality field | **DQ** |
| D038 | ما مدى موثوقية بيانات عدد المتبقيات؟ | How reliable is the residue-count data? | **DQ, CENS** |
| D039 | ما هي المؤشرات الرئيسية للأداء لهذا الشهر في صفحة واحدة؟ | One-page KPI summary for this month | PD, composite |
| D040 | ما هو معدل العينات المفحوصة أسبوعياً؟ | Weekly testing throughput rate | PD, trend |
| D041 | هل يوجد اختناق في الطاقة الاستيعابية للمختبر؟ | Is there a lab capacity bottleneck? | throughput |
| D042 | ما هي التوصيات المقترحة بناءً على أنماط المخالفة؟ | Recommended actions based on violation patterns | advisory |
| D043 | ما هي المنتجات التي تستحق زيادة تكرار الفحص؟ | Which commodities warrant increased sampling frequency? | advisory |
| D044 | ما هي الأحياء التي تحتاج حملة رقابية عاجلة؟ | Which neighborhoods need an urgent inspection campaign? | NB, advisory |
| D045 | قارن أداء المختبر بين النصف الأول والنصف الثاني من الفترة | Compare lab performance across the first vs second half of the period | PD×2 |

---

## GROUP E — Statistical Analysis & Risk Indices (E001–E035)
*Persona A + B · Clusters C5, C10*

| # | Arabic | English | Tags |
|---|---|---|---|
| E001 | ما هو أعلى وأقل تركيز لمبيد الإيميداكلوبرايد؟ | Max and min concentration of imidacloprid | AN, stats |
| E002 | ما هو المدى لتركيزات الإيميداكلوبرايد في الطماطم؟ | Concentration range of imidacloprid in tomato | AN, CM, stats |
| E003 | ما هو المتوسط والوسيط لمبيد الإيميداكلوبرايد في الطماطم؟ | Mean and median of imidacloprid in tomato | AN, CM, stats |
| E004 | ما متوسط تركيز الإيميداكلوبرايد في العينات فوق الحدود؟ | Mean imidacloprid concentration in exceeding samples only | AN, filter |
| E005 | ما هو المتوسط والوسيط للأزوكسي ستروبين في الخيار؟ | Mean and median of azoxystrobin in cucumber | AN, CM, stats |
| E006 | ما هو أعلى تركيز مسجّل للكلوربيريفوس ولأي عينة؟ | Highest recorded chlorpyrifos concentration and in which sample | AN, stats |
| E007 | ما هو الانحراف المعياري لتركيزات الكاربندازيم في التوابل؟ | Standard deviation of carbendazim in spices | AN, CG, stats |
| E008 | ما هي الشرائح المئوية (P25, P50, P75, P95) لتركيزات الأسيتاميبريد؟ | Percentiles (P25/P50/P75/P95) of acetamiprid concentrations | AN, stats |
| E009 | ما هي min و max و mean و median لكل مجموعة كيميائية عبر كل العينات؟ | min/max/mean/median per chemical class across all samples | class, stats |
| E010 | ما هي min و max و mean و median لكل مبيد في الطماطم؟ | min/max/mean/median per pesticide in tomato | CM, stats, SPLIT |
| E011 | ما هي نسبة التركيز إلى الحد (%MRL) لكل متبقي في عينة الطماطم؟ | %MRL per residue in tomato samples | CM, %MRL |
| E012 | ما متوسط نسبة %MRL لكل منتج؟ | Mean %MRL per commodity | CM, %MRL |
| E013 | ما هي القيم الشاذة (outliers) في تركيزات المبيدات؟ | Outlier detection in pesticide concentrations | outlier |
| E014 | هل توزيع تركيزات الإيميداكلوبرايد طبيعي أم ملتوٍ؟ | Is the imidacloprid concentration distribution normal or skewed? | AN, dist |
| E015 | ما هو متوسط التركيز لكل حي على حده؟ | Mean concentration per neighborhood, separately | NB, SPLIT |
| E016 | قارن متوسط تركيز الكاربندازيم بين التوابل والخضراوات | Compare mean carbendazim: spices vs vegetables | AN, CG×2 |
| E017 | ما هو مؤشر الخطر الصحي (HRI) الإجمالي لعينات الخيار لكل المبيدات المكتشفة، بناءً على معدل استهلاك فئة البالغين في السعودية، باستخدام حدود الداتاسيت الأصلي؟ | Overall HRI for cucumber, all detected pesticides, Saudi adult ingestion rate, Original Dataset MRLs | HRI, canonical |
| E018 | ما هو مؤشر الخطر الصحي (HRI) لمجموعة البيرثرويد في عينات الطماطم لفئة البالغين في السعودية؟ | HRI for pyrethroids in tomato, Saudi adults | HRI, class |
| E019 | ما هو مؤشر الخطر الصحي (HRI) لمجموعة الأورجانوفوسفورس في عينات الخيار باستخدام حدود EU الفورية؟ | HRI for organophosphates in cucumber, real-time EU MRLs | HRI, class, mrl_source |
| E020 | ما هو مؤشر الخطر الصحي (HRI) لمجموعة النيونيكوتينويد في عينات الفلفل لفئة البالغين؟ | HRI for neonicotinoids in pepper, adults | HRI, class |
| E021 | ما هو مؤشر الخطر الصحي (HRI) لمجموعة الأورجانوكلورين في عينات الطماطم؟ | HRI for organochlorines in tomato | HRI, class, **EMPTY** |
| E022 | ما هو مؤشر الخطر الصحي لأعلى ٣ منتجات استهلاكاً؟ | HRI for the three most-consumed commodities | HRI, top_n |
| E023 | قارن مؤشر الخطر الصحي (HRI) للبيرثرويد في الخيار بين فئة البالغين وفئة الأطفال | Compare pyrethroid HRI in cucumber: adults vs children | HRI, compare-population |
| E024 | قارن مؤشر الخطر الصحي (HRI) للنيونيكوتينويد بين الطماطم والخيار لفئة البالغين | Compare neonicotinoid HRI: tomato vs cucumber, adults | HRI, compare-commodity |
| E025 | قارن مؤشر الخطر الصحي (HRI) للأورجانوفوسفورس في الطماطم باستخدام حدود الداتاسيت مقابل حدود EU | Compare organophosphate HRI in tomato: Original Dataset vs EU MRLs | HRI, compare-mrl_source |
| E026 | ما هو معامل الخطر (HQ) لكل مبيد مكتشف في عينة الطماطم؟ | Hazard Quotient per detected pesticide in tomato | HQ |
| E027 | ما هو مؤشر الخطر التراكمي (HI) للمبيدات المشتركة في آلية السمّية في الخيار؟ | Cumulative Hazard Index for common-mechanism pesticides in cucumber | HI, CMG |
| E028 | ما هي المبيدات التي تجاوز معامل الخطر (HQ) لها الواحد الصحيح؟ | Which pesticides have HQ > 1? | HQ, threshold |
| E029 | احسب مؤشر الجودة لعينات الفلفل | Compute the quality index for pepper samples | QI, CM |
| E030 | احسب مؤشر الجودة لكل منتج على حده | Compute the quality index per commodity, separately | QI, SPLIT |
| E031 | ما هو مؤشر الجودة لكل حي؟ | Quality index per neighborhood | QI, NB |
| E032 | كيف تغيّر مؤشر الجودة للطماطم بين الربع الأول والربع الثاني؟ | Tomato quality-index change: Q1 vs Q2 | QI, PD×2 |
| E033 | ما هي العينات ذات أعلى مؤشر خطر صحي؟ | Which samples have the highest health risk index? | HRI, rank |
| E034 | هل توجد علاقة بين عدد المبيدات في العينة ومؤشر الخطر؟ | Is there a relationship between residue count and risk index? | correlation, **CENS** |
| E035 | ما هو متوسط عدد المبيدات في العينات التي تجاوز مؤشر خطرها الحد الآمن؟ | Mean residue count in samples exceeding the safe risk threshold | HRI, **CENS** |

---

## 2.6 Question bank totals

| Group | Range | Count | Persona skew |
|---|---|---|---|
| A — Analyte & Commodity Lookup | A001–A060 | 60 | A |
| B — Compliance, MRL & Thresholds | B001–B050 | 50 | A |
| C — Multi-Residue & Chemical Class | C001–C030 | 30 | A |
| D — Executive & Dashboard Metrics | D001–D045 | 45 | B |
| E — Statistical Analysis & Risk Indices | E001–E035 | 35 | A + B |
| **Total** | | **220** | |

---

# SECTION 3 — UPDATED 3-TIER ROUTING ARCHITECTURE

> **Table-name convention:** every SQL statement below references `residues`. To support alternate backends, resolve the identifier at build time from `LARS_TABLE_NAME` (default `residues`); do **not** hard-code alternates inside prompt examples, or the few-shot model will learn the wrong identifier.

## 3.1 Mandatory pre-processing chain (runs before every tier)

| Step | Operation | Reason |
|---|---|---|
| 1 | Arabic normalization: `أإآ→ا`, `ى→ي`, `ؤ→و`, `ئ→ي`; strip tashkeel and tatweel | `كل علي حده` and `كل على حده` must collapse to one token |
| 2 | Arabic-Indic digit fold: `٠١٢٣٤٥٦٧٨٩ → 0123456789` | `٦ مبيد` must parse as N=6 |
| 3 | Number-word mapping incl. **dual forms** | `مبيدين`→2, `عينتين`→2, `شهرين`→2, `حيين`→2, `واحد`→1, `ثلاثة`→3 |
| 4 | Definite-article strip for analyte matching: leading `ال` | `البايفنثرين` → `بايفنثرين` |
| 5 | Analyte alias resolution against §4.1 | Prevents silent undercount (finding 0.3) |
| 6 | Commodity alias resolution against §4.2 | Prevents split counts (finding 0.7) |
| 7 | Script separation: tokenize Latin and Arabic runs independently | Handles `مبيد bifenthrin في الخيار` |

## 3.2 Tier 0 — Deterministic handlers (0% LLM · $0 cost)

| Handler | Trigger regex (post-normalization) | Params | Bank coverage |
|---|---|---|---|
| `h_residue_count` | `عدد\s+العينات.*(تحتوي\|بها).*(\d+\|واحد\|مبيدين)\s*مبيد` | `N`, `operator` | C001, C004–C007 |
| `h_residue_count_multi` | `(كل\s*علي\s*حده\|مفصل)` **and** ≥2 numerals | `N_list`, `split=True` | C002, C003 |
| `h_analyte_in_commodity` | `(ابحث\|اوجد\|هل\s+ظهر\|find).{0,25}(?P<an>[\w\u0600-\u06FF]+).{0,12}(في\|داخل\|in)\s*(?P<cm>.+)` | `analyte`, `commodity` | A001–A020 |
| `h_analyte_reverse` | `(في\s+اي\|ما\s+هي).*(ظهر\|يوجد)\s*(?P<an>.+)` | `analyte` → entity list | A021–A024, A050, A051 |
| `h_sample_count_by_commodity` | `عدد\s*عينات\s*(?P<list>.+?)(كل\s*علي\s*حده)?$` | `commodity_list`, `split` | A041, A044, A045 |
| `h_unique_samples` | `(الفريدة\|بناء[ًا]?\s*علي\s*كود)` | `commodity` | A042, A043 |
| `h_noncompliant_by_commodity` | `(غير\s*مطابق\|راسب\|رسبت\|مخالف).*(?P<cm>.+)` | `commodity`, `basis` | B007–B015 |
| `h_above_limit` | `(فوق\|اكبر\s*من\|تجاوز\|اعلي\s*من).{0,12}(الحد\|الحدود\|المسموح)` | `analyte?`, `commodity?` | B003, B005, B006 |
| `h_multiplier` | `(ضعف\|ضعفي\|(\d+)\s*(مرات\|اضعاف)\|(\d+)\s*times)` | `multiplier` | B016–B019 |
| `h_topn` | `(اعلي\|اكثر\|افضل)\s*(?P<n>\d+)?.*(مخالف\|رسوب\|تكرار)` | `top_n`, `group_by`, `metric` | D005–D010 |
| `h_rank_entities` | `(تنازلي\|ترتيب).*(الاحياء\|البلديات\|المنشات\|المبيدات)` | `group_by` | D009 |
| `h_desc_stats` | `(المتوسط\|الوسيط\|اعلي\s*تركيز\|اقل\s*تركيز\|المدي\|الانحراف)` | `analyte`, `commodity?`, `stat_set` | E001–E008 |
| `h_poisoning_count` | `(حالات\|عدد).*(التسمم)` | `period?` | D025, D026 |
| `h_data_quality` | `(الفترة\s*التي\s*تغطيها\|تعذر\|ناقص\|بدون\s*حي\|بدون\s*بلدية\|موثوقية)` | `dimension` | A056, A057, B032–B036, D034–D038 |
| `h_empty_class_guard` | `اورجانوكلورين\|organochlorine\|OC` | — | **C025, C026, E021** → §3.4 |

**Tier-0 unit-test matrix — linguistic edge cases:**

| Case | Variants observed | Expected resolution |
|---|---|---|
| Dual form | `مبيدين`, `عينتين`, `شهرين`, `حيين` | N=2 |
| Split flag | `كل على حده`, `كل علي حده`, `كل على حدة`, `مفصلة حسب`, `منفصلة` | `split=True` |
| Threshold phrasing | `على الأقل`, `أكثر من`, `فوق`, `تجاوز`, `أكبر من`, `أعلى من` | `at_least` vs `greater_than` |
| Transliterated analytes | `الإيميداكلوبرايد`, `البايفنثرين`, `البابروفيزن`, `الكلوربيريفوس`, `الفيبرونيل`, `الأزوكسي ستروبين` | canonical via §4.1 |
| Mixed script | `ما هي عينات الكوسه … مبيد bifenthrin` | dual tokenization |
| Commodity sub-variants | `فلفل بارد اخضر` / `فلفل حار احمر` / `فلفل حار حلو احمر` | **do not silently collapse** — list both or ask |
| Multiplier phrasing | `ضعفي`, `٢ أضعاف`, `مرتين`, `more than 2 times` | `multiplier=2` |

## 3.3 Tier 1 — Few-shot SQL candidates (~50% LLM)

Include these (Question → SQL) pairs verbatim in the prompt.

**FS-1 · Residue-count distribution per commodity**
```sql
-- Q: ما عدد المبيدات في كل صنف طماطم — كم عينة بمبيد واحد وكم بمبيدين؟
WITH per_sample AS (
  SELECT sample_code,
         COUNT(DISTINCT pesticide_canonical) FILTER (WHERE is_detected) AS n_res,
         MAX(slot_no) AS max_slot
  FROM residues
  WHERE commodity = 'طماطم'
  GROUP BY sample_code)
SELECT n_res,
       COUNT(*) AS n_samples,
       COUNT(*) FILTER (WHERE max_slot = 10) AS n_censored
FROM per_sample
GROUP BY n_res ORDER BY n_res;
```

**FS-2 · Per-neighborhood split (never merge)**
```sql
-- Q: ماهي المبيدات الموجودة في حي الريان والإسكان كل على حده
SELECT neighborhood, pesticide_canonical, COUNT(*) AS n
FROM residues
WHERE neighborhood IN ('الريان','الإسكان') AND is_detected
GROUP BY neighborhood, pesticide_canonical
ORDER BY neighborhood, n DESC;
```

**FS-3 · Descriptive stats scoped to exceedances**
```sql
-- Q: ما متوسط تركيز الإيميداكلوبرايد في العينات فوق الحدود؟
SELECT COUNT(*) AS n,
       MIN(reading) AS min_c, MAX(reading) AS max_c,
       AVG(reading) AS mean_c, MEDIAN(reading) AS median_c
FROM residues
WHERE pesticide_canonical = 'imidacloprid' AND is_exceedance;
```

**FS-4 · Multiplier threshold**
```sql
-- Q: أوجد Buprofezin بأكثر من ضعفي الحد في الطماطم
SELECT sample_code, sample_date, reading, mrl,
       ROUND(reading / mrl, 2) AS ratio
FROM residues
WHERE pesticide_canonical = 'buprofezin'
  AND commodity = 'طماطم'
  AND mrl IS NOT NULL AND reading > 2 * mrl
ORDER BY ratio DESC;
```

**FS-5 · Top-N by violation count and rate**
```sql
-- Q: أعلى ٥ مبيدات من حيث عدد المخالفات
SELECT pesticide_canonical,
       COUNT(*) FILTER (WHERE is_exceedance) AS violations,
       COUNT(*) FILTER (WHERE is_detected)   AS detections,
       ROUND(100.0 * COUNT(*) FILTER (WHERE is_exceedance)
             / NULLIF(COUNT(*) FILTER (WHERE is_detected), 0), 1) AS pct
FROM residues
GROUP BY 1
HAVING COUNT(*) FILTER (WHERE is_detected) > 0
ORDER BY violations DESC
LIMIT 5;
```

**FS-6 · Period anchored to data, never to the clock**
```sql
-- Q: ما عدد عينات الطماطم الراسبة آخر ٣ شهور؟
WITH anchor AS (SELECT MAX(sample_date) AS d FROM residues)
SELECT COUNT(DISTINCT sample_code) AS failed_samples
FROM residues, anchor
WHERE commodity = 'طماطم'
  AND is_exceedance
  AND sample_date >= anchor.d - INTERVAL 3 MONTH;
```

**FS-7 · Composite non-compliance report**
```sql
-- Q: تقرير العينات غير المطابقة لشهر مارس (المنتج، المبيد، التركيز، المنطقة، التاريخ)
SELECT sample_code, commodity, pesticide_canonical AS pesticide,
       reading, mrl, neighborhood, municipality, sample_date
FROM residues
WHERE is_exceedance
  AND date_part('month', sample_date) = 3
ORDER BY sample_date, sample_code;
```

**FS-8 · Chemical-class summary for multi-residue samples**
```sql
-- Q: ملخص المجموعات الكيميائية لكل عينة تحتوي على أكثر من ٣ مبيدات
WITH s AS (
  SELECT sample_code
  FROM residues WHERE is_detected
  GROUP BY sample_code
  HAVING COUNT(DISTINCT pesticide_canonical) > 3)
SELECT r.sample_code, r.commodity, r.pesticide_class,
       COUNT(DISTINCT r.pesticide_canonical) AS n_in_class
FROM residues r JOIN s USING (sample_code)
WHERE r.is_detected
GROUP BY 1, 2, 3
ORDER BY r.sample_code, n_in_class DESC;
```

**FS-9 · Detection vs failure split for one analyte**
```sql
-- Q: كم تكرارية الإيميداكلوبرايد في الطماطم وكم عينة رسبت؟
SELECT COUNT(*)                                   AS detections,
       COUNT(DISTINCT sample_code)                AS samples,
       COUNT(*) FILTER (WHERE is_exceedance)      AS violations,
       COUNT(*) FILTER (WHERE mrl IS NULL)        AS not_evaluable
FROM residues
WHERE pesticide_canonical = 'imidacloprid' AND commodity = 'طماطم';
```

**FS-10 · Data-quality KPI**
```sql
-- Q: ما نسبة المتبقيات التي تعذر تقييمها لعدم وجود حد؟
SELECT COUNT(*) FILTER (WHERE is_detected)                       AS detections,
       COUNT(*) FILTER (WHERE is_detected AND mrl IS NULL)       AS no_mrl,
       ROUND(100.0 * COUNT(*) FILTER (WHERE is_detected AND mrl IS NULL)
             / NULLIF(COUNT(*) FILTER (WHERE is_detected), 0), 1) AS pct
FROM residues;
```

**FS-11 · Statistics per chemical class (correct grain — across dataset)**
```sql
-- Q: min/max/mean/median لكل مجموعة كيميائية عبر كل العينات
SELECT pesticide_class,
       COUNT(*)          AS n_detections,
       MIN(reading)      AS min_c,
       MAX(reading)      AS max_c,
       AVG(reading)      AS mean_c,
       MEDIAN(reading)   AS median_c
FROM residues
WHERE is_detected AND reading IS NOT NULL
GROUP BY pesticide_class
HAVING COUNT(*) >= 5          -- suppress statistically void groups
ORDER BY n_detections DESC;
```

**FS-12 · Compliance basis reconciliation**
```sql
-- Q: ما الفرق بين عدد المخالفات حسب التصنيف وحسب الحساب؟
WITH per_sample AS (
  SELECT sample_code,
         MAX(sample_result_label) AS label,
         BOOL_OR(is_exceedance)   AS computed_fail
  FROM residues GROUP BY sample_code)
SELECT label, computed_fail, COUNT(*) AS n_samples
FROM per_sample GROUP BY 1, 2 ORDER BY 1, 2;
```

**FS-13 · Neighborhood ranking with unassigned bucket**
```sql
-- Q: اعرض الأحياء في ترتيب تنازلي من الأكثر إلى الأقل مخالفة
SELECT COALESCE(neighborhood, 'غير محدد') AS neighborhood,
       COUNT(DISTINCT sample_code) FILTER (WHERE is_exceedance) AS violations,
       COUNT(DISTINCT sample_code)                              AS samples,
       ROUND(100.0 * COUNT(DISTINCT sample_code) FILTER (WHERE is_exceedance)
             / NULLIF(COUNT(DISTINCT sample_code), 0), 1)       AS pct
FROM residues
GROUP BY 1 ORDER BY violations DESC;
```

**FS-14 · Censoring-aware residue-count query**
```sql
-- Q: ما هي العينات التي وصلت للحد الأقصى ١٠ متبقيات؟
SELECT sample_code, commodity, sample_date,
       COUNT(DISTINCT pesticide_canonical) AS n_res,
       TRUE AS is_censored
FROM residues
WHERE is_detected
GROUP BY sample_code, commodity, sample_date
HAVING COUNT(DISTINCT pesticide_canonical) >= 10;
```

**FS-15 · Period-over-period comparison**
```sql
-- Q: كيف تغيرت نسبة المخالفة بين الربع الأول والربع الثاني؟
SELECT date_part('quarter', sample_date) AS qtr,
       COUNT(DISTINCT sample_code)                              AS samples,
       COUNT(DISTINCT sample_code) FILTER (WHERE is_exceedance) AS violations,
       ROUND(100.0 * COUNT(DISTINCT sample_code) FILTER (WHERE is_exceedance)
             / NULLIF(COUNT(DISTINCT sample_code), 0), 1)       AS pct
FROM residues
WHERE sample_date IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

## 3.4 Empty-class handler — Organochlorines (and any zero-detection class)

Finding 0.12 confirms **zero organochlorine detections across all 272 analyte strings.** A bare `0` or empty result set is misleading: the user cannot tell whether the class is absent from the data, absent from the scope, or the query failed.

**Required behaviour:**

```python
EMPTY_CLASSES = {"organochlorine"}   # populated from a startup scan of pesticide_class

def guard_empty_class(pesticide_class: str, rows: list) -> str | None:
    if pesticide_class in EMPTY_CLASSES or (not rows and class_has_zero_detections(pesticide_class)):
        return (
            "لا توجد اكتشافات لهذه المجموعة في البيانات الحالية.\n"
            f"المجموعة المطلوبة: {pesticide_class}\n"
            "لم تُسجّل أي نتيجة إيجابية لهذه المجموعة ضمن الفترة "
            "05/01/2026 – 17/05/2026 (1,859 عينة).\n"
            "هذه نتيجة صحيحة وليست خطأ في الاستعلام."
        )
    return None
```

**Equivalent SQL-level guard** (returns an explanatory row rather than an empty set):

```sql
-- Q: ما هي عينات الطماطم التي تحتوي على أورجانوكلورين؟
WITH hits AS (
  SELECT sample_code, commodity, pesticide_canonical, reading, mrl
  FROM residues
  WHERE pesticide_class = 'organochlorine'
    AND commodity = 'طماطم' AND is_detected)
SELECT * FROM hits
UNION ALL
SELECT NULL, 'لا توجد اكتشافات لهذه المجموعة في البيانات الحالية',
       NULL, NULL, NULL
WHERE NOT EXISTS (SELECT 1 FROM hits);
```

**Startup requirement:** `EMPTY_CLASSES` must be computed at ETL time by scanning `pesticide_class` for classes with zero rows — not hard-coded. When new data arrives containing organochlorines, the guard must retire itself automatically.

The same guard applies to `EMPTY` -tagged bank items **C025, C026, E021**, and to any future class that scans empty.

## 3.5 Tier 2 — Dynamic LLM + mandatory post-execution sanity checks

| Trigger | Sanity check | Action on failure |
|---|---|---|
| Any `COUNT` result | `NULL`, `0`, or `1` on a table with >1,000 rows | Re-run with relaxed analyte matching before answering |
| Analyte-scoped query | Canonical resolved but raw table shows more spelling variants than matched | Append undercount warning (finding 0.3) |
| Compliance query | Label-based and computed differ by >10% | **Return both numbers**; never pick one silently |
| Residue-count query | Any returned sample has `n_res = 10` | Append censoring caveat (finding 0.1) |
| Statistics query | `n < 5` for `MEDIAN` / `MEAN` | Return raw values instead of a summary statistic |
| Any `mrl`-dependent query | — | Always emit `n_evaluable / n_total` |
| Period query | Resolved window does not intersect `[MIN(date), MAX(date)]` | Say so explicitly; do not return `0` |
| Neighborhood/municipality ranking | — | Always append the `NULL` bucket count |
| Municipality rate on `بلدية الرس` / `الجامعة` / `مواطنين` | `n < 15` | Suppress the rate; report raw count only (finding 0.17) |
| Chemical-class query | Class scans empty | Route to §3.4 guard |
| Cross-join / multi-join | Output rows > input rows × 2 | Abort — suspected fan-out |
| HRI / QI | `ingestion_rate`, `body_weight`, or `ADI` is NULL | Refuse partial computation |
| Mycotoxin query (`سموم فطرية`) | No mycotoxin analyte names exist (finding 0.13) | Warn that the test-type tag cannot be resolved to analytes |

---

# SECTION 4 — NORMALIZATION & ALIAS TABLES

## 4.1 Analyte alias table (measured variants — extend, never replace)

| Canonical | Raw variants present in the file | Arabic transliteration(s) |
|---|---|---|
| `azoxystrobin` | azoxystrobin, azoxystrobim, azoxystobin, azoxystribin, azoxysterobin, azoxysttrobin, azoxytrobin | الأزوكسي ستروبين |
| `chlorpyrifos` | chlorpyrifos, chlorpyriphos, chlorpyrifis, chlorpyriprhos, **chlorpyrifos1.057** | الكلوربيريفوس |
| `acetamiprid` | acetamiprid, acetamipeid, acetamaiprid | الأسيتاميبريد |
| `spirotetramat` | spirotetramat, spirotetramate, spirotrtramate | السبيروتيترامات |
| `profenofos` | profenfos, profenofos | البروفينوفوس |
| `clothianidin` | clothianidin, clothiandin | الكلوثيانيدين |
| `cyhalothrin` | cyhalothrin, cyhalithrin, cyhalothein | السيهالوثرين |
| `cypermethrin` | cypermethrin, **ctpermethrin** | السايبرمثرين |
| `buprofezin` | buprofezin, buprofuzin | البابروفيزن / البروفيزين |
| `ethion` | ethion, **tethion** *(verify — may be a distinct compound)* | الإيثيون |
| `imidacloprid` | imidacloprid | الإيميداكلوبرايد |
| `bifenthrin` | bifenthrin | البايفنثرين |
| `bifenazate` | bifenazate | البايفينازيت |
| `fipronil` | fipronil | الفيبرونيل |
| `carbendazim` | carbendazim | الكاربندازيم |
| `difenoconazole` | difenoconazole | الديفينوكونازول |
| `tebuconazole` | tebuconazole | التيبوكونازول |
| `thiamethoxam` | thiamethoxam | الثياميثوكسام |
| `metalaxyl` | metalaxyl | الميتالاكسيل |
| `carbofuran` | carbofuran | الكاربوفيوران |
| `emamectin` | emamectin | الإيمامكتين |
| `abamectin` | abamectin | الأبامكتين |
| `malathion` | malathion | الملاثيون |
| `diazinon` | diazinon | الديازينون |
| `deltamethrin` | deltamethrin | الدلتامثرين |
| `aflab` **(unresolved)** | aflab — 32 rows | — · **flag for source-system verification (finding 0.13)** |

**Corruption class — not spelling variants:**

| String | Nature | Required action |
|---|---|---|
| `chlorpyrifos1.057` | analyte name concatenated with its reading | Split into `chlorpyrifos` + `reading = 1.057`; **do not discard** (finding 0.14) |
| `ctpermethrin` | leading-character corruption | Fuzzy matcher must tolerate leading noise, not only trailing (finding 0.16) |
| `aflab` | truncated / unresolved | Escalate — do not guess `aflatoxin` |

**Matching policy:** exact → alias-table lookup → Levenshtein ≤ 2 against the canonical list → **escalate to the user**. Never fuzzy-match silently below the reporting layer; every fuzzy resolution must appear in the answer footer.

## 4.2 Commodity normalization

Trim whitespace first: **279 raw → 243 distinct.** Then decide roll-up policy explicitly.

| Base term | Sub-variants present | Combined rows | Policy |
|---|---|---|---|
| كمون | كمون, كمون بلدي, كمون سوري, كمون هندي, كمون سوداني | ~1,610 | **Ask or list both** — never collapse silently |
| هيل | هيل, هيل هندي | ~618 | Ask or list both |
| فلفل | فلفل بارد اخضر, فلفل حار احمر, فلفل حار اخضر, فلفل حار حلو احمر | ~651 | Ask or list both |
| طماطم | طماطم, طماطم شيري | ~669 | Ask or list both |
| عنب | عنب, عنب اخضر | ~205 | Ask or list both |
| شمر | شمر, شمر هندي | ~168 | Ask or list both |

**Commodity groups present:** توابل (3,004) · خضراوات (2,221) · فواكهة (789) · حبوب (394) · مكسرات (261) · ورقيات (83) · تمور (45) · خام (1) · أغذية جاهزة (1)

> The two singleton groups (`خام`, `أغذية جاهزة`) must never appear in a ranking or rate calculation.

## 4.3 Chemical-class mapping (classes observed in this dataset)

| Class | Compounds present |
|---|---|
| **Neonicotinoid** | imidacloprid, acetamiprid, thiamethoxam, clothianidin, dinotefuran |
| **Organophosphate** | chlorpyrifos, profenofos, ethion, malathion, diazinon |
| **Pyrethroid** | cyhalothrin, cypermethrin, bifenthrin, deltamethrin |
| **Carbamate** | carbendazim, carbofuran, propamocarb |
| **Triazole** | difenoconazole, tebuconazole, propiconazole, penconazole, myclobutanil, tricyclazole |
| **Strobilurin** | azoxystrobin, pyraclostrobin, trifloxystrobin |
| **Benzimidazole** | thiabendazole, carbendazim, thiophanate |
| **Avermectin** | abamectin, emamectin |
| **Anthranilic diamide** | chlorantraniliprole |
| **Tetronic acid** | spirotetramat, spirodiclofen, spiromesifen |
| **Phenylpyrazole** | fipronil |
| **Other / miscellaneous** | indoxacarb, etoxazole, bifenazate, fluopyram, boscalid, fludioxonil, fenhexamid, pyriproxyfen, methoxyfenozide, chlorfenapyr, mandipropamid, dimethomorph, pyrimethanil, pyridaben, metalaxyl |
| **Organochlorine** | **NONE — zero detections (finding 0.12)** → §3.4 guard |

## 4.4 Common Mechanism Group (CMG) mapping — for cumulative risk only

Chemical family is a *reporting* dimension. CMG is the *risk* dimension. They are not interchangeable, and the question bank carries both under distinct labels.

| CMG | Mechanism | Members in this dataset |
|---|---|---|
| **AChE inhibitors** | acetylcholinesterase inhibition | chlorpyrifos, profenofos, ethion, malathion, diazinon, carbendazim*, carbofuran, propamocarb |
| **nAChR agonists** | nicotinic acetylcholine receptor agonism | imidacloprid, acetamiprid, thiamethoxam, clothianidin, dinotefuran |
| **Sodium-channel modulators** | voltage-gated Na⁺ channel modulation | cyhalothrin, cypermethrin, bifenthrin, deltamethrin |
| **Sterol biosynthesis inhibitors** | C14-demethylase inhibition | difenoconazole, tebuconazole, propiconazole, penconazole, myclobutanil |
| **Mitochondrial complex III inhibitors** | QoI respiration inhibition | azoxystrobin, pyraclostrobin, trifloxystrobin |

> \* Carbamates share AChE inhibition with organophosphates — this is precisely why family-based grouping under-reports cumulative risk. `HI = Σ HQ` must be summed **within a CMG**, not within a chemical family.

**Correct risk chain:**
```
EDI = (residue_concentration × ingestion_rate) / body_weight
HQ  = EDI / ADI            (or ARfD for acute assessment)
HI  = Σ HQ  within a CMG
```

## 4.5 Quality Index — explicit definition

`مؤشر الجودة` has no standard definition in residue monitoring. LARS adopts, and must state in every answer:

```
QI = 1 − (عدد المتبقيات المخالفة ÷ عدد المتبقيات المفحوصة القابلة للتقييم)
```

Denominator excludes rows with missing/unparseable MRL. Every QI answer must report the excluded count. Standard alternatives to consider instead: compliance rate, % MRL exceedance, Pesticide Load Indicator (PLI).

## 4.6 HRI question templates (canonical parametrized forms)

**Type 1 — general form (3 dropdowns):**
```
ما هو مؤشر الخطر الصحي (HRI) لـ{pesticide_group}
في عينات {commodity}، بناءً على معدل استهلاك
فئة {population_class} في السعودية،
باستخدام {mrl_source}؟
```

| Slot | Values |
|---|---|
| `pesticide_group` | `كل المبيدات المكتشفة` *(explicit value, never NULL)* · بيرثرويد · أورجانوفوسفورس · نيونيكوتينويد · كارباميت · ترايازول · ستروبيلورين · ~~أورجانوكلورين~~ *(→ §3.4 guard)* |
| `commodity` | خيار · طماطم · فلفل بارد اخضر · كمون · هيل · عنب · … *(must match the UI dropdown string exactly)* |
| `population_class` | Adults (Saudi) — 53.0 kg · *(additional classes as configured)* |
| `mrl_source` | حدود الداتاسيت الأصلي (Original Dataset) · حدود EU MRLs الفورية |

**Type 2 — comparison forms (exactly one axis varies):**
```
(أ) قارن HRI لـ{pesticide_group} في عينات {commodity}
    بين فئة {population_class_1} وفئة {population_class_2}

(ب) قارن HRI لـ{pesticide_group}
    بين عينات {commodity_1} وعينات {commodity_2} لفئة {population_class}

(ج) قارن HRI لـ{pesticide_group} في عينات {commodity} لفئة {population_class}
    باستخدام حدود الداتاسيت الأصلي مقابل حدود EU MRLs الفورية
```

> **Rule:** two or more varying slots produce confounded output that cannot be attributed to a single cause. Reject such queries at the router.

**Statistics grain rule (corrects the original logged phrasing):** `min/max/mean/median per pesticide group` is only valid **across the dataset**, never within a single sample. Within one sample a class holds 3–4 values; a median over n=3 carries no information. Within-sample requests resolve to `count` and `sum` instead.

---

# SECTION 5 — REFUSAL & OUT-OF-SCOPE HANDLERS

The persona brief requests uncertainty and QC analytics. **The schema cannot support them.** Building handlers here produces confident fabrication — the most damaging failure mode for a regulatory tool.

## 5.1 Out-of-scope matrix

| Requested capability | Required column(s) | Present? |
|---|---|---|
| GUM measurement uncertainty | `expanded_uncertainty`, `k_factor`, `u_combined` | ❌ |
| Westgard multi-rule QC | `qc_sample_id`, `qc_value`, `qc_target`, `qc_sd` | ❌ |
| Control charts (Levey-Jennings) | QC time series | ❌ |
| False positive / negative rate | confirmatory-result column | ❌ |
| Instrument calibration | `instrument_id`, `calibration_date`, `r²` | ❌ |
| Batch / re-testing | `batch_id`, `retest_flag` | ❌ |
| Analyst performance | `analyst_id` | ❌ |
| Recovery / spike results | `recovery_pct` | ❌ |
| Turnaround time | `received_date` **and** `reported_date` — only one date column exists | ❌ |
| LOD / LOQ reporting | `lod`, `loq` | ❌ |
| Method / SOP reference | `method_id` | ❌ |
| Sampling officer / chain of custody | `officer_id`, `custody_log` | ❌ |

## 5.2 Required refusal behaviour

These intents must be **matched explicitly at Tier 0** and refused with a scoped message. They must **never** fall through to the LLM, which will generate a plausible number.

```python
OUT_OF_SCOPE_PATTERNS = {
  "gum_uncertainty":  r"(عدم\s*اليقين|الشك\s*القياسي|uncertainty|GUM|k\s*factor)",
  "westgard_qc":      r"(ويستجارد|westgard|ضبط\s*الجودة|control\s*chart|levey)",
  "calibration":      r"(معايرة|calibration|منحني\s*المعايرة|R2|r²)",
  "turnaround":       r"(زمن\s*الإنجاز|turnaround|TAT|مدة\s*التحليل)",
  "recovery":         r"(الاسترداد|recovery|spike|استرجاع)",
  "lod_loq":          r"(حد\s*الكشف|حد\s*القياس|LOD|LOQ)",
  "analyst":          r"(المحلل|الفني\s*المسؤول|analyst)",
  "false_rates":      r"(إيجابية\s*كاذبة|سلبية\s*كاذبة|false\s*positive|false\s*negative)",
}
```

**Refusal template (Arabic, user-facing):**

```
هذه المعلومة غير متوفرة في مجموعة البيانات الحالية.

الاستعلام المطلوب: {intent_label}
الحقول المطلوبة: {required_columns}
الحالة: غير موجودة في جدول residues

للحصول على هذه البيانات يلزم ربط جدول ضبط الجودة (QC)
من نظام المختبر المصدر (LIMS).

يمكنني بدلاً من ذلك مساعدتك في: {nearest_supported_intents}
```

**Design principle:** a scoped refusal that names the missing columns is more useful to a Technical Director than a hedged approximation — it tells them exactly which integration would unlock the capability. Always offer the nearest supported alternative rather than ending on the refusal.

## 5.3 Soft-warning handlers (answerable, but with mandatory caveats)

Distinct from refusals — these questions *can* be answered, but the answer is misleading without the caveat.

| Question pattern | Mandatory caveat |
|---|---|
| Any residue-count question | If any result hits 10 → *"العدد الفعلي قد يكون أعلى — النظام يسجل ١٠ متبقيات كحد أقصى لكل عينة"* |
| Any compliance question | *"الأساس المستخدم: {label-based \| computed}. توجد ٣٩٢ عينة مصنّفة مطابقة رغم احتوائها على قراءة فوق الحد."* |
| Any period question | *"البيانات تغطي 05/01/2026 – 17/05/2026 فعلياً (٤.٤ شهر)، وليس ٦ أشهر."* |
| Any MRL-dependent question | *"تم تقييم {n_evaluable} من أصل {n_total} متبقي؛ الباقي بدون حد مسجّل."* |
| Any neighborhood ranking | *"٨٨٠ سجل بدون حي مسجّل غير مشمول في الترتيب."* |
| Any mycotoxin question | *"تصنيف 'سموم فطرية' موجود في البيانات لكن أسماء التحاليل المسجلة هي مبيدات، لا سموم فطرية."* |
| Any analyte question | If fuzzy resolution occurred → *"تم توحيد {n} صيغة إملائية تحت الاسم القياسي {canonical}."* |

---

# APPENDIX — Measured dataset facts (grounding reference)

| Metric | Value |
|---|---|
| Total rows | 6,811 |
| Unique sample codes | 1,859 |
| Date span | 05 Jan 2026 → 17 May 2026 (11 unparseable) |
| Distinct commodities (raw / trimmed) | 279 / 243 |
| Distinct analyte strings | 272 (~150 real compounds) |
| Rows with no detection (`NO CBD`) | 655 |
| Rows with both reading and MRL parseable | 6,036 |
| Rows where reading > MRL | 1,880 |
| Samples labelled compliant but containing an exceedance | **392** |
| Max residues per sample | 10 (schema ceiling) |
| Samples at the 10-residue ceiling | 100 |
| Residue-count distribution | 1→288 · 2→273 · 3→210 · 4→143 · 5→124 · 6→75 · 7→46 · 8→39 · 9→44 · **10→100** |
| Neighborhoods | 54 (+880 unassigned rows) |
| Municipalities | 9 (+503 unassigned rows) |
| Test types | متبقيات مبيدات (4,281) · سموم فطرية (2,518) |
| Sample states | Dry (3,716) · Fresh (3,068) |
| Top commodities | كمون 999 · طماطم 590 · خيار 447 · فلفل بارد اخضر 428 · هيل 369 |
| Top analytes | azoxystrobin 415 · acetamiprid 368 · imidacloprid 362 · difenoconazole 323 · carbendazim 318 |
| Top neighborhoods | الجردة 420 · النهضة 351 · الأفق 332 · النخيل 331 · الإسكان 306 |
| Top municipalities | بلدية الصفراء الفرعية 2,349 · بلدية الديرة الفرعية 1,474 · بلدية شرق بريدة 895 |
