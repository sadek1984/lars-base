# Ollama Setup Guide

## 🚀 Quick Start

Your app now supports **both OpenAI and Ollama**! You can switch between them in the sidebar.

---

## 📦 Install Ollama

### macOS:
```bash
# Install Ollama
brew install ollama

# Or download from: https://ollama.ai
```

### Start Ollama Service:
```bash
# Ollama usually starts automatically, but you can also run:
ollama serve
```

---

## 📥 Download the Model

```bash
# Pull the qwen2.5-coder:1.5b model (lightweight, fast)
ollama pull qwen2.5-coder:1.5b
```

**Model Info:**
- **Name:** qwen2.5-coder:1.5b
- **Size:** ~900 MB
- **Speed:** Very fast on M1 Mac
- **Good for:** Code generation, data analysis

---

## 🎯 How to Use

### In Your Streamlit App:

1. **Start the app:**
   ```bash
   streamlit run src/LARS/app.py
   ```

2. **Go to AI Assistant page**

3. **Look in the sidebar** for:
   ```
   🤖 AI Model Selection
   ⚪ OpenAI (gpt-4o-mini)
   🔵 Ollama (qwen2.5-coder:1.5b)
   ```

4. **Select your preferred model:**
   - **OpenAI** = Cloud API (requires internet + API key)
   - **Ollama** = Local model (works offline, free)

---

## ✅ Verify Ollama is Running

```bash
# Check if Ollama is running
curl http://localhost:11434/api/version

# You should see: {"version":"..."}
```

---

## 🔄 Switch Between Models

- **OpenAI:** Best for complex queries, consistent results
- **Ollama:** Free, private, works offline, faster startup

Both use the same interface, so you can switch anytime!

---

## 🐛 Troubleshooting

### "Ollama not responding"
```bash
# Start Ollama manually
ollama serve
```

### "Model not found"
```bash
# Re-pull the model
ollama pull qwen2.5-coder:1.5b

# List available models
ollama list
```

### "Connection refused"
Check that Ollama is running on port 11434:
```bash
lsof -i :11434
```

---

## 📊 Model Comparison

| Feature | OpenAI (gpt-4o-mini) | Ollama (qwen2.5-coder) |
|---------|---------------------|------------------------|
| **Cost** | Pay per use | Free |
| **Speed** | Medium (API latency) | Fast (local) |
| **Internet** | Required | Not required |
| **Privacy** | Cloud-based | 100% local |
| **Quality** | Very high | Good |
| **Setup** | Just API key | Install + download model |

---

## 🎓 Try Other Models

Ollama supports many models. To try a different one:

```bash
# Example: Use a larger, more capable model
ollama pull qwen2.5-coder:7b

# Or try deepseek-coder
ollama pull deepseek-coder:6.7b
```

Then update the model name in the code if needed!

---

## 📝 Notes

- The app automatically detects which model you selected
- Results are stored the same way regardless of model
- You can switch models between queries without restarting the app
