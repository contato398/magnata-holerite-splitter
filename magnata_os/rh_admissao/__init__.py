"""RH / Admissão-Demissão — capacidade transversal (não módulo paralelo).

Reaproveita o mesmo desenho da distribuição documental: o domínio produz
uma INTENÇÃO (cadastrar/desligar), o Orquestrador autoriza, e um adapter
duck-typed executa contra o sistema externo -- aqui, o PontoWeb (Secullum),
via `src/services/secullum_ponto.py` já existente (nunca reimplementado).

Ver `docs/decisoes/escopo-rh-admissao-demissao-pontoweb-v1.md` para o
escopo completo e o gate de produção.
"""
