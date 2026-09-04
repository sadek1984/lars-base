import os
import duckdb
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from faster_whisper import WhisperModel
from openai import OpenAI
from difflib import get_close_matches
from io import BytesIO

# ============================================================
# Configuration & Models Setup
# ============================================================
print("🔄 Loading Whisper large-v3 model (optimized for M1)...")
stt_model = WhisperModel(
    "large-v3",
    device="cpu",
    compute_type="int8",
    num_workers=2,
    cpu_threads=4
)
print("✅ Whisper model loaded!")

client = OpenAI(base_url="http://localhost:11434/v1", api_key="not-needed")
DB_PATH = "/Users/a12/Buraidah_lars/src/LARS/data/lars_data_demo.duckdb"

# ============================================================
# Constants & Dictionaries
# ============================================================
# Threshold for "small vs large" results
SMALL_RESULT_THRESHOLD = 5  # rows
EXECUTIVE_SUMMARY_THRESHOLD = 10  # rows for voice summary

# User personas
PERSONA_MANAGER = "manager"
PERSONA_TECHNICIAN = "technician"
PERSONA_ANALYST = "analyst"

from modules.prompt_loader import load_prompt
from modules.mappings import (
    STT_CORRECTIONS,
    KNOWN_PESTICIDES_AR,
    PESTICIDE_AR_TO_EN as ARABIC_TO_ENGLISH,
    SAMPLE_CORRECTIONS,
    correct_stt_text,
)

def get_schema_info():
    """Get database schema"""
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute("DESCRIBE chemistry_tidy").df()
        columns = ", ".join([f"{row['column_name']} ({row['column_type']})" 
                           for _, row in df.iterrows()])
        con.close()
        
        schema_note = f"""
Table: chemistry_tidy
Columns: {columns}

⚠️ IMPORTANT COLUMN NAMES (use exactly as shown):
- "التاريخ" (NOT "تاريخ") - for dates
- "كود العينة" (NOT "كود") - for sample code
- "اسم العينة" (NOT "العينة") - for sample name
- "pesticide_name" - for pesticide names (English)
- "concentration" - for concentration values
- "is_detected" - 1 if detected, 0 if not
- "sample_result" - 'مطابق' or 'غير مطابق'
"""
        return schema_note
    except Exception as e:
        return "Error getting schema: " + str(e)


def detect_user_persona(text):
    """
    Detect user type based on question pattern
    - Manager: wants KPIs, summaries, decisions
    - Technician: data entry, quick confirmation
    - Analyst: detailed queries, trends
    """
    manager_keywords = ['كام', 'نسبة', 'إجمالي', 'اجمالي', 'ملخص', 'تقرير']
    tech_keywords = ['سجل', 'أضف', 'احفظ', 'التركيز']
    analyst_keywords = ['تحليل', 'مقارنة', 'اتجاه', 'trend', 'توزيع']
    
    text_lower = text.lower()
    
    if any(kw in text or kw in text_lower for kw in tech_keywords):
        return PERSONA_TECHNICIAN
    elif any(kw in text or kw in text_lower for kw in manager_keywords):
        return PERSONA_MANAGER
    elif any(kw in text or kw in text_lower for kw in analyst_keywords):
        return PERSONA_ANALYST
    
    return PERSONA_MANAGER  # Default


def route_intent(text):
    """تحديد نوع الطلب: QUERY أو ENTRY"""
    query_keywords = [
        'ما عدد', 'كم عدد', 'كم', 'ماهي', 'ما هي', 'ما هو', 'ماهو',
        'اعرض', 'أظهر', 'بحث', 'ابحث', 'جد', 'اوجد',
        'عينات', 'مبيدات', 'تحتوي', 'فوق الحد', 'تحت الحد',
        'how many', 'what', 'find', 'show', 'list', 'count'
    ]
    
    entry_keywords = [
        'سجل', 'أضف', 'ادخل', 'احفظ', 'اكتب',
        'record', 'add', 'save', 'enter', 'log',
        'التركيز', 'ppm', 'mg/kg'
    ]
    
    text_lower = text.lower()
    query_score = sum(1 for kw in query_keywords if kw in text_lower or kw in text)
    entry_score = sum(1 for kw in entry_keywords if kw in text_lower or kw in text)
    
    if query_score > entry_score:
        return "QUERY"
    elif entry_score > query_score:
        return "ENTRY"
    
    # Use LLM as fallback
    prompt = load_prompt("voice_intent_classify", text=text)
    
    response = client.chat.completions.create(
        model="gemma3:4b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5,
        temperature=0
    )
    result = response.choices[0].message.content.strip().upper()
    return "QUERY" if "QUERY" in result else "ENTRY"


def generate_executive_summary(df, question):
    """
    Generate executive summary for managers
    Progressive Disclosure: show summary + offer full report
    """
    row_count = len(df)
    
    if row_count == 0:
        return "لم أجد أي نتائج تطابق سؤالك."
    
    # Get key insights
    if 'is_compliant' in df.columns or 'is_above_limit' in df.columns:
        compliance_col = 'is_compliant' if 'is_compliant' in df.columns else 'is_above_limit'
        violations = df[df[compliance_col] == 0].shape[0] if 'is_compliant' in df.columns else df[df[compliance_col] == 1].shape[0]
        compliance_rate = ((row_count - violations) / row_count * 100) if row_count > 0 else 0
        
        summary = f"📊 **ملخص تنفيذي:**\n"
        summary += f"• إجمالي النتائج: {row_count}\n"
        summary += f"• المخالفات: {violations}\n"
        summary += f"• نسبة الالتزام: {compliance_rate:.1f}%\n\n"
    else:
        summary = f"📊 **ملخص تنفيذي:**\n• وجدت {row_count} نتيجة\n\n"
    
    # Show top 3 results
    if row_count <= 3:
        summary += f"🔍 **النتائج:**\n{df.to_markdown(index=False)}"
    else:
        summary += f"🔍 **عينة من النتائج (أول 3):**\n{df.head(3).to_markdown(index=False)}\n\n"
        summary += f"💡 *يوجد {row_count - 3} نتيجة إضافية. سأرسل التقرير الكامل كملف Excel.*"
    
    return summary


def create_excel_report(df, filename="lars_report.xlsx"):
    """Create Excel file from DataFrame"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='النتائج')
        
        # Auto-adjust column widths
        worksheet = writer.sheets['النتائج']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    return output


# ============================================================
# Main Query Function with Progressive Disclosure
# ============================================================

def answer_database_question(question, persona=PERSONA_MANAGER):
    """
    Answer database questions with progressive disclosure
    Returns: (text_response, excel_file_bytes, needs_dashboard)
    """
    schema = get_schema_info()
    
    # Pattern matching for common queries (optimized path)
    import re
    
    # ========== PATTERN 1: نسبة المخالفات في عينة معينة ==========
    # مثال: "كم نسبة المخالفات في الطماطم"
    if 'نسبة' in question and 'مخالف' in question:
        # Find sample name
        sample_name = None
        sample_patterns = {
            'طماطم': 'طماطم', 'الطماطم': 'طماطم',
            'خيار': 'خيار', 'الخيار': 'خيار',
            'فلفل': 'فلفل', 'الفلفل': 'فلفل',
            'باذنجان': 'باذنجان', 'الباذنجان': 'باذنجان',
            'كوسة': 'كوسة', 'الكوسة': 'كوسة',
            'فاصوليا': 'فاصوليا', 'الفاصوليا': 'فاصوليا',
            'بقدونس': 'بقدونس', 'البقدونس': 'بقدونس',
            'جزر': 'جزر', 'الجزر': 'جزر',
        }
        for pattern, name in sample_patterns.items():
            if pattern in question:
                sample_name = name
                break
        
        if sample_name:
            sql_query = f"""
            SELECT 
                COUNT(DISTINCT "كود العينة") as إجمالي_العينات,
                SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as عدد_المخالفات,
                ROUND(SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as نسبة_المخالفات
            FROM chemistry_tidy
            WHERE is_detected = 1
            AND "اسم العينة" ILIKE '%{sample_name}%'
            """
            try:
                con = duckdb.connect(DB_PATH, read_only=True)
                result_df = con.execute(sql_query).df()
                con.close()
                
                if not result_df.empty:
                    total = result_df['إجمالي_العينات'].iloc[0]
                    violations = result_df['عدد_المخالفات'].iloc[0]
                    percentage = result_df['نسبة_المخالفات'].iloc[0]
                    
                    text = f"📊 **إحصائيات {sample_name}:**\n\n"
                    text += f"• إجمالي العينات: {total}\n"
                    text += f"• عدد المخالفات: {violations}\n"
                    text += f"• **نسبة المخالفات: {percentage}%**"
                    
                    return text, None, False
            except Exception as e:
                pass  # Fall through to LLM
    
    # ========== PATTERN 2: تحليل مفصل لمبيد ==========
    # مثال: "تحليل مفصل لمبيد البايفنثرن"
    if 'تحليل' in question or 'مفصل' in question:
        # Detect pesticide
        for ar_name, en_name in ARABIC_TO_ENGLISH.items():
            if ar_name in question:
                sql_query = f"""
                SELECT 
                    "اسم العينة" as نوع_العينة,
                    COUNT(DISTINCT "كود العينة") as عدد_العينات,
                    ROUND(AVG(concentration), 4) as متوسط_التركيز,
                    ROUND(MAX(concentration), 4) as أعلى_تركيز,
                    SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as فوق_الحد,
                    SUM(CASE WHEN is_above_limit = 0 THEN 1 ELSE 0 END) as تحت_الحد
                FROM chemistry_tidy
                WHERE is_detected = 1
                AND pesticide_name ILIKE '%{en_name}%'
                GROUP BY "اسم العينة"
                ORDER BY عدد_العينات DESC
                """
                try:
                    con = duckdb.connect(DB_PATH, read_only=True)
                    result_df = con.execute(sql_query).df()
                    con.close()
                    
                    if not result_df.empty:
                        text = f"📊 **تحليل مفصل لمبيد {ar_name} ({en_name}):**\n\n"
                        text += result_df.to_markdown(index=False)
                        
                        excel_file = create_excel_report(result_df) if len(result_df) > 5 else None
                        return text, excel_file, False
                except Exception as e:
                    pass
                break
    
    # ========== Existing patterns ==========
    # Detect pesticide names
    detected_pesticide = None
    for ar_name, en_name in ARABIC_TO_ENGLISH.items():
        if ar_name in question:
            detected_pesticide = en_name
            break
    
    # Detect sample names
    detected_sample = None
    for wrong, correct in SAMPLE_CORRECTIONS.items():
        if wrong in question or correct in question:
            detected_sample = correct
            break
    
    # Direct SQL for pesticide + sample queries
    if detected_pesticide and detected_sample:
        sql_query = f"""
        SELECT 
            "كود العينة" as كود_العينة,
            "اسم العينة" as اسم_العينة,
            pesticide_name as المبيد,
            concentration as التركيز,
            limit_value as الحد_المسموح,
            CASE WHEN is_above_limit = 1 THEN 'فوق الحد' ELSE 'تحت الحد' END as الحالة
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND pesticide_name ILIKE '%{detected_pesticide}%'
        AND "اسم العينة" ILIKE '%{detected_sample}%'
        ORDER BY concentration DESC
        """
    elif detected_pesticide:
        sql_query = f"""
        SELECT 
            "اسم العينة" as نوع_العينة,
            COUNT(DISTINCT "كود العينة") as عدد_العينات,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as فوق_الحد,
            SUM(CASE WHEN is_above_limit = 0 THEN 1 ELSE 0 END) as تحت_الحد
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND pesticide_name ILIKE '%{detected_pesticide}%'
        GROUP BY "اسم العينة"
        ORDER BY عدد_العينات DESC
        """
    else:
        # Use LLM to generate SQL
        system_prompt = load_prompt("voice_sql_gen", schema=schema, persona=persona)
        
        response = client.chat.completions.create(
            model="gemma3:4b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            temperature=0
        )
        sql_query = response.choices[0].message.content.replace("```sql", "").replace("```", "").strip()
    
    # Execute SQL
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        result_df = con.execute(sql_query).df()
        con.close()
        
        if result_df.empty:
            return "لم أجد نتائج تطابق سؤالك.", None, False
        
        row_count = len(result_df)
        
        # Decision tree based on result size and persona
        if persona == PERSONA_MANAGER:
            # Managers get executive summary
            text_response = generate_executive_summary(result_df, question)
            excel_file = create_excel_report(result_df) if row_count > SMALL_RESULT_THRESHOLD else None
            needs_dashboard = row_count > 50  # Suggest dashboard for complex analysis
            
        elif persona == PERSONA_TECHNICIAN:
            # Technicians get quick confirmations
            if row_count <= 3:
                text_response = f"✅ تم. النتائج:\n{result_df.to_markdown(index=False)}"
            else:
                text_response = f"✅ تم. وجدت {row_count} نتيجة. التفاصيل في الملف المرفق."
            excel_file = create_excel_report(result_df) if row_count > 3 else None
            needs_dashboard = False
            
        else:  # PERSONA_ANALYST
            # Analysts get detailed data
            if row_count <= 10:
                text_response = f"📊 النتائج:\n{result_df.to_markdown(index=False)}"
                excel_file = None
            else:
                text_response = f"📊 وجدت {row_count} نتيجة. أول 5:\n{result_df.head(5).to_markdown(index=False)}\n\n"
                text_response += "باقي النتائج في الملف المرفق."
                excel_file = create_excel_report(result_df)
            needs_dashboard = row_count > 100
        
        # Add dashboard suggestion if needed
        if needs_dashboard:
            text_response += "\n\n💡 **نصيحة:** لتحليل أعمق مع رسوم بيانية وخرائط، افتح لوحة التحكم في تطبيق LARS."
        
        return text_response, excel_file, needs_dashboard
        
    except Exception as e:
        return f"⚠️ خطأ في تنفيذ الاستعلام:\n{e}\n\nSQL:\n{sql_query}", None, False


def extract_lab_data(user_text):
    """Extract structured data for lab entry"""
    system_prompt = load_prompt("voice_data_extraction")
    
    response = client.chat.completions.create(
        model="gemma3:4b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        temperature=0
    )
    return response.choices[0].message.content


# ============================================================
# Enhanced Voice Transcription with Two-Pass
# ============================================================

def transcribe_audio(file_path):
    """
    Enhanced transcription with:
    - Language hints
    - Initial prompts with pesticide names
    - Two-pass transcription for low confidence
    """
    # PASS 1: Initial transcription with prompts
    segments, info = stt_model.transcribe(
        file_path,
        beam_size=5,
        language="ar",
        initial_prompt="مبيدات حشرية: كلوربيريفوس، فبرونيل، ايميداكلوبريد، بوبروفيزين، دلتامثرن",
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=True
    )
    
    raw_text = " ".join([s.text for s in segments])
    
    # PASS 2: If confidence is low, re-transcribe with detected terms
    if info.language_probability < 0.85:
        # Extract potential pesticide names from first pass
        detected_terms = []
        for known_pest in KNOWN_PESTICIDES_AR:
            if known_pest in raw_text:
                detected_terms.append(known_pest)
        
        if detected_terms:
            new_prompt = f"مبيدات: {', '.join(detected_terms[:5])}"
            
            segments, info = stt_model.transcribe(
                file_path,
                beam_size=7,  # Higher beam for second pass
                language="ar",
                initial_prompt=new_prompt,
                word_timestamps=True,
                vad_filter=True
            )
            raw_text = " ".join([s.text for s in segments])
    
    # Apply corrections
    corrected_text = correct_stt_text(raw_text)
    
    return raw_text, corrected_text, info.language_probability


# ============================================================
# Telegram Handlers (QUERY ONLY - No Data Entry)
# ============================================================

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages - QUERY ONLY"""
    voice_file = await update.message.voice.get_file()
    file_path = "temp_voice.ogg"
    await voice_file.download_to_drive(file_path)
    
    await update.message.reply_text("🎧 سمعتك، جاري التحليل...")
    
    try:
        # Enhanced transcription
        raw_text, corrected_text, confidence = transcribe_audio(file_path)
        
        # Show transcription (with correction if applied)
        if corrected_text != raw_text:
            await update.message.reply_text(
                f"📝 النص المسموع: {raw_text}\n"
                f"✅ بعد التصحيح: {corrected_text}\n"
                f"🎯 الدقة: {confidence*100:.1f}%"
            )
        else:
            await update.message.reply_text(f"📝 النص: {corrected_text}")
        
        # Detect persona for response style
        persona = detect_user_persona(corrected_text)
        
        # Always execute as QUERY
        await update.message.reply_text("🔍 جاري البحث...")
        
        try:
            text_response, excel_file, needs_dashboard = answer_database_question(
                corrected_text, 
                persona
            )
            
            # Send text response
            await update.message.reply_text(text_response, parse_mode='Markdown')
            
            # Send Excel file if generated
            if excel_file:
                await update.message.reply_document(
                    document=excel_file,
                    filename="lars_report.xlsx",
                    caption="📎 التقرير الكامل"
                )
        except Exception as query_error:
            await update.message.reply_text(
                f"⚠️ عذراً، حدث خطأ أثناء معالجة الاستعلام:\n"
                f"`{str(query_error)[:200]}`\n\n"
                f"الرجاء المحاولة مرة أخرى أو إعادة صياغة السؤال.",
                parse_mode='Markdown'
            )
    
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ عذراً، حدث خطأ:\n`{str(e)[:200]}`",
            parse_mode='Markdown'
        )
    
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages - QUERY ONLY"""
    text = update.message.text
    persona = detect_user_persona(text)
    
    await update.message.reply_text("🔍 جاري البحث...")
    
    try:
        text_response, excel_file, needs_dashboard = answer_database_question(text, persona)
        
        await update.message.reply_text(text_response, parse_mode='Markdown')
        
        if excel_file:
            await update.message.reply_document(
                document=excel_file,
                filename="lars_report.xlsx",
                caption="📎 التقرير الكامل"
            )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ عذراً، حدث خطأ أثناء معالجة الاستعلام:\n"
            f"`{str(e)[:200]}`\n\n"
            f"الرجاء المحاولة مرة أخرى أو إعادة صياغة السؤال.",
            parse_mode='Markdown'
        )


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    TOKEN = TELEGRAM_TOKEN
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🚀 LARS Voice Assistant is running...")
    print(f"📂 Database: {DB_PATH}")
    print("✨ Mode: QUERY ONLY (Read-Only)")
    app.run_polling()