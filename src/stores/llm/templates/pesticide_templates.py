
class PesticideTemplateParser:
    """
    Enhanced template parser specifically designed for pesticide data analysis
    """
    
    def __init__(self):
        self.templates = {
            "rag": {
                "system_prompt": """You are a helpful assistant specializing in pesticide analysis reports. You analyze laboratory data and provide structured, detailed responses about pesticide residues in agricultural samples.

Key Guidelines:
- Always provide complete, structured data when available
- List individual readings, don't summarize
- Use both Arabic and English terms when appropriate
- For compliance queries, clearly separate compliant from non-compliant results
- When listing readings, use the format: Sample Code, Sample Name, Pesticide Name, Limits, Reading of device, Result""",

                "footer_prompt": """Based on the provided pesticide analysis data, answer this question: {query}

Instructions:
- If asking for readings with specific results (غير مطابق/non-compliant), list ALL individual readings
- Do NOT summarize, provide every individual reading found
- Structure the output clearly with headers
- Include Arabic and English terms where appropriate
- If no data matches the criteria, state this clearly

QUESTION: {query}""",

                "structured_response": {
                    "non_compliant": """Based on the provided data, here's a structured list of samples where the result (النتيجة) is "غير مطابق" (non-compliant):

**Non-Compliant Pesticide Readings:**

| كود العينة (Sample Code) | اسم العينة (Sample Name) | اسم المبيد (Pesticide Name) | الحدود (Limits) | قراءة الجهاز (Reading of device) | النتيجة (Result) |
|-------------------------|-------------------------|----------------------------|-----------------|--------------------------------|------------------|
{readings_table}

**Summary:**
- Total non-compliant readings: {total_count}
- Samples affected: {sample_count}
- Common pesticides found: {common_pesticides}""",

                    "compliant": """Based on the provided data, here's a structured list of samples where the result (النتيجة) is "مطابق" (compliant):

**Compliant Pesticide Readings:**

| كود العينة (Sample Code) | اسم العينة (Sample Name) | اسم المبيد (Pesticide Name) | الحدود (Limits) | قراءة الجهاز (Reading of device) | النتيجة (Result) |
|-------------------------|-------------------------|----------------------------|-----------------|--------------------------------|------------------|
{readings_table}

**Summary:**
- Total compliant readings: {total_count}
- Samples analyzed: {sample_count}""",

                    "pepper_analysis": """Based on the provided data, here are the pesticide analysis results for pepper (فلفل) samples:

**Pepper Sample Analysis:**

{readings_table}

**Analysis Summary:**
- Total pepper samples: {total_count}
- Compliant samples: {compliant_count}
- Non-compliant samples: {non_compliant_count}
- Pesticides detected: {pesticides_found}""",

                    "general_summary": """**Pesticide Analysis Summary Report:**

**Overview:**
- Total readings analyzed: {total_readings}
- Total samples: {total_samples}
- Compliance rate: {compliance_rate}%

**By Result Status:**
- Compliant (مطابق): {compliant_count}
- Non-compliant (غير مطابق): {non_compliant_count}

**By Sample Type:**
{sample_type_breakdown}

**Pesticides Found:**
{pesticide_breakdown}

**Detailed Readings:**
{detailed_readings}"""
                }
            }
        }

    def get(self, category: str, template_name: str, variables: dict = None) -> str:
        """Get template with variable substitution"""
        try:
            template = self.templates[category][template_name]
            if variables:
                return template.format(**variables)
            return template
        except KeyError:
            return f"Template not found: {category}.{template_name}"

    def generate_structured_response(self, intent_type: str, structured_data: list) -> str:
        """Generate structured response based on intent and data"""
        
        if not structured_data:
            return "No pesticide analysis data found matching your criteria."

        if intent_type == "non_compliant":
            return self._generate_non_compliant_report(structured_data)
        elif intent_type == "compliant":
            return self._generate_compliant_report(structured_data)
        elif intent_type == "summary":
            return self._generate_summary_report(structured_data)
        else:
            return self._generate_general_report(structured_data)

    def _generate_non_compliant_report(self, data: list) -> str:
        """Generate non-compliant readings report"""
        # Filter non-compliant readings
        non_compliant = [item for item in data if item.get('is_non_compliant', False)]
        
        if not non_compliant:
            return "No non-compliant (غير مطابق) readings found in the provided data."

        # Build table
        table_rows = []
        pesticides_found = set()
        
        for item in non_compliant:
            row = f"| {item.get('sample_code', 'N/A')} | {item.get('sample_name', 'N/A')} | {item.get('pesticide_name', 'N/A')} | {item.get('limits', 'N/A')} | {item.get('device_reading', 'N/A')} | {item.get('result', 'N/A')} |"
            table_rows.append(row)
            
            if item.get('pesticide_name'):
                pesticides_found.add(item.get('pesticide_name'))

        readings_table = "\n".join(table_rows)
        
        return self.get("rag", "structured_response").get("non_compliant", "").format(
            readings_table=readings_table,
            total_count=len(non_compliant),
            sample_count=len(set(item.get('sample_code', '') for item in non_compliant)),
            common_pesticides=", ".join(list(pesticides_found)[:5])
        )

    def _generate_compliant_report(self, data: list) -> str:
        """Generate compliant readings report"""
        # Filter compliant readings
        compliant = [item for item in data if item.get('is_compliant', False)]
        
        if not compliant:
            return "No compliant (مطابق) readings found in the provided data."

        # Build table
        table_rows = []
        
        for item in compliant:
            row = f"| {item.get('sample_code', 'N/A')} | {item.get('sample_name', 'N/A')} | {item.get('pesticide_name', 'N/A')} | {item.get('limits', 'N/A')} | {item.get('device_reading', 'N/A')} | {item.get('result', 'N/A')} |"
            table_rows.append(row)

        readings_table = "\n".join(table_rows)
        
        return self.get("rag", "structured_response").get("compliant", "").format(
            readings_table=readings_table,
            total_count=len(compliant),
            sample_count=len(set(item.get('sample_code', '') for item in compliant))
        )

    def _generate_summary_report(self, data: list) -> str:
        """Generate comprehensive summary report"""
        total_readings = len(data)
        compliant_count = len([item for item in data if item.get('is_compliant', False)])
        non_compliant_count = len([item for item in data if item.get('is_non_compliant', False)])
        
        # Sample type breakdown
        sample_types = {}
        for item in data:
            if item.get('is_pepper'):
                sample_types['Pepper (فلفل)'] = sample_types.get('Pepper (فلفل)', 0) + 1
            elif item.get('is_tomato'):
                sample_types['Tomato (طماطم)'] = sample_types.get('Tomato (طماطم)', 0) + 1
            elif item.get('is_cucumber'):
                sample_types['Cucumber (خيار)'] = sample_types.get('Cucumber (خيار)', 0) + 1

        sample_breakdown = "\n".join([f"- {k}: {v}" for k, v in sample_types.items()])
        
        # Pesticide breakdown
        pesticides = {}
        for item in data:
            pest_name = item.get('pesticide_name', 'Unknown')
            if pest_name and pest_name != 'Unknown':
                pesticides[pest_name] = pesticides.get(pest_name, 0) + 1
                
        pesticide_breakdown = "\n".join([f"- {k}: {v} readings" for k, v in list(pesticides.items())[:10]])
        
        # Detailed readings (first 20)
        detailed_readings = self._build_detailed_table(data[:20])
        
        compliance_rate = round((compliant_count / total_readings * 100), 1) if total_readings > 0 else 0
        
        return self.get("rag", "structured_response").get("general_summary", "").format(
            total_readings=total_readings,
            total_samples=len(set(item.get('sample_code', '') for item in data)),
            compliance_rate=compliance_rate,
            compliant_count=compliant_count,
            non_compliant_count=non_compliant_count,
            sample_type_breakdown=sample_breakdown or "- No specific sample types identified",
            pesticide_breakdown=pesticide_breakdown or "- No pesticides identified",
            detailed_readings=detailed_readings
        )

    def _generate_general_report(self, data: list) -> str:
        """Generate general report for unspecified queries"""
        return f"""**Pesticide Analysis Data Found:**

Total records: {len(data)}

**Sample of readings:**
{self._build_detailed_table(data[:10])}

{"*Showing first 10 records*" if len(data) > 10 else ""}"""

    def _build_detailed_table(self, data: list) -> str:
        """Build detailed table for readings"""
        if not data:
            return "No data available"
            
        table_header = """| كود العينة | اسم العينة | اسم المبيد | الحدود | قراءة الجهاز | النتيجة |
|-----------|-----------|----------|-------|------------|--------|"""
        
        table_rows = [table_header]
        
        for item in data:
            row = f"| {item.get('sample_code', 'N/A')} | {item.get('sample_name', 'N/A')} | {item.get('pesticide_name', 'N/A')} | {item.get('limits', 'N/A')} | {item.get('device_reading', 'N/A')} | {item.get('result', 'N/A')} |"
            table_rows.append(row)
            
        return "\n".join(table_rows)