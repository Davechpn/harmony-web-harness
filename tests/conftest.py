import os

# Set dummy provider keys so Agent.from_file() can construct providers during
# tests. TestModel overrides the actual model at run time so no real API calls
# are made.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")
