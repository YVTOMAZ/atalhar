# atalhar
A IA para de repetir o caminho caro: detecta tarefas repetidas, pergunta a voce e troca por ferramenta, script ou API que custa menos token, com teste e economia medida.

## Detectar repeticoes

`atalhar detect` le o livro-caixa local e lista impressoes digitais com N ou mais ocorrencias em J dias e custo medio acima de um minimo (em tokens). Somente leitura: nao cria nem altera o banco.

```bash
atalhar detect --min-ocorrencias 3 --dias 14 --json
```

Saida (exemplo sintetico):

```
impressao     tipo        alvo                  n  dias  tokens/exec   total
a1b2c3d4e5f6  consultar   https://api/x/items   3     1         15.0      45
```

## Inventario de hardware

`atalhar route inventariar` le um inventario declarativo (ou sonda a maquina) e mostra RAM/VRAM/CPU/GPU e modelos instalados.

```bash
atalhar route inventariar --inventario inventario.example.toml --json
```

## Verificar antes de gastar

`atalhar check <alvo>` percorre a escada "existe caminho mais barato?" (ferramenta existente -> dado estruturado -> robots.txt -> gerar script -> IA) e para no primeiro degrau que resolve. Nunca contorna bloqueio.

```bash
atalhar check https://exemplo.test/produtos --json
```

Degraus: `ferramenta`, `dado_estruturado`, `gerar_script`, `ia`. O `check` nao escreve no livro-caixa.

## Perguntar antes de criar

`atalhar propose` transforma um candidato repetido (do `detect`/`estimate`) e, se houver, o resultado do `check` em uma proposta em portugues (modelo 5.3) com vantagem estimada e origem dos numeros. `atalhar decide <id> sim|nao|depois|nunca` grava a resposta do usuario. Sem "sim", nada e criado. O agente nunca decide por voce.

```bash
atalhar propose --stdin --tokens-atalho 150 --tokens-criacao 4000 --json < candidato.json
atalhar decide p-3f9a1c2b7d4e sim --json
```

Exemplo de texto (modelo 5.3, sem emojis):

```
Percebi que repeti esta acao 5 vezes em 14 dias: consultar em api.exemplo.test.
Cada vez a IA gasta cerca de 1240 tokens.
Caminho mais barato: script novo.
Economia estimada: ~12345 tokens por semana (cenarios de quebra: 0%: 12345, 10%: 11000).
Custo unico para criar: ~4000 tokens. Retorno em ~4 execucoes.
Riscos: o site pode mudar; robots.txt: permitido; vou comparar com 3 resultados que a IA ja entregou.
Posso seguir? (sim / nao / depois / nunca para este alvo)
```

Decisoes: `sim` (aprova, proximo passo `atalhar scaffold <id>`), `nao` (bloqueia 30 dias), `depois` (repropoe apos 7 dias), `nunca` (bloqueia o alvo para sempre, revogavel com `--revogar-nunca`). `pode_criar(id)` e True apenas com `sim`. A lista `nunca` e por alvo sanitizado. Nenhuma rede e nenhum arquivo alem do `atalhar.db` e criado.
