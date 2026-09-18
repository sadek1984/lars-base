"""
llm_fallback.py — extracted from core_query_engine.py (2026-09-18, Phase 3 split).

Everything that talks to an LLM: ollama client init, the
ollama SQL fallback, schema prompting, and the Gemini/GPT/ollama
process_with_gemini_fallback() entry used by ai_assistant.
Methods are byte-identical to their pre-split versions; this module only
relocates them. LLMFallbackMixin is mixed into CoreQueryEngine — methods refer to
engine state (self._get_connection(), detection helpers, handlers) via self.
"""
import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from modules.utils.prompt_loader import load_prompt

# Intent enum (optional - graceful fallback, same guard as core_query_engine)
try:
    from modules.query.intent_router import Intent
except ImportError:
    Intent = None

# LLM Configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b-it-qat")


class LLMFallbackMixin:
    def _init_llm(self):
        """Initialize LLM client for fallback queries"""
        try:
            from ollama import Client
            self.llm_client = Client(host=OLLAMA_URL)
            # Test connection
            self.llm_client.list()
        except Exception as e:
            print(f"⚠️ LLM initialization failed: {e}")
            self.llm_client = None

    def _handle_llm_query(self, query: str, samples: List[str], 
                           neighborhoods: List[str], pesticide: Optional[str]) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        LLM Fallback - Generate SQL using LLM
        Used when no pattern matches. Poisoning-domain queries are
        intercepted first and routed to the dedicated handler instead
        of the generic SQL-generation path.
        """
        from modules.poisoning import is_poisoning_domain
        if is_poisoning_domain(query):
            text, df, _ = self._handle_poisoning(Intent.POISONING_HEADLINE, query, None)
            return text, df

        if self.llm_client is None:
            return None, None
        
        try:
            # Build context
            schema_context = f"""
Available columns in chemistry_tidy table:
{', '.join(self.schema_columns[:30])}

Available sample types: {', '.join(self.available_sample_types[:15])}
Available neighborhoods: {', '.join(self.available_neighborhoods[:15])}

Key columns:
- "كود العينة": Sample code (unique identifier)
- "اسم العينة": Sample name/type
- "الحى": Neighborhood
- pesticide_name: Pesticide name (English)
- concentration: Pesticide concentration
- limit_value: MRL limit value
- is_detected: 1 if detected, 0 otherwise
- is_above_limit: 1 if concentration > limit
- sample_result: 'compliant (مطابقة)' or 'non-compliant (غير مطابقة)'
"""
            
            # Build prompt
            prompt = load_prompt(
                "sql_ollama_fallback",
                query=query,
                schema_context=schema_context,
                samples=samples if samples else "None",
                neighborhoods=neighborhoods if neighborhoods else "None",
                pesticide=pesticide if pesticide else "None",
            )
            
            # Call LLM
            response = self.llm_client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1}
            )
            
            sql = response['message']['content'].strip()
            
            # Clean up SQL
            sql = sql.replace('```sql', '').replace('```', '').strip()
            
            # Validate SQL (basic check)
            if not sql.upper().startswith('SELECT'):
                return None, None
            
            # Execute SQL
            con = self._get_connection()
            df = con.execute(sql).df()
            con.close()
            
            if not df.empty:
                response_text = f"🤖 **نتيجة من الذكاء الاصطناعي:**\n\n"
                response_text += f"📊 **{query}**\n\n"
                response_text += df.to_markdown(index=False)
                return response_text, df
            else:
                return f"🤖 الاستعلام لم يُرجع نتائج.\n\nSQL: `{sql[:200]}...`", None
                
        except Exception as e:
            print(f"⚠️ LLM query failed: {e}")
            return None, None

    # LLM SQL Generation (Gemini / GPT / Ollama Fallback)

    def _get_schema_info(self) -> str:
        """Return DB schema as a formatted string for LLM prompting (schema-only, no data)."""
        try:
            con = self._get_connection()
            cols = con.execute("DESCRIBE chemistry_tidy").df()
            con.close()
        except Exception as exc:
            logging.warning(f"Schema fetch failed: {exc}")
            return (
                "Table: chemistry_tidy — key columns: كود العينة, اسم العينة, "
                "pesticide_name, concentration, limit_value, is_above_limit, "
                "is_detected, sample_result, الحى, نوع العينة"
            )

        DESCRIPTIONS: Dict[str, str] = {
            "كود العينة":       "Sample code (unique identifier)",
            "اسم العينة":       "Sample name in English (Tomato, Cucumber, Cardamom, …)",
            "نوع العينة":       "Category: Vegetables / Fruits / Spices / Nuts / Grains",
            "الحى":             "Neighborhood name (Arabic)",
            "اسم المنشاة":      "Establishment / facility name",
            "التاريخ":          "Sample date (TIMESTAMP)",
            "pesticide_name":   "Pesticide name in English",
            "concentration":    "Measured concentration (DOUBLE)",
            "limit_value":      "Maximum Residue Limit – MRL (DOUBLE)",
            "exceedance_ratio": "concentration / limit_value",
            "is_above_limit":   "1 = above MRL, 0 = within MRL",
            "is_compliant":     "1 = compliant, 0 = non-compliant (lab judgment)",
            "is_detected":      "1 = detected, 0 = not detected",
            "sample_result":    "Lab verdict: 'Compliant' | 'Non-Compliant'",
        }

        lines = [
            "**Table: chemistry_tidy**",
            "| Column | Type | Description |",
            "|--------|------|-------------|",
        ]
        for _, row in cols.iterrows():
            col = row["column_name"]
            lines.append(f"| {col} | {row['column_type']} | {DESCRIPTIONS.get(col, '')} |")
        return "\n".join(lines)

    def _build_llm_sql_prompt(
        self,
        query: str,
        detected_samples: List[str],
        detected_neighborhoods: List[str],
        detected_pesticide: Optional[str],
    ) -> str:
        """Build the schema-only SQL prompt for Gemini / GPT / Ollama."""
        from modules.poisoning import POISONING_SCHEMA_CARD
        return load_prompt(
            "sql_llm_fallback",
            detected_samples=detected_samples or "None",
            detected_neighborhoods=detected_neighborhoods or "None",
            schema=self._get_schema_info() + "\n" + POISONING_SCHEMA_CARD,
            detected_pesticide=detected_pesticide or "None",
            query=query,
        )

    def process_with_gemini_fallback(
        self,
        query: str,
        llm_model: Any = None,
    ) -> Tuple[str, Optional[Any], Optional[str]]:

        from modules.poisoning import is_poisoning_domain
        if is_poisoning_domain(query):
            return self._handle_poisoning(Intent.POISONING_HEADLINE, query, None)
        """
        Full query processing with LLM SQL generation as a fallback.

        Processing order:
          Tier 1 — Pattern matching + intent routing  (self.process)
          Tier 2 — LLM SQL generation (Gemini / GPT / Ollama)

        Returns:
            (response_text, dataframe_or_None, generated_sql_or_None)

        The third element lets the caller display a "View SQL" expander AND
        double as a trust-level signal: Tier 1 (pattern/template matched)
        never populates generated_sql, only Tier 2 (LLM) does. Use
        get_trust_badge() below to render that distinction in the UI.
        """
        # ── Tier 1: existing pattern / intent routing ──
        response_text, df = self.process(query)

        is_unknown = (
            "Sorry, I couldn't fully understand" in response_text
            or "لم أتمكن من فهم" in response_text
        )

        if not is_unknown:
            return response_text, df, None

        # ── Tier 2: LLM SQL generation ──
        active_llm = llm_model if llm_model is not None else self.llm_client
        if active_llm is None:
            return response_text, None, None

        detected_samples       = self._detect_sample_types(query)
        detected_neighborhoods = self._detect_neighborhoods(query)
        detected_pesticide     = self._detect_pesticide(query)

        prompt = self._build_llm_sql_prompt(
            query, detected_samples, detected_neighborhoods, detected_pesticide
        )

        generated_sql: Optional[str] = None
        try:
            # Determine which LLM interface to use
            if llm_model is not None:
                if hasattr(llm_model, "chat") and hasattr(llm_model.chat, "completions"):
                    # OpenAI-compatible (GPT / local Ollama via openai SDK)
                    model_name = getattr(self, "_llm_model_name", "gpt-4o-mini")
                    resp = llm_model.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a SQL expert. Return ONLY valid DuckDB SQL.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.0,
                    )
                    generated_text = resp.choices[0].message.content
                else:
                    # Gemini (google.generativeai GenerativeModel)
                    generated_text = llm_model.generate_content(prompt).text
            else:
                # Ollama client (self.llm_client)
                resp = self.llm_client.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1},
                )
                generated_text = resp["message"]["content"]

            # ── Extract SQL from response ──
            sql_match = re.search(
                r"```sql\n?(.*?)```", generated_text, re.DOTALL | re.IGNORECASE
            ) or re.search(r"```\n?(.*?)```", generated_text, re.DOTALL)

            if sql_match:
                generated_sql = sql_match.group(1).strip()
            else:
                generated_sql = generated_text.replace("```", "").strip()

            if not generated_sql.upper().startswith("SELECT"):
                logging.warning("LLM returned non-SELECT SQL — skipping execution")
                return response_text, None, generated_sql

            # ── Execute SQL ──
            con = self._get_connection()
            try:
                df = con.execute(generated_sql).df()
            except Exception as sql_err:
                logging.warning(f"LLM SQL execution failed: {sql_err}")
                con.close()
                return (
                    f"❌ AI-generated SQL had an error: `{sql_err}`\n\n"
                    "Try rephrasing your question.",
                    None,
                    generated_sql,
                )
            con.close()

            if not df.empty:
                response_text = (
                    f"🤖 **AI-generated result ({len(df)} rows):**\n\n"
                    + df.head(50).to_markdown(index=False)
                )
            else:
                response_text = (
                    "⚠️ The query ran successfully but returned no results. "
                    "Try rephrasing."
                )

            return response_text, df, generated_sql

        except Exception as exc:
            logging.error(f"LLM fallback failed: {exc}")
            return response_text, None, generated_sql
