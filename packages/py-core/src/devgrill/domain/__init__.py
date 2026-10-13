"""Pure domain model. Must not import FastAPI, SQLAlchemy, Docker, Temporal or OpenAI.

- `enums`: closed vocabularies shared with the database and the API
- `attempt`: the attempt lifecycle (allowed transitions, live states)
- `glicko2`: player and scenario ratings
- `scoring`: verify probes and the score an attempt earns
- `streaks`: streaks derived from activity days
"""
