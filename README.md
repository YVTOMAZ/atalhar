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
