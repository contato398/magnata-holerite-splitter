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

GATE CONTROLADO REGISTRO -> CLASSIFICACAO (politica_classificacao.py):
para Documento NOVO cujo roteamento shadow terminou normalmente (nao
ERRO_TECNICO_SHADOW), a MESMA `DecisaoRoteamentoDocumental` ja calculada
e traduzida por `decidir_transicao_classificacao` e aplicada via
`ServicoAvancoEsteira.aplicar_resultado_classificacao` -- nunca uma
segunda classificacao. CLASSIFICACAO nesta fase significa somente "a
tentativa de classificacao foi realizada e seu resultado operacional foi
registrado na esteira", nunca "processador disponivel"/"documento pronto
para processar". RESOLVIDA avanca com situacao CONCLUIDO mesmo quando a
acao recomendada pelo roteamento ainda e REVISAR_HUMANO por falta de
processador avulso (limitacao da PROXIMA fase, nao da classificacao em
si); AMBIGUA e INVALIDA avancam e ficam BLOQUEADO (motivo estruturado);
NAO_RECONHECIDA avanca com EM_REVISAO (soft-flag, nunca hard-block).
Documento duplicado NUNCA tenta esta transicao de novo (idempotencia
preservada -- reaproveita o estado ja existente do documento original).
O resultado de TENTAR aplicar o gate (promovido/nao aplicavel/falhou
tecnicamente) fica em `ItemResumoLote.resultado_gate_classificacao`
(`ResultadoGateClassificacaoDTO`, dtos_esteira.py) -- distinto de
`ItemResumoLote.sucesso` (que reflete so a ingestao) e distinto de
`roteamento_shadow` (que reflete so o resultado da classificacao).

GATE CONTROLADO CLASSIFICACAO -> IDENTIFICACAO, só Holerite avulso
(politica_identificacao_holerite.py, auditoria read-only prévia): para
Documento NOVO, Holerite, RESOLVIDO, cujo gate de classificação terminou
com sucesso em CLASSIFICACAO/CONCLUIDO (ver critérios completos de
elegibilidade em `_processar_um_arquivo`), o MESMO texto já extraído uma
única vez (`extrair_texto_seguro`, reaproveitado da classificação acima)
é usado para: detectar múltiplos CPFs distintos (sinal de possível PDF
mestre não fatiado -- nunca decidido por contagem de páginas), extrair
nome (fallback) e chamar `resolver_funcionario` (importacao_lote/
dominio.py, função pura já existente, reaproveitada sem alteração) com
uma lista de candidatos obtida de `FonteCandidatosFuncionario` (Protocol
injetável -- `LeitorAirtableSomenteLeitura.listar_funcionarios()` já
satisfaz, nenhum adapter novo). NUNCA usa `processar_holerite`/
`ItemManifestoHolerite`/`ConfiguracaoExecucao` (contratos da Família B,
ZIP/manifesto) nem extrai/valida competência (fora de escopo desta
etapa -- ver auditoria). Resultado traduzido para o contrato neutro já
existente `ResolucaoDimensao` (classificacao/contratos.py, dimensão
COLABORADOR) e aplicado via `ServicoAvancoEsteira.
aplicar_resultado_identificacao`. CPF/nome extraídos são estritamente
transitórios -- nunca em DTO, evento ou log; só a contagem de CPFs
distintos (nunca os valores) chega a `MotivoBloqueio` no caso de mestre
suspeito. O resultado de TENTAR aplicar este segundo gate fica em
`ItemResumoLote.resultado_gate_identificacao`
(`ResultadoGateIdentificacaoDTO`, dtos_esteira.py) -- DTO próprio,
independente de `resultado_gate_classificacao`.

PONTE PARA A PRESTAÇÃO DE CONTAS (`ponte_prestacao_holerite.py`, mesma
fase): quando -- e só quando -- a identificação acima termina de fato
RESOLVIDA (IDENTIFICACAO/CONCLUIDO, colaborador único), o MESMO `texto`
já extraído é reaproveitado por `extrair_competencia_de_texto`
(importacao_lote/dominio.py, função pura já existente) só para observar
a competência OBSERVADA no documento -- nunca a esperada. O resultado
sanitizado fica em `ItemResumoLote.holerite_confirmado`
(`HoleriteConfirmadoDTO`, dtos_esteira.py), `None` em qualquer outro
caso. Este serviço NUNCA decide se a competência observada bate com a
esperada nem qual cliente -- essas duas decisões pertencem
exclusivamente a `ponte_prestacao_holerite.py`, com uma competência
esperada e uma `FonteVinculosPrestacao` injetadas de fora (nunca
inferidas do próprio documento -- proibição de validação circular).

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
from typing import Callable, List, Optional, Protocol, Sequence

from magnata_os.classificacao.classificador_documental import EstadoClassificacao
from magnata_os.classificacao.contratos import EstadoResolucaoDimensao, ResolucaoDimensao
from magnata_os.classificacao.roteamento_documental import decidir_roteamento_de_texto, extrair_texto_seguro

from ..importacao_lote.contratos import CandidatoFuncionario
from ..importacao_lote.dominio import extrair_competencia_de_texto
from .dominio_esteira import EtapaEsteira, LoteDocumental, SituacaoEsteira, gerar_correlation_id_lote, gerar_lote_id
from .dtos_esteira import (
    ItemResumoLote,
    ResumoLote,
    holerite_confirmado_para_dto,
    resultado_gate_classificacao_erro_tecnico,
    resultado_gate_classificacao_nao_aplicavel,
    resultado_gate_classificacao_promovida,
    resultado_gate_identificacao_erro_tecnico,
    resultado_gate_identificacao_nao_aplicavel,
    resultado_gate_identificacao_promovida,
    roteamento_shadow_erro_tecnico,
    roteamento_shadow_para_dto,
)
from .politica_classificacao import decidir_transicao_classificacao
from .politica_identificacao_holerite import (
    decidir_transicao_identificacao,
    resolver_identificacao_holerite_de_texto,
)
from .repositorio_esteira import RepositorioLotes
from .servico_avanco_esteira import ServicoAvancoEsteira
from .servico_entrada import ServicoEntradaDocumental

# Tipo documental elegível para o gate de identificação nesta
# microetapa -- só Holerite avulso (ver politica_identificacao_holerite.py
# e auditoria read-only prévia). Constante isolada aqui (não em
# politica_identificacao_holerite.py) porque é o CHAMADOR (este módulo)
# quem decide QUANDO tentar a identificação -- a política em si já
# assume que só recebe Holerite, nunca decide isso sozinha.
_TIPO_DOCUMENTAL_HOLERITE = 'Holerite'


class FonteCandidatosFuncionario(Protocol):
    """Fonte substituível e somente leitura de candidatos de
    colaborador -- mesmo padrão já usado em
    magnata_os/classificacao/inventario_prestacao.py
    (FonteInventarioPrestacao) e vinculos_prestacao.py
    (FonteVinculosPrestacao): Protocol pequeno, sem estado, satisfeito
    por duck-typing. `LeitorAirtableSomenteLeitura.listar_funcionarios()`
    (magnata_os/documental/importacao_lote/adapters/airtable_leitura.py)
    já satisfaz este contrato sem alteração nenhuma -- nenhum adapter
    novo foi criado."""

    def listar_funcionarios(self) -> list[CandidatoFuncionario]: ...


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
        fonte_candidatos_funcionario: Optional[FonteCandidatosFuncionario] = None,
    ) -> None:
        self._lotes = repositorio_lotes
        self._servico_entrada = servico_entrada
        self._servico_avanco = servico_avanco_esteira
        self._gerar_lote_id = gerador_lote_id
        self._relogio = relogio
        # Optional e com default None de propósito: nenhum chamador
        # existente (scripts, testes, composição de serviços) precisa
        # mudar. Quando None, o gate de identificação de Holerite avulso
        # simplesmente não é tentado (resultado_gate_identificacao =
        # não aplicável) -- nunca fabrica candidatos, nunca lê Airtable
        # real sem essa fonte ter sido explicitamente injetada por quem
        # monta o serviço em produção.
        self._fonte_candidatos_funcionario = fonte_candidatos_funcionario

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

        # Candidatos de funcionário buscados no máximo UMA vez por lote
        # (nunca por arquivo), e só se algum arquivo realmente precisar
        # (Holerite RESOLVIDO) -- lista mutável de 1 posição usada só
        # como cache preguiçoso fechado no closure, sem estado novo na
        # instância do serviço. `None` quando nenhuma fonte foi
        # injetada -- `_processar_um_arquivo` trata isso como
        # identificação não aplicável, nunca fabrica uma lista vazia
        # fingindo ser um resultado real de leitura.
        candidatos_funcionario_cache: List[Optional[List[CandidatoFuncionario]]] = [None]

        def _obter_candidatos_funcionario() -> List[CandidatoFuncionario]:
            if candidatos_funcionario_cache[0] is None:
                candidatos_funcionario_cache[0] = list(
                    self._fonte_candidatos_funcionario.listar_funcionarios())
            return candidatos_funcionario_cache[0]

        obter_candidatos_funcionario = (
            _obter_candidatos_funcionario if self._fonte_candidatos_funcionario is not None else None
        )

        itens: List[ItemResumoLote] = []
        for arquivo in arquivos:
            itens.append(self._processar_um_arquivo(
                lote_id, origem, correlation_id, arquivo, obter_candidatos_funcionario))

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
        obter_candidatos_funcionario: Optional[Callable[[], List[CandidatoFuncionario]]] = None,
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

        # Extração de texto UNICA (auditoria read-only prévia -- bridge
        # de identificação de Holerite avulso): `texto` e `decisao` sao
        # calculados uma so vez aqui e reaproveitados tanto para o
        # RoteamentoShadowDTO/gate de classificacao abaixo quanto para o
        # gate de identificacao de Holerite mais abaixo -- nunca uma
        # segunda chamada a extrair_texto_seguro/extrair_texto_pdf.
        texto = None
        decisao = None
        try:
            texto = extrair_texto_seguro(arquivo.conteudo)
            decisao = decidir_roteamento_de_texto(texto)
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

        # Gate REGISTRO -> CLASSIFICACAO (politica_classificacao.py).
        # Reaproveita a MESMA `decisao` ja calculada acima -- nunca
        # reclassifica, nunca rechama decidir_roteamento(). So aplicado
        # quando: (a) o roteamento shadow terminou normalmente (`decisao`
        # nao e None -- ERRO_TECNICO_SHADOW e a PanicException absorvida
        # acima nunca chegam a definir `decisao`, entao o gate
        # simplesmente nao roda, permanecendo em REGISTRO, conforme
        # tabela de decisao); e (b) o Documento e NOVO (`criado_agora`) --
        # duplicado nunca tenta a transicao de novo (idempotencia
        # preservada, nenhum segundo evento CLASSIFICACAO).
        #
        # Falha do GATE em si (distinta de "gate nao aplicavel") NUNCA
        # muda `ItemResumoLote.sucesso` (que reflete so a INGESTAO) nem
        # desfaz o Documento/roteamento shadow ja calculados, mesma
        # filosofia de tolerancia ja usada por `_registrar_evento`
        # (servico_avanco_esteira.py) -- mas, ao contrario da versao
        # anterior desta integracao, a falha NAO e mais engolida em
        # silencio: `ResultadoGateClassificacaoDTO` distingue
        # explicitamente os 3 casos (promovido / falhou tecnicamente /
        # nao aplicavel), sem expor `str(exc)`.
        estado_pos_gate_classificacao = None
        if decisao is not None and criado_agora:
            try:
                decisao_transicao = decidir_transicao_classificacao(decisao)
                estado_pos_gate_classificacao = self._servico_avanco.aplicar_resultado_classificacao(
                    documento.documento_id, decisao_transicao, correlation_id,
                )
                if estado_pos_gate_classificacao is None:
                    # Nunca deveria ocorrer -- as 4 branches de
                    # EstadoClassificacao sempre produzem deve_avancar=True
                    # (ver politica_classificacao.py). Tratado como falha
                    # tecnica do gate, nao como sucesso silencioso.
                    raise RuntimeError('aplicar_resultado_classificacao retornou None inesperadamente')
                resultado_gate_classificacao = resultado_gate_classificacao_promovida(
                    estado_pos_gate_classificacao)
            except Exception:
                resultado_gate_classificacao = resultado_gate_classificacao_erro_tecnico()
        else:
            resultado_gate_classificacao = resultado_gate_classificacao_nao_aplicavel()

        # Gate CLASSIFICACAO -> IDENTIFICACAO (politica_identificacao_holerite.py)
        # -- primeiro gate controlado depois de CLASSIFICACAO (auditoria
        # read-only prévia). SÓ tentado quando TODAS as condições de
        # elegibilidade abaixo são verdadeiras -- qualquer uma falsa e o
        # resultado é "não aplicável", nunca uma tentativa parcial:
        #   1. criado_agora -- documento duplicado NUNCA reaplica
        #      identificação (idempotência preservada, mesmo princípio do
        #      gate de classificação acima);
        #   2. decisao is not None -- classificação shadow executada com
        #      sucesso (ERRO_TECNICO_SHADOW/PanicException nunca chegam
        #      aqui com decisao preenchida);
        #   3. decisao.estado_classificacao == RESOLVIDA;
        #   4. decisao.tipo_documental == "Holerite" -- os outros 16
        #      tipos documentais têm comportamento INALTERADO;
        #   5. resultado_gate_classificacao.sucesso -- o gate de
        #      classificação em si terminou com sucesso;
        #   6. estado_pos_gate_classificacao indica CLASSIFICACAO/CONCLUIDO
        #      de fato persistido -- nunca assume, verifica o estado real
        #      devolvido por aplicar_resultado_classificacao;
        #   7. texto is not None -- extração de texto disponível (reaproveita
        #      a MESMA extração já feita acima, nunca uma segunda leitura
        #      do PDF);
        #   8. obter_candidatos_funcionario is not None -- alguma fonte de
        #      candidatos foi injetada (ver FonteCandidatosFuncionario) --
        #      nunca fabrica uma lista vazia fingindo ser leitura real.
        elegivel_para_identificacao = (
            criado_agora
            and decisao is not None
            and decisao.estado_classificacao == EstadoClassificacao.RESOLVIDA
            and decisao.tipo_documental == _TIPO_DOCUMENTAL_HOLERITE
            and resultado_gate_classificacao.sucesso
            and estado_pos_gate_classificacao is not None
            and estado_pos_gate_classificacao.etapa_atual == EtapaEsteira.CLASSIFICACAO
            and estado_pos_gate_classificacao.situacao == SituacaoEsteira.CONCLUIDO
            and texto is not None
            and obter_candidatos_funcionario is not None
        )

        # `holerite_confirmado` -- ponte para a Prestação de Contas
        # (ver ponte_prestacao_holerite.py e dtos_esteira.
        # HoleriteConfirmadoDTO). Só preenchido quando a identificação
        # de colaborador terminou de fato RESOLVIDA (nunca AMBIGUA,
        # NAO_ENCONTRADA, MESTRE_SUSPEITO ou erro técnico) -- reaproveita
        # o MESMO `texto` já extraído acima (extrair_competencia_de_texto
        # é pura, nunca reabre o PDF) só para observar a competência
        # OBSERVADA no documento; NUNCA decide aqui se essa competência
        # bate com a esperada nem qual cliente -- isso é decisão
        # exclusiva da ponte, com uma fonte de competência esperada
        # injetada de fora (nunca o próprio documento).
        holerite_confirmado = None

        if elegivel_para_identificacao:
            try:
                candidatos_funcionario = obter_candidatos_funcionario()
                resultado_identificacao = resolver_identificacao_holerite_de_texto(
                    texto, candidatos_funcionario,
                )
                decisao_transicao_identificacao = decidir_transicao_identificacao(resultado_identificacao)
                estado_pos_gate_identificacao = self._servico_avanco.aplicar_resultado_identificacao(
                    documento.documento_id, decisao_transicao_identificacao, correlation_id,
                )
                if estado_pos_gate_identificacao is None:
                    # Nunca deveria ocorrer -- as 4 branches de
                    # decidir_transicao_identificacao sempre produzem
                    # deve_avancar=True. Tratado como falha tecnica do
                    # gate, nao como sucesso silencioso.
                    raise RuntimeError('aplicar_resultado_identificacao retornou None inesperadamente')
                resultado_gate_identificacao = resultado_gate_identificacao_promovida(
                    estado_pos_gate_identificacao)
                if (
                    resultado_gate_identificacao.sucesso
                    and estado_pos_gate_identificacao.situacao == SituacaoEsteira.CONCLUIDO
                    and isinstance(resultado_identificacao, ResolucaoDimensao)
                    and resultado_identificacao.estado == EstadoResolucaoDimensao.RESOLVIDA
                ):
                    competencia_observada = extrair_competencia_de_texto(texto)
                    holerite_confirmado = holerite_confirmado_para_dto(
                        documento.documento_id, documento.hash_sha256,
                        resultado_identificacao.valores_confirmados[0].entidade_id,
                        competencia_observada,
                    )
            except Exception:
                # Falha SECUNDARIA -- nunca desfaz o Documento, o
                # roteamento shadow nem o gate de classificacao ja
                # aplicados com sucesso acima; nunca expoe str(exc)
                # (poderia conter fragmento de CPF/nome/texto).
                resultado_gate_identificacao = resultado_gate_identificacao_erro_tecnico()
        else:
            resultado_gate_identificacao = resultado_gate_identificacao_nao_aplicavel()

        # `texto` e estritamente transitório -- nunca persistido, nunca
        # em DTO/evento/log; sai de escopo aqui, ao fim da função.
        del texto

        return ItemResumoLote(
            nome_original=arquivo.nome_original, documento_id=documento.documento_id,
            sucesso=True, duplicado=not criado_agora, erro=None,
            roteamento_shadow=roteamento_shadow,
            resultado_gate_classificacao=resultado_gate_classificacao,
            resultado_gate_identificacao=resultado_gate_identificacao,
            holerite_confirmado=holerite_confirmado,
        )
