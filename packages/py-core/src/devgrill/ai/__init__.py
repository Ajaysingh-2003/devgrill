"""The AI layer (ADR 016): prompts, safety, pricing and the features built on the LLM port.

Nothing here talks to OpenAI directly: features call the `LLM` port (`devgrill.ai.port`), which
`devgrill.infra.llm` implements (and tests fake). Feature modules take plain inputs and return
validated results, so they are testable without a network.
"""
