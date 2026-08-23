"""
Nucleo minimo executavel do Grande Orquestrador do Magnata OS.

Ver docs/magnata-os/central-command/ARQUITETURA_EVENTOS.md e
MATRIZ_AUTONOMIA.md para o desenho que este pacote implementa.

Escopo desta primeira versao, deliberadamente pequeno: coordena o que
ja existe (scripts/ci/central_command_sensor.py) em vez de reimplementar
deteccao de estado. Uma unica Acao Nivel 4 real -- atualizar AUTO_FACT
(ESTADO.json) -- e o resto do motor (state machine, idempotencia,
retry, politica de autonomia, audit log) e generico e reusavel para a
proxima Acao que precisar dele.

Nada aqui toca app.py, producao, Airtable ou qualquer HUMAN_DECISION --
essa e uma regra de codigo (motor.py: CAMINHOS_PROIBIDOS), nao so de
documentacao.
"""
