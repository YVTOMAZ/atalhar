# Seguranca

## Reportar vulnerabilidade

Abra uma issue privada ou envie e-mail ao mantenedor. Nao publique detalhes publicamente antes da correcao.

## Principios

- Nenhum segredo em codigo, logs, exemplos ou fixtures.
- `.env.example` contem apenas placeholders.
- O livro-caixa nunca grava conteudo de pagina, prompt ou resposta.
- URLs sao armazenadas sem query string e sem credenciais.
- A `nota` tem no maximo 200 caracteres e passa por filtro de padroes de segredo.
- Nenhuma telemetria e enviada para servicos externos.
- Nao contornar bloqueios, CAPTCHA ou autenticacao. Respeitar `robots.txt` e termos de uso.