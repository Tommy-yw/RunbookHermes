# RunbookHermes MemoryProvider

`runbook_hermes` is the Hermes-native bridge for RunbookHermes domain memory.

It exposes RunbookHermes service profiles, incident summaries, fault patterns,
governance rules, team runbook habits and skill indexes through the official
Hermes `MemoryProvider` lifecycle while keeping production incident knowledge in
a RunbookHermes namespace.

Enable it in the RunbookHermes profile:

```yaml
memory:
  provider: runbook_hermes
```

The provider contributes system prompt guidance, per-turn recall, safe domain
memory tools, chat/Feishu routing and official Hermes Skills publishing.
