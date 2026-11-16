# Calibração dos parâmetros do `atalhar detect`

Os valores padrão `N=3` ocorrências em `J=14` dias são **provisórios** (hipóteses da especificação do MVP). Este documento descreve como calibrá-los com dados próprios, sem expor nada sensível.

## Como calibrar

1. Aponte `ATALHAR_HOME` para uma pasta temporária **fora do repositório**:
   ```bash
   export ATALHAR_HOME="$(mktemp -d)"
   ```
2. Importe seus próprios `*.events.jsonl` (OpenCode) com `atalhar import opencode <arquivo>`.
3. Rode uma grade de parâmetros e capture a saída JSON:
   ```bash
   for N in 2 3 5; do
     for J in 7 14 30; do
       atalhar detect --min-ocorrencias $N --dias $J --json
     done
   done
   ```
   (Use `--ate` para fixar o fim da janela e tornar a comparação reproduzível.)

## O que registrar

Registre **somente agregados**:

- número de candidatos retornados;
- fração de `custo_total_tokens` coberta pelos candidatos (soma dos `custo_total_tokens` dos candidatos ÷ total de tokens da janela).

**Nunca** registre hosts, comandos, notas, impressões digitais nem qualquer dado da máquina. Se a calibração for executada, preencha apenas os agregados medidos, com a data. Se não for executada, os marcadores `[[MEDIR]]` permanecem.

## Tabela de calibração

| N \ J | 7 dias | 14 dias | 30 dias |
|---|---|---|---|
| 2 | [[MEDIR: candidatos=?, cobertura=?%]] | [[MEDIR: candidatos=?, cobertura=?%]] | [[MEDIR: candidatos=?, cobertura=?%]] |
| 3 | [[MEDIR: candidatos=?, cobertura=?%]] | [[MEDIR: candidatos=?, cobertura=?%]] | [[MEDIR: candidatos=?, cobertura=?%]] |
| 5 | [[MEDIR: candidatos=?, cobertura=?%]] | [[MEDIR: candidatos=?, cobertura=?%]] | [[MEDIR: candidatos=?, cobertura=?%]] |

## Interpretação

- Se com `N=3/J=14` o número de candidatos for zero, isso pode ser resultado legítimo (comandos longos e únicos raramente repetem). Não mascarar baixando `N` para 1.
- Se mais de 5% das linhas reais tiverem `ts` inválido (`ignorados_ts_invalido`), anotar como pendência.
- `N=3/J=14` são padrões provisórios até que a calibração acima seja preenchida.