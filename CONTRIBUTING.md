# Contribuir

## Fluxo

1. Crie uma branch a partir de `main`.
2. Faca mudancas pequenas e focadas.
3. Rode `python -m pytest -q`.
4. Abra PR com `gh pr create`.
5. Aguarde checks verdes e faca merge com squash.

## Regras

- Zero dependencias de runtime (apenas biblioteca padrao).
- Testes com dados sinteticos; sem rede externa nos testes.
- Nenhum dado pessoal, segredo ou log real no repositorio.
- Codigo deterministico: mesma entrada, mesma saida, listas ordenadas.