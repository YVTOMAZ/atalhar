# Concorrência do `atalhar route` — plano de modelos por fase

Revalidação executada em **20/11/2026 22:22 BRT** (America/Sao_Paulo, UTC-3), sobre a tabela da seção 3 da especificação do marco `route`. Estrelas dos repositórios GitHub foram conferidas via API pública no mesmo horário; serviços/sites não hospedados no GitHub mantêm o link original.

## 1. Roteadores (escolhem um modelo por pedido, em geral na rota da API)

| Ferramenta | O que faz | Limite frente a este marco |
|---|---|---|
| RouteLLM (LMSYS, ICLR 2025), **5.722** estrelas | Classificador forte vs. fraco por prompt, limiar de custo/qualidade. | https://github.com/lm-sys/RouteLLM — não conhece fase do fluxo de dev, inventário da máquina nem cota semanal; é biblioteca na rota do pedido. |
| Not Diamond | Seletor hospedado por consulta (qualidade, custo ou latência). | Serviço comercial, não é local-first. |
| OpenRouter Auto / Auto Code | Classifica o pedido e escolhe modelo + esforço; Auto Code é para agentes de código. Só modelos hospedados. | https://openrouter.ai/docs/guides/routing/routers/auto-router |
| LiteLLM Auto Router | Faixas SIMPLE/MEDIUM/COMPLEX/REASONING no *gateway*. | https://docs.litellm.ai/docs/auto_router/ — precisa estar no caminho do request. |
| Cursor Router (Auto: Cost/Balance/Intelligence) | Classificador por tipo e complexidade. O usuário não escolhe o modelo; o pool é da Cursor; não usa modelo local. | https://cursor.com/docs/cursor-router |
| musistudio/claude-code-router, **38.274** estrelas | Gateway local com slots `default` / `think` / `background`, inclusive Ollama. | https://github.com/musistudio/claude-code-router — você preenche os slots; ele não recomenda a partir de hardware + cota + fase. |
| Aider architect/editor | Dois modelos (planeja / aplica edição), só no Aider. | https://aider.chat/docs/usage/modes.html |
| OpenCode agents (`plan`, `build`, subagentes) | Cada agente pode ter um `model` configurado manualmente. | https://opencode.ai/docs/agents/ |
| Martian Gateway | Roteador comercial OpenAI-compatível. | https://docs.withmartian.com/gateway |
| Rayline, Tokenless (YC S26), role-model, Wayfinder | Gateways/protocolos recentes (HN 2026) para trocar de modelo ou ir on-device. | https://news.ycombinator.com/item?id=48448372 , https://news.ycombinator.com/item?id=49099143 , https://news.ycombinator.com/item?id=48706181 , https://news.ycombinator.com/item?id=48704373 |

## 2. Recomendadores por hardware (o que a máquina consegue rodar)

| Ferramenta | O que faz | Limite frente a este marco |
|---|---|---|
| **llmfit** (AlexsJones), **39.155** estrelas | Detecta CPU/RAM/GPU/VRAM e recomenda modelos que cabem, com quantização, *fit* e `--use-case coding\|reasoning\|chat`. Tem skill e overrides para simular outro hardware (`--memory`, `--ram`). | https://github.com/AlexsJones/llmfit — não monta um plano por fase do fluxo de dev, não mistura local com pago, não fala de cota semanal, não gera checagem da saída nem guia de prompt por fase, não emite trecho para Claude Code/Codex/OpenCode/Cursor. É o melhor detector/recomendador de hardware encontrado; o atalhar deve reutilizar, não competir. |
| Can I Run This LLM + Build Advisor | Site: o que cabe no hardware; o advisor inverte ("qual hardware comprar para rodar o modelo X"). | https://canirunthisllm.com/ e https://canirunthisllm.com/build-advisor/ — não é CLI no fluxo do agente e não recomenda por fase. |
| LM Studio | Indicador de compatibilidade na loja de modelos; `lms load --estimate-only`. | https://lmstudio.ai/docs/cli/local-models/load e https://lmstudio.ai/docs/app/system-requirements — preso ao app. |
| Ollama (**187.764** estrelas em `ollama/ollama`) | `ollama list` / `ps` / `show`; ajusta contexto padrão conforme a VRAM. Não recomenda o que baixar por fase. | https://ollama.com/library ; comportamento de contexto descrito na documentação da comunidade e no próprio runtime. |
| ollama-gpu-calculator, 74 estrelas | Calculadora web de VRAM/KV cache para tags do Ollama. | https://github.com/aleibovici/ollama-gpu-calculator |

## 3. Diferencial concreto (só isto justifica o go)

Nenhuma das ferramentas acima, **sozinha**, entrega: (1) recomendação por fase do fluxo (plano / execução / revisão / simples), (2) local-first a partir do hardware e do que já está instalado, intercalando com modelo pago só onde a fase pede, (3) ciente da cota semanal e da tabela `precos.toml` já existente, (4) roadmap de upgrade ("se no futuro tiver hardware Y, use Z nesta fase"), (5) plano de checagem da saída local (teste, segunda opinião barata, critério de aceite), (6) guia de prompts curtos para modelo local por fase, (7) trechos de config para mais de um agente, (8) a regra de ouro do atalhar: perguntar antes de gravar qualquer coisa.

O que não é diferencial — e está proibido reinventar:

- Calculadora de VRAM / catálogo enorme de Hugging Face (já é o llmfit / canirunthisllm / LM Studio).
- Proxy na rota do pedido (já é CCR, LiteLLM, OpenRouter, Rayline).
- Detecção de repetição, scaffold de script, paridade de raspagem (já é o atalhar atual).

Regra de ouro deste marco, igual à do atalhar: primeiro usar a ferramenta que já existe (llmfit para caber-ou-não, Ollama para o inventário, `estimate` para a conta). Só implementar um fallback mínimo quando a ferramenta não estiver instalada.

## 4. Conclusão (T0)

**go** — nenhuma ferramenta sozinha cobre os 8 itens da seção 3, e a revalidação de 20/11/2026 manteve as estrelas e o posicionamento dos concorrentes chave (RouteLLM 5.722, claude-code-router 38.274, llmfit 39.155). Projetos recentes de roteamento por fase (ex.: gateways e clientes de chat) seguem sendo roteadores na rota do pedido ou clientes, não um comando de CLI que produz um plano por fase a partir do hardware + inventário + cota, com checagem e prompts, pedindo confirmação antes de gravar config. Logo, o `atalhar route` se justifica como cola entre dois mundos que não se conversam, reutilizando llmfit/CCR/Ollama e `estimate`/`precos`, sem reescrevê-los.

Aviso: recomendação, não medição. Nenhum arquivo da T5 foi alterado nesta missão.