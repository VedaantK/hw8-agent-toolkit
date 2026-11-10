# Iteration

<!-- Written by you. Pick ONE failure. Fill every [bracket]; delete comments when done.
     Candidates: (a) v1 SQLite server: stale data, only players A–D, "smith" matched "Nesmith"
                 (b) v2 "last 10" mixed in last season's/playoff games (Murray, Flagg in Run 1) -->

## Before

The project pulled, and used wrong data when I asked it to pull it. 

## What went wrong

The newest game it knew about was from April 2026, so it couldn't answer anything about this season.
It only had players whose names start with A–D. Ask about anyone else and it found no match.

## Diagnosis

The Project 3 backfill fell back to an alphabetical player list and stopped partway, which is why only A–D got loaded.
The database also hadn't been refreshed since last season.


## The change

mcp/nba_history_server.py, now pulls live data from ESPN's public API
Name matching now uses ESPN's own player search plus word-start matching

## Rerun

Now when I asked it for picks in this chat it worked well (transcripts/2026-11-09_d12263c7.md)

**Did it fix it?** 

Yes
