"""Model backends. Each talks to an OpenAI-compatible server (vLLM) and returns None when it is not configured
or not reachable, so the caller falls back to the CPU path instead of failing."""
