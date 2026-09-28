# Batch 5 backlog (handlers)

Found during the semantic-layer evaluation (feat/semantic-layer, tag
`demo-semantic-2026-09`). None of these are fixed yet: with
`LARS_SEMANTIC_MODE=off` the branch must behave exactly like its base.
Evidence: `phase0/semantic_eval/` (bank_semantic_only_reviewed.csv, failure.csv).

## Decisions already made
- [ ] **"مخالفة" = official verdict (`sample_result`) in the handlers too.** Today the
      handlers read "مخالفة / المخالفات / نسبة المخالفة / نسبة المطابقة" as above the EU MRL
      (Batch 4, option A). The semantic layer already uses the official verdict. 16 bank
      questions differ for this reason only: B007, B011, B014, B041, B045, D007, D008, D009,
      D010, D011, D012, D016, D019, D020, D030, E031 (e.g. cumin 182 above MRL vs 147
      officially non-compliant). The per-pesticide "violations" can only stay technical
      (no per-pesticide verdict) and keep the EU MRL wording.
- [ ] **Apply `config/analyte_map.csv` in the handlers.** Handlers count raw spellings
      (A023: cumin with carbendazim 135 vs 136 with 'carbemdazim' merged; F06 ranking
      imidacloprid 41 vs canonical counts). Also merges aflaB1 / "Afla B1".

## Handler bugs
- [ ] **"تقرير بآخر شهر" drops the period.** The attached "بـ" hides "آخر شهر"; the KPI summary
      answers over all 1,859 samples. "عطني تقرير عن آخر شهر" correctly gives 469.
- [ ] **KPI summary ignores "هذا الشهر" and "الربع الأول"** (D003, D039, D004): answers over all
      data. Semantic reading to match: this month = calendar month of the latest data
      (May 2026, 229 samples, "آخر شهر في البيانات: مايو 2026"); Q1 = Jan–Mar (1,111).
- [ ] **Out-of-scope gate misses prices:** "كم سعر الطماطم؟" is answered with tomato sample counts.
- [ ] **D005, D006, D029** ("أعلى ٥ مبيدات من حيث عدد المخالفات" …) answer "samples with exactly
      N pesticides".
- [ ] **Answers that don't address the question** (semantic answers them): A029 and B008
      (pesticides in cardamom → handler gives sample counts), A034 (pistachio and cashew
      "each separately" → merged, raw spellings), A047–A049 (pesticides per neighborhood →
      product summary; A049 covers one neighborhood only), D031 (monthly report → per-product
      compliance table).
- [ ] **Counting unit:** A008, A026–A028, A050, A051, B003, B018 list detection rows (with
      duplicates and raw spellings) where the question asks for samples / neighborhoods /
      municipalities.
- [ ] **D022 category shares:** each sample is put in one category (Spices 461); the lab data
      files 43 samples under two categories (Spices 479 distinct). Decide the rule.

## Semantic layer
- [ ] **A046 misread:** "ما هي أنواع التوابل الموجودة في حي الإسكان؟" is read as pesticides by
      product and omits products with no detections (Dried Lemon, Cloves, Fennel). Needs a
      "products present" reading (sample_count by product) — prompt rule or example.
- [ ] Unstable reading of the vague "وش صار بالعينات شهر ورا شهر؟" (sample count vs
      non-compliance rate per month); the live cache pins the first answer.
- [ ] **"أخطر N أحياء … آخر شهر/شهرين":** Gemini sets unsupported=true about half the time
      ("cannot compute the rate per neighborhood"), so live mode keeps the period_not_applied
      refusal. When it does return a spec, the coverage repair restores the dropped period and
      top_n and the answer matches SQL. Prompt rules/examples tried; they regressed A039 and F07d, so they were reverted.
- [ ] **Period-blind handlers** (refused with a period since 2026-09-28): _handle_top_n_by_metric,
      _handle_inspection_priority, _handle_time_series_*, the municipality handlers and the rest
      not on CoreQueryEngine._PERIOD_VERIFIED. Adding date_filter to one = audit + add to the list.

## Older open findings
- [ ] "المايونيز" fuzzy-matched to ethion in handler pesticide detection.
- [ ] "عدم المطابقة" reads as compliant in the shared `compliance_intent`.
- [ ] Misfiled category rows (Ketchup under Spices, fruits under Vegetables, "Wheat" in every
      category) — data issue for the lab.
