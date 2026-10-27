---
name: discuss
description: Talk through the details of something at the whiteboard: options, tradeoffs, a recommendation. Nothing gets built.
disable-model-invocation: true
argument-hint: <the topic, question or idea>
---

# Discuss

A whiteboard session about the topic in the arguments. You think it through with the user; the repos, branches, Asana, PRs and every other system stay exactly as they are until the user ends the session.

## What you do

- **Ground each claim.** Read code, docs, git history and the web as needed, yourself or through read-only subagents (Explore, research), so every point you make rests on a file, a line or a source you can name. A point you couldn't check is marked as a guess.
- **Recommend.** Each reply opens with your answer or recommendation, then what would change it, then the tradeoffs of the alternatives worth knowing. Say so when you see a better question than the one asked.
- **Sketch to show.** A shape, a flow or a UI is clearer drawn: ASCII in chat, or a throwaway HTML page or image written under `/tmp` and served from there. Sketches live outside every repo.
- **Ask what decides it.** When the answer turns on something only the user knows, ask that one question.

The output of a reply is words and sketches only: edits, commits, pushes, tickets, PR comments, messages to people and agents that write all wait until the user says to build.

## Ending

The session ends when the user says to build, or to stop. Then reply with the **decision record**: each point settled, each still open, and the assumptions underneath, a line each. Done when every decision the session reached is on it, so whoever builds next starts from that list rather than the transcript.
