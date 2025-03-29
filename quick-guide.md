# Ollama Teacher - Quick Start Guide

## What is Ollama Teacher?

Ollama Teacher is a Discord bot that uses Ollama's local language models to help users learn about AI, machine learning, and programming. It processes ArXiv papers, searches the web, explains documentation, and stores information for future retrieval.

## Commands Reference

Always mention the bot: `@Ollama Teacher command`

| Command | Function | Example |
|---------|----------|---------|
| `!help` | Show help | `@Ollama Teacher !help` |
| `!reset` | Clear context | `@Ollama Teacher !reset` |
| `!arxiv <id> <question>` | Analyze papers | `@Ollama Teacher !arxiv 1706.03762 What is self-attention?` |
| `!ddg <search> <question>` | Web search | `@Ollama Teacher !ddg "ollama api" How do I use it?` |
| `!crawl <url> <question>` | Analyze websites | `@Ollama Teacher !crawl https://pypi.org/project/ollama/ How do I use this?` |
| `!pandas <query>` | Query stored data | `@Ollama Teacher !pandas Show recent searches` |
| `!learn` | Get resources | `@Ollama Teacher !learn` |

## Features at a Glance

- 📚 **Research Helper**: Summarizes and explains ArXiv papers
- 🔍 **Smart Search**: AI-enhanced web search results
- 🌐 **Doc Explorer**: Crawls and explains documentation
- 💾 **Memory**: Stores all interactions for future reference
- 🧠 **Data Analysis**: Query past information using natural language
- 📝 **Code Helper**: Analyzes code attachments and provides examples

## Data Storage

All interactions are stored locally in the `data` directory using Parquet files:
- `data/papers/`: ArXiv paper analyses
- `data/searches/`: Web search results
- `data/crawls/`: Website content

Query this data anytime with the `!pandas` command.
