# Changelog

Todas as mudancas notaveis deste projeto serao documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Unreleased]

### Added
- Esqueleto inicial do pacote `atalhar` (CLI, livro-caixa SQLite, impressao digital, adaptador OpenCode).
- `atalhar detect`: lista tarefas repetidas e caras do livro-caixa (somente leitura), com `docs/calibracao.md`.
- `atalhar estimate`: estimativa de economia em tokens (cenarios de quebra, retorno, dinheiro opcional via `precos.toml`) e `precos.example.toml`.
### Fixed
- Saida de texto do `estimate` exibe percentual do cenario corretamente (10%, 30%) e tokens inteiros.
- `estimate` retorna codigo 2 quando `--precos` aponta para arquivo invalido ou modelo inexistente.
