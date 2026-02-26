# LifePilot

LifePilot is a Telegram bot designed to serve as a personal assistant, featuring a tiered memory system and an LLM provider abstraction, connecting through an MCP gateway.

## Why I Created This Project

I built LifePilot to solve a recurring frustration I had with general-purpose LLMs: they simply aren't specialized for the distinct facets of daily life. I often found myself spending valuable time few-shot prompting and context-loading an AI just to tackle a specific problem. 

Moreover, keeping track of different chat sessions is cumbersome, and seamlessly interacting with them on the go via mobile is difficult. Existing tool (such as OpenClaw) are often too heavyweight and require significant effort to set up for simple, everyday use. LifePilot is designed to be a lightweight, accessible, and continuously context-aware assistant, right inside Telegram.

## Getting Started

1. Execute `./setup.sh` to set up your environment (if you are running locally without Docker).
2. Run `./start.sh` to start the bot.

## Running the Bot

### Using Docker (Recommended)

You can run the application seamlessly using Docker Compose:

```bash
docker-compose up -d
```

### Running Locally

To run the application locally without Docker, use the following:

```bash
./start.sh
```

## Project Structure

- `src/` - Contains the main source code for the LifePilot bot (agents, Telegram handlers, memory layer, LLM providers).
- `skills/` - Domain-specific skill guides (`.md` files) that teach each agent how to handle queries, when to use web search, which sources to trust, and how to format responses for Telegram.
- `config/` - Configuration files for the project.
- `data/` - Directory for storing local data (like SQLite databases/logs, if applicable).
- `setup.sh` - Development setup script.
- `start.sh` - Application execution script.

## Acknowledgments

Some features in this project, such as the agent skill system (domain-specific `.md` guides loaded at runtime to steer agent behavior), are inspired by [nanobot](https://github.com/HKUDS/nanobot).
