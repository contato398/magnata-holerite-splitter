"""
Servico de criacao de lote (Modulo 01, Fase 3).

PORTA OFICIAL DE ENTRADA OPERACIONAL a partir desta fase: qualquer
integracao NOVA que precise registrar documentos deve chamar
ServicoCriacaoLote.criar_lote(), nunca ServicoEntradaDocumental
(Fase 1) diretamente -- ver aviso na docstring de
ServicoEntradaDocumental em servico_entrada.py.

Agrupa N arquivos recebidos juntos (mesma origem, mesmo
correlation_id) num LoteDocumental, delega a cada arquivo
individualmente ao ServicoEntradaDocumental (Fase 1, reaproveitado sem
alteracao) e cria o EstadoEsteiraDocumento inicial de cada um via
ServicoAvancoEsteira (Fase 3).

Garantias desta porta:
  - Todo Documento NOVO criado por criar_lote() sempre recebe lote_id
    (nunca None) E EstadoEsteiraDocumento inicial -- as duas coisas
    juntas, nunca uma sem a outra silenciosamente. lote_id vem de
    passar sempre um lote_id real para
    ServicoEntradaDocumental.registrar_entrada() (o unico lugar que
    fabrica lote_id e gerar_lote_id(), dominio_esteira.py).
  - Se o Documento for persistido com sucesso mas a criacao do estado
    inicial da esteira falhar (ex.: RepositorioEstadosEsteira
    indisponivel), o item do resumo e marcado sucesso=False com
    documento_id preenchido e uma mensagem de erro explicita
    (ver _processar_um_arquivo) -- o Documento JA EXISTE e NUNCA fica
    escondido do resumo, mesmo sem estado de esteira. Esse Documento
    fica, na pratica, no mesmo caso de "documento legado" tratado por
    dtos_esteira.montar_item_esteira (rastreado_pela_esteira=False) ate
    que uma nova tentativa (com o mesmo conteudo, via idempotencia por
    hash) crie o estado que faltou.
  - Duplicidade nunca aborta o lote -- um arquivo cujo conteudo ja foi
    registrado antes (neste lote ou em qualquer lote anterior) e
    marcado `duplicado=True` no resumo, sem interromper o processamento
    dos demais arquivos.
  - Erro isolado nunca aborta o lote -- uma excecao ao processar UM
    arquivo (ex.: arquivo vazio, falha de persistencia, falha de
    estado inicial da esteira) e capturada, registrada no item
    correspondente do resumo, e o loop continua para o proximo
    arquivo.

INTEGRACAO SHADOW DE ROTEAMENTO DOCUMENTAL (auditoria read-only prévia,
implementada nesta fase): apos o Documento existir e o estado inicial/avanco
da esteira ja terem sido tratados como hoje, `_processar_um_arquivo` chama
`decidir_roteamento(arquivo.conteudo)` (magnata_os/classificacao/
roteamento_documental.py) reaproveitando OS MESMOS bytes ja em escopo --
nunca uma segunda leitura, nunca reabertura de anexo, nunca recalculo de
hash. O resultado (RoteamentoShadowDTO, dtos_esteira.py) e so OBSERVAVEL
no retorno em memoria (`ItemResumoLote.roteamento_shadow`) -- nada e
persistido, nenhuma etapa da esteira avanca para CLASSIFICACAO nesta fase
(isso fica para uma decisao separada, depois que esta integracao estiver
validada). Falha do roteamento shadow (extracao, classificacao, ou
`pyo3_runtime.PanicException` comprovado neste ambiente por dependencia
nativa quebrada) e SEMPRE isolada no ponto de integracao -- nunca desfaz
o Documento ja persistido nem aborta o lote, mesmo principio ja aplicado
ao erro de estado da esteira acima. O isolamento e CIRURGICO, nao um
`except BaseException` generico: absorve `Exception` normal e o caso
especifico e comprovado de `PanicException`, mas SEMPRE repropaga
qualquer outro BaseException especial (KeyboardInterrupt, SystemExit,
GeneratorExit, cancelamento) -- ver comentario em `_processar_um_arquivo`.
Roda tambem para documento duplicado (mesmo Documento existente, mesmos
bytes, funcao pura) -- mantem diagnostico uniforme sem criar novo
Documento nem alterar a flag `duplicado`.

ServicoEntradaDocumental (Fase 1) continua aceitando lote_id=None para
nao quebrar nenhum chamador existente (scripts internos, testes,
composicao de servicos) -- a garantia de "toda entrada nova tem lote" e
de CONVENCAO a partir desta porta, nao um parametro obrigatorio novo
que quebraria a Fase 1/2 ja mergeadas. Ver "Documentos legados" e
"Entrada oficial por lote" em MAGNATA_OS_DOCUMENTAL_MODULO01_FASE3.md.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence

from magnata_os.classificacao.roteamento_documental import decidir_roteamento

from .dominio_esteira import EtapaEsteira, LoteDocumental, SituacaoEsteira, gerar_correlation_id_lote, gerar_lote_id
from .dtos_esteira import ItemResumoLote, ResumoLote, roteamento_shadow_erro_tecnico, roteamento_shadow_para_dto
from .repositorio_esteira import RepositorioLotes
from .servico_avanco_esteira import ServicoAvancoEsteira
from .servico_entrada import ServicoEntradaDocumental


@dataclasses.dataclass(frozen=True)
class ArquivoEntradaLote:
    """Um arquivo dentro de uma solicitacao de criacao de lote."""

    conteudo: bytes
    nome_original: str
    mime_type: str
    metadados: Optional[dict] = None


def _relogio_padrao() -> datetime:
    return datetime.now(timezone.utc)


class ServicoCriacaoLote:
    """Orquestra a criacao de um LoteDocumental e o registro de cada
    arquivo nele, isolando falha e duplicidade por arquivo."""

    def __init__(
        self,
        repositorio_lotes: RepositorioLotes,
        servico_entrada: ServicoEntradaDocumental,
        servico_avanco_esteira: ServicoAvancoEsteira,
        gerador_lote_id: Callable[[], str] = gerar_lote_id,
        relogio: Callable[[], datetime] = _relogio_padrao,
    ) -> None:
        self._lotes = repositorio_lotes
        self._servico_entrada = servico_entrada
        self._servico_avanco = servico_avanco_esteira
        self._gerar_lote_id = gerador_lote_id
        self._relogio = relogio

    def criar_lote(
        self,
        origem: str,
        arquivos: Sequence[ArquivoEntradaLote],
        correlation_id: Optional[str] = None,
        metadados: Optional[dict] = None,
    ) -> ResumoLote:
        """
        Cria um lote com os arquivos informados. Cada arquivo e
        processado isoladamente: uma falha ou uma duplicidade em um
        arquivo nunca impede o processamento dos demais nem aborta o
        lote como um todo. Retorna um ResumoLote completo, sempre --
        mesmo que todos os arquivos tenham falhado (nesse caso,
        situacao=ERRO).
        """
        correlation_id = correlation_id or gerar_correlation_id_lote()
        agora = self._relogio()
        lote_id = self._gerar_lote_id()

        lote = LoteDocumental(
            lote_id=lote_id,
            origem=origem,
            recebido_em=agora,
            quantidade_arquivos=len(arquivos),
            situacao=SituacaoEsteira.EM_PROCESSAMENTO,
            correlation_id=correlation_id,
            criado_em=agora,
            atualizado_em=agora,
            metadados=metadados or {},
        )
        self._lotes.salvar(lote)

        itens: List[ItemResumoLote] = []
        for arquivo in arquivos:
            itens.append(self._processar_um_arquivo(lote_id, origem, correlation_id, arquivo))

        quantidade_sucesso = sum(1 for i in itens if i.sucesso and not i.duplicado)
        quantidade_duplicados = sum(1 for i in itens if i.sucesso and i.duplicado)
        quantidade_erro = sum(1 for i in itens if not i.sucesso)

        if quantidade_erro == 0:
            situacao_final = SituacaoEsteira.CONCLUIDO
        elif quantidade_erro == len(itens):
            situacao_final = SituacaoEsteira.ERRO
        else:
            situacao_final = SituacaoEsteira.EM_REVISAO  # sucesso parcial -- precisa de olhar humano

        agora_final = self._relogio()
        lote_final = dataclasses.replace(lote, situacao=situacao_final, atualizado_em=agora_final)
        self._lotes.salvar(lote_final)

        return ResumoLote(
            lote_id=lote_id,
            origem=origem,
            correlation_id=correlation_id,
            quantidade_arquivos=len(arquivos),
            quantidade_sucesso=quantidade_sucesso,
            quantidade_duplicados=quantidade_duplicados,
            quantidade_erro=quantidade_erro,
            situacao=situacao_final,
            criado_em=agora,
            itens=tuple(itens),
        )

    def _processar_um_arquivo(
        self, lote_id: str, origem: str, correlation_id: str, arquivo: ArquivoEntradaLote,
    ) -> ItemResumoLote:
        try:
            documento = self._servico_entrada.registrar_entrada(
                arquivo.conteudo, arquivo.nome_original, arquivo.mime_type, origem,
                correlation_id=correlation_id, lote_id=lote_id, metadados=arquivo.metadados,
            )
        except Exception as exc:
            return ItemResumoLote(
                nome_original=arquivo.nome_original, documento_id=None,
                sucesso=False, duplicado=False, erro=str(exc),
            )

        try:
            _estado, criado_agora = self._servico_avanco.criar_estado_inicial(
                documento.documento_id, lote_id, correlation_id,
            )
            if criado_agora:
                # Documento novo na esteira: ServicoEntradaDocumental (Fase 1)
                # ja persistiu o Documento com status REGISTRADO nesta mesma
                # chamada -- a etapa REGISTRO ja esta, de fato, concluida.
                self._servico_avanco.avancar_etapa(
                    documento.documento_id, EtapaEsteira.REGISTRO, correlation_id,
                    situacao_nova_etapa=SituacaoEsteira.CONCLUIDO,
                )
        except Exception as exc:
            # O Documento JA FOI PERSISTIDO com sucesso (linha acima) --
            # essa falha e so no estado da esteira. Nunca escondemos o
            # documento_id aqui: o item de resumo deixa explicito que o
            # Documento existe, mas ficou sem (ou com) estado de esteira
            # incompleto, para que quem consumir o ResumoLote saiba que
            # precisa investigar/reconciliar esse documento_id
            # especificamente -- nao e o mesmo caso de "arquivo nunca
            # virou Documento" (bloco try acima).
            return ItemResumoLote(
                nome_original=arquivo.nome_original, documento_id=documento.documento_id,
                sucesso=False, duplicado=False,
                erro=(
                    f'Documento persistido com sucesso (documento_id={documento.documento_id}), '
                    f'mas falha ao criar/avancar o estado inicial da esteira: {exc}'
                ),
            )

        # Integracao shadow de roteamento documental (ver docstring do
        # modulo). Roda tanto para Documento novo quanto duplicado --
        # nos dois casos `documento` ja existe de verdade e
        # `arquivo.conteudo` sao OS MESMOS bytes ja em escopo, nunca uma
        # segunda leitura. `origem_message_id` e lido defensivamente:
        # nenhuma origem alem de e-mail preenche esta chave, e o
        # resultado shadow continua origem-agnostico.
        origem_message_id = None
        if arquivo.metadados:
            origem_message_id = arquivo.metadados.get('origem_message_id')

        try:
            decisao = decidir_roteamento(arquivo.conteudo)
            roteamento_shadow = roteamento_shadow_para_dto(
                decisao, documento.documento_id, documento.hash_sha256, origem_message_id,
            )
        except Exception:
            # Falha SECUNDARIA normal (extracao, classificacao ou erro
            # tecnico inesperado do roteamento shadow, dentro da
            # hierarquia usual de Exception) -- o Documento e o estado da
            # esteira ja foram tratados com sucesso acima; esta excecao
            # NUNCA desfaz nenhum dos dois nem aborta o lote. Mensagem da
            # excecao nunca exposta (poderia conter fragmento de PDF/PII)
            # -- so o codigo sanitizado fixo MOTIVO_ERRO_TECNICO_SHADOW.
            roteamento_shadow = roteamento_shadow_erro_tecnico(
                documento.documento_id, documento.hash_sha256, origem_message_id,
            )
        except BaseException as exc:
            # Isolamento CIRURGICO, nao generico: so um caso especifico e
            # comprovado de BaseException-fora-de-Exception e absorvido
            # aqui -- pyo3_runtime.PanicException, achado real ao testar
            # esta integracao (dependencia nativa quebrada
            # pdfplumber/cryptography via pyo3, ambiente com
            # `_cffi_backend` ausente; confirmado empiricamente:
            # exc.__class__.__module__ == 'pyo3_runtime' e
            # exc.__class__.__name__ == 'PanicException'). Identificado
            # por nome/modulo, nunca por import de `pyo3_runtime` como
            # dependencia de producao (modulo interno de uma biblioteca
            # terceira, nao uma API publica).
            #
            # Qualquer OUTRO BaseException especial -- KeyboardInterrupt,
            # SystemExit, GeneratorExit, cancelamento de asyncio, ou
            # qualquer excecao desconhecida fora de Exception -- e
            # SEMPRE repropagado, nunca engolido: o principio shadow
            # protege contra falha de classificacao/extracao, nao contra
            # sinal de controle do processo/runtime.
            e_panic_pyo3 = (
                exc.__class__.__module__ == 'pyo3_runtime'
                and exc.__class__.__name__ == 'PanicException'
            )
            if not e_panic_pyo3:
                raise
            roteamento_shadow = roteamento_shadow_erro_tecnico(
                documento.documento_id, documento.hash_sha256, origem_message_id,
            )

        return ItemResumoLote(
            nome_original=arquivo.nome_original, documento_id=documento.documento_id,
            sucesso=True, duplicado=not criado_agora, erro=None,
            roteamento_shadow=roteamento_shadow,
        )
