# agent_society_experiment_v1
Agents building a society

## Quick start
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...     # omit to use the offline mock
python run.py --rounds 3         # or: python run.py --mock
```
Six agents (Ada/Leader, Brix/Builder, Cleo/Explorer, Dov/Trader, Eli/Skeptic, and Fenn/Mediator, who runs on `claude-opus-5-5`) are spawned
with different roles, goals, skills and Big-Five personality traits (`society/society.py`).
Each round every agent speaks publicly or privately to one other; transcripts go to `society_log.json`.
Pass `--agents my.json` to define your own agents.
