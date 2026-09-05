# Relatório — WhatsApp Composição Otimizada V1

Data: 2026-09-04
Branch: `fix/whatsapp-composicao-otimizada-v1`
PR: #130

## Objetivo

Criar a fundação do Magnata OS para escolher e validar a composição de uma comunicação WhatsApp antes do transporte, reduzindo notificações quando o canal suportar legenda de mídia, sem duplicar o motor legado e sem acessar produção.

## Decisão implementada

A composição passa a ser representada em três etapas independentes de fornecedor:

1. `politica_comunicacao.py`: gera a prévia determinística, deduplica destinatários, exige decisão explícita de assinatura/comprovante e vincula a autorização ao conteúdo e à composição por `preview_id`.
2. `plano_comunicacao.py`: materializa exatamente a prévia autorizada em ações de envio, rejeitando troca posterior de texto e divergência de conteúdos.
3. `transporte_comunicacao.py`: define a porta de transporte e executa o plano sem recompor a campanha. Falha de transporte é fail-fast e preserva evidência das ações já concluídas.

A opção `preferencia="otimizar"` usa o texto como legenda do primeiro vídeo/documento/imagem compatível. `preferencia="separado"` preserva a composição fragmentada escolhida pelo operador. A política informa a alternativa compacta e sinaliza fragmentação com três ou mais notificações por destinatário.

## Invariantes de segurança

- Nenhuma das três camadas conhece Flask, Evolution, Airtable, Render ou credenciais.
- Nenhuma camada realiza I/O por conta própria.
- Um disparo não pode ser materializado sem uma prévia autorizada correspondente.
- Alterar destinatários, texto, itens, assinatura, comprovante ou preferência invalida a autorização anterior.
- O executor valida todo o plano antes da primeira chamada externa e não inicia plano com tipo ainda sem adapter oficial.
- Falha de uma ação interrompe as seguintes e expõe ao caller somente a evidência estruturada das ações já concluídas.

## Compatibilidade com o legado

O transporte oficial atual já tem rotas separadas para texto, vídeo e documento. Esta etapa não altera `app.py`, porque ele é legado protegido e sua constituição exige branch própria. A porta criada nesta etapa foi desenhada para ser ligada a essas rotas sem importar o fornecedor no domínio.

Há uma lacuna objetiva para a composição otimizada de vídeo: a rota pública de vídeo atual não aceita campo de legenda, embora o transporte de documento já tenha suporte interno a `caption`. Portanto, esta V1 entrega integralmente política, plano e porta, mas não ativa a legenda no `app.py` nem em produção.

## Validação

No commit `eb98535c39be9f5228153180c93cfeb6f130bf32`:

- CI de Governança e Qualidade: **success**.
- Suíte principal `pytest`: **success**.
- Job de alocação/autenticação com PostgreSQL efêmero: **success**.

Nenhuma integração real, deploy ou envio WhatsApp foi executado nesta etapa.

## Próxima etapa técnica

Criar branch exclusiva para `app.py` e seus testes, adicionando `legenda` opcional à rota `/whatsapp/enviar-video` e encaminhando-a como `caption` ao `sendMedia` da Evolution. Depois, ligar um adapter da porta `PortaTransporteWhatsapp` ao legado. Essa etapa deve preservar compatibilidade retroativa: chamadas sem `legenda` continuam produzindo o mesmo payload atual.
