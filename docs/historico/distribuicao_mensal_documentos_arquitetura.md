---
name: distribuicao-mensal-documentos-arquitetura
description: Diretriz futura de arquitetura do projeto Magnata - Distribuição Mensal de Documentos (fluxo Colaborador/WhatsApp x fluxo Cliente/E-mail)
metadata: 
  node_type: memory
  type: project
  originSessionId: 798af317-f0d2-4a99-9677-e8e8f77ce019
---

Diretriz registrada em 2026-06-14, ainda NÃO implementada. Reformula a visão dos módulos futuros do magnata-holerite-splitter como "Distribuição Mensal de Documentos", com dois fluxos:

1. **Colaborador - WhatsApp** (individual): hoje só Holerite e Folha de Ponto.
2. **Cliente - E-mail** (pacote mensal por cliente/local): Holerites + Folhas de Ponto dos colaboradores daquele local + Extrato da folha, FGTS Digital, guias, boletos, certidões, notas fiscais e outros docs mensais.

Holerite e Folha de Ponto pertencem aos DOIS fluxos (vínculo duplo: vão ao colaborador individualmente E entram no pacote do cliente). Os demais documentos do pacote são "cliente-only" salvo regra futura.

Diretriz geral: automação como regra, manual só por exceção (mesmo princípio já aplicado em [[fase5c_pre_cadastro_funcionarios]]).

**Why:** o usuário quer reaproveitar a árvore de decisão genérica (`decidir_acao_documento`, 5 categorias, app.py v2.18) também para classificar destino dos documentos, não só decidir ação de cadastro.

**How to apply:** ao planejar/implementar qualquer novo handler de documento (Folha de Ponto, FGTS, guias, etc.), considerar SEMPRE dois eixos: (a) categoria genérica de ação (decidir_acao_documento) e (b) destino(s) — `destino_colaborador` (WhatsApp individual) e/ou `destino_cliente` (pacote mensal por e-mail). Holerite/Folha de Ponto = ambos true; demais = só destino_cliente.

Pontos de modelagem levantados (ainda sem implementação):
- Possível campo "Destino(s)" em Arquivos/Processar Arquivos (Colaborador-WhatsApp / Cliente-Email / Ambos).
- Possível nova tabela "Pacotes Mensais" (cliente/local x mês), agregando registros de Arquivos.
- Funcionários precisa de telefone (WhatsApp) acessível; Locais/Clientes precisa de e-mail do contato.
- Pendências/Revisar reaproveitada para: telefone ausente, e-mail ausente, colaborador não identificado, cliente não identificado, documento faltante, baixa confiança.

Ordem de implementação sugerida (após fechar contratos Fase 5C):
1. Modelar schema (campos "destino" + tabela Pacotes Mensais), sem automação.
2. Ligar holerites já existentes ao cliente/local (agrupamento/relatório read-only).
3. Pendências específicas dessa etapa.
4. Envio WhatsApp individual de holerite.
5. Montagem + envio do pacote mensal por cliente (e-mail).
6. Expandir Folha de Ponto pelo mesmo padrão.
7. Demais documentos do pacote cliente (FGTS, guias, boletos, certidões, notas fiscais, extrato), um a um, todos via `decidir_acao_documento`.

Próximo passo seguro recomendado (não feito ainda): endpoint de diagnóstico read-only que classifica holerites já processados em "pronto para WhatsApp" / "pronto para pacote cliente" / "pendência (dado faltante)", sem gravar nada.
