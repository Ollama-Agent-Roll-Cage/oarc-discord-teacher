# Ollama Teacher Discord Bot

<div align="center">
  <img src="ollamaBotLogo.png" alt="Ollama Bot Logo" width="250"/>
  <br>
  <h3>Bringing AI-powered learning to your Discord server</h3>
</div>

A powerful Discord bot that helps your community learn about AI, Machine Learning, and programming concepts using Ollama's LLM capabilities. The bot features multiple learning modes, including research paper analysis, web searches, documentation crawling, and data analysis, all while storing information locally for quick retrieval later.

## About Ollama Teacher

Ollama Teacher is designed to make advanced AI learning accessible through Discord. Using Ollama's powerful LLMs locally, the bot serves as a dedicated learning assistant that can explain complex topics, analyze papers, search for information, and even understand documentation on the fly.

### How It Works

The bot leverages Ollama's local language models to provide AI-powered responses without sending user data to external services. It maintains conversation context, allowing for natural discussions about technical topics, and can intelligently parse different types of content:

- **ArXiv Papers**: Automatically extracts and summarizes academic papers
- **Web Content**: Crawls websites and documentation pages to understand and explain their content
- **Search Results**: Enhances DuckDuckGo search results with AI explanations
- **Stored Data**: Uses natural language to query previously encountered information

Each interaction is stored locally using efficient Parquet files, creating a growing knowledge base that can be queried later, making the bot smarter and more helpful over time.

## ✨ Features

### 🔍 Multiple Learning Modes

- **ArXiv Research Mode**: Access, summarize, and learn from academic papers on ArXiv
- **Web Search Mode**: Get AI-enhanced explanations from DuckDuckGo search results 
- **Documentation Crawler**: Extract and explain content from websites and documentation
  - *Special handling for PyPI documentation* to provide accurate package information
- **Data Analysis Engine**: Query stored information using natural language

### 🧠 Enhanced Learning Experience

- Context-aware conversations powered by Ollama models
- Markdown-formatted responses with proper code syntax highlighting
- Intelligent code examples and step-by-step explanations
- Persistent memory of previous searches and queries
- File attachment support for analyzing code samples

### 💾 Efficient Data Storage

- Parquet-based local storage for efficiency and performance
- No need for external databases or cloud storage
- Persistent history of searches, papers, and web crawls
- Query previous findings using natural language
- Intelligent data organization by type (searches, papers, crawls)

### 🤖 Discord Integration

- Mention-based command system that doesn't conflict with other bots
- Support for file attachments to share and analyze code
- Long message chunking for comprehensive explanations
- Customizable appearance and behavior
- Automatic restart and recovery with the startup script

## Technical Architecture

Ollama Teacher combines several technologies to provide a seamless learning experience:

- **Discord.py**: Handles Discord integration and message management
- **Ollama API**: Provides access to powerful language models running locally
- **BeautifulSoup**: Extracts and structures content from web pages
- **Pandas & PyArrow**: Manages and queries stored data efficiently
- **aiohttp**: Handles asynchronous network requests

The bot uses a modular architecture with specialized components:
- **ArxivSearcher**: Interfaces with ArXiv's API to fetch academic papers
- **DuckDuckGoSearcher**: Retrieves search results from DuckDuckGo
- **WebCrawler**: Intelligently extracts content from webpages
- **PandasQueryEngine**: Converts natural language to data queries
- **ParquetStorage**: Efficiently stores and manages local data

## 📋 Prerequisites

- Python 3.8 or higher
- Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))
- [Ollama](https://ollama.ai/download) installed and configured on your machine
- Recommended models: llama3.1:8b or faster/smaller models for better response time

## 🛠️ Installation

### Step 1: Get the code
```bash
git clone https://github.com/yourusername/ollama-teacher-bot.git
cd ollama-teacher-bot
```

### Step 2: Set up environment
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure the bot
Create a `.env` file in the project root:
```
# Discord Bot Configuration
DISCORD_TOKEN=your_discord_token_here

# Bot Configuration
OLLAMA_MODEL=llama3.1:8b
TEMPERATURE=0.7
TIMEOUT=120.0

# Storage Configuration
DATA_DIR=data
```

### Step 4: Start the bot
```bash
# Linux/Mac
./startup.sh

# Windows
startup.bat
```

## 🤖 Bot Commands

All commands require mentioning the bot: `@Ollama Teacher command`

| Command | Description | Example |
|---------|-------------|---------|
| `!help` | Display help information | `@Ollama Teacher !help` |
| `!reset` | Reset the conversation context | `@Ollama Teacher !reset` |
| `!arxiv <id> <question>` | Learn from an ArXiv paper | `@Ollama Teacher !arxiv 1706.03762 What is self-attention?` |
| `!ddg <query> <question>` | Search with DuckDuckGo | `@Ollama Teacher !ddg "ollama api" How do I use it?` |
| `!crawl <url> <question>` | Crawl a webpage & learn | `@Ollama Teacher !crawl https://pypi.org/project/ollama/ How do I use the ollama python package?` |
| `!pandas <query>` | Query stored data | `@Ollama Teacher !pandas Show me a summary of my searches` |
| `!learn` | Get default resources | `@Ollama Teacher !learn` |

## Example Use Cases

### Learning Complex Concepts
Ask the bot to explain difficult AI/ML concepts with code examples:
```
@Ollama Teacher What's the difference between CNN and RNN architectures?
```

### Researching Academic Papers
Let the bot summarize and explain research papers from ArXiv:
```
@Ollama Teacher !arxiv 1706.03762 Explain the key innovation in the paper
```

### Understanding Documentation
Have the bot crawl and explain documentation pages:
```
@Ollama Teacher !crawl https://pytorch.org/docs/stable/nn.html What is a Sequential module?
```

### Code Analysis
Attach code files to have the bot analyze and explain them:
```
@Ollama Teacher Can you explain what this code does? [attach file]
```

### Data Analysis
Query previously stored information using natural language:
```
@Ollama Teacher !pandas Which ArXiv papers I've searched contain "transformer" in the title?
```

## 📚 Default Learning Resources

The bot comes pre-configured with links to common AI/ML documentation:

- [Ollama API Docs](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Ollama Python Package](https://pypi.org/project/ollama/)
- [Hugging Face Documentation](https://huggingface.co/docs)
- [Transformers Library](https://huggingface.co/docs/transformers/index)
- And more!

## 🏃‍♂️ Running in Production

For long-term hosting on your local PC:

### Automatic Startup

#### Windows
1. Place `startup.bat` in your startup folder: `shell:startup`
2. Or create a scheduled task to run at login:
   ```
   schtasks /create /tn "Start Ollama Teacher Bot" /tr "path\to\startup.bat" /sc onlogon
   ```

#### Linux
1. Make the startup script executable: `chmod +x startup.sh`
2. Add to your startup applications or create a systemd service

### Performance Considerations

- Choose the appropriate Ollama model size for your hardware
- Adjust `MAX_CONVERSATION_LOG_SIZE` for memory usage
- Monitor disk space usage in the data directory

## 🛠️ Customization

You can modify the bot's behavior by editing these variables in the `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | llama3.1:8b | Ollama model to use |
| `TEMPERATURE` | 0.7 | Response creativity (0.0-1.0) |
| `TIMEOUT` | 120.0 | Max seconds to wait for responses |
| `DATA_DIR` | data | Directory for storing data |

## Advanced Configuration

For more advanced customization, you can modify these parameters in `bot.py`:

- `MAX_CONVERSATION_LOG_SIZE`: Controls how much conversation history is kept (affects memory usage)
- `MAX_TEXT_ATTACHMENT_SIZE`: Maximum size for text file attachments
- `MAX_FILE_SIZE`: Maximum size for any file attachment
- `SYSTEM_PROMPT`: The base instructions that define the bot's personality and capabilities

## 🔍 Troubleshooting

- **Bot not responding**: Make sure Ollama is running (`ollama serve`)
- **Slow responses**: Use a smaller model or increase timeout
- **High memory usage**: Reduce `MAX_CONVERSATION_LOG_SIZE` in the code
- **Storage issues**: Check disk space if you've stored many papers/searches
- **Model loading issues**: Ensure you've pulled the model with `ollama pull model_name`
- **Command not working**: Make sure you're mentioning the bot before every command

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## Recent Updates

- Added special handling for PyPI documentation pages with improved extraction
- Enhanced the Pandas Query Engine for better natural language queries
- Improved error handling and automatic recovery
- Added persistent conversation context
- Updated for compatibility with latest Ollama models
