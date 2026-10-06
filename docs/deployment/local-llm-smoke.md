# Local LLM smoke check

Use this only after the LangGraph Shadow runtime is configured with the local
OpenAI-compatible provider.

The check is opt-in and performs one synthetic provider request. It does not
execute SQL against DuckLake, does not use benchmark data, and does not print
the endpoint, credential, prompt body, or raw provider response.

Run inside the LangGraph runtime environment:

```bash
python scripts/check_local_llm_runtime.py
```

Expected before network smoke:

```text
GO: local LLM runtime configuration is complete.
```

Then explicitly enable one synthetic provider call:

```bash
LOCAL_LLM_SMOKE_ENABLED=true python scripts/smoke_local_llm_provider.py
```

Expected:

```text
GO: local LLM provider smoke succeeded.
provider_key=infodive_local
model_key=sql-infodive
config_version=sql-infodive-demo-v1
...
response_contract=select_1
```

The smoke requires the provider to answer the synthetic instruction with a
single read-only `SELECT 1`. A failure does not trigger fallback and does not
change the OFFICIAL n8n flow.


## Private VPN HTTP endpoint

If the local provider is reachable only through a private VPN address using
plain HTTP, keep the exception explicit:

```text
OPENAI_COMPATIBLE_SQL_ALLOW_PRIVATE_HTTP=true
```

The runtime accepts this only when the configured base URL uses a literal
private, loopback, or link-local IP address. Public IPs and HTTP hostnames remain
rejected. HTTPS does not require this flag.

Keep the flag `false` when the provider is available over HTTPS.
