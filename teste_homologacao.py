#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
teste_homologacao.py — Disparo de 1 (UM) registro de teste do pacote
HOLERITE_FOLHA_PONTO, para validar no celular, ANTES de rodar os 102/103
disparos reais, a correção feita em app.py nesta Macro:

  1. WhatsApp agora manda os 2 PDFs de verdade (Holerite + Folha de Ponto),
     não só texto com link.
  2. O link de assinatura mostra os 2 PDFs embutidos na página (PDF.js,
     com fallback pra iframe) e o botão "Confirmar e Assinar" começa
     DESABILITADO até você visualizar os 2 documentos.
  3. Depois de assinar, a tela de sucesso mostra um botão "Baixar PDF
     Combinado Carimbado".

NÃO RODA SOZINHO: precisa que você preencha as 4 variáveis abaixo e
defina a variável de ambiente MAGNATA_API_KEY (mesma EMAIL_WEBHOOK_KEY
do Render — nunca cole a chave direto no arquivo).

IMPORTANTE — o que usar como "funcionário de teste":
  A API não aceita um número de WhatsApp avulso; ela sempre manda pro
  WhatsApp cadastrado no registro do Funcionário. Duas opções:

  (a) Recomendado — criar 1 registro novo na tabela "Funcionários" do
      Airtable, com Nome = "TESTE HOMOLOGACAO", Status = Ativo, WhatsApp
      = o SEU número (o que você vai testar no celular). Isso evita
      qualquer risco de mexer em dado de colaborador real.
  (b) Alternativa — usar um funcionário real que já concordou em ser o
      piloto do teste, sabendo que ele vai receber esse disparo de novo.

  ARQUIVO_HOLERITE_RECORD_ID / ARQUIVO_FOLHA_PONTO_RECORD_ID: 2 registros
  já existentes na tabela "Arquivos" (qualquer PDF real serve — é só pra
  testar a entrega/visualização, o conteúdo em si não importa pro teste).

Uso:
  $env:MAGNATA_API_KEY = (cole aqui, entre aspas, a EMAIL_WEBHOOK_KEY do Render)     [PowerShell]
  python teste_homologacao.py
"""
import os
import sys
import json
import urllib.request
import urllib.error

# ── PREENCHA ANTES DE RODAR ────────────────────────────────────────────
FUNCIONARIO_ID = "recXXXXXXXXXXXXXX"              # <- Funcionário de teste (ver docstring)
ARQUIVO_HOLERITE_RECORD_ID = "recXXXXXXXXXXXXXX"  # <- Arquivos: qualquer Holerite real
ARQUIVO_FOLHA_PONTO_RECORD_ID = "recXXXXXXXXXXXXXX"  # <- Arquivos: qualquer Folha de Ponto real
BASE_URL = "https://magnata-holerite-splitter.onrender.com/assinatura/gerar"
# ────────────────────────────────────────────────────────────────────────

PLACEHOLDER = "recXXXXXXXXXXXXXX"


def main():
    api_key = os.environ.get("MAGNATA_API_KEY", "").strip()
    if not api_key:
        print("ERRO: defina a variável de ambiente MAGNATA_API_KEY antes de rodar.")
        print('  PowerShell: $env:MAGNATA_API_KEY = (cole aqui, entre aspas, a EMAIL_WEBHOOK_KEY do Render)')
        sys.exit(1)

    if PLACEHOLDER in (FUNCIONARIO_ID, ARQUIVO_HOLERITE_RECORD_ID, ARQUIVO_FOLHA_PONTO_RECORD_ID):
        print("ERRO: edite este arquivo e preencha FUNCIONARIO_ID, ARQUIVO_HOLERITE_RECORD_ID")
        print("e ARQUIVO_FOLHA_PONTO_RECORD_ID com IDs reais antes de rodar (ver docstring).")
        sys.exit(1)

    payload = {
        "funcionario_id": FUNCIONARIO_ID,
        "tipo_documento": "HOLERITE_FOLHA_PONTO",
        "arquivo_holerite_record_id": ARQUIVO_HOLERITE_RECORD_ID,
        "arquivo_folha_ponto_record_id": ARQUIVO_FOLHA_PONTO_RECORD_ID,
        "mensagem_extra": "[TESTE DE HOMOLOGAÇÃO — ignore se não for você quem está testando.]",
        "disparar_whatsapp": True,
        "dry_run": False,
    }

    print(f"Disparando 1 registro de teste para {FUNCIONARIO_ID}...")
    req = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"X-API-KEY": api_key, "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            print(f"HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} — resposta do servidor:")
        print(body_text)
        sys.exit(1)
    except Exception as exc:
        print(f"Falha de conexão: {exc}")
        sys.exit(1)

    print(json.dumps(body, indent=2, ensure_ascii=False))

    link = body.get("link")
    if link:
        print("\n" + "=" * 70)
        print("PRÓXIMO PASSO — no celular do número de teste:")
        print("1. Confira se chegaram 2 PDFs no WhatsApp (Holerite + Folha de Ponto),")
        print("   além da mensagem de texto com o link.")
        print(f"2. Abra o link:\n   {link}")
        print("3. Confirme que os 2 documentos aparecem embutidos na página e que o")
        print('   botão "Confirmar e Assinar" só libera depois de você rolar/ver os 2.')
        print("4. Assine com os 4 últimos dígitos do CPF do funcionário de teste e")
        print('   confira se aparece o botão "Baixar PDF Combinado Carimbado".')
        print("=" * 70)
    else:
        print("\nAVISO: resposta não trouxe 'link' — confira o corpo acima "
              "(pode ser duplicado/idempotência ou erro de validação).")


if __name__ == "__main__":
    main()
