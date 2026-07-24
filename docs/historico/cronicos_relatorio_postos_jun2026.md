---
name: cronicos_relatorio_postos_jun2026
description: 14 colaboradores crônicos (Batida Ímpar) de Junho/2026 agrupados por posto — 4 postos concentram 2-3 cada
metadata: 
  node_type: memory
  type: project
  originSessionId: c4f52740-3116-4b22-a0f6-9006fb43317c
---

Relatório entregue em 24/06/2026 (sem gravar nada no Airtable, só leitura de
`junho_alertas.json` + cruzamento com Airtable Funcionários). Ver [[v2_49_secullum_ponto]].

## Achado central
Dos 687 alertas de Junho (dry_run), 14 colaboradores = 403 alertas (58,7% do total;
75,4% se olhar só o tipo Batida Ímpar). Padrão: registram só 1 batida por turno
(não é esquecimento isolado, é estrutural).

## Postos com múltiplos crônicos (problema de posto, não só do indivíduo)
- **LAGO DOS IPÊS** — Ismael do Espirito Santo, Carlos Eduardo Tavares Rodrigues Jr,
  Denilson Felipe Rodrigues da Cruz → 85 pendências
- **MORADAS DO SOL** — Lucidio Nunes dos Santos, Luiz Fernando Rocha Camargo,
  Andre Luiz de Moraes Pereira Ribeiro → 85 pendências
- **QUINTA DAS PALMEIRAS** — Pedro Kempoviki Junior, Matheus Augusto Muza Medeiros → 51
- **CASTROLANDA** — Raphael Antonio Pedroso Marino, Laercio de Proenca → 50

## Postos com 1 crônico (mais provável caso individual)
ECOLE INDÚSTRIA E COMÉRCIO (Jose Antonio Generoso Neto — confirmado pelo usuário:
não sabe usar o Ponto Web + internet ruim no local), HOSPITAL REGIONAL ITAPETININGA
(Victor Henrique), UNIMED - VIRGÍLIO (Teodolino), MENEGAZO (Jose Francisco).

## Status / próximo passo (retomar quando o usuário voltar)
Usuário pausou a sessão em 24/06/2026 antes de decidir a estratégia de agregação/
supressão para tirar o dry_run. Nada implementado ainda no código a partir deste
relatório — esperar decisão explícita antes de alterar `secullum_ponto.py`.
