#!/bin/bash

# LARS Voice Bot Setup Script
# Run with: bash setup_voice_bot.sh

echo "🚀 إعداد بوت LARS الصوتي..."

# 1. تحديث pip
echo "📦 تحديث pip..."
pip3 install --upgrade pip

# 2. تثبيت المكتبات
echo "📥 تثبيت المكتبات المطلوبة..."
pip3 install -r voice_bot_requirements.txt

# 3. التحقق من Ollama
echo "🤖 التحقق من خدمة Ollama..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama يعمل بنجاح"
    echo "📋 النماذج المتاحة:"
    curl -s http://localhost:11434/api/tags | python3 -m json.tool | grep '"name"' | head -5
else
    echo "⚠️ Ollama غير متصل! تأكد من تشغيله بـ: ollama serve"
fi

# 4. التحقق من قاعدة البيانات
echo "🗄️ التحقق من قاعدة البيانات..."
if [ -f "/Users/a12/Buraidah_lars/src/LARS/data/lars_data_demo.duckdb" ]; then
    echo "✅ قاعدة البيانات موجودة"
else
    echo "⚠️ قاعدة البيانات غير موجودة! قم بتشغيل migrate_db.py أولاً"
fi

# 5. تحميل نموذج Whisper
echo "🎤 تحميل نموذج Whisper (قد يستغرق وقتاً في المرة الأولى)..."

# 6. التعليمات النهائية
echo ""
echo "✅ الإعداد مكتمل!"
echo ""
echo "📝 لتشغيل البوت:"
echo "   cd /Users/a12/Buraidah_lars/src/LARS/modules"
echo "   python3 voice_lars.py"
echo ""
echo "⚙️ تأكد من:"
echo "   1. Ollama يعمل (ollama serve)"
echo "   2. النموذج qwen2.5-coder:3b متاح"
echo "   3. قاعدة البيانات موجودة"
echo ""
