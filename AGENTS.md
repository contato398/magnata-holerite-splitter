# Protocolo do Codex — Magnata OS

Este arquivo vale para todo o repositório. `CLAUDE.md` é a constituição de
engenharia existente e deve ser lido e obedecido antes de qualquer mudança.
Este arquivo não substitui nem duplica suas regras arquiteturais.

## Início e encerramento de sessão

- Execute o `SESSION_START` definido em
  `docs/magnata-os/central-command/HANDOFF.md` antes de investigar ou alterar o
  repositório.
- Antes de encerrar uma sessão, siga o `SESSION_END` do mesmo HANDOFF.
- Consulte a Central Command progressivamente: comece por `HANDOFF.md`,
  `ESTADO.json` e `INDEX.md`; abra documentos adicionais somente quando a
  tarefa exigir.

## Localização e escopo

- Para localizar estrutura, módulos, símbolos e dependências, consulte primeiro
  o snapshot do Graphify em
  `docs/magnata-os/central-command/ARQUITETURA_SNAPSHOT.json`; depois leia apenas
  os arquivos específicos necessários. Não explore o repositório inteiro sem
  uma justificativa concreta.
- Trabalhe no menor escopo capaz de cumprir o objetivo. Não inclua correções,
  refatorações ou documentação adjacentes sem autorização.
- Preserve alterações e arquivos preexistentes que estejam fora do escopo.

## Gates e entrega

- Não faça merge, deploy nem qualquer acesso ou escrita em produção sem
  autorização humana explícita e específica. Respeite também todos os demais
  gates de Git e de sistemas externos definidos em `CLAUDE.md`.
- Execute os testes e gates proporcionais à mudança e não declare sucesso sem
  evidência.
- Encerre com relatório curto: resultado, validações executadas, riscos ou
  divergências e próxima ação recomendada.
- Divergências entre documentação, código e estado real devem ser reportadas e
  registradas quando pertinente; nunca as resolva silenciosamente.
