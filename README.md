# HW8 Agent Toolkit

<!-- Fill in every [bracket]. Delete these comments when done. Write it in your own words. -->

This repo has two things, one is a skill that helps me ensure that every part of a project I have to do is fullfilled or is accounted for. The second pulls data from ESPN, and creates a small server that gets a player's recent game log against a betting line available as a tool any agent can use.

## The skill: `rubric-check`

**What it does:** I can give claude a PDF or a link to a project of some kind and it can pull out the reuiqrments and also classify them as if they are met or not met yet. 

**The friction behind it:** Often times since there are a lot of different things that go into project that are spread out over multiple files it is hard to track if everything that needs to be there is finished. I found myself sometimes missing one or two items that were asked for, and ended up missing me points. I can also use the project to help me plan certain project by asking if my idea fits everything the project is looking for. 

> At the end of my Project 2, wich asked for the most things. "would it meet all the requirements of the project"

> For homework 4, after I suggested the idea of a chat-bot I asked " Does this project fits these requirements [link to assignment]"

## The MCP tool: `nba-history` → `player_history`

**What it does:** It gets data from ESPN, and then looks up the player id and the game log to see how the player does against its betting line. 

**The friction behind it:** Before, it would either get things from its memory or look things up which would take a long time. By making it this way it gets the data needed quickly and correctly. 

> Before the season started I tried to pull data from the previous season to test the accuracy that the model had, but it did not work, and it was not able to give me all the information I wanted. 

## Install

<!-- Exact commands. Paths with /Users/vedaant are machine-specific; mark them. -->

**Skill:**
```
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/rubric-check" ~/.claude/skills/rubric-check
```

**MCP server:**
```
python3 -m venv .venv
.venv/bin/pip install -r mcp/requirements.txt
claude mcp add --scope user nba-history -- <ABSOLUTE PATH>/.venv/bin/python <ABSOLUTE PATH>/mcp/nba_history_server.py
claude mcp list   # should show: nba-history ✔ Connected
```


## Tools confirmed

-  I tested it with Claude Opus and Claude Haiku, it worked with both.

## Borrowed material

- I used https://github.com/Left-Coast-Tech/espn-mcp to get the data but I wrote my own MCP for my purpouse. 

## AI-use note

I used AI to write all the code, but I did the demonstrations and wrote the Read-Me myself. 

## Repo layout

- `skills/rubric-check/SKILL.md`: [one line]
- `skills/skill-canary/SKILL.md`: [one line]
- `mcp/nba_history_server.py`: [one line]
- `mcp/v1_sqlite_nba_history_server.py`: [one line]
- `.claude/hooks/log_session.py`: [one line]
- `transcripts/`, `prompt_log.md`: [one line]
